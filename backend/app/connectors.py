from __future__ import annotations

import os
import csv
import json
import time
import asyncio
import re
import urllib.robotparser
from urllib.parse import parse_qs, urlparse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
import httpx

from .seed_data import SEED_PRODUCTS
from .user_dataset import load_user_dataset

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "platforms.yaml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "platforms.yaml"
SEARCH_CATEGORIES = [
    {"id": "all", "label": "All"},
    {"id": "electronics", "label": "Electronics"},
    {"id": "fashion", "label": "Fashion"},
    {"id": "grocery_quick_commerce", "label": "Grocery"},
    {"id": "beauty", "label": "Beauty"},
    {"id": "pharmacy", "label": "Pharmacy"},
    {"id": "home_furniture", "label": "Home"},
    {"id": "books", "label": "Books"},
    {"id": "baby_kids", "label": "Baby"},
]


async def affiliate_tracking_url(url: str) -> str:
    api_key = os.getenv("CUELINKS_API_KEY")
    if not api_key or not url:
        return url
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.post("https://developers.cuelinks.com/pub_api/v3/links/convert", headers={"Authorization": f"Token {api_key}", "Content-Type": "application/json"}, json={"url": url, "shorten": False})
            response.raise_for_status()
            data = response.json().get("data", {})
            return data.get("tracking_url", url) if data.get("affiliated") else url
    except httpx.HTTPError:
        return url


class PlatformConnector(ABC):
    """Common listing, barcode, price and user-confirmed checkout interface."""

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str):
        self.platform_id = platform_id
        self.config = config
        self.name = config["name"]
        self.categories = categories
        self.mode = mode

    @abstractmethod
    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None: ...

    @abstractmethod
    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]: ...


