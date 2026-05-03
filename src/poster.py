import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

COOKIES_PATH = os.path.join("data", "poster_cookies.json")


def _save_cookies(context, path):
    with open(path, "w") as f:
        json.dump(context.cookies(), f)


def _load_cookies(context, path):
    if os.path.exists(path):
        with open(path) as f:
            context.add_cookies(json.load(f))
        return True
    return False


def post_pin(email: str, password: str, board_name: str, local_file: str, description: str) -> bool:
    """
    Open Pinterest in a headless browser, log into YOUR account,
    navigate to the pin creation page, upload the file, and publish.

    Returns True on success, False on failure.
    """
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

        cookie_loaded = _load_cookies(context, COOKIES_PATH)

        if not cookie_loaded:
            _login(page, email, password)
            _save_cookies(context, COOKIES_PATH)
        else:
            page.goto("https://www.pinterest.com/", timeout=30000)
            if "login" in page.url:
                _login(page, email, password)
                _save_cookies(context, COOKIES_PATH)

        try:
            success = _create_pin(page, board_name, local_file, description)
        except Exception as e:
            print(f"[poster] Error during pin creation: {e}")
            success = False
        finally:
            browser.close()

    return success


def _login(page, email: str, password: str):
    print("[poster] Logging in to your account...")
    page.goto("https://www.pinterest.com/login/", timeout=30000)
    page.wait_for_selector('input[name="id"]', timeout=15000)
    page.fill('input[name="id"]', email)
    time.sleep(random.uniform(0.5, 1.5))
    page.fill('input[name="password"]', password)
    time.sleep(random.uniform(0.5, 1.0))
    page.click('button[type="submit"]')
    page.wait_for_url("https://www.pinterest.com/", timeout=20000)
    time.sleep(random.uniform(2, 3))
    print("[poster] Login successful")


def _create_pin(page, board_name: str, local_file: str, description: str) -> bool:
    """Navigate the Pinterest create-pin UI and submit."""

    # Go to pin creation page
    page.goto("https://www.pinterest.com/pin-creation-tool/", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(random.uniform(2, 4))

    # Upload file via the hidden file input
    file_input = page.query_selector('input[type="file"]')
    if not file_input:
        print("[poster] Could not find file upload input")
        return False

    file_input.set_input_files(local_file)
    print(f"[poster] Uploaded file: {local_file}")
    time.sleep(random.uniform(3, 6))  # wait for upload to process

    # Fill in description
    desc_el = page.query_selector('[data-test-id="pin-draft-description"] div[contenteditable]')
    if not desc_el:
        # fallback selector
        desc_el = page.query_selector('textarea[placeholder]')
    if desc_el:
        desc_el.click()
        time.sleep(0.5)
        desc_el.type(description, delay=random.randint(30, 80))
        time.sleep(random.uniform(1, 2))

    # Select the board
    board_selector = page.query_selector('[data-test-id="board-dropdown-select-button"]')
    if board_selector:
        board_selector.click()
        time.sleep(random.uniform(1, 2))

        # Search for board by name
        search_input = page.query_selector('[data-test-id="board-search-input"]')
        if search_input:
            search_input.type(board_name, delay=50)
            time.sleep(1.5)

        # Click matching board option
        board_option = page.query_selector(f'[data-test-id="board-option"]:has-text("{board_name}")')
        if board_option:
            board_option.click()
            time.sleep(random.uniform(1, 2))
        else:
            print(f"[poster] Board '{board_name}' not found, attempting to create it...")
            # Click the 'Create board' button that appears when search fails
            create_board_btn = page.query_selector('div[role="button"]:has-text("Create board"), button:has-text("Create board")')
            if create_board_btn:
                create_board_btn.click()
                time.sleep(2)
                
                # Type the board name in the popup
                name_input = page.query_selector('input[id="boardEditName"], input[name="boardName"], input[placeholder*="Name"]')
                if name_input:
                    name_input.fill("")
                    name_input.type(board_name, delay=50)
                    time.sleep(1)
                
                # Click the final Create button
                submit_btn = page.query_selector('button:has-text("Create")')
                if submit_btn:
                    submit_btn.click()
                    time.sleep(4)  # Wait for creation to finish
            else:
                # Absolute fallback: just click the very first available board
                fallback_board = page.query_selector('[data-test-id="board-option"]')
                if fallback_board:
                    fallback_board.click()
                    time.sleep(random.uniform(1, 2))

    # Click Publish button
    publish_btn = page.query_selector('[data-test-id="storyboard-creation-nav-done"]')
    if not publish_btn:
        publish_btn = page.query_selector('button:has-text("Publish")')
    if not publish_btn:
        print("[poster] Could not find Publish button")
        return False

    publish_btn.click()
    print("[poster] Clicked Publish")

    # Wait to confirm success (URL changes or success message)
    time.sleep(random.uniform(4, 7))

    # Check if we're still on the creation page (means it failed)
    if "pin-creation-tool" in page.url:
        print("[poster] Still on creation page — publish may have failed")
        return False

    print("[poster] Pin published successfully")
    return True
