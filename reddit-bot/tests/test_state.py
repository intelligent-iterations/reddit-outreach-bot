"""
Unit tests for src/state.py - the single source of truth for state management.

Tests cover:
- Atomic user claiming (CLAIMED, ALREADY_CLAIMED, ALREADY_CONTACTED)
- Thread claiming
- Action recording
- Statistics
"""

import json
import os
import tempfile
import pytest
from datetime import datetime
from unittest.mock import patch

# We'll patch the STATE_FILE path to use a temp file
import src.state as state_module
from src.state import (
    claim_user,
    claim_thread,
    can_engage_user,
    can_comment_in_thread,
    record_action,
    get_stats,
    get_todays_action_count,
)
from src.models import ActionType, ActionResult, ClaimStatus


@pytest.fixture
def temp_state_file():
    """Create a temporary state file for testing."""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)

    # Initialize with empty state
    with open(path, 'w') as f:
        json.dump({
            "users": {},
            "threads": {},
            "leads": [],
            "logs": [],
            "meta": {"first_run_date": datetime.now().strftime("%Y-%m-%d")}
        }, f)

    # Patch the STATE_FILE constant
    original_path = state_module.STATE_FILE
    state_module.STATE_FILE = path

    yield path

    # Cleanup
    state_module.STATE_FILE = original_path
    if os.path.exists(path):
        os.unlink(path)


class TestClaimUser:
    """Tests for claim_user() atomic claiming logic."""

    def test_claim_new_user_returns_claimed(self, temp_state_file):
        """First claim on a new user should return CLAIMED."""
        result = claim_user("newuser", "Account_A")
        assert result == ClaimStatus.CLAIMED

    def test_claim_same_user_same_account_returns_already_contacted(self, temp_state_file):
        """Same account claiming same user again should return ALREADY_CONTACTED."""
        claim_user("testuser", "Account_A")
        result = claim_user("testuser", "Account_A")
        assert result == ClaimStatus.ALREADY_CONTACTED

    def test_claim_same_user_different_account_returns_already_claimed(self, temp_state_file):
        """Different account trying to claim same user should return ALREADY_CLAIMED."""
        claim_user("testuser", "Account_A")
        result = claim_user("testuser", "Account_B")
        assert result == ClaimStatus.ALREADY_CLAIMED

    def test_claim_is_case_insensitive(self, temp_state_file):
        """Username claims should be case-insensitive."""
        claim_user("TestUser", "Account_A")
        result = claim_user("testuser", "Account_B")
        assert result == ClaimStatus.ALREADY_CLAIMED

    def test_claim_persists_to_file(self, temp_state_file):
        """Claimed users should be persisted to the state file."""
        claim_user("persistuser", "Account_A")

        with open(temp_state_file, 'r') as f:
            state = json.load(f)

        assert "persistuser" in state["users"]
        assert state["users"]["persistuser"]["claimed_by"] == "Account_A"


class TestClaimThread:
    """Tests for claim_thread() thread isolation logic."""

    def test_claim_new_thread_returns_true(self, temp_state_file):
        """First claim on a new thread should return True."""
        result = claim_thread("post123", "Account_A", "/r/test/comments/post123/title/")
        assert result is True

    def test_claim_same_thread_same_account_returns_true(self, temp_state_file):
        """Same account claiming same thread should return True."""
        claim_thread("post123", "Account_A", "/r/test/comments/post123/title/")
        result = claim_thread("post123", "Account_A", "/r/test/comments/post123/title/")
        assert result is True

    def test_claim_same_thread_different_account_returns_false(self, temp_state_file):
        """Different account trying to claim same thread should return False."""
        claim_thread("post123", "Account_A", "/r/test/comments/post123/title/")
        result = claim_thread("post123", "Account_B", "/r/test/comments/post123/title/")
        assert result is False

    def test_claim_empty_post_id_returns_true(self, temp_state_file):
        """Empty post_id should return True (no thread to claim)."""
        result = claim_thread("", "Account_A", "")
        assert result is True