class QuickCommerceApiConnector(PlatformConnector):
    """QuickCommerceAPI adapter for location-aware Blinkit product search."""

    API_ROOT = "https://api.quickcommerceapi.com/v1"

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str):
        super().__init__(platform_id, config, categories, mode)
        self.api_key = os.environ["QUICKCOMMERCE_API_KEY"]
        self.latitude = float(os.environ.get("QUICKCOMMERCE_LAT", "12.90"))
        self.longitude = float(os.environ.get("QUICKCOMMERCE_LON", "77.66"))

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{self.API_ROOT}/{endpoint}",
                params=params,
                headers={"X-API-Key": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("status") not in {None, "success"}:
            raise RuntimeError(str(payload.get("error") or payload.get("message") or "QuickCommerce API request failed"))
        return payload.get("data") or {}

    def _normalize(self, product: dict[str, Any], query: str = "") -> dict[str, Any] | None:
        title = str(product.get("name") or product.get("title") or "").strip()
        if not title:
            return None
        product_id = str(product.get("id") or product.get("item_id") or product.get("product_id") or title)
        try:
            price = float(product.get("offer_price", product.get("price", 0)) or 0)
            mrp = float(product.get("mrp", price) or price)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        images = product.get("images") or []
        image = images[0] if isinstance(images, list) and images else product.get("image_url", "")
        platform_info = product.get("platform") or {}
        availability_value = product.get("available")
        availability = "In stock" if availability_value is True else "Out of stock" if availability_value is False else "Check retailer"
        eta = str(platform_info.get("sla") or product.get("delivery_eta") or "See Blinkit")
        same_product = re.sub(r"[^a-z0-9]+", "-", f"{product.get('brand', '')}-{title}".casefold()).strip("-")
        return {
            "id": f"{self.platform_id}:{product_id}", "product_id": product_id,
            "same_product_id": same_product or f"{self.platform_id}:{product_id}",
            "platform": self.platform_id, "platform_name": self.name,
            "platform_color": self.config.get("color", "#f8cb46"), "mode": self.mode,
            "category": "grocery_quick_commerce", "title": title, "price": price,
            "mrp": mrp, "original_price": mrp,
            "discount_percent": round(max(0, (mrp - price) / mrp * 100), 1) if mrp else 0,
            "rating": float(product.get("rating") or 0), "review_count": int(product.get("rating_count") or 0),
            "availability": availability, "delivery_eta": eta,
            "delivery_fee": float(self.config.get("delivery_fee", 0)),
            "image_url": str(image or ""),
            "url": str(product.get("deeplink") or product.get("url") or "https://blinkit.com"),
            "barcode": str(product.get("barcode") or ""), "same_product_confidence": 0.9,
            "variants": [], "is_rx": False,
        }

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        data = await self._get("search", {
            "q": query, "lat": self.latitude, "lon": self.longitude, "platform": "BlinkIt",
        })
        return [row for product in data.get("products", []) if (row := self._normalize(product, query))][:100]

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return [row for row in await self.search(code, pincode) if row.get("barcode") == code]

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        data = await self._get("item", {
            "item_id": product_id, "lat": self.latitude, "lon": self.longitude, "platform": "BlinkIt",
        })
        items = data.get("items") or []
        return next((row for item in items if (row := self._normalize(item)) is not None), None)

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = items[0].get("url", "https://blinkit.com") if items else "https://blinkit.com"
        return {"status": "awaiting_user_confirmation", "message": "Review and complete checkout on Blinkit. SmartCart does not submit payment.", "checkout_url": url}


class MockConnector(PlatformConnector):
    def _can_list(self, product: dict[str, Any]) -> bool:
        return "general" in self.categories or product["category"] in self.categories

    def _listing(self, product: dict[str, Any], query: str = "") -> dict[str, Any]:
        # Stable, modest store-specific price movement across the seed catalogue.
        seed = sum(ord(ch) for ch in self.platform_id) % 17
        factor = 0.94 + seed / 100 + (sum(ord(ch) for ch in product["canonical_id"]) % 5) / 100
        price = round(product["base"] * factor, 2)
        mrp = float(product["mrp"])
        search_url = self.config.get("url", "https://example.com/?q={query}").format(query=quote_plus(query or product["title"]))
        listing: dict[str, Any] = {
            "id": f"{self.platform_id}:{product['canonical_id']}",
            "product_id": product["canonical_id"],
            "same_product_id": product["canonical_id"],
            "platform": self.platform_id,
            "platform_name": self.name,
            "platform_color": self.config.get("color", "#2563eb"),
            "mode": self.mode,
            "category": product["category"],
            "title": product["title"],
            "price": price,
            "mrp": mrp,
            "original_price": mrp,
            "discount_percent": round(max(0, (mrp - price) / mrp * 100), 1) if mrp else 0,
            "rating": product["rating"],
            "review_count": product["reviews"],
            "availability": "In stock",
            "delivery_eta": "10 min" if self.config.get("quick_commerce") else "2–5 days",
            "delivery_fee": float(self.config.get("delivery_fee", 0)),
            "free_delivery_threshold": float(self.config.get("free_delivery_threshold", 0)),
            "image_url": (
                "https://cdn.shopify.com/s/files/1/0516/3761/6830/files/63fa1776-8ad3-4ad3-a54f-f4c3484cfbe7_A3035Z11_Rich_image_TD01_US_V1.png?v=1749637691"
                if product.get("canonical_id") == "headphones-anc"
                else f"https://placehold.co/240x180/eef2ff/334155?text={quote_plus(product['title'][:19])}"
            ),
            "url": search_url,
            "barcode": product.get("barcode", ""),
            "same_product_confidence": 0.94,
            "variants": product.get("variants", []),
            "is_rx": bool(product.get("rx", False)),
        }
        if self.config.get("quick_commerce") and not listing["delivery_fee"]:
            listing["delivery_fee"] = 25.0
        if self.config.get("pharmacy"):
            listing["rx_label"] = "Rx" if listing["is_rx"] else "Non-Rx"
        if product["category"] == "electronics":
            listing.update({"warranty": "1 year manufacturer warranty", "seller_name": self.name + " authorised seller", "emi_offer": "No-cost EMI may be available at checkout"})
        if self.platform_id in {"meesho", "snapdeal"}:
            listing.update({"seller_name": self.name + " marketplace seller", "seller_rating": 4.2})
        return listing

    def _dataset_listing(self, product: dict[str, Any], query: str = "") -> dict[str, Any]:
        title = product["title"]
        product_id = product["id"]
        mrp = float(product.get("mrp") or product["price"])
        price = float(product["price"])
        search_url = self.config.get("url", "https://example.com/?q={query}").format(query=quote_plus(query or title))
        row_url = product.get("url") or search_url
        return {
            "id": f"{self.platform_id}:{product_id}", "product_id": product_id,
            "same_product_id": re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:100],
            "platform": self.platform_id, "platform_name": self.name,
            "platform_color": self.config.get("color", "#2563eb"), "mode": "dataset",
            "category": product["category"], "title": title, "price": price,
            "mrp": mrp, "original_price": mrp,
            "discount_percent": round(max(0, (mrp - price) / mrp * 100), 1) if mrp else 0,
            "rating": float(product.get("rating") or 0), "review_count": int(product.get("reviews") or 0),
            "availability": "Dataset record · check retailer", "delivery_eta": "Check retailer",
            "delivery_fee": float(self.config.get("delivery_fee", 0)),
            "free_delivery_threshold": float(self.config.get("free_delivery_threshold", 0)),
            "image_url": product.get("image_url") or f"https://placehold.co/240x180/eef2ff/334155?text={quote_plus(title[:19])}",
            "url": row_url, "barcode": "", "same_product_confidence": 0.72,
            "variants": [], "is_rx": False, "price_is_current": False,
            "snapshot_date": product.get("listing_date") or product.get("captured_at") or "Dataset date not supplied",
            "data_source": product.get("source_file", "User supplied dataset"),
            "seller_name": product.get("seller", "") or None,
            "seller_rating": product.get("seller_rating"),
        }

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        terms = [term.lower() for term in query.split() if len(term) > 1]
        products = []
        for product in SEED_PRODUCTS:
            if not self._can_list(product):
                continue
            searchable = f"{product['title']} {product.get('tags', '')}".lower()
            if not terms or any(term in searchable or any(word.startswith(term) for word in searchable.split()) for term in terms):
                products.append(self._listing(product, query))
        imported = [row for row in load_user_dataset()["offers"] if row["platform"] == self.platform_id]
        for product in imported:
            if not self._can_list(product):
                continue
            searchable = f"{product['title']} {product.get('item_type', '')} {product.get('quantity', '')} {product.get('weight_g', '')}".casefold()
            if not terms or any(term in searchable or any(word.startswith(term) for word in searchable.split()) for term in terms):
                products.append(self._dataset_listing(product, query))
        return products[:100] if category == "grocery_quick_commerce" else products[:20]

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        matches = [p for p in SEED_PRODUCTS if p.get("barcode") == code and self._can_list(p)]
        return [self._listing(product) for product in matches]

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        product = next((p for p in SEED_PRODUCTS if p["canonical_id"] == product_id), None)
        return self._listing(product) if product and self._can_list(product) else None

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = await affiliate_tracking_url(items[0].get("url", "")) if items else ""
        return {"status": "awaiting_user_confirmation", "message": f"Demo checkout ready on {self.name}", "checkout_url": url}


