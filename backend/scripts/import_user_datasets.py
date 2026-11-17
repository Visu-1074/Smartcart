"""Normalize the user's supplied product files into a local, read-only catalog.

Source files stay untouched. Historical/demo rows are marked as non-current and
the Amazon US scrape is retained as catalog-only because its prices are USD.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

SOURCE = Path(os.getenv("SMARTCART_DATA_DIR", r"C:\Users\visha\Downloads\Sem7\New folder"))
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "user_dataset_catalog.json.gz"


def number(value: Any) -> float | None:
    if value is None:
        return None
    value = re.sub(r"[^0-9.,]", "", str(value)).replace(",", "")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def category(value: str, fallback: str = "general") -> str:
    text = (value or "").casefold()
    if any(x in text for x in ("grocery", "food", "beverage", "snack", "dairy", "fruit", "vegetable", "biscuits", "cooking", "munchies", "household", "cleaning", "bakery", "breakfast", "meat", "frozen", "canned", "baking", "soft drink", "starchy")):
        return "grocery_quick_commerce"
    if any(x in text for x in ("fashion", "clothing", "apparel", "footwear", "jewellery", "toy", "sports")):
        return "fashion"
    if any(x in text for x in ("beauty", "personal care", "health & hygiene", "skin care", "makeup")):
        return "beauty"
    if any(x in text for x in ("home", "kitchen", "furniture", "appliance", "household")):
        return "home_furniture"
    if "baby" in text or "kids" in text:
        return "baby_kids"
    if "book" in text:
        return "books"
    if any(x in text for x in ("electronics", "mobile", "computer", "headphone", "smartwatch", "cable", "camera", "audio", "tv")):
        return "electronics"
    return fallback


def record(platform: str, product_id: str, title: str, category_id: str, price: float | None,
           mrp: float | None, rating: float | None = None, reviews: int = 0,
           image: str = "", url: str = "", source: str = "", **extra: Any) -> dict[str, Any]:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", product_id).strip("-")[:100]
    return {
        "id": f"{platform}-{safe_id}", "platform": platform, "title": title.strip()[:300],
        "category": category_id, "price": price, "mrp": mrp or price,
        "rating": rating or 0, "reviews": reviews, "image_url": image,
        "url": url, "source_file": source, **extra,
    }


def read_csv(name: str):
    with (SOURCE / name).open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def main() -> None:
    offers: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # Amazon India product catalog with original product links and photos.
    for row in read_csv("amazon.csv"):
        title = (row.get("product_name") or "").strip()
        price, mrp = number(row.get("discounted_price")), number(row.get("actual_price"))
        if not title or not price:
            continue
        key = ("amazon_in", row.get("product_id") or title.casefold())
        if key in seen:
            continue
        seen.add(key)
        offers.append(record("amazon_in", key[1], title, category(row.get("category", "")), price, mrp,
            number(row.get("rating")), int(number(row.get("rating_count")) or 0), row.get("img_link", ""),
            row.get("product_link", ""), "amazon.csv", price_currency="INR", price_is_current=False,
            rating_is_historical=True))

    # Flipkart CSV appears synthetic (generated names/categories); keep it usable
    # only as an explicitly labeled classroom dataset snapshot.
    for row in read_csv("flipkard.csv"):
        title = (row.get("product_name") or "").strip()
        price, mrp = number(row.get("final_price")), number(row.get("price"))
        if not title or not price:
            continue
        key = ("flipkart", row.get("product_id") or title.casefold())
        if key in seen:
            continue
        seen.add(key)
        offers.append(record("flipkart", key[1], title, category(row.get("category", "")), price, mrp,
            number(row.get("rating")), int(number(row.get("review_count")) or 0), "",
            "https://www.flipkart.com/search?q=" + title.replace(" ", "%20"), "flipkard.csv",
            price_currency="INR", price_is_current=False, listing_date=row.get("listing_date", ""),
            seller=row.get("seller", ""), seller_rating=number(row.get("seller_rating"))))

    # Zepto CSV and XLSX are copies of the same data. Import CSV once and dedupe
    # repeated package variants by all searchable offer fields.
    for row in read_csv("zepto_v2.csv"):
        title = (row.get("name") or "").strip()
        price_raw, mrp_raw = number(row.get("discountedSellingPrice")), number(row.get("mrp"))
        if not title or not price_raw:
            continue
        # The supplied Zepto file stores rupees multiplied by 100.
        price, mrp = price_raw / 100, (mrp_raw / 100 if mrp_raw else price_raw / 100)
        key_text = f"{title.casefold()}|{row.get('Category')}|{price}|{row.get('weightInGms')}"
        key = ("zepto", key_text)
        if key in seen:
            continue
        seen.add(key)
        offers.append(record("zepto", key_text, title, category(row.get("Category", ""), "grocery_quick_commerce"),
            price, mrp, 0, 0, "", "https://www.zeptonow.com/search?query=" + title.replace(" ", "%20"),
            "zepto_v2.csv", price_currency="INR", price_is_current=False,
            quantity=row.get("quantity", ""), weight_g=number(row.get("weightInGms")),
            out_of_stock=str(row.get("outOfStock", "")).casefold() == "true"))

    # This workbook is a retail outlet sales analysis dataset, not a live Blinkit
    # offer feed. One sample row per item; all prices remain non-current.
    wb = load_workbook(SOURCE / "Tableau BlinkIT Grocery Project U16955293080 (4).xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = [str(x) for x in next(rows)]
    for values in rows:
        row = dict(zip(headers, values))
        title = str(row.get("Item_Identifier") or "").strip()
        price = number(row.get("Item_MRP"))
        if not title or not price:
            continue
        key = ("blinkit", title)
        if key in seen:
            continue
        seen.add(key)
        offers.append(record("blinkit", title, title, "grocery_quick_commerce", price, price, 0, 0,
            "", "https://blinkit.com/s/?q=" + title, "Tableau BlinkIT Grocery Project U16955293080 (4).xlsx",
            price_currency="INR", price_is_current=False, item_type=row.get("Item_Type", ""),
            item_weight=number(row.get("Item_Weight")), outlet_type=row.get("Outlet_Type", "")))
    wb.close()

    # The 2025 Amazon scrape is US data and has USD prices. Preserve searchable
    # names/photos/URLs for identification; do not convert or present prices as INR.
    for row in read_csv("amazon_sales_data_uncleaned.csv"):
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        key = ("amazon_us_catalog", title.casefold())
        if key in seen:
            continue
        seen.add(key)
        catalog.append({"code": row.get("product_url", "")[-80:] or str(len(catalog)), "title": title[:300],
            "brand": "", "quantity": "", "image_url": row.get("image_url", ""),
            "countries": "United States", "stores": "Amazon.com", "source": "Amazon US dataset (USD; catalog only)",
            "source_url": "https://www.amazon.com" + row.get("product_url", "") if row.get("product_url", "").startswith("/") else row.get("product_url", ""),
            "category": category(title, "general"), "price_usd": number(row.get("Current/discounted_price")),
            "captured_at": row.get("collected_at", "")})

    # The separate Zepto workbook is inventory history, not a Zepto product feed.
    # Keep its products searchable in the catalog without inventing live offers.
    wb = load_workbook(SOURCE / "zepto_data.xlsx", read_only=True, data_only=True)
    ws = wb["Inventory Data"]
    rows = ws.iter_rows(values_only=True)
    headers = [str(x) for x in next(rows)]
    for values in rows:
        row = dict(zip(headers, values))
        title = str(row.get("ProductName") or "").strip()
        if not title:
            continue
        key = ("zepto_inventory_catalog", str(row.get("ProductID") or title).casefold())
        if key in seen:
            continue
        seen.add(key)
        catalog.append({"code": str(row.get("ProductID") or len(catalog)), "title": title[:300],
            "brand": "", "quantity": "", "image_url": "", "countries": "India",
            "stores": "Inventory dataset", "source": "zepto_data.xlsx inventory history (catalog only)",
            "source_url": "https://www.zeptonow.com/search?query=" + title.replace(" ", "%20"),
            "category": category(str(row.get("Category", "")), "grocery_quick_commerce"),
            "captured_at": str(row.get("Date", ""))})
    wb.close()

    payload = {"offers": offers, "catalog": catalog, "source_files": [
        "flipkard.csv", "amazon.csv", "amazon_sales_data_uncleaned.csv",
        "Tableau BlinkIT Grocery Project U16955293080 (4).xlsx", "zepto_v2.csv",
        "zepto_v1.xlsx (duplicate source copy; deduplicated)", "zepto_data.xlsx (inventory dataset; kept separate from product offers)"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", compresslevel=8) as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"offers": len(offers), "catalog_only": len(catalog), "output": str(OUTPUT), "bytes": OUTPUT.stat().st_size}))


if __name__ == "__main__":
    main()
