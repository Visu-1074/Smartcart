# SmartCart

SmartCart is a mobile-first Indian product comparison app. Its homepage links to real retailer product pages; live search uses retailer APIs when configured, and sample products are opt-in. Checkout is prepared per store and always pauses for the shopper before payment.

For a no-terminal startup on Windows, double-click [`START_SMARTCART.cmd`](START_SMARTCART.cmd). It starts only missing local services and opens the website. First-time API credentials are optional; read [`BEGINNER_SETUP.md`](BEGINNER_SETUP.md) if you want live Amazon or Flipkart product search.

## Folder layout

```text
backend/                 FastAPI API, SQLAlchemy models, mock connectors, scheduler
  app/
  tests/
frontend/                React + TypeScript + Vite + Tailwind
  src/
config/platforms.yaml    Platform registry, display metadata, delivery rules
```

## Run the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0
```

The API is at http://localhost:8000 and interactive docs are at http://localhost:8000/docs. SQLite is created as `backend/smartcart.db` by default.

## Run the frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Keep the API running. To use a different API host, set `VITE_API_URL` before starting Vite.

## Camera testing

Camera permission is requested only after tapping **Scan** and **Continue to camera**. For a phone on the same network, the Vite dev server must use HTTPS; browser camera APIs are blocked on ordinary LAN HTTP addresses. Start Vite with its basic SSL plugin:

```powershell
npm run dev -- --mode https
```

Find the computer's LAN IP, then visit `https://<computer-ip>:5173` on the phone, accept the local development certificate warning, and allow camera access. A trusted HTTPS tunnel to port 5173 is another option. Keep the backend reachable from the phone as well. Vite proxies `/api` to the backend, so the phone can reach it through the same computer without a separate API URL. BarcodeDetector is used natively when present; ZXing is the fallback. A barcode lookup mock is included for `012345678905`, `4006381333931`, and `8901030865312`.

## Tests

```powershell
cd backend
pip install -r requirements.txt
pytest
```

Search uses live Amazon/Flipkart retailer APIs when credentials are configured. Otherwise it searches the supplied local dataset rows first, then the linked repository's exported smartphone archive when there is no local match. Dataset and archive prices are labeled historical and cannot be added to cart. The homepage also features two source-linked retailer pages (Blue Tokai coffee on Blinkit and Minimalist sunscreen on Apollo Pharmacy); check those pages for current prices and availability. Every checkout flow stops before payment.

Searches in **All** or **Grocery** also show India-tagged product identity matches from Open Food Facts. **All** and **Beauty** searches also query Open Beauty Facts. These open, community-contributed catalogs can add product photos, brands and barcode source links. They are not retailer offers; SmartCart does not show their prices as live or add them to the cart. See [`DATA_SOURCES.md`](DATA_SOURCES.md) for details.

User-provided CSV/XLSX files are normalized into a local read-only search catalog (`backend/app/user_dataset_catalog.json.gz`). Searchable Amazon India, Flipkart, BlinkIT and Zepto dataset rows are labeled with their source file and cannot be added to cart because their prices are not live. The Amazon.com scrape and Zepto inventory workbook are catalog-only; their USD prices are not converted to INR. The Flipkart CSV has generated-looking records, and the BlinkIT workbook is outlet-sales analysis data, so neither should be described as verified live retailer inventory. Rebuild the catalog with `python backend/scripts/import_user_datasets.py` after updating the original files. See [`DATA_SOURCES.md`](DATA_SOURCES.md) for file-by-file handling.

The grocery catalogue includes 103 everyday products (biscuits, snacks, staples, tea, coffee, dairy and more). Blinkit search uses the configured QuickCommerceAPI credentials and sample Bangalore coordinates; BigBasket and JioMart offers remain clearly labeled demo data. Choose **Grocery** and search **milk**, **biscuits**, **tea**, **rice**, or **snacks**. Blinkit API searches use one provider credit per request. No pincode is needed.

## Platform registry and source modes