_SNAPSHOT_URL = "https://raw.githubusercontent.com/ShauryaSwarup/Ecommerce-Scraper/main/final-flipkart-amazon-data.json"
_SNAPSHOT_DATE = "2023-02-01"
_SNAPSHOT_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_SNAPSHOT_LOCK = asyncio.Lock()


class CommunitySnapshotConnector(PlatformConnector):
    """Read-only catalog snapshot published by the user-selected GitHub repository.

    This connector never runs the repository's scraper. Prices are archival values,
    never current offers, so listings cannot be added to the cart.
    """

    data_source = f"Community GitHub export; archived prices from {_SNAPSHOT_DATE}"

    async def _source_rows(self) -> list[dict[str, Any]]:
        global _SNAPSHOT_CACHE
        if _SNAPSHOT_CACHE and time.time() - _SNAPSHOT_CACHE[0] < 3600:
            return _SNAPSHOT_CACHE[1]
        async with _SNAPSHOT_LOCK:
            if _SNAPSHOT_CACHE and time.time() - _SNAPSHOT_CACHE[0] < 3600:
                return _SNAPSHOT_CACHE[1]
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                response = await client.get(_SNAPSHOT_URL)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, list):
                raise ValueError("Community product snapshot must be a JSON list")
            _SNAPSHOT_CACHE = (time.time(), data)
            return data

    @staticmethod
    def _number(value: Any, default: float = 0) -> float:
        match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value or ""))
        return float(match.group(0).replace(",", "")) if match else default

    def _normalise(self, item: dict[str, Any], index: int) -> dict[str, Any] | None:
        if self.platform_id == "amazon_in":
            product_url = str(item.get("url", ""))
            title = str(item.get("title", "")).strip()
            price = self._number(item.get("price"))
            rating = self._number(item.get("star_rating"))
            parsed = urlparse(product_url)
            product_id = parsed.path.split("/dp/")[-1].split("/")[0] if "/dp/" in parsed.path else f"archive-{index}"
        else:
            product_url = str(item.get("flipkart_url", ""))
            title = str(item.get("title", "")).strip()
            price = self._number(item.get("flipkart_price"))
            rating = self._number(item.get("flipkart_star_rating"))
            if not product_url or not price:
                return None
            parsed = urlparse(product_url)
            product_id = parse_qs(parsed.query).get("pid", [f"archive-{index}"])[0]
        if not product_url or not title or not price:
            return None
        canonical = str(item.get("model_name") or title).casefold()
        canonical = re.sub(r"[^a-z0-9]+", "-", canonical).strip("-") or f"phone-{index}"
        review_text = item.get("flipkart_no_rating", "") if self.platform_id == "flipkart" else item.get("star_rating", "")
        review_match = re.search(r"([\d,]+)\s*(?:ratings?|reviews?)", str(review_text), re.IGNORECASE)
        review_count = int(review_match.group(1).replace(",", "")) if review_match else 0
        mrp = price
        return {
            "id": f"{self.platform_id}:{product_id}", "product_id": product_id,
            "same_product_id": canonical, "platform": self.platform_id,
            "platform_name": self.name, "platform_color": self.config.get("color", "#2563eb"),
            "mode": "snapshot", "category": "electronics", "title": title,
            "price": price, "mrp": mrp, "original_price": mrp, "discount_percent": 0,
            "rating": rating, "review_count": review_count,
            "availability": "Unknown · check retailer", "delivery_eta": "Check retailer",
            "delivery_fee": float(self.config.get("delivery_fee", 0)),
            "image_url": str(item.get("img_url", "")), "url": product_url,
            "barcode": "", "same_product_confidence": 0.72, "variants": [], "is_rx": False,
            "price_is_current": False, "snapshot_date": _SNAPSHOT_DATE,
            "data_source": "ShauryaSwarup/Ecommerce-Scraper GitHub export",
        }

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        if category not in {"all", "general"} and "general" not in self.categories and category not in self.categories:
            return []
        terms = [term.casefold() for term in query.split() if len(term) > 1]
        if not terms:
            output = [
                MockConnector(self.platform_id, self.config, self.categories, "dataset")._dataset_listing(product, query)
                for product in load_user_dataset()["offers"]
                if product["platform"] == self.platform_id
                and (category in {"all", "general"} or product["category"] == category)
            ]
            return output[:30]
        output = []
        seen_products: set[str] = set()
        for product in load_user_dataset()["offers"]:
            if product["platform"] != self.platform_id:
                continue
            if category not in {"all", "general"} and product["category"] != category:
                continue
            searchable = f"{product['title']} {product.get('category', '')}".casefold()
            if not terms or any(term in searchable or any(word.startswith(term) for word in searchable.split()) for term in terms):
                output.append(MockConnector(self.platform_id, self.config, self.categories, "dataset")._dataset_listing(product, query))
                seen_products.add(str(product["id"]))
        # The local user-supplied rows should render immediately; only reach out
        # for the older community snapshot when this query has no local matches.
        if output:
            return output[:30]
        try:
            source_items = await self._source_rows()
        except Exception:
            return output[:30]
        for index, item in enumerate(source_items):
            searchable = " ".join(str(item.get(key, "")) for key in ("title", "brand", "model_name", "colour", "storage_cap")).casefold()
            if any(term in searchable for term in terms):
                listing = self._normalise(item, index)
                if listing and listing["product_id"] not in seen_products:
                    output.append(listing)
                    seen_products.add(listing["product_id"])
        return output[:30]

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return []

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        return None

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = items[0].get("url", "") if items else ""
        return {"status": "awaiting_user_confirmation", "message": "This archived listing has no live price. Check the retailer page directly.", "checkout_url": url}


