"""Phase 3 (reordered): Tracker unit tests.

Tests all CRUD operations and deduplication.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")


def reset_data_files():
    """Reset all data files to empty state for testing."""
    with open(os.path.join(DATA_DIR, "contacted.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(DATA_DIR, "commented.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(DATA_DIR, "leads.json"), "w") as f:
        json.dump([], f)
    with open(os.path.join(DATA_DIR, "logs.json"), "w") as f:
        json.dump({"first_run_date": None, "actions": []}, f)


def test_dm_tracking():
    print("TEST: DM tracking...")
    from src.tracker import has_been_dmed, log_dm

    assert not has_been_dmed("testuser1"), "Should not have been DMed yet"

    log_dm("testuser1", "Hello testuser1, this is a test message", True)
    assert has_been_dmed("testuser1"), "Should now be marked as DMed"
    assert not has_been_dmed("testuser2"), "testuser2 should not be DMed"

    # Verify JSON persistence
    with open(os.path.join(DATA_DIR, "contacted.json"), "r") as f:
        contacted = json.load(f)
    assert len(contacted) == 1
    assert contacted[0]["username"] == "testuser1"
    assert contacted[0]["success"] is True

    print("  PASSED")


def test_comment_tracking():
    print("TEST: Comment tracking...")
    from src.tracker import has_been_commented, log_comment

    permalink = "/r/test/comments/abc123/test_post/"
    assert not has_been_commented(permalink), "Should not have been commented yet"

    log_comment(permalink, "This is a test comment", True)
    assert has_been_commented(permalink), "Should now be marked as commented"
    assert not has_been_commented("/r/other/comments/xyz/"), "Other permalink should not be commented"

    print("  PASSED")


def test_lead_saving():
    print("TEST: Lead saving + dedup...")
    from src.tracker import save_lead

    lead = {
        "username": "leaduser1",
        "comment_text": "I love yuka app",
        "subreddit": "YukaApp",
        "permalink": "/r/YukaApp/comments/abc/post/comment1",
        "keyword_matched": "yuka app",
        "found_at": "2025-01-01T00:00:00"
    }

    save_lead(lead)
    save_lead(lead)  # Duplicate should not add again

    with open(os.path.join(DATA_DIR, "leads.json"), "r") as f:
        leads = json.load(f)
    assert len(leads) == 1, f"Expected 1 lead, got {len(leads)}"

    # Different lead
    lead2 = {**lead, "username": "leaduser2", "permalink": "/r/YukaApp/comments/def/post/comment2"}
    save_lead(lead2)

    with open(os.path.join(DATA_DIR, "leads.json"), "r") as f:
        leads = json.load(f)
    assert len(leads) == 2, f"Expected 2 leads, got {len(leads)}"

    print("  PASSED")


def test_action_counts():
    print("TEST: Action counts...")
    from src.tracker import get_todays_action_count, log_dm, log_comment

    dm_count = get_todays_action_count("dm")
    # We logged 1 DM earlier in test_dm_tracking
    assert dm_count == 1, f"Expected 1 DM today, got {dm_count}"

    comment_count = get_todays_action_count("comment")
    assert comment_count == 1, f"Expected 1 comment today, got {comment_count}"

    # Log more actions
    log_dm("testuser3", "Another DM", True)
    log_dm("testuser4", "Failed DM", False)

    dm_count = get_todays_action_count("dm")
    assert dm_count == 2, f"Expected 2 successful DMs, got {dm_count}"

    print("  PASSED")


def test_first_run_date():
    print("TEST: First run date...")
    from src.tracker import get_first_run_date
    from datetime import date

    first = get_first_run_date()
    assert first == date.today(), f"First run date should be today, got {first}"

    # Calling again should return same date
    second = get_first_run_date()
    assert first == second, "First run date should not change"

    print("  PASSED")


def main():
    print("=" * 60)
    print("Tracker Tests")
    print("=" * 60)

    reset_data_files()

    test_dm_tracking()
    test_comment_tracking()
    test_lead_saving()
    test_action_counts()
    test_first_run_date()

    print("\n" + "=" * 60)
    print("ALL TRACKER TESTS PASSED")
    print("=" * 60)

    # Reset data files after testing
    reset_data_files()


if __name__ == "__main__":
    main()
