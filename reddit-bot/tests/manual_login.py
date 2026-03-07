"""Manual login helper.

Opens a browser to Reddit login page. You log in manually (solve captcha etc).
Once logged in, press Enter in the terminal to save cookies.
"""
import asyncio
import os
import sys
import platform

import zendriver as zd
from zendriver.core.config import Config as ZDConfig

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIES_PATH = os.path.join(BASE_DIR, "data", "cookies.json")
CHROME_PATH_MACOS = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


async def main():
    print("Opening browser for manual Reddit login...")
    print("Log in manually, solve any captchas, then come back here.")
    print()

    zd_kwargs = {"headless": False, "browser_connection_timeout": 2.0, "browser_connection_max_tries": 15}
    if platform.system() == "Darwin" and os.path.exists(CHROME_PATH_MACOS):
        zd_kwargs["browser_executable_path"] = CHROME_PATH_MACOS

    zd_config = ZDConfig(**zd_kwargs)
    browser = await zd.start(zd_config)
    page = await browser.get("https://www.reddit.com/login")

    print("Browser opened to reddit.com/login")
    print("Log in manually, then press Enter here when done...")

    # Wait for user input in a non-blocking way
    await asyncio.get_event_loop().run_in_executor(None, input)

    # Save cookies
    try:
        await browser.cookies.save(COOKIES_PATH)
        file_size = os.path.getsize(COOKIES_PATH)
        print(f"Cookies saved to {COOKIES_PATH} ({file_size} bytes)")
    except Exception as e:
        print(f"Failed to save cookies: {e}")

    # Verify we're on reddit and logged in
    page = await browser.get("https://www.reddit.com")
    await asyncio.sleep(3)
    await page.save_screenshot(os.path.join(BASE_DIR, "data", "manual_login_verify.png"))
    print("Screenshot saved to data/manual_login_verify.png")

    await browser.stop()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