class UnconfiguredConnector(PlatformConnector):
    """A requested live source without a safe, configured implementation."""

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        raise RuntimeError(f"{self.name} live source is not configured")

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        raise RuntimeError(f"{self.name} barcode source is not configured")

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        raise RuntimeError(f"{self.name} price source is not configured")

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"status": "awaiting_user_confirmation", "message": "Open the retailer page to review and pay.", "checkout_url": items[0].get("url", "") if items else ""}


class AmazonCreatorsConnector(PlatformConnector):
    """Amazon.in Creators API adapter; activated only by explicit API mode and credentials."""

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str):
        super().__init__(platform_id, config, categories, mode)
        self.client_id = os.environ["AMAZON_CREATORS_CLIENT_ID"]
        self.client_secret = os.environ["AMAZON_CREATORS_CLIENT_SECRET"]
        self.credential_version = os.environ["AMAZON_CREATORS_VERSION"]
        self.partner_tag = os.environ["AMAZON_PARTNER_TAG"]
        self.access_token = ""
        self.token_expiry = 0.0

    async def _token(self, client: httpx.AsyncClient) -> str:
        if self.access_token and time.time() < self.token_expiry - 60:
            return self.access_token
        endpoint_host = "api.amazon.co.uk" if self.credential_version.startswith("3.2") else ("api.amazon.co.jp" if self.credential_version.startswith("3.3") else "api.amazon.com")
        response = await client.post(f"https://{endpoint_host}/auth/o2/token", json={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret, "scope": "creatorsapi::default"})
        response.raise_for_status()
        data = response.json()
        self.access_token = data["access_token"]
        self.token_expiry = time.time() + int(data.get("expires_in", 3600))
        return self.access_token

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5) as client:
            token = await self._token(client)
            response = await client.post("https://creatorsapi.amazon/catalog/v1/searchItems", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "x-marketplace": "www.amazon.in"}, json={"keywords": query, "partnerTag": self.partner_tag, "marketplace": "www.amazon.in", "itemCount": 10, "resources": ["images.primary.medium", "itemInfo.title", "offersV2.listings.price", "offersV2.listings.availability"]})
            response.raise_for_status()
            body = response.json()
        rows = []
        for item in body.get("searchResult", {}).get("items", []):
            title = (item.get("itemInfo", {}).get("title") or {}).get("displayValue", "Amazon item")
            offer = next(iter((item.get("offersV2") or {}).get("listings", [])), {})
            price_info = offer.get("price", {}).get("money", {})
            if not price_info.get("amount"):
                continue
            mrp_info = offer.get("price", {}).get("savingBasis", {}).get("money", {})
            price = float(price_info["amount"]); mrp = float(mrp_info.get("amount", price))
            image = (item.get("images", {}).get("primary", {}).get("medium") or {}).get("url", "")
            rows.append({"id": f"amazon_in:{item.get('asin')}", "product_id": item.get("asin", ""), "same_product_id": item.get("asin", ""), "platform": self.platform_id, "platform_name": self.name, "platform_color": self.config.get("color", "#ff9900"), "mode": self.mode, "category": category if category != "all" else "general", "title": title, "price": price, "mrp": mrp, "original_price": mrp, "discount_percent": round(max(0, (mrp-price)/mrp*100), 1) if mrp else 0, "rating": 0, "review_count": 0, "availability": offer.get("availability", {}).get("type", "Check retailer"), "delivery_eta": "See Amazon.in", "delivery_fee": float(self.config.get("delivery_fee", 0)), "image_url": image, "url": item.get("detailPageURL", "https://www.amazon.in"), "barcode": "", "same_product_confidence": 0.82, "variants": [], "is_rx": False})
        return rows

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return await self.search(code, pincode)

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        return next((row for row in await self.search(product_id, pincode) if row["product_id"] == product_id), None)

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = items[0].get("url", "https://www.amazon.in") if items else "https://www.amazon.in"
        return {"status": "awaiting_user_confirmation", "message": "Review your basket directly on Amazon.in. SmartCart does not submit payment.", "checkout_url": await affiliate_tracking_url(url)}


