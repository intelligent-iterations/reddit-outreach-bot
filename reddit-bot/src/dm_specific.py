"""Send DMs to a specific list of users."""
import asyncio
import random

from src.auth import login
from src.dm import send_dm, DM_SUCCESS, DM_RATE_LIMITED
from src.templates import select_and_fill
from src.tracker import has_been_dmed, log_dm
from src.utils import load_config, load_templates, random_delay

# These are the 10 users we want to DM
TARGET_LEADS = [
    {
        "username": "slightleee",
        "comment_text": "Get the yuka app. You will stop eating rubbish like this after a while. Even simple things like bread, some have like 50 ingredients and not all nice. Bread should have something like 3 ingredients.",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5iv04q/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "BurnyMadeoffJR",
        "comment_text": "",
        "subreddit": "AskReddit",
        "permalink": "/r/AskReddit/comments/1r5a06o/what_is_your_favourite_app_and_why/o5hf6jv/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "UP_PLANET",
        "comment_text": "",
        "subreddit": "nashville",
        "permalink": "/r/nashville/comments/1r1pye4/any_cool_valentines_day_ideas/o4xhdqt/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "smiggle3",
        "comment_text": "Use a app called Yuka it will tell you what's in them",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5ilpsg/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "Hampshire_Coast",
        "comment_text": "Download the YUKA app. Scan the barcodes and choose the meal with the highest score.",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5ksszd/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "holaamigo10",
        "comment_text": "Not sure if this has already been commented but download the app 'Yuka' and you can scan the bar codes of food and it will explain what's in them. Excellent excellent app!",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5kmepb/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "oznkarsli",
        "comment_text": "TBF, ingredients seem better than expected but for more insight on the ingredients, I recommend the Yuka app. It is brilliant in terms of classifying the ingredients and giving alternative products for you. I found some better alternatives which I didn't know existed.",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5kke65/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "candidate26",
        "comment_text": "Scan with the Yuka app. Frozen stuff ca be quite surprising (healthy)",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5kjlrb/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "Mindless_Ad1501",
        "comment_text": "Try downloading Yuka app to get a breakdown of how healthy food is. Was searching for a free app that shows you whether something is ultra processed and this does the job",
        "subreddit": "AskUK",
        "permalink": "/r/AskUK/comments/1r5aycp/how_healthy_or_unhealthy_are_these_frozen_ready/o5kg201/",
        "keyword_matched": "yuka app"
    },
    {
        "username": "I-own-a-shovel",
        "comment_text": "I scan my product with the free app YUKA. It gives list of potential harmful ingredient and explain why. (fragrances are then described as so) They also list other irritant that aren't necessarily fragrances, which is useful for my asthma / hypersensitivity to irritant in general, not just scented one.",
        "subreddit": "FragranceFreeBeauty",
        "permalink": "/r/FragranceFreeBeauty/comments/1r59igf/can_i_use_ai_to_detect_fragrances_in_ingredient/o5kcqvw/",
        "keyword_matched": "yuka app"
    },
]


async def run():
    config = load_config()
    templates = load_templates()

    print("=" * 60)
    print("DM Specific Users Script")
    print(f"Targeting {len(TARGET_LEADS)} users")
    print("=" * 60)

    # Track users we've DMed this session (case-insensitive)
    session_dmed = set()

    # Use first DM-capable account
    account = next((a for a in config["accounts"] if a.get("can_dm", True)), config["accounts"][0])
    acct_name = account["username"]

    # Login
    print(f"\n[DM] Logging in as {acct_name}...")
    browser, page = await login(config, account, headless=False)

    dms_sent = 0
    dms_failed = 0

    try:
        for i, lead in enumerate(TARGET_LEADS):
            username = lead["username"]
            username_lower = username.lower()

            print(f"\n{'─' * 40}")
            print(f"[DM] ({i+1}/{len(TARGET_LEADS)}) Processing u/{username}")

            # Check if already DMed (session or file)
            if username_lower in session_dmed:
                print(f"[DM] Already DMed this session, skipping")
                continue

            if has_been_dmed(username):
                print(f"[DM] Already in contacted.json, skipping")
                continue

            # Generate message
            filled_dm, archetype, subject = select_and_fill(lead, "dm", templates, config)

            if not filled_dm:
                print(f"[DM] No template matched, skipping")
                continue

            # Mark as DMed immediately to prevent duplicates
            session_dmed.add(username_lower)

            print(f"[DM] Archetype: {archetype}")
            print(f"[DM] Subject: {subject}")
            print(f"[DM] Message preview: {filled_dm[:100]}...")

            # Send DM
            result = await send_dm(page, username, subject or "hey", filled_dm, config)
            log_dm(username, filled_dm, result == DM_SUCCESS, account=acct_name)

            if result == DM_SUCCESS:
                dms_sent += 1
                print(f"[DM] SUCCESS - DM sent to u/{username}")
            elif result == DM_RATE_LIMITED:
                dms_failed += 1
                print(f"[DM] RATE LIMITED - Stopping all DMs for this session")
                break
            else:
                dms_failed += 1
                print(f"[DM] FAILED - Could not DM u/{username}")

            # Wait 12-18 minutes between DMs
            if i < len(TARGET_LEADS) - 1:
                wait_time = random.uniform(720, 1080)
                print(f"[DM] Waiting {wait_time / 60:.1f} minutes before next DM...")
                await asyncio.sleep(wait_time)

    except KeyboardInterrupt:
        print("\n[DM] Interrupted by user")
    except Exception as e:
        print(f"\n[DM] Error: {e}")
    finally:
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"  DMs sent: {dms_sent}")
        print(f"  DMs failed: {dms_failed}")
        print(f"  Skipped: {len(TARGET_LEADS) - dms_sent - dms_failed}")
        print(f"{'=' * 60}")

        try:
            await browser.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run())
