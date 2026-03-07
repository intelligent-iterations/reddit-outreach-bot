"""Multi-account integration test using the real DM and comment flows.

Tests:
1. Account A sends 2 DMs to different users
2. Account A comments on 2 different threads
3. Account B sends 2 DMs — verifies it skips users Account A already engaged
4. Account B comments on 2 threads — verifies it skips threads Account A touched
5. Cross-account isolation via users_engaged.json and threads_touched.json

Usage:
    python src/test_banana.py                  # uses first 2 DM-capable accounts
    python src/test_banana.py --dry-run        # show what would happen without sending
    python src/test_banana.py --reset          # clear test tracking data and run
"""
import asyncio
import json
import os
import re
import sys

from src.auth import login
from src.dm import send_dm, DM_SUCCESS, DM_RATE_LIMITED
from src.comment import post_comment, COMMENT_SUCCESS, COMMENT_LOCKED
from src.tracker import (
    has_been_dmed, log_dm, log_comment,
    can_engage_user, can_comment_in_thread,
    log_user_engaged, log_thread_touched, extract_post_id,
)
from src.utils import load_config, BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")

DMS_PER_ACCOUNT = 2
COMMENTS_PER_ACCOUNT = 2
DM_WAIT_SECONDS = 300  # 5 min between DMs (shorter than prod for testing)
COMMENT_WAIT_SECONDS = 120  # 2 min between comments


async def find_dm_targets(page, count=8):
    """Find users to DM by searching recent comments."""
    print(f"[FIND] Searching for {count} DM targets...")
    await page.get("https://www.reddit.com/search/?q=bananas&type=comment&sort=new")
    await asyncio.sleep(5)

    for _ in range(3):
        await page.scroll_down(2000)
        await asyncio.sleep(2)

    html = await page.get_content()
    users = re.findall(r'/user/([A-Za-z0-9_-]+)', html)

    seen = set()
    valid = []
    skip = {
        'automoderator', 'bot', 'ilovereddidotcom',
        'this_photo5976', 'working_golf72',
    }

    for u in users:
        ul = u.lower()
        if ul in seen or ul in skip:
            continue
        if has_been_dmed(u):
            continue
        if not can_engage_user(u):
            continue
        seen.add(ul)
        valid.append(u)
        if len(valid) >= count:
            break

    print(f"[FIND] Found {len(valid)} DM targets: {valid}")
    return valid


async def find_comment_targets(page, count=8):
    """Find post permalinks on r/test to comment on."""
    print(f"[FIND] Searching for {count} comment targets on r/test...")
    await page.get("https://www.reddit.com/r/test/new/")
    await asyncio.sleep(5)

    for _ in range(2):
        await page.scroll_down(1500)
        await asyncio.sleep(2)

    html = await page.get_content()
    # Match post permalinks (not comment permalinks)
    links = re.findall(r'(/r/test/comments/[A-Za-z0-9]+/[^/"\'>\s]*)', html)

    seen_posts = set()
    valid = []

    for link in links:
        post_id = extract_post_id(link)
        if not post_id or post_id in seen_posts:
            continue
        if not can_comment_in_thread(post_id):
            continue
        seen_posts.add(post_id)
        # Normalize: strip trailing segments after title
        parts = link.rstrip('/').split('/')
        # /r/test/comments/postid/title → keep as is
        if len(parts) >= 5:
            permalink = '/'.join(parts[:6]) + '/'
        else:
            permalink = link
        valid.append({"permalink": permalink, "post_id": post_id})
        if len(valid) >= count:
            break

    print(f"[FIND] Found {len(valid)} comment targets")
    for t in valid:
        print(f"  {t['permalink']} (post_id: {t['post_id']})")
    return valid


