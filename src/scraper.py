import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

COOKIES_PATH = os.path.join("data", "source_cookies.json")


def _save_cookies(context, path):
    cookies = context.cookies()
    with open(path, "w") as f:
        json.dump(cookies, f)


def _load_cookies(context, path):
    if os.path.exists(path):
        with open(path) as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        return True
    return False


def scrape_pins(source_url: str, email: str, password: str, limit: int) -> list[dict]:
    """
    Open Pinterest in a headless browser, log in, navigate to source account,
    and collect up to `limit` pin objects.

    Returns list of dicts:
      { pin_id, media_url, description, pin_type }  # pin_type: "image" or "video"
    """
    pins = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Try loading saved cookies first to skip login
        cookie_loaded = _load_cookies(context, COOKIES_PATH)

        if not cookie_loaded:
            _login(page, email, password)
            _save_cookies(context, COOKIES_PATH)
        else:
            # Verify cookies are still valid
            page.goto("https://www.pinterest.com/", timeout=30000)
            if "login" in page.url:
                _login(page, email, password)
                _save_cookies(context, COOKIES_PATH)

        # Navigate to source account
        page.goto(source_url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(random.uniform(2, 4))

        # Scroll deep to load older pins
        for _ in range(30):
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(random.uniform(1.0, 2.0))

        # Extract pin data from page
        pin_elements = page.query_selector_all('[data-test-id="pin"]')

        for el in pin_elements[:limit]:
            try:
                pin_data = _extract_pin(page, el)
                if pin_data:
                    pins.append(pin_data)
            except Exception as e:
                print(f"[scraper] Failed to extract pin: {e}")
                continue

        browser.close()

    print(f"[scraper] Collected {len(pins)} pins from {source_url}")
    return pins


def _login(page, email: str, password: str):
    """Log into Pinterest with email and password."""
    print("[scraper] Logging in to source account...")
    page.goto("https://www.pinterest.com/login/", timeout=30000)
    page.wait_for_selector('input[name="id"]', timeout=15000)

    page.fill('input[name="id"]', email)
    time.sleep(random.uniform(0.5, 1.5))
    page.fill('input[name="password"]', password)
    time.sleep(random.uniform(0.5, 1.0))
    page.click('button[type="submit"]')

    page.wait_for_url("https://www.pinterest.com/", timeout=20000)
    time.sleep(random.uniform(2, 4))
    print("[scraper] Login successful")


def _extract_pin(page, el) -> dict | None:
    """Extract pin metadata from a pin element."""
    try:
        # Get link to pin detail page
        link_el = el.query_selector("a")
        if not link_el:
            return None
        href = link_el.get_attribute("href")
        if not href or "/pin/" not in href:
            return None

        pin_id = href.split("/pin/")[1].strip("/").split("/")[0]

        # Detect video pin
        video_el = el.query_selector("video")
        if video_el:
            media_url = f"https://www.pinterest.com{href}"
            pin_type = "video"
        else:
            img_el = el.query_selector("img")
            if not img_el:
                return None
            media_url = img_el.get_attribute("src") or img_el.get_attribute("data-src")
            if not media_url:
                return None
            # Get full-size image (replace size suffix in URL)
            media_url = media_url.replace("236x", "originals").replace("474x", "originals")
            pin_type = "image"

        # Get description from alt text or aria-label
        description = (
            el.get_attribute("aria-label")
            or el.query_selector("img") and el.query_selector("img").get_attribute("alt")
            or ""
        )

        return {
            "pin_id": pin_id,
            "media_url": media_url,
            "description": description[:500],  # Pinterest description limit
            "pin_type": pin_type,
            "source_href": href,
        }

    except Exception:
        return None
