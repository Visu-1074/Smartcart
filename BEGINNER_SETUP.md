# SmartCart: beginner setup for real retailer listings

## Run SmartCart

Open the SmartCart project folder and double-click **`START_SMARTCART.cmd`**. It starts the website and API if they are not already running, then opens the site in your browser. You do not need to type commands or edit code to view the project.

The homepage has two real product pages with photos and direct retailer links: Blue Tokai on Blinkit and Minimalist sunscreen on Apollo Pharmacy. Their live price and delivery availability are shown by the retailers. Search also loads the linked repository's exported phone catalogue for Amazon and Flipkart when their retailer APIs are not configured. That archive contains real product titles and photos, but its prices and ratings are from February 2023; the site marks them as archived and won't let you add them to cart. The **Include demo listings** checkbox only shows separate sample data.

SmartCart can work without retailer API accounts: it automatically uses the community export as a dated archive for Amazon and Flipkart. To get current prices, you need approved API access from those retailers. Do not send API keys or passwords in chat.

## Which accounts you need

### Amazon.in

Amazon requires an Amazon Associates account for India before you can register for Creators API. Its current requirements also say an account needs at least 10 qualifying sales in the past 30 days before API access is available. If you do not meet that requirement yet, current Amazon API prices will not activate; the archived product export still works. [Amazon Associates sign-up](https://affiliate-program.amazon.in/) · [Creators API instructions](https://affiliate-program.amazon.in/creatorsapi/docs/en-us/introduction)

Once eligible, open Associates Central, open the **CreatorsAPI** area, create an application, then create a credential. Keep the Client ID, Client Secret, Version, and your India Associate/Partner Tag. Use the value called **Version** exactly as shown in your dashboard.

### Flipkart

Register for the [Flipkart Affiliate Program](https://affiliate.flipkart.com/registerme). After you are signed in, open **API → API Token** and generate a token. The page shows your Affiliate Tracking ID. Keep both values private. Flipkart allows one active token per affiliate account; generating another disables the old one. [Official token steps](https://affiliate.flipkart.com/api-docs/af_register.html)

You can start with either retailer. Both accounts are not required. If you don't have API access today, you can still use the archived Amazon and Flipkart product records; the site warns that their prices are old.

## Add your keys without changing code

1. Open the SmartCart folder in File Explorer, then open the `backend` folder.
2. Make a copy of `.env.example` and name the copy `.env` (keep the leading dot; do not name it `.env.txt`).
3. Open `backend/.env` in Notepad.
4. For Amazon, fill in these existing lines with the values from Associates Central:

   ```text
   PLATFORM_MODE_AMAZON_IN=api
   AMAZON_CREATORS_CLIENT_ID=your Client ID
   AMAZON_CREATORS_CLIENT_SECRET=your Client Secret
   AMAZON_CREATORS_VERSION=your Version
   AMAZON_PARTNER_TAG=your India Associate tag
   ```

5. For Flipkart, fill in these existing lines:

   ```text
   PLATFORM_MODE_FLIPKART=api
   FLIPKART_AFFILIATE_ID=your Affiliate Tracking ID
   FLIPKART_AFFILIATE_TOKEN=your API Token
   ```

6. Save the file. Do not email it, upload it, or paste its contents into chat.

## Restart the backend

After saving your API keys, the frontend can stay open. Find the PowerShell window running the backend, press **Ctrl+C** once, then run:

```powershell
cd "C:\Users\visha\Documents\Codex\2026-11-15\files-pasted-by-the-user-build\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0
```

Refresh [SmartCart](http://localhost:5173/) and search. Approved APIs show current retailer data. If an API is unavailable, SmartCart uses the dated GitHub archive instead. Search for **Redmi** or **Samsung** to see archived phone listings; each card warns that its price is historical and links to the retailer. Keep **Include demo listings** off to avoid sample catalogue prices.

## What the scraper link does

SmartCart reads only the repository's exported JSON data file; it does not run the scraper or rotating proxies. The export is an archive snapshot, not a live product feed. The repository is licensed GPL-3.0; see [its license](https://github.com/ShauryaSwarup/Ecommerce-Scraper/blob/main/LICENSE.md).
