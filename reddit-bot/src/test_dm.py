"""Simple test: go to a user's profile and try to DM them."""
import asyncio
import sys

from src.auth import login
from src.utils import load_config, take_error_screenshot


async def run():
    config = load_config()
    account = config["accounts"][0]

    # Use smiggle3 as test target (one that failed before)
    target_user = "smiggle3"
    if len(sys.argv) > 1:
        target_user = sys.argv[1]

    print(f"=== DM Test: u/{target_user} ===")
    print(f"Logging in as {account['username']}...")
    browser, page = await login(config, account, headless=False)

    try:
        # Step 1: Navigate to their profile
        print(f"\n[TEST] Going to u/{target_user}'s profile...")
        await page.get(f"https://www.reddit.com/user/{target_user}")
        await asyncio.sleep(4)

        # Step 2: Take screenshot to see state
        print("[TEST] Taking screenshot of profile...")
        await take_error_screenshot(page, "test_profile")

        # Step 3: List all buttons
        print("\n[TEST] Looking for buttons...")
        buttons = await page.select_all('button')
        print(f"[TEST] Found {len(buttons)} buttons total")

        chat_btn = None
        for i, btn in enumerate(buttons[:30]):  # Check first 30
            try:
                text = btn.text or ""
                text = text.strip()
                if text and len(text) < 50:
                    print(f"[TEST]   Button {i}: '{text}'")
                    if "Chat" in text:
                        chat_btn = btn
                        print(f"[TEST]   >>> This is the chat button!")
            except Exception as e:
                pass

        if not chat_btn:
            print("\n[TEST] No Chat button found via select_all!")
            print("[TEST] Trying page.find...")
            try:
                chat_btn = await page.find("Start Chat", best_match=True, timeout=10)
                print(f"[TEST] page.find returned: {chat_btn}")
                if chat_btn:
                    print(f"[TEST] Button text: {chat_btn.text}")
            except Exception as e:
                print(f"[TEST] page.find failed: {e}")

        if not chat_btn:
            print("\n[TEST] FAILED: Could not find Start Chat button")
            await take_error_screenshot(page, "test_no_chat_btn")
            return

        # Step 4: Click the button
        print("\n[TEST] Clicking Start Chat...")
        try:
            await chat_btn.scroll_into_view()
            await asyncio.sleep(0.5)
        except:
            pass
        await chat_btn.click()
        await asyncio.sleep(3)

        # Step 5: Screenshot after click
        await take_error_screenshot(page, "test_after_chat_click")

        # Step 6: Find message input
        print("\n[TEST] Looking for message input...")
        try:
            msg_input = await page.find("Message", best_match=True, timeout=10)
            print(f"[TEST] Found message input")

            await msg_input.click()
            await asyncio.sleep(0.5)

            # Type test message
            print("[TEST] Typing 'test message do not reply'...")
            await msg_input.send_keys("test message do not reply")
            await asyncio.sleep(1)

            await take_error_screenshot(page, "test_typed_message")

            print("\n[TEST] SUCCESS! Message typed.")
            print("[TEST] NOT sending - this is just a test.")

        except Exception as e:
            print(f"[TEST] Could not find/use message input: {e}")
            await take_error_screenshot(page, "test_no_input")

    except Exception as e:
        print(f"\n[TEST] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[TEST] Waiting 10 seconds before closing...")
        await asyncio.sleep(10)
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(run())