Every registry entry is configured `mock` by default. For Amazon and Flipkart, missing credentials select the dataset/archive connector; valid credentials activate the official retailer API. Historical rows are labeled and blocked from cart. Other mock listings stay hidden unless **Include demo listings** is enabled. When no supplied local row matches, the older community archive is fetched from [the repository's exported JSON file](https://raw.githubusercontent.com/ShauryaSwarup/Ecommerce-Scraper/main/final-flipkart-amazon-data.json); SmartCart does not run its scraper. For current pricing, add your own registered API credentials to `backend/.env`, set `PLATFORM_MODE_AMAZON_IN=api` and/or `PLATFORM_MODE_FLIPKART=api`, then restart the backend. A normalized partner product feed can also be configured per platform using `AFFILIATE_FEED_<PLATFORM_ID>` with explicit API mode. No platform scraper runs in this build.

Amazon credential generation and access are documented in the [Amazon Creators API getting-started guide](https://affiliate-program.amazon.in/creatorsapi/docs/en-us/introduction). Flipkart product search is limited to registered affiliates; see its [official API overview](https://affiliate.flipkart.com/api-docs/af_overview.html). Configure the values listed in `backend/.env.example`; never paste API secrets into the browser UI or commit them to source control.

| Category | Platform | Mode | Why |
|---|---|---|---|
| General | Amazon.in | snapshot / api | Uses the repository archive when API credentials are unavailable; official Creators API can replace the snapshot when configured. |
| General | Flipkart | snapshot / api | Uses the repository archive when API credentials are unavailable; official Affiliate API can replace the snapshot when configured. |
| General | Meesho | mock | No verified product feed/API configured in this build. |
| General | Snapdeal | mock | No verified product feed/API configured in this build. |
| General | JioMart | mock | No verified product feed/API configured in this build. |
| General | Tata CLiQ | mock | No verified product feed/API configured in this build. |
| Electronics | Croma | mock | No verified product feed/API configured in this build. |
| Electronics | Reliance Digital | mock | No verified product feed/API configured in this build. |
| Electronics | Vijay Sales | mock | No verified product feed/API configured in this build. |
| Fashion | Myntra | mock | No verified product feed/API configured in this build. |
| Fashion | AJIO | mock | No verified product feed/API configured in this build. |
| Fashion | Tata CLiQ Fashion | mock | No verified product feed/API configured in this build. |
| Beauty | Nykaa | mock | No verified product feed/API configured in this build. |
| Beauty | Purplle | mock | No verified product feed/API configured in this build. |
| Beauty | Tira | mock | No verified product feed/API configured in this build. |
| Grocery / quick commerce | bigbasket | mock | Seeded classroom-demo offers; no live pincode inventory is connected. |
| Grocery / quick commerce | Blinkit | api / mock | Uses QuickCommerceAPI when `QUICKCOMMERCE_API_KEY` is set; otherwise seeded demo offers. |
| Grocery / quick commerce | Zepto | mock | No live product source is configured. |
| Grocery / quick commerce | Swiggy Instamart | mock | No live product source is configured. |
| Grocery / quick commerce | DMart Ready | mock | No live product source is configured. |
| Pharmacy | Tata 1mg | mock | No verified product feed/API configured; prescription safeguards apply to mock Rx data. |
| Pharmacy | PharmEasy | mock | No verified product feed/API configured; prescription safeguards apply to mock Rx data. |
| Pharmacy | Apollo Pharmacy | mock | No verified product feed/API configured; prescription safeguards apply to mock Rx data. |
| Pharmacy | Netmeds | mock | No verified product feed/API configured; prescription safeguards apply to mock Rx data. |
| Home / furniture | Pepperfry | mock | No verified product feed/API configured in this build. |
| Home / furniture | Urban Ladder | mock | No verified product feed/API configured in this build. |
| Home / furniture | IKEA India | mock | No verified product feed/API configured in this build. |
| Baby / kids | FirstCry | mock | No verified product feed/API configured in this build. |
| Books | Bookswagon | mock | No verified product feed/API configured in this build. |
| Books | Crossword | mock | No verified product feed/API configured in this build. |

Amazon mode `api` uses the official Creators API OAuth flow and SearchItems operation; Amazon requires Associates enrollment, API access, credentials and a valid India partner tag. Flipkart mode `api` uses its registered-affiliate search endpoint. Cuelinks can convert retailer URLs to affiliate links when `CUELINKS_API_KEY` is set; its documented API does not provide merchant product feeds, so it is not treated as a price source. A normalized JSON/CSV affiliate feed can be assigned per platform with `AFFILIATE_FEED_<PLATFORM_ID>` and explicit API mode.

To enable the Amazon headed review session, set `AMAZON_CHECKOUT_ENABLED=true` and set a private Fernet key in `SMARTCART_ENCRYPTION_KEY` (generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). The browser opens Amazon.in using the user's own session; the user handles OTP and retailer steps, and can save the browser state encrypted under `backend/.data/`. SmartCart does not click the final payment action. Other stores use a mock handoff and direct retailer link.

Scrapers are off by default. To opt a retailer in, add selectors and a `search_url` under that platform's `scraper` block in the YAML, set `terms_allowed: true` only after reviewing the site's terms, set `PLATFORM_MODE_<PLATFORM_ID>=scraper`, `SCRAPER_TERMS_APPROVED_<PLATFORM_ID>=true`, and provide `SMARTCART_CONTACT_EMAIL`. The adapter checks robots.txt on each uncached query, identifies SmartCart in its User-Agent, spaces requests by 2.5 seconds per host, caches successful results for five minutes, and falls back to mock results with a blocked badge when denied. It does not handle CAPTCHA, login, or bot protection.

The mock catalogue contains 139 demo products, including 103 grocery and everyday-use products. Values are illustrative INR examples and are not live prices. Grocery demo searches do not require a pincode. Fashion items with variants require a size/colour selection. Rx listings are informational and are excluded from SmartCart checkout; users are directed to the pharmacy website.

Official source documentation checked for adapters: [Amazon Creators API SearchItems](https://affiliate-program.amazon.in/creatorsapi/docs/en-us/api-reference/operations/search-items), [Amazon Creators API migration and endpoint details](https://affiliate-program.amazon.in/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi), [Flipkart Affiliate API product search](https://affiliate.flipkart.com/api-docs/af_prod_ref.html), [Cuelinks link conversion API](https://apiui.cuelinks.com/docs/reference/links/convert), and [Cuelinks API coverage](https://cuelinks.zohodesk.com/portal/en/kb/articles/what-are-the-different-types-of-apis-available).


