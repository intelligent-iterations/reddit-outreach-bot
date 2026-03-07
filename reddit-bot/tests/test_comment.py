"""Phase 4: Comment Functionality Test

Tests:
1. Post a comment on r/test
2. Reply to a comment on r/test
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import login
from src.comment import post_comment, reply_to_comment
from src.utils import load_config


async def test_comment_on_test_sub():
    """Test commenting on r/test (bot testing subreddit)."""
    print("=" * 60)
    print("TEST: Comment on r/test")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    browser, page = await login(config, account, headless=False)

    # First, find a recent post on r/test to comment on
    print("\n[TEST] Navigating to r/test...")
    await page.get("https://www.reddit.com/r/test/new/")
    await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

    # Find first post link
    import re
    html = await page.get_content()
    post_links = re.findall(r'/r/test/comments/([A-Za-z0-9]+)/[^"\'>\s]*', html)

    if post_links:
        permalink = f"/r/test/comments/{post_links[0]}/"
        print(f"[TEST] Found post: {permalink}")

        # Post a comment
        success = await post_comment(
            page, permalink,
            "test comment from bot - please ignore",
            config
        )
        if success:
            print("[TEST] Comment posted: SUCCESS")
        else:
            print("[TEST] Comment posted: FAILED")
    else:
        print("[TEST] Could not find any posts on r/test")

    await asyncio.sleep(3)
    await browser.stop()
    print("\n[TEST] Comment test complete")


if __name__ == "__main__":
    asyncio.run(test_comment_on_test_sub())
