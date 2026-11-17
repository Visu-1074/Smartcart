import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv()
from .connectors import CONNECTORS, CONNECTORS_BY_ID, REGISTRY, SEARCH_CATEGORIES, CommunitySnapshotConnector, MockConnector, ScraperBlockedError, affiliate_tracking_url
from .database import Base, SessionLocal, engine, get_db, migrate_dev_schema
from .models import CartItem, Listing, Order, OrderItem
from .seed_data import SEED_PRODUCTS
from .user_dataset import load_user_dataset

Base.metadata.create_all(bind=engine)
migrate_dev_schema()
PLATFORM_TIMEOUT_SECONDS = float(os.getenv("PLATFORM_TIMEOUT_SECONDS", "6"))
GROCERY_CATEGORY = "grocery_quick_commerce"
CATALOG_CACHE: dict[str, tuple[float, list[dict[str, Any]], bool]] = {}


def selected_connectors(category: str, include_demo: bool = False) -> list[Any]:
    if category == GROCERY_CATEGORY:
        grocery_stores = {"bigbasket", "jiomart", "blinkit", "zepto"}
        return [connector for connector in CONNECTORS if connector.platform_id in grocery_stores and (include_demo or connector.mode != "mock")]
    if category == "all":
        return [connector for connector in CONNECTORS if include_demo or connector.mode != "mock"]
    if category not in REGISTRY["categories"]:
        raise HTTPException(400, f"Unknown category: {category}")
    wanted = set(REGISTRY["categories"][category])
    # General marketplaces sell across categories, while specialist categories stay focused.
    if category != "general":
        wanted.update(REGISTRY["categories"].get("general", []))
    return [connector for connector in CONNECTORS if connector.platform_id in wanted and (include_demo or connector.mode != "mock")]


def persist_listings(db: Session, rows: list[dict[str, Any]]) -> None:
    unique_rows = {row["id"]: row for row in rows}
    for row in unique_rows.values():
        db.merge(Listing(id=row["id"], platform=row["platform_name"], title=row["title"], price=row["price"], original_price=row["mrp"], rating=row["rating"], availability=row["availability"], image_url=row["image_url"], url=row["url"]))
    db.commit()