class TestCanEngage:
    """Tests for can_engage_user() and can_comment_in_thread() checks."""

    def test_can_engage_unclaimed_user(self, temp_state_file):
        """Should be able to engage a user that hasn't been claimed."""
        assert can_engage_user("newuser") is True

    def test_cannot_engage_claimed_user(self, temp_state_file):
        """Should not be able to engage a user that has been claimed."""
        claim_user("claimeduser", "Account_A")
        assert can_engage_user("claimeduser") is False

    def test_can_comment_in_unclaimed_thread(self, temp_state_file):
        """Should be able to comment in a thread that hasn't been claimed."""
        assert can_comment_in_thread("newthread") is True

    def test_cannot_comment_in_claimed_thread(self, temp_state_file):
        """Should not be able to comment in a thread that has been claimed."""
        claim_thread("claimedthread", "Account_A", "/r/test/comments/claimedthread/")
        assert can_comment_in_thread("claimedthread") is False


class TestRecordAction:
    """Tests for record_action() logging."""

    def test_record_action_adds_to_user(self, temp_state_file):
        """Recording an action should add it to the user's action list."""
        claim_user("actionuser", "Account_A")
        record_action(
            username="actionuser",
            account="Account_A",
            action_type=ActionType.DM,
            result=ActionResult.SUCCESS,
            target="actionuser",
            message_preview="Hello!",
        )

        with open(temp_state_file, 'r') as f:
            state = json.load(f)

        user = state["users"]["actionuser"]
        assert len(user["actions"]) == 1
        assert user["actions"][0]["type"] == "dm"
        assert user["actions"][0]["result"] == "success"

    def test_record_action_creates_user_if_not_exists(self, temp_state_file):
        """Recording an action for non-existent user should create the user."""
        record_action(
            username="newactionuser",
            account="Account_A",
            action_type=ActionType.COMMENT,
            result=ActionResult.SUCCESS,
            target="/r/test/comments/123/",
            message_preview="Nice post!",
        )

        with open(temp_state_file, 'r') as f:
            state = json.load(f)

        assert "newactionuser" in state["users"]


class TestGetStats:
    """Tests for get_stats() statistics."""

    def test_get_stats_empty_state(self, temp_state_file):
        """Stats on empty state should return zeros."""
        stats = get_stats()
        assert stats["today"]["dms_success"] == 0
        assert stats["today"]["dms_failed"] == 0
        assert stats["today"]["comments_success"] == 0
        assert stats["today"]["comments_failed"] == 0

    def test_get_stats_counts_actions(self, temp_state_file):
        """Stats should correctly count actions."""
        claim_user("user1", "Account_A")
        record_action(
            username="user1",
            account="Account_A",
            action_type=ActionType.DM,
            result=ActionResult.SUCCESS,
            target="user1",
        )

        claim_user("user2", "Account_A")
        record_action(
            username="user2",
            account="Account_A",
            action_type=ActionType.DM,
            result=ActionResult.FAILED,
            target="user2",
        )

        stats = get_stats()
        assert stats["all_time"]["dms_success"] == 1
        assert stats["all_time"]["dms_failed"] == 1


class TestGetTodaysActionCount:
    """Tests for get_todays_action_count() rate limiting support."""

    def test_count_starts_at_zero(self, temp_state_file):
        """Count should start at zero for fresh state."""
        # Note: signature is (action_type, account)
        count = get_todays_action_count(ActionType.DM, "Account_A")
        assert count == 0

    def test_count_increments_after_action(self, temp_state_file):
        """Count should increment after recording an action."""
        claim_user("user1", "Account_A")
        record_action(
            username="user1",
            account="Account_A",
            action_type=ActionType.DM,
            result=ActionResult.SUCCESS,
            target="user1",
        )

        # Note: signature is (action_type, account)
        count = get_todays_action_count(ActionType.DM, "Account_A")
        assert count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
