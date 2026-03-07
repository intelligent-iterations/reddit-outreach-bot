"""Phase 2: Search & Result Scraping Test

This is the EXPLORATORY phase. We'll:
1. Login
2. Navigate to search
3. Print everything we can find
4. Extract leads and verify data quality
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import login
from src.search import search_comments, explore_search_page
from src.utils import load_config


async def test_explore_search():
    """Exploratory: print everything from a search page."""
    print("=" * 60)
    print("TEST: Explore Search Page (Exploratory)")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    browser, page = await login(config, account, headless=False)

    try:
        html = await explore_search_page(page, "yuka app", config)
        print(f"\n[TEST] Total HTML length: {len(html)}")
    except Exception as e:
        print(f"[TEST] Exploration failed: {e}")

    await asyncio.sleep(3)
    await browser.stop()


async def test_search_extraction():
    """Test actual lead extraction from search."""
    print("\n" + "=" * 60)
    print("TEST: Search Lead Extraction")
    print("=" * 60)

    config = load_config()
    account = config["accounts"][0]
    browser, page = await login(config, account, headless=False)

    try:
        leads = await search_comments(page, "yuka app", config)

        print(f"\n[TEST] Extracted {len(leads)} leads:")
        for i, lead in enumerate(leads[:10]):
            print(f"\n  Lead {i + 1}:")
            print(f"    Username:  u/{lead['username']}")
            print(f"    Subreddit: r/{lead['subreddit']}")
            print(f"    Permalink: {lead['permalink'][:80]}")
            print(f"    Text:      {lead['comment_text'][:100]}...")

        if leads:
            print("\n[TEST] Search extraction PASSED")
        else:
            print("\n[TEST] WARNING: No leads extracted may need to adjust parsing")

    except Exception as e:
        print(f"[TEST] Search extraction failed: {e}")

    await asyncio.sleep(3)
    await browser.stop()


async def main():
    mode = "extract"
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if mode == "explore":
        await test_explore_search()
    elif mode == "extract":
        await test_search_extraction()
    else:
        await test_explore_search()
        await asyncio.sleep(5)
        await test_search_extraction()


if __name__ == "__main__":
    asyncio.run(main())