class FlipkartAffiliateConnector(PlatformConnector):
    """Official Flipkart Affiliate Search API adapter for registered affiliate credentials."""

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str):
        super().__init__(platform_id, config, categories, mode)
        self.affiliate_id = os.environ["FLIPKART_AFFILIATE_ID"]
        self.affiliate_token = os.environ["FLIPKART_AFFILIATE_TOKEN"]

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("https://affiliate-api.flipkart.net/affiliate/1.0/search.json", params={"query": query, "resultCount": 10}, headers={"Fk-Affiliate-Id": self.affiliate_id, "Fk-Affiliate-Token": self.affiliate_token})
            response.raise_for_status(); body = response.json()
        rows = []
        for info in body.get("productInfoList", []):
            base = info.get("productBaseInfoV1") or info.get("productBaseInfo") or {}
            attrs = base.get("productAttributes") or {}
            if not attrs:
                # Older API shape exposes offer attributes directly on the base.
                attrs = base
            price = attrs.get("sellingPrice") or attrs.get("flipkartSpecialPrice") or attrs.get("flipkartSellingPrice") or {}
            mrp = attrs.get("maximumRetailPrice") or {}
            product_id = base.get("productId") or (base.get("productIdentifier") or {}).get("productId", "")
            amount = (price.get("amount") if isinstance(price, dict) else 0) or 0
            if not amount: continue
            mrp_amount = (mrp.get("amount") if isinstance(mrp, dict) else 0) or amount
            images = attrs.get("imageUrls", {})
            image = images.get("400x400") or images.get("200x200") or next(iter(images.values()), "") if isinstance(images, dict) else ""
            title = attrs.get("title") or base.get("title") or "Flipkart item"
            url = attrs.get("productUrl") or base.get("productUrl") or "https://www.flipkart.com"
            rows.append({"id": f"flipkart:{product_id}", "product_id": product_id, "same_product_id": f"flipkart:{product_id}", "platform": self.platform_id, "platform_name": self.name, "platform_color": self.config.get("color", "#2874f0"), "mode": self.mode, "category": category if category != "all" else "general", "title": title, "price": float(amount), "mrp": float(mrp_amount), "original_price": float(mrp_amount), "discount_percent": float(attrs.get("discountPercentage", 0) or 0), "rating": 0, "review_count": 0, "availability": "In stock" if attrs.get("inStock", True) else "Out of stock", "delivery_eta": "See Flipkart", "delivery_fee": float(self.config.get("delivery_fee", 0)), "image_url": image, "url": url, "barcode": "", "same_product_confidence": 0.82, "variants": [], "is_rx": False, "seller_name": info.get("productShippingInfoV1", {}).get("sellerName", "")})
        return rows

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return await self.search(code, pincode)

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        return next((row for row in await self.search(product_id, pincode) if row["product_id"] == product_id), None)

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = items[0].get("url", "https://www.flipkart.com") if items else "https://www.flipkart.com"
        return {"status": "awaiting_user_confirmation", "message": "Review and pay directly on Flipkart.", "checkout_url": await affiliate_tracking_url(url)}


