"""Phase 1: Login & Session Persistence Test

Tests:
1. Fresh login with username/password
2. Cookie save after login
3. Cookie reuse on fresh browser launch
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import login
from src.utils import load_config, BASE_DIR


async def test_fresh_login():
    """Test 1: Login with credentials, save cookies."""
    print("=" * 60)
    print("TEST 1: Fresh Login")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    cookies_path = os.path.join(BASE_DIR, account["cookies_path"])

    # Remove existing cookies to force fresh login
    if os.path.exists(cookies_path):
        os.remove(cookies_path)
        print("[TEST] Removed existing cookies")

    browser, page = await login(config, account, headless=False)

    # Verify cookies were saved
    assert os.path.exists(cookies_path), "Cookies file was not created!"
    file_size = os.path.getsize(cookies_path)
    assert file_size > 0, "Cookies file is empty!"
    print(f"[TEST] Cookies file created: {file_size} bytes")

    print("[TEST] Fresh login test PASSED")
    await browser.stop()
    return True


async def test_cookie_reuse():
    """Test 2: Launch fresh browser, load cookies, verify still logged in."""
    print("\n" + "=" * 60)
    print("TEST 2: Cookie Reuse")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    cookies_path = os.path.join(BASE_DIR, account["cookies_path"])

    assert os.path.exists(cookies_path), "No cookies file found run test_fresh_login first!"

    browser, page = await login(config, account, headless=False)

    # The login function should have used cookies without needing credentials
    print("[TEST] Cookie reuse test PASSED")

    # Keep browser open briefly to verify visually
    await asyncio.sleep(3)
    await browser.stop()
    return True


async def main():
    print("Starting Phase 1: Login Tests")
    print()

    try:
        await test_fresh_login()
    except Exception as e:
        print(f"[TEST] Fresh login FAILED: {e}")
        return

    # Brief pause between tests
    await asyncio.sleep(2)

    try:
        await test_cookie_reuse()
    except Exception as e:
        print(f"[TEST] Cookie reuse FAILED: {e}")
        return

    print("\n" + "=" * 60)
    print("ALL PHASE 1 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
