"""Phase 3: DM Functionality Test

Tests:
1. Navigate to message compose
2. Fill fields and send
3. Verify with safe targets (brand accounts)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import login
from src.dm import send_dm
from src.utils import load_config


async def test_dm_compose():
    """Test DM to safe targets."""
    print("=" * 60)
    print("TEST: DM Compose & Send")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    browser, page = await login(config, account, headless=False)

    # Test targets (brand/large accounts that won't notice)
    targets = [
        ("reddit", "test from bot", "This is a test message, please ignore."),
    ]

    for username, subject, body in targets:
        print(f"\n--- Sending DM to u/{username} ---")
        success = await send_dm(page, username, subject, body, config)
        if success:
            print(f"[TEST] DM to u/{username}: SUCCESS")
        else:
            print(f"[TEST] DM to u/{username}: FAILED (may be expected)")
        await asyncio.sleep(5)

    await asyncio.sleep(3)
    await browser.stop()
    print("\n[TEST] DM test complete")


if __name__ == "__main__":
    asyncio.run(test_dm_compose())
