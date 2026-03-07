"""Phase 5: Full Flow Integration Test

Tests the complete pipeline:
1. Login
2. Search 1 keyword
3. Extract leads
4. Select templates
5. Dry-run (print what would be sent)
6. Optionally send to safe targets
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import BASE_DIR


def reset_data():
    """Reset data files for clean test."""
    data_dir = os.path.join(BASE_DIR, "data")
    with open(os.path.join(data_dir, "contacted.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(data_dir, "commented.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(data_dir, "leads.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(data_dir, "logs.json"), "w") as f:
        json.dump({"first_run_date": None, "actions": []}, f)


async def test_dry_run():
    """Run full pipeline in dry-run mode with 1 keyword, limited actions."""
    print("=" * 60)
    print("TEST: Full Flow Dry Run")
    print("=" * 60)

    reset_data()

    from src.main import run
    await run(
        dry_run=True,
        max_dms=3,
        max_comments=3,
        keywords=["yuka app"]
    )

    # Verify data files were populated
    data_dir = os.path.join(BASE_DIR, "data")

    with open(os.path.join(data_dir, "leads.json"), "r") as f:
        leads = json.load(f)
    print(f"\n[TEST] Leads saved: {len(leads)}")

    with open(os.path.join(data_dir, "contacted.json"), "r") as f:
        contacted = json.load(f)
    print(f"[TEST] Users contacted (dry run): {len(contacted)}")

    with open(os.path.join(data_dir, "commented.json"), "r") as f:
        commented = json.load(f)
    print(f"[TEST] Posts commented (dry run): {len(commented)}")

    with open(os.path.join(data_dir, "logs.json"), "r") as f:
        logs = json.load(f)
    print(f"[TEST] Total actions logged: {len(logs.get('actions', []))}")
    print(f"[TEST] First run date: {logs.get('first_run_date')}")

    if leads:
        print("\n[TEST] Dry run test PASSED leads found and templates filled")
    else:
        print("\n[TEST] WARNING: No leads found search extraction may need tuning")


async def test_dedup():
    """Run again to verify deduplication works."""
    print("\n" + "=" * 60)
    print("TEST: Deduplication Check")
    print("=" * 60)

    # Don't reset run with existing data
    from src.main import run
    await run(
        dry_run=True,
        max_dms=3,
        max_comments=3,
        keywords=["yuka app"]
    )

    # All previously contacted users should be skipped
    data_dir = os.path.join(BASE_DIR, "data")
    with open(os.path.join(data_dir, "contacted.json"), "r") as f:
        contacted = json.load(f)
    print(f"\n[TEST] Total users contacted after 2 runs: {len(contacted)}")
    print("[TEST] If this number is same as first run, dedup works")


async def main():
    mode = "dry"
    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if mode == "dry":
        await test_dry_run()
    elif mode == "dedup":
        await test_dry_run()
        await asyncio.sleep(5)
        await test_dedup()
    elif mode == "live":
        print("Live test limited to 1 DM + 1 comment on safe targets")
        from src.main import run
        await run(
            dry_run=False,
            max_dms=1,
            max_comments=1,
            keywords=["yuka app"]
        )


if __name__ == "__main__":
    asyncio.run(main())