async def run_account_test(config, account, dm_targets, comment_targets, dry_run=False):
    """Run DM + comment test for one account. Returns results dict."""
    acct = account["username"]
    can_dm = account.get("can_dm", True)

    print(f"\n{'=' * 60}")
    print(f"TESTING ACCOUNT: {acct}")
    print(f"  can_dm: {can_dm}")
    print(f"  DM targets available: {len(dm_targets)}")
    print(f"  Comment targets available: {len(comment_targets)}")
    print(f"{'=' * 60}")

    browser, page = await login(config, account, headless=False)

    results = {"dms": [], "comments": []}
    dm_count = 0
    comment_count = 0

    try:
        # --- DMs ---
        if can_dm:
            for username in dm_targets:
                if dm_count >= DMS_PER_ACCOUNT:
                    break

                if not can_engage_user(username):
                    print(f"\n[{acct}] SKIP DM u/{username} — already engaged by another account")
                    results["dms"].append({"user": username, "result": "skipped_cross_account"})
                    continue

                print(f"\n[{acct}] DM {dm_count + 1}/{DMS_PER_ACCOUNT}: u/{username}")

                if dry_run:
                    print(f"  [DRY RUN] Would send 'bananas' to u/{username}")
                    log_user_engaged(username, acct, "dm")
                    log_dm(username, "bananas", True, account=acct)
                    results["dms"].append({"user": username, "result": "dry_run"})
                    dm_count += 1
                    continue

                result = await send_dm(page, username, "hey", "bananas", config)

                if result == DM_SUCCESS:
                    log_user_engaged(username, acct, "dm")
                    log_dm(username, "bananas", True, account=acct)
                    results["dms"].append({"user": username, "result": "success"})
                    dm_count += 1
                    print(f"[{acct}] DM SUCCESS ({dm_count}/{DMS_PER_ACCOUNT})")
                    if dm_count < DMS_PER_ACCOUNT:
                        print(f"[{acct}] Waiting {DM_WAIT_SECONDS // 60} min before next DM...")
                        await asyncio.sleep(DM_WAIT_SECONDS)
                elif result == DM_RATE_LIMITED:
                    log_dm(username, "bananas", False, account=acct)
                    results["dms"].append({"user": username, "result": "rate_limited"})
                    print(f"[{acct}] RATE LIMITED — stopping DMs")
                    break
                else:
                    log_dm(username, "bananas", False, account=acct)
                    results["dms"].append({"user": username, "result": "failed"})
                    print(f"[{acct}] DM FAILED to u/{username}")
        else:
            print(f"\n[{acct}] Skipping DMs (can_dm=false)")

        # --- Comments ---
        for target in comment_targets:
            if comment_count >= COMMENTS_PER_ACCOUNT:
                break

            permalink = target["permalink"]
            post_id = target["post_id"]

            if not can_comment_in_thread(post_id):
                print(f"\n[{acct}] SKIP thread {post_id} — already touched by another account")
                results["comments"].append({"permalink": permalink, "result": "skipped_cross_account"})
                continue

            print(f"\n[{acct}] Comment {comment_count + 1}/{COMMENTS_PER_ACCOUNT}: {permalink}")

            comment_text = f"test from {acct} - please ignore"

            if dry_run:
                print(f"  [DRY RUN] Would comment '{comment_text}' on {permalink}")
                log_user_engaged(acct, acct, "comment")  # no real user for top-level
                log_thread_touched(post_id, acct)
                log_comment(permalink, comment_text, True, account=acct)
                results["comments"].append({"permalink": permalink, "result": "dry_run"})
                comment_count += 1
                continue

            result = await post_comment(page, permalink, comment_text, config)

            if result == COMMENT_SUCCESS:
                log_thread_touched(post_id, acct)
                log_comment(permalink, comment_text, True, account=acct)
                results["comments"].append({"permalink": permalink, "result": "success"})
                comment_count += 1
                print(f"[{acct}] COMMENT SUCCESS ({comment_count}/{COMMENTS_PER_ACCOUNT})")
                if comment_count < COMMENTS_PER_ACCOUNT:
                    print(f"[{acct}] Waiting {COMMENT_WAIT_SECONDS // 60} min before next comment...")
                    await asyncio.sleep(COMMENT_WAIT_SECONDS)
            elif result == COMMENT_LOCKED:
                results["comments"].append({"permalink": permalink, "result": "locked"})
                print(f"[{acct}] Post locked, trying next")
            else:
                log_comment(permalink, comment_text, False, account=acct)
                results["comments"].append({"permalink": permalink, "result": "failed"})
                print(f"[{acct}] COMMENT FAILED on {permalink}")

    except KeyboardInterrupt:
        print(f"\n[{acct}] Interrupted")
        raise
    except Exception as e:
        print(f"\n[{acct}] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await browser.stop()
        except Exception:
            pass

    return results


def print_summary(all_results):
    """Print test results summary."""
    print(f"\n{'=' * 60}")
    print("TEST RESULTS")
    print(f"{'=' * 60}")

    for acct, results in all_results.items():
        print(f"\n  {acct}:")
        print(f"    DMs:")
        for dm in results["dms"]:
            print(f"      u/{dm['user']}: {dm['result']}")
        if not results["dms"]:
            print(f"      (none)")
        print(f"    Comments:")
        for c in results["comments"]:
            print(f"      {c['permalink']}: {c['result']}")
        if not results["comments"]:
            print(f"      (none)")

    # Cross-account verification
    print(f"\n{'─' * 40}")
    print("CROSS-ACCOUNT ISOLATION CHECK:")

    users_engaged = {}
    users_file = os.path.join(DATA_DIR, "users_engaged.json")
    if os.path.exists(users_file):
        with open(users_file) as f:
            users_engaged = json.load(f)

    threads_touched = {}
    threads_file = os.path.join(DATA_DIR, "threads_touched.json")
    if os.path.exists(threads_file):
        with open(threads_file) as f:
            threads_touched = json.load(f)

    # Check no user was engaged by multiple accounts
    user_accounts = {}
    for user, info in users_engaged.items():
        acct = info["account"]
        if user not in user_accounts:
            user_accounts[user] = set()
        user_accounts[user].add(acct)

    overlap_users = {u: accts for u, accts in user_accounts.items() if len(accts) > 1}
    if overlap_users:
        print(f"  FAIL: Users engaged by multiple accounts: {overlap_users}")
    else:
        print(f"  PASS: No user overlap ({len(users_engaged)} users, each touched by exactly 1 account)")

    # Check no thread was touched by multiple accounts
    thread_accounts = {}
    for tid, info in threads_touched.items():
        acct = info["account"]
        if tid not in thread_accounts:
            thread_accounts[tid] = set()
        thread_accounts[tid].add(acct)

    overlap_threads = {t: accts for t, accts in thread_accounts.items() if len(accts) > 1}
    if overlap_threads:
        print(f"  FAIL: Threads touched by multiple accounts: {overlap_threads}")
    else:
        print(f"  PASS: No thread overlap ({len(threads_touched)} threads, each touched by exactly 1 account)")

    print(f"{'=' * 60}")


async def run():
    dry_run = "--dry-run" in sys.argv
    reset = "--reset" in sys.argv

    config = load_config()

    # Get DM-capable accounts (need at least 2 for cross-account test)
    dm_accounts = [a for a in config["accounts"] if a.get("can_dm", True)]
    if len(dm_accounts) < 2:
        print("Need at least 2 DM-capable accounts for cross-account test")
        print(f"Found: {[a['username'] for a in dm_accounts]}")
        return

    test_accounts = dm_accounts[:2]

    print("=" * 60)
    print(f"MULTI-ACCOUNT INTEGRATION TEST {'[DRY RUN]' if dry_run else '[LIVE]'}")
    print(f"Accounts: {[a['username'] for a in test_accounts]}")
    print(f"Per account: {DMS_PER_ACCOUNT} DMs, {COMMENTS_PER_ACCOUNT} comments")
    print("=" * 60)

    if reset:
        print("\n[RESET] Clearing test tracking data...")
        for f in ["users_engaged.json", "threads_touched.json"]:
            path = os.path.join(DATA_DIR, f)
            with open(path, "w") as fh:
                json.dump({}, fh)
        print("[RESET] Done")

    # Phase 1: Find targets using the first account
    print(f"\n[SETUP] Finding targets (logging in as {test_accounts[0]['username']})...")
    browser, page = await login(config, test_accounts[0], headless=False)

    total_dm_targets_needed = DMS_PER_ACCOUNT * len(test_accounts) + 4  # extras for skips
    total_comment_targets_needed = COMMENTS_PER_ACCOUNT * len(test_accounts) + 4

    dm_targets = await find_dm_targets(page, count=total_dm_targets_needed)
    comment_targets = await find_comment_targets(page, count=total_comment_targets_needed)

    await browser.stop()
    await asyncio.sleep(2)

    if len(dm_targets) < DMS_PER_ACCOUNT * 2:
        print(f"[SETUP] Not enough DM targets ({len(dm_targets)}), need {DMS_PER_ACCOUNT * 2}")
        return
    if len(comment_targets) < COMMENTS_PER_ACCOUNT * 2:
        print(f"[SETUP] Not enough comment targets ({len(comment_targets)}), need {COMMENTS_PER_ACCOUNT * 2}")
        return

    # Phase 2: Run each account sequentially
    all_results = {}

    for account in test_accounts:
        try:
            results = await run_account_test(
                config, account, dm_targets, comment_targets, dry_run
            )
            all_results[account["username"]] = results
        except KeyboardInterrupt:
            print("\nInterrupted — stopping all accounts")
            break
        except Exception as e:
            print(f"\nAccount {account['username']} failed: {e}")
            all_results[account["username"]] = {"dms": [], "comments": []}

        # Brief pause between accounts
        await asyncio.sleep(5)

    # Phase 3: Summary + cross-account verification
    print_summary(all_results)


if __name__ == "__main__":
    asyncio.run(run())