class AffiliateFeedConnector(MockConnector):
    """Reads an explicitly configured partner product feed (JSON array or CSV)."""

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str, feed_path: str):
        super().__init__(platform_id, config, categories, mode)
        self.feed_path = Path(feed_path)

    def _feed_rows(self) -> list[dict[str, Any]]:
        if not self.feed_path.is_file(): return []
        if self.feed_path.suffix.lower() == ".json":
            data = json.loads(self.feed_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("products", [])
        with self.feed_path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        terms = [term.casefold() for term in query.split()]
        found = []
        for row in self._feed_rows():
            title = str(row.get("title", ""))
            if terms and not any(term in title.casefold() for term in terms): continue
            try:
                price = float(row.get("price", 0)); mrp = float(row.get("mrp", row.get("original_price", price)))
            except (TypeError, ValueError): continue
            found.append({"id": str(row.get("id") or f"{self.platform_id}:{row.get('product_id', title)}"), "product_id": str(row.get("product_id", row.get("id", title))), "same_product_id": str(row.get("same_product_id", row.get("product_id", row.get("id", title)))), "platform": self.platform_id, "platform_name": self.name, "platform_color": self.config.get("color", "#2563eb"), "mode": "api", "category": str(row.get("category", category)), "title": title, "price": price, "mrp": mrp, "original_price": mrp, "discount_percent": float(row.get("discount_percent", max(0, (mrp-price)/mrp*100 if mrp else 0))), "rating": float(row.get("rating", 0)), "review_count": int(row.get("review_count", 0)), "availability": str(row.get("availability", "Check retailer")), "delivery_eta": str(row.get("delivery_eta", "See retailer")), "delivery_fee": float(row.get("delivery_fee", self.config.get("delivery_fee", 0))), "image_url": str(row.get("image_url", "")), "url": str(row.get("url", "")), "barcode": str(row.get("barcode", "")), "same_product_confidence": float(row.get("same_product_confidence", 0.85)), "variants": row.get("variants", []), "is_rx": bool(row.get("is_rx", False))})
        return found[:20]

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return [row for row in await self.search(code, pincode) if row.get("barcode") == code]

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        return next((row for row in await self.search(product_id, pincode) if row["product_id"] == product_id), None)


class ScraperBlockedError(RuntimeError):
    pass


_SCRAPER_LAST_REQUEST: dict[str, float] = {}
_SCRAPER_LOCKS: dict[str, asyncio.Lock] = {}
_SCRAPER_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


class CompliantPlaywrightConnector(PlatformConnector):
    """Opt-in scraper requiring explicit terms approval, robots permission and selectors."""

    def __init__(self, platform_id: str, config: dict[str, Any], categories: list[str], mode: str):
        super().__init__(platform_id, config, categories, mode)
        self.scraper = config["scraper"]
        self.user_agent = f"SmartCart/0.1 (+mailto:{os.environ['SMARTCART_CONTACT_EMAIL']})"

    async def search(self, query: str, pincode: str | None = None, category: str = "all") -> list[dict[str, Any]]:
        cache_key = (self.platform_id, query.casefold())
        cached = _SCRAPER_CACHE.get(cache_key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        url = self.scraper["search_url"].format(query=quote_plus(query))
        parts = urlparse(url)
        host = parts.netloc
        lock = _SCRAPER_LOCKS.setdefault(host, asyncio.Lock())
        async with lock:
            wait = 2.5 - (time.monotonic() - _SCRAPER_LAST_REQUEST.get(host, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            async with httpx.AsyncClient(timeout=5, headers={"User-Agent": self.user_agent}) as client:
                robots_response = await client.get(robots_url)
                if robots_response.status_code >= 500:
                    raise ScraperBlockedError("robots.txt could not be checked")
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(robots_response.text.splitlines() if robots_response.status_code != 404 else [])
                if not parser.can_fetch(self.user_agent, url):
                    raise ScraperBlockedError("robots.txt disallows this search page")
            _SCRAPER_LAST_REQUEST[host] = time.monotonic()
            # Robots and page fetches share the same per-host budget.
            await asyncio.sleep(2.5)
            _SCRAPER_LAST_REQUEST[host] = time.monotonic()
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(user_agent=self.user_agent)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=6000)
                    body = (await page.locator("body").inner_text(timeout=1500)).casefold()
                    if any(marker in body for marker in ("captcha", "verify you are human", "access denied", "unusual traffic")):
                        raise ScraperBlockedError("The retailer blocked this request")
                    selectors = self.scraper["selectors"]
                    products = page.locator(selectors["item"])
                    output = []
                    for index in range(min(await products.count(), 20)):
                        product = products.nth(index)
                        title = await product.locator(selectors["title"]).inner_text()
                        price_text = await product.locator(selectors["price"]).inner_text()
                        digits = "".join(char for char in price_text if char.isdigit() or char == ".")
                        if not digits: continue
                        price = float(digits)
                        link = await product.locator(selectors["link"]).get_attribute("href")
                        image = await product.locator(selectors["image"]).get_attribute("src") if selectors.get("image") else ""
                        key = f"{self.platform_id}:scrape:{index}:{quote_plus(title[:24])}"
                        output.append({"id": key, "product_id": key, "same_product_id": key, "platform": self.platform_id, "platform_name": self.name, "platform_color": self.config.get("color", "#2563eb"), "mode": "scraper", "category": category if category != "all" else (self.categories[-1] if self.categories else "general"), "title": title, "price": price, "mrp": price, "original_price": price, "discount_percent": 0, "rating": 0, "review_count": 0, "availability": "Check retailer", "delivery_eta": "See retailer", "delivery_fee": float(self.config.get("delivery_fee", 0)), "image_url": image or "", "url": link if (link or "").startswith("http") else f"{parts.scheme}://{host}{link or ''}", "barcode": "", "same_product_confidence": 0.5, "variants": [], "is_rx": False})
                    _SCRAPER_CACHE[cache_key] = (time.time(), output)
                    return output
                finally:
                    await browser.close()

    async def get_by_barcode(self, code: str, pincode: str | None = None) -> list[dict[str, Any]]:
        return [row for row in await self.search(code, pincode) if row.get("barcode") == code]

    async def get_price(self, product_id: str, pincode: str | None = None) -> dict[str, Any] | None:
        return next((row for row in await self.search(product_id, pincode) if row["product_id"] == product_id), None)

    async def place_order(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        url = items[0].get("url", "") if items else ""
        return {"status": "awaiting_user_confirmation", "message": "Review and complete checkout on the retailer site.", "checkout_url": await affiliate_tracking_url(url)}


def load_registry(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def create_connectors(registry: dict[str, Any] | None = None) -> list[PlatformConnector]:
    registry = registry or load_registry()
    membership: dict[str, list[str]] = {}
    for category, platform_ids in registry["categories"].items():
        for platform_id in platform_ids:
            membership.setdefault(platform_id, []).append(category)
    connectors: list[PlatformConnector] = []
    for platform_id, config in registry["platforms"].items():
        requested_mode = os.getenv(f"PLATFORM_MODE_{platform_id.upper()}", config.get("mode", "mock")).lower()
        categories = membership.get(platform_id, [])
        feed_path = os.getenv(f"AFFILIATE_FEED_{platform_id.upper()}")
        has_amazon_credentials = all(os.getenv(k) for k in ("AMAZON_CREATORS_CLIENT_ID", "AMAZON_CREATORS_CLIENT_SECRET", "AMAZON_CREATORS_VERSION", "AMAZON_PARTNER_TAG"))
        has_flipkart_credentials = all(os.getenv(k) for k in ("FLIPKART_AFFILIATE_ID", "FLIPKART_AFFILIATE_TOKEN"))
        has_quickcommerce_credentials = bool(os.getenv("QUICKCOMMERCE_API_KEY"))
        scraper_config = config.get("scraper")
        scraper_approved = os.getenv(f"SCRAPER_TERMS_APPROVED_{platform_id.upper()}") == "true" and bool(os.getenv("SMARTCART_CONTACT_EMAIL"))
        if requested_mode == "scraper" and scraper_config and scraper_approved and scraper_config.get("terms_allowed"):
            connectors.append(CompliantPlaywrightConnector(platform_id, config, categories, "scraper"))
        elif requested_mode == "api" and feed_path and Path(feed_path).is_file():
            connectors.append(AffiliateFeedConnector(platform_id, config, categories, "api", feed_path))
        elif requested_mode == "api" and platform_id == "amazon_in" and has_amazon_credentials:
            connectors.append(AmazonCreatorsConnector(platform_id, config, categories, "api"))
        elif requested_mode == "api" and platform_id == "flipkart" and has_flipkart_credentials:
            connectors.append(FlipkartAffiliateConnector(platform_id, config, categories, "api"))
        elif requested_mode == "api" and platform_id == "blinkit" and has_quickcommerce_credentials:
            connectors.append(QuickCommerceApiConnector(platform_id, config, categories, "api"))
        elif platform_id in {"amazon_in", "flipkart"}:
            connectors.append(CommunitySnapshotConnector(platform_id, config, categories, "snapshot"))
        else:
            # No product-feed API has been verified for the other registrants; scraper mode stays mock until a permitted adapter exists.
            connectors.append(MockConnector(platform_id, config, categories, "mock"))
    return connectors


REGISTRY = load_registry()
CONNECTORS = create_connectors(REGISTRY)
CONNECTORS_BY_ID = {connector.platform_id: connector for connector in CONNECTORS}
