# SmartCart data sources

## Amazon and Flipkart archive fallback

- Source file: [Ecommerce-Scraper exported data](https://raw.githubusercontent.com/ShauryaSwarup/Ecommerce-Scraper/main/final-flipkart-amazon-data.json)
- Repository: [ShauryaSwarup/Ecommerce-Scraper](https://github.com/ShauryaSwarup/Ecommerce-Scraper)
- Repository license: [GNU GPL-3.0](https://github.com/ShauryaSwarup/Ecommerce-Scraper/blob/main/LICENSE.md)
- Retrieved and checked: 2026-11-16
- Product record count at retrieval: 276 Amazon records; 152 include a Flipkart listing
- Catalog coverage: smartphones
- Snapshot date inferred from the export's Amazon query timestamps: 2023-02-01

SmartCart fetches the pre-exported JSON file and does not run the repository's spiders, Scrapy jobs, proxy services, or CAPTCHA/bot-protection workarounds. Snapshot prices, ratings, availability and product pages may be stale. Results display an archive warning, cannot be added to the SmartCart cart, and link to the retailer for a current check.

If the official Amazon Creators API or Flipkart Affiliate API is configured, that direct API takes priority. The repository snapshot is the fallback when those APIs are not configured or their response is unavailable.

## Retailer showcase links

- Blue Tokai Vienna Roast coffee image and retailer page: Blinkit
- Minimalist SPF 50 sunscreen image and retailer page: Apollo Pharmacy

These are direct retailer pages. Price, delivery and stock are checked on the retailer page rather than treated as SmartCart live comparison data.

## Supplemental product catalog

- Sources: [Open Food Facts API documentation](https://openfoodfacts.github.io/documentation/docs/Product-Opener/v2/search/get-search/) and the Open Beauty Facts catalog using the same Product Opener read/search API.
- Endpoint: `world.openfoodfacts.org/cgi/search.pl` read/search API; the official docs note that API v2 does not support full-text search and point users to the search API v1. The app requests at most 12 records and only asks for product name, barcode, brand, image, quantity, store and country fields.
- Coverage: supplemental Open Food Facts matches for `All` and `Grocery`, and Open Beauty Facts matches for `All` and `Beauty`; queries ask for products tagged with India.
- Use: product identification and photos only. Catalog entries are not retailer listings, and SmartCart does not use them for prices, stock, or cart/checkout.
- API access: read-only requests use an identifying SmartCart User-Agent, as requested by [the official API documentation](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/). Open Food Facts data is under ODbL with attribution and share-alike terms; see its [API reuse guidance](https://support.openfoodfacts.org/help/en-gb/12-api-data-reuse/94-are-there-conditions-to-use-the-api). The product database is community contributed, so records and images should be checked at the linked source page.

## Grocery demo offers

- Local demo catalogue: 103 grocery and everyday-use products, including biscuits, snacks, rice, flour, pulses, tea, coffee, cooking oil, dairy and packaged drinks.
- Demo stores: BigBasket, JioMart and Blinkit.
- Prices, ratings, stock and delivery estimates for these three stores are generated sample values. They are not scraped from the retailers and are not live offers. Grocery demo search does not require a pincode.

## Live Blinkit API

- Source: [QuickCommerceAPI documentation](https://quickcommerceapi.com/docs), `GET /v1/search`.
- SmartCart sends the user's search term and the configured latitude/longitude, with the API key in the `X-API-Key` request header. The key is stored only in ignored `backend/.env`.
- The configured coordinates match the sample coordinates supplied for setup (`12.90, 77.66`); update `QUICKCOMMERCE_LAT` and `QUICKCOMMERCE_LON` in `backend/.env` for another delivery area.
- This provider documents a credit cost of one per platform result. Searching Blinkit uses one API credit per request; SmartCart does not poll in the background.
- BigBasket and JioMart remain labeled demo offers. Blinkit API results are live and location-specific when the key is active.

## User supplied product datasets

- Imported files: `amazon.csv`, `flipkard.csv`, `amazon_sales_data_uncleaned.csv`, `Tableau BlinkIT Grocery Project U16955293080 (4).xlsx`, `zepto_v1.xlsx`, `zepto_v2.csv`, and `zepto_data.xlsx` from the user's Downloads folder.
- The importer is `backend/scripts/import_user_datasets.py`. It writes the normalized, compressed catalog to `backend/app/user_dataset_catalog.json.gz`; source files are read-only and are not copied into the repository.
- Searchable dataset offers are labeled with their source filename and are marked non-current. They cannot be added to cart; the retailer link opens a page for checking current price and stock.
- `amazon.csv` contains Amazon India catalog rows, image links and product URLs. Its price/rating values are historical dataset values, not live Amazon offers.
- `flipkard.csv` has 80,000 rows but its generated-looking product names and randomized category assignments are not verified retailer records. It is included only as a classroom dataset snapshot and must not be presented as authentic Flipkart inventory.
- The BlinkIT workbook is a grocery outlet sales-analysis dataset with item MRP and outlet sales fields, not a live Blinkit catalog. Rows are searchable as historical/sample data.
- `zepto_v2.csv` is used once; `zepto_v1.xlsx` is a duplicate copy and is not double-counted. The supplied prices are stored in hundredths of a rupee and normalized to INR.
- `amazon_sales_data_uncleaned.csv` contains Amazon.com product scrape rows with USD prices. The rows are added to the product identity catalog only; the app does not convert USD into INR or show those values as Indian offers.
- `zepto_data.xlsx` contains inventory history and generated product identifiers, not a verified Zepto listing feed. It is catalog-only, with no imported price.
- Imported counts are generated by the import script and may change when the source files change. To rebuild after replacing them, run `python backend/scripts/import_user_datasets.py` from the project folder.

