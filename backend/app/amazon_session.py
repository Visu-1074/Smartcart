from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).resolve().parents[1] / ".data" / "amazon-storage-state.enc"


class AmazonReviewSession:
    def __init__(self):
        self.sessions: dict[str, tuple[object, object, object]] = {}

    def _cipher(self) -> Fernet:
        key = os.getenv("SMARTCART_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("Set SMARTCART_ENCRYPTION_KEY before enabling a saved Amazon session.")
        return Fernet(key.encode())

    def _read_state(self) -> dict | None:
        if not SESSION_FILE.exists():
            return None
        try:
            raw = self._cipher().decrypt(SESSION_FILE.read_bytes())
            return json.loads(raw)
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("The saved Amazon session cannot be decrypted. Check SMARTCART_ENCRYPTION_KEY.") from exc

    async def start(self, product_urls: list[str]) -> str:
        self._cipher()
        manager = await async_playwright().start()
        browser = None
        try:
            browser = await manager.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=self._read_state())
            for index, product_url in enumerate(product_urls[:10]):
                page = await context.new_page()
                url = product_url if product_url.startswith("https://www.amazon.in/") else "https://www.amazon.in/"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if index == 0:
                    await page.bring_to_front()
        except Exception:
            if browser:
                await browser.close()
            await manager.stop()
            raise
        session_id = secrets.token_urlsafe(18)
        self.sessions[session_id] = (manager, browser, context)
        return session_id

    async def save(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("Amazon review session is no longer active")
        manager, browser, context = session
        state = await context.storage_state()
        encrypted = self._cipher().encrypt(json.dumps(state).encode())
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_bytes(encrypted)
        await browser.close()
        await manager.stop()
        self.sessions.pop(session_id, None)

    async def prepare_basket(self, session_id: str, items: list[dict]) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("Amazon review session is no longer active")
        _, _, context = session
        added = 0
        for item in items[:10]:
            url = item.get("url", "")
            if not url.startswith("https://www.amazon.in/"):
                continue
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if "/ap/signin" in page.url or await page.locator("input#ap_email").count():
                return {"status": "login_required", "added": added, "message": "Finish Amazon OTP login in the headed browser, then prepare the basket again."}
            body = (await page.locator("body").inner_text(timeout=2500)).casefold()
            if any(marker in body for marker in ("captcha", "verify you are human", "access denied", "unusual traffic")):
                return {"status": "blocked", "added": added, "message": "Amazon requires a manual check. SmartCart stopped and did not bypass it."}
            add_button = None
            for selector in ("#add-to-cart-button", "input[name='submit.add-to-cart']", "button[name='submit.add-to-cart']"):
                candidate = page.locator(selector).first
                if await candidate.count() and await candidate.is_visible():
                    add_button = candidate
                    break
            if add_button is None:
                return {"status": "manual_action_required", "added": added, "message": f"Could not find an Add to Cart control for {item.get('title', 'an item')}. Use the Amazon tab to add it manually."}
            try:
                quantity = min(99, max(1, int(item.get("quantity", 1))))
                quantity_select = page.locator("#quantity")
                if await quantity_select.count():
                    await quantity_select.select_option(str(quantity))
                await add_button.click(timeout=5000)
                added += 1
            except Exception:
                return {"status": "manual_action_required", "added": added, "message": "Amazon did not accept the add-to-cart action. Finish that item manually in the headed browser."}
            finally:
                await page.close()
        cart_page = await context.new_page()
        await cart_page.goto("https://www.amazon.in/gp/cart/view.html", wait_until="domcontentloaded", timeout=30000)
        return {"status": "awaiting_user_confirmation", "added": added, "message": "Amazon cart is open for review. SmartCart stopped before checkout and payment."}


amazon_review_session = AmazonReviewSession()
