import asyncio
import os
import platform

import zendriver as zd
from zendriver.core.config import Config as ZDConfig

from src.utils import BASE_DIR, human_type, random_delay, take_error_screenshot

# macOS needs explicit Chrome path and longer connection timeout
CHROME_PATH_MACOS = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


async def login(config, account, headless=False):
    """Login to Reddit with a specific account. Returns (browser, page).

    Tries cookies first, falls back to fresh login.
    """
    zd_kwargs = {"headless": headless, "browser_connection_timeout": 2.0, "browser_connection_max_tries": 15}
    if platform.system() == "Darwin" and os.path.exists(CHROME_PATH_MACOS):
        zd_kwargs["browser_executable_path"] = CHROME_PATH_MACOS

    zd_config = ZDConfig(**zd_kwargs)
    browser = await zd.start(zd_config)
    cookies_path = os.path.join(BASE_DIR, account["cookies_path"])

    # Try loading cookies if they exist
    if os.path.exists(cookies_path):
        print(f"[AUTH] Found cookies for {account['username']}, attempting to restore session...")
        try:
            page = await browser.get("https://www.reddit.com")
            await browser.cookies.load(cookies_path)
            # Navigate again so cookies take effect
            page = await browser.get("https://www.reddit.com")
            await asyncio.sleep(config["delays"]["page_load_wait_seconds"])

            if await _is_logged_in(page, account):
                print(f"[AUTH] Cookie login successful for {account['username']}!")
                return browser, page
            else:
                print("[AUTH] Cookies expired, doing fresh login...")
                os.remove(cookies_path)
        except Exception as e:
            print(f"[AUTH] Cookie load failed: {e}")

    # Fresh login
    page = await _do_login(browser, config, account)

    # Save cookies
    try:
        await browser.cookies.save(cookies_path)
        print(f"[AUTH] Cookies saved to {cookies_path}")
    except Exception as e:
        print(f"[AUTH] Failed to save cookies: {e}")

    return browser, page


async def _is_logged_in(page, account):
    """Check if we're logged in by looking for the username or user menu."""
    try:
        username = account["username"]
        # Try to find the username displayed on the page
        el = await page.find(username, best_match=True, timeout=5)
        if el:
            print(f"[AUTH] Found username '{username}' on page logged in")
            return True
    except Exception:
        pass

    # Try finding common logged-in indicators
    for indicator in ["Create Post", "Create a community", "Open inbox"]:
        try:
            el = await page.find(indicator, best_match=True, timeout=3)
            if el:
                print(f"[AUTH] Found '{indicator}' logged in")
                return True
        except Exception:
            continue

    return False


async def _do_login(browser, config, account):
    """Perform fresh login with username/password."""
    print(f"[AUTH] Logging in as {account['username']}...")
    page = await browser.get("https://www.reddit.com/login")
    await asyncio.sleep(config["delays"]["page_load_wait_seconds"])

    username = account["username"]
    password = account["password"]

    try:
        # Find and fill username field using CSS selector (Reddit uses custom web components)
        print("[AUTH] Looking for username field...")
        username_field = await page.select("faceplate-text-input#login-username", timeout=10)
        await username_field.click()
        await random_delay(0.3, 0.8)
        await human_type(username_field, username, config)
        print(f"[AUTH] Typed username: {username}")

        await random_delay(0.5, 1.5)

        # Find and fill password field using CSS selector
        print("[AUTH] Looking for password field...")
        password_field = await page.select("faceplate-text-input#login-password", timeout=10)
        await password_field.click()
        await random_delay(0.3, 0.8)
        await human_type(password_field, password, config)
        print("[AUTH] Typed password")

        await random_delay(0.5, 1.5)

        # Click login button - it's inside a faceplate-form, find by class
        print("[AUTH] Looking for Log In button...")
        login_btn = await page.select("faceplate-form#login button.login", timeout=10)
        await login_btn.click()
        print("[AUTH] Clicked Log In")

        # Wait for redirect/page load
        await asyncio.sleep(5)

        # Check for captcha
        try:
            captcha = await page.find("captcha", best_match=True, timeout=3)
            if captcha:
                print("[AUTH] *** CAPTCHA DETECTED ***")
                print("[AUTH] Please solve the captcha manually in the browser window.")
                print("[AUTH] Waiting up to 120 seconds...")
                # Poll for captcha resolution
                for _ in range(24):
                    await asyncio.sleep(5)
                    if await _is_logged_in(page, account):
                        print("[AUTH] Captcha solved, logged in!")
                        return page
                print("[AUTH] Captcha timeout login may have failed")
        except Exception:
            pass

        # Check for 2FA
        try:
            twofa = await page.find("verification code", best_match=True, timeout=3)
            if twofa:
                print("[AUTH] *** 2FA DETECTED ***")
                print("[AUTH] Please enter 2FA code manually.")
                print("[AUTH] Waiting up to 120 seconds...")
                for _ in range(24):
                    await asyncio.sleep(5)
                    if await _is_logged_in(page, account):
                        print("[AUTH] 2FA complete, logged in!")
                        return page
                print("[AUTH] 2FA timeout")
        except Exception:
            pass

        # Verify login succeeded
        if await _is_logged_in(page, account):
            print("[AUTH] Login successful!")
            return page
        else:
            print("[AUTH] Login may have failed could not confirm logged-in state")
            await take_error_screenshot(page, "login_unconfirmed")
            return page

    except Exception as e:
        print(f"[AUTH] Login error: {e}")
        await take_error_screenshot(page, "login_error")
        raise