async def platform_search(connector: Any, query: str, category: str, pincode: str | None, include_demo: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    async def blinkit_demo_fallback(reason: str):
        fallback = MockConnector(connector.platform_id, connector.config, connector.categories, "mock")
        rows = await fallback.search(query, pincode=pincode, category=category)
        return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": connector.mode, "status": "unavailable", "reason": reason, "fallback": "demo", "count": len(rows)}, rows)
    try:
        rows = await asyncio.wait_for(connector.search(query, pincode=pincode, category=category), timeout=PLATFORM_TIMEOUT_SECONDS)
        if category != "all":
            rows = [row for row in rows if row["category"] == category]
        if not rows and connector.mode == "api" and connector.platform_id in {"amazon_in", "flipkart"}:
            fallback = CommunitySnapshotConnector(connector.platform_id, connector.config, connector.categories, "snapshot")
            rows = await fallback.search(query, pincode=pincode, category=category)
            return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": "snapshot", "status": "ok", "count": len(rows), "fallback": "community_snapshot"}, rows)
        return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": connector.mode, "status": "ok", "count": len(rows)}, rows)
    except asyncio.TimeoutError:
        if connector.platform_id == "blinkit" and include_demo:
            return await blinkit_demo_fallback("Live API timed out; showing sample offers")
        if connector.mode == "api" and connector.platform_id in {"amazon_in", "flipkart"}:
            fallback = CommunitySnapshotConnector(connector.platform_id, connector.config, connector.categories, "snapshot")
            rows = await fallback.search(query, pincode=pincode, category=category)
            return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": "snapshot", "status": "ok", "count": len(rows), "fallback": "community_snapshot", "reason": "Retailer API timed out"}, rows)
        return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": connector.mode, "status": "unavailable", "reason": "Timed out"}, [])
    except ScraperBlockedError as exc:
        fallback = MockConnector(connector.platform_id, connector.config, connector.categories, "mock")
        rows = await fallback.search(query, pincode=pincode, category=category)
        return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": "scraper", "status": "blocked", "reason": str(exc), "fallback": "mock", "count": len(rows)}, rows)
    except Exception as exc:
        if connector.platform_id == "blinkit" and include_demo:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            reason = "QuickCommerceAPI has no credits; showing sample offers" if status_code == 402 else "Live API unavailable; showing sample offers"
            return await blinkit_demo_fallback(reason)
        if connector.mode == "api" and connector.platform_id in {"amazon_in", "flipkart"}:
            try:
                fallback = CommunitySnapshotConnector(connector.platform_id, connector.config, connector.categories, "snapshot")
                rows = await fallback.search(query, pincode=pincode, category=category)
                return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": "snapshot", "status": "ok", "count": len(rows), "fallback": "community_snapshot", "reason": "Retailer API unavailable"}, rows)
            except Exception:
                pass
        return ({"platform": connector.platform_id, "platform_name": connector.name, "mode": connector.mode, "status": "unavailable", "reason": str(exc)[:120]}, [])


async def collect_search(query: str, category: str, pincode: str | None, db: Session, include_demo: bool = False) -> dict[str, Any]:
    connectors = selected_connectors(category, include_demo)
    tasks = [platform_search(c, query, category, pincode, include_demo) for c in connectors]
    results: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for completed in asyncio.as_completed(tasks):
        status, rows = await completed
        statuses.append(status)
        results.extend(rows)
    results.sort(key=lambda row: row["price"])
    persist_listings(db, results)
    return {"results": results, "platforms": statuses, "category": category}


async def stream_search(query: str, category: str, pincode: str | None, db: Session, include_demo: bool = False):
    connectors = selected_connectors(category, include_demo)
    async def run(connector):
        return await platform_search(connector, query, category, pincode, include_demo)
    tasks = [asyncio.create_task(run(connector)) for connector in connectors]
    combined: list[dict[str, Any]] = []
    for task in asyncio.as_completed(tasks):
        status, rows = await task
        combined.extend(rows)
        yield json.dumps({"type": "platform", "platform": status, "results": rows}) + "\n"
    combined.sort(key=lambda row: row["price"])
    persist_listings(db, combined)
    yield json.dumps({"type": "done", "platform_count": len(connectors), "result_count": len(combined)}) + "\n"


def refresh_cart_prices() -> None:
    async def refresh() -> None:
        with SessionLocal() as db:
            for item in db.scalars(select(CartItem)).all():
                connector = CONNECTORS_BY_ID.get(item.platform)
                if connector:
                    updated = await connector.get_price(item.listing_id.split(":", 1)[-1])
                    if updated:
                        item.price = updated["price"]
                        db.merge(Listing(id=updated["id"], platform=updated["platform_name"], title=updated["title"], price=updated["price"], original_price=updated["mrp"], rating=updated["rating"], availability=updated["availability"], image_url=updated["image_url"], url=updated["url"]))
            db.commit()
    asyncio.run(refresh())


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Vercel Functions are short-lived; do not leave a background scheduler running there.
    scheduler = None
    if os.getenv("VERCEL") != "1":
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(refresh_cart_prices, "interval", minutes=max(1, int(os.getenv("PRICE_REFRESH_MINUTES", "30"))), id="cart-price-refresh", replace_existing=True)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="SmartCart API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ScanRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class CartRequest(BaseModel):
    listing: dict[str, Any]
    quantity: int = Field(default=1, ge=1, le=99)
    variant: str | None = None
    pincode: str | None = None


class QuantityRequest(BaseModel):
    quantity: int = Field(ge=1, le=99)


class SaveAmazonSessionRequest(BaseModel):
    session_id: str = Field(min_length=10, max_length=128)


class PrepareAmazonBasketRequest(BaseModel):
    session_id: str = Field(min_length=10, max_length=128)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/platforms")
def platforms():
    return {"categories": SEARCH_CATEGORIES, "platforms": [{"id": c.platform_id, "name": c.name, "mode": c.mode, "api_source": c.config.get("api_source"), "data_source": getattr(c, "data_source", None), "categories": c.categories, "color": c.config.get("color", "#2563eb"), "delivery_fee": float(c.config.get("delivery_fee", 0)), "free_delivery_threshold": float(c.config.get("free_delivery_threshold", 0))} for c in CONNECTORS]}


@app.get("/api/search")
async def search(q: str, category: str = "all", pincode: str | None = None, stream: bool = False, include_demo: bool = False, db: Session = Depends(get_db)):
    if stream:
        return StreamingResponse(stream_search(q.strip(), category, pincode, db, include_demo), media_type="application/x-ndjson")
    return await collect_search(q.strip(), category, pincode, db, include_demo)


@app.get("/api/catalog")
async def catalog_search(q: str, category: str = "all"):
    """Supplemental product identity catalog, intentionally separate from priced retailer offers."""
    if not q.strip():
        raise HTTPException(400, "Search query is required")
    terms = [term.casefold() for term in q.split() if len(term) > 1]
    local_rows = []
    for product in load_user_dataset()["catalog"]:
        if category not in {"all", product.get("category", "general")}:
            continue
        searchable = f"{product.get('title', '')} {product.get('brand', '')} {product.get('stores', '')}".casefold()
        if terms and any(term in searchable or any(word.startswith(term) for word in searchable.split()) for term in terms):
            local_rows.append(product)
    local_rows = local_rows[:20]
    catalogs = []
    if category in {"all", GROCERY_CATEGORY}:
        catalogs.append(("world.openfoodfacts.org", "Open Food Facts"))
    if category in {"all", "beauty"}:
        catalogs.append(("world.openbeautyfacts.org", "Open Beauty Facts"))
    if not catalogs:
        return {"source": "Supplied product datasets", "results": local_rows}
    params = {
        "search_terms": q.strip()[:100], "search_simple": "1", "action": "process",
        "json": "1", "page_size": "12",
        "tagtype_0": "countries", "tag_contains_0": "contains", "tag_0": "India",
        "fields": "code,product_name,brands,image_url,product_quantity,stores,countries",
    }
    headers = {"User-Agent": "SmartCart/1.0 (https://github.com; product catalog search)"}
    async def fetch_catalog(host: str, source: str) -> tuple[list[dict[str, Any]], bool]:
        cache_key = f"{host}:{q.strip().casefold()}"
        cached = CATALOG_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True, headers=headers) as client:
                response = await client.get(f"https://{host}/cgi/search.pl", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            CATALOG_CACHE[cache_key] = (time.monotonic() + 45, [], True)
            return [], True
        rows = []
        for product in payload.get("products", []):
            code = str(product.get("code") or "").strip()
            title = str(product.get("product_name") or "").strip()
            if not code or not title:
                continue
            rows.append({
                "code": code, "title": title, "brand": str(product.get("brands") or "").strip(),
                "quantity": str(product.get("product_quantity") or "").strip(),
                "image_url": str(product.get("image_url") or "").strip(),
                "countries": str(product.get("countries") or "").strip(),
                "stores": str(product.get("stores") or "").strip(), "source": source,
                "source_url": f"https://{host}/product/{code}",
            })
        CATALOG_CACHE[cache_key] = (time.monotonic() + 600, rows, False)
        return rows, False
    fetched = await asyncio.gather(*(fetch_catalog(host, source) for host, source in catalogs))
    return {"source": "Open product catalogs and supplied datasets", "results": local_rows + [row for rows, _ in fetched for row in rows], "unavailable": all(failed for _, failed in fetched)}


BARCODE_MOCKS = {"012345678905": "wireless headphones", "4006381333931": "coffee beans", "8901030865312": "shampoo"}


@app.post("/api/scan")
async def scan(payload: ScanRequest, pincode: str | None = None, include_demo: bool = False, db: Session = Depends(get_db)):
    product = next((p for p in SEED_PRODUCTS if p.get("barcode") == payload.code), None)
    query = product["title"] if product else BARCODE_MOCKS.get(payload.code, f"barcode {payload.code}")
    category = product["category"] if product else "all"
    return {"code": payload.code, "product_name": query, **await collect_search(query, category, pincode, db, include_demo)}


def cart_groups(rows: list[CartItem]) -> tuple[list[dict[str, Any]], float]:
    groups: dict[str, list[CartItem]] = {}
    for row in rows:
        groups.setdefault(row.platform, []).append(row)
    platforms = []
    total = 0.0
    for platform_id, items in groups.items():
        config = REGISTRY["platforms"].get(platform_id, {})
        subtotal = sum(item.price * item.quantity for item in items)
        threshold = float(config.get("free_delivery_threshold", 0))
        fee = 0.0 if threshold and subtotal >= threshold else float(config.get("delivery_fee", 0))
        platforms.append({"platform": platform_id, "platform_name": config.get("name", platform_id), "subtotal": round(subtotal, 2), "delivery_fee": fee, "estimated_total": round(subtotal + fee, 2), "items": [{"id": r.id, "listing_id": r.listing_id, "product_id": r.listing_id.split(":", 1)[-1], "platform": r.platform, "title": r.title, "price": r.price, "quantity": r.quantity, "image_url": r.image_url, "url": r.url, "category": r.category, "variant": r.variant, "is_rx": r.is_rx} for r in items]})
        total += subtotal + fee
    return platforms, round(total, 2)


@app.get("/api/cart")
def get_cart(db: Session = Depends(get_db)):
    rows = db.scalars(select(CartItem).order_by(CartItem.platform, CartItem.id)).all()
    groups, total = cart_groups(rows)
    return {"items": [item for group in groups for item in group["items"]], "platforms": groups, "total": total}


@app.post("/api/cart")
def add_cart(payload: CartRequest, db: Session = Depends(get_db)):
    listing = payload.listing
    required = ("id", "platform", "title", "price")
    if any(k not in listing for k in required):
        raise HTTPException(422, "Listing is missing required fields")
    if listing.get("price_is_current") is False or listing.get("mode") == "snapshot":
        raise HTTPException(422, "This is an archived price snapshot. Open the retailer listing to check today's price; archived prices cannot be added to cart.")
    if listing.get("variants") and not payload.variant:
        raise HTTPException(422, "Select a size or colour before adding this fashion item.")
    row = db.scalar(select(CartItem).where(CartItem.listing_id == listing["id"], CartItem.variant == (payload.variant or "")))
    if row:
        row.quantity += payload.quantity
    else:
        row = CartItem(listing_id=listing["id"], platform=listing["platform"], title=listing["title"], price=float(listing["price"]), quantity=payload.quantity, image_url=listing.get("image_url", ""), url=listing.get("url", ""), category=listing.get("category", "general"), variant=payload.variant or "", is_rx=bool(listing.get("is_rx", False)))
        db.add(row)
    db.commit(); db.refresh(row)
    return {"id": row.id, "quantity": row.quantity}


@app.patch("/api/cart/{item_id}")
def patch_cart(item_id: int, payload: QuantityRequest, db: Session = Depends(get_db)):
    row = db.get(CartItem, item_id)
    if not row: raise HTTPException(404, "Cart item not found")
    row.quantity = payload.quantity; db.commit(); return {"ok": True}


@app.delete("/api/cart/{item_id}")
def delete_cart(item_id: int, db: Session = Depends(get_db)):
    row = db.get(CartItem, item_id)
    if not row: raise HTTPException(404, "Cart item not found")
    db.delete(row); db.commit(); return {"ok": True}


@app.post("/api/checkout")
async def checkout(db: Session = Depends(get_db)):
    cart = db.scalars(select(CartItem)).all()
    if not cart: raise HTTPException(400, "Your cart is empty")
    outcomes = []
    for platform_id in dict.fromkeys(item.platform for item in cart):
        items = [item for item in cart if item.platform == platform_id]
        connector = CONNECTORS_BY_ID.get(platform_id)
        if not connector: continue
        rx_items = [item for item in items if item.is_rx]
        if rx_items:
            outcomes.append({"platform": platform_id, "status": "rx_info_only", "message": "Prescription medicines require a valid prescription. SmartCart does not place orders for prescription-only drugs.", "checkout_url": await affiliate_tracking_url(rx_items[0].url)})
            continue
        checkout_items = [{"url": i.url, "title": i.title, "is_rx": i.is_rx} for i in items]
        if platform_id == "amazon_in" and os.getenv("AMAZON_CHECKOUT_ENABLED", "false").lower() == "true":
            try:
                from .amazon_session import amazon_review_session
                session_id = await amazon_review_session.start([item["url"] for item in checkout_items])
                result = {"status": "awaiting_user_confirmation", "message": "Amazon product pages opened in a headed browser. Complete OTP login if prompted, add and review items on Amazon, stop before payment, then save your session here.", "checkout_url": checkout_items[0]["url"], "session_id": session_id}
            except Exception as exc:
                result = await connector.place_order(checkout_items)
                result["message"] = f"Amazon browser session unavailable ({str(exc)[:90]}). Use the retailer page to review and pay."
        else:
            result = await connector.place_order(checkout_items)
        order = Order(platform=platform_id, status=result["status"], timestamp=datetime.now(timezone.utc), confirmation_ref="Pending user confirmation")
        db.add(order); db.flush()
        for item in items: db.add(OrderItem(order_id=order.id, platform=platform_id, item=item.title, price_paid=item.price, quantity=item.quantity))
        outcomes.append({"platform": platform_id, **result, "order_id": order.id})
    db.commit()
    return {"platforms": outcomes}


@app.post("/api/checkout/amazon/save-session")
async def save_amazon_session(payload: SaveAmazonSessionRequest):
    from .amazon_session import amazon_review_session
    try:
        await amazon_review_session.save(payload.session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "saved", "message": "Amazon session saved encrypted on this device."}


@app.post("/api/checkout/amazon/prepare")
async def prepare_amazon_basket(payload: PrepareAmazonBasketRequest, db: Session = Depends(get_db)):
    from .amazon_session import amazon_review_session
    amazon_items = db.scalars(select(CartItem).where(CartItem.platform == "amazon_in")).all()
    if not amazon_items:
        raise HTTPException(400, "There are no Amazon items in the cart.")
    if any(item.is_rx for item in amazon_items):
        raise HTTPException(400, "Prescription-only items cannot be added to an automated checkout flow.")
    try:
        return await amazon_review_session.prepare_basket(payload.session_id, [{"url": item.url, "title": item.title, "quantity": item.quantity} for item in amazon_items])
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/orders")
def orders(db: Session = Depends(get_db)):
    rows = db.scalars(select(Order).order_by(Order.timestamp.desc())).all()
    return [{"id": o.id, "platform": o.platform, "status": o.status, "timestamp": o.timestamp.isoformat(), "confirmation_ref": o.confirmation_ref, "items": [{"item": i.item, "price_paid": i.price_paid, "quantity": i.quantity} for i in db.scalars(select(OrderItem).where(OrderItem.order_id == o.id)).all()]} for o in rows]
