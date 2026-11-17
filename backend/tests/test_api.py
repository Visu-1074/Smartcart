import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_search_returns_ranked_listings():
    response = client.get("/api/search", params={"q": "wireless headphones", "include_demo": "true"})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert len(rows) >= 6
    assert [x["price"] for x in rows] == sorted(x["price"] for x in rows)

def test_scan_resolves_mock_barcode():
    response = client.post("/api/scan", params={"include_demo": "true"}, json={"code": "012345678905"})
    assert response.status_code == 200
    assert response.json()["product_name"] == "wireless headphones"

def test_cart_add_quantity_and_remove():
    listing = {"id": "test-cart-item", "platform": "ShopHub", "title": "Test item", "price": 12.5}
    added = client.post("/api/cart", json={"listing": listing, "quantity": 2})
    assert added.status_code == 200
    cart = client.get("/api/cart").json()
    item = next(row for row in cart["items"] if row["listing_id"] == "test-cart-item")
    assert item["quantity"] == 2
    changed = client.patch(f"/api/cart/{item['id']}", json={"quantity": 3})
    assert changed.status_code == 200
    assert next(row for row in client.get("/api/cart").json()["items"] if row["id"] == item["id"])["quantity"] == 3
    assert client.delete(f"/api/cart/{item['id']}").status_code == 200

def test_platform_registry_and_category_filters():
    registry = client.get("/api/platforms").json()
    assert len(registry["platforms"]) == 30
    assert len(registry["categories"]) == 9
    modes = {platform["id"]: platform["mode"] for platform in registry["platforms"]}
    assert modes["amazon_in"] == "snapshot"
    assert modes["flipkart"] == "snapshot"
    assert all(mode == "mock" for platform_id, mode in modes.items() if platform_id not in {"amazon_in", "flipkart"})
    grocery = client.get("/api/search", params={"q": "coffee", "category": "grocery_quick_commerce"})
    assert grocery.status_code == 422
    grocery = client.get("/api/search", params={"q": "coffee", "category": "grocery_quick_commerce", "pincode": "560001", "include_demo": "true"})
    assert grocery.status_code == 200
    assert all(row["category"] == "grocery_quick_commerce" for row in grocery.json()["results"])

def test_search_streams_platform_updates():
    response = client.get("/api/search", params={"q": "coffee beans", "stream": "true", "include_demo": "true"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert events[-1]["type"] == "done"
    assert sum(event["type"] == "platform" for event in events) == 30

def test_fashion_variants_are_required_and_rx_checkout_is_blocked():
    fashion = client.get("/api/search", params={"q": "kurta", "category": "fashion", "include_demo": "true"}).json()["results"]
    listing = next(row for row in fashion if row["variants"])
    missing_variant = client.post("/api/cart", json={"listing": listing})
    assert missing_variant.status_code == 422
    added = client.post("/api/cart", json={"listing": listing, "variant": listing["variants"][0]})
    assert added.status_code == 200
    client.delete(f"/api/cart/{added.json()['id']}")

    pharmacy = client.get("/api/search", params={"q": "antibiotic", "category": "pharmacy", "include_demo": "true"}).json()["results"]
    rx = next(row for row in pharmacy if row["is_rx"])
    rx_added = client.post("/api/cart", json={"listing": rx})
    response = client.post("/api/checkout")
    assert response.status_code == 200
    assert any(platform["status"] == "rx_info_only" for platform in response.json()["platforms"])
    client.delete(f"/api/cart/{rx_added.json()['id']}")
