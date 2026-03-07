"""
Unit tests for src/models.py - enums and data classes.
"""

import pytest
from src.models import (
    ActionType,
    ActionResult,
    AccountMode,
    ClaimStatus,
    Lead,
)


class TestActionType:
    """Tests for ActionType enum."""

    def test_dm_value(self):
        assert ActionType.DM.value == "dm"

    def test_comment_value(self):
        assert ActionType.COMMENT.value == "comment"

    def test_all_values(self):
        """All enum values should be unique strings."""
        values = [e.value for e in ActionType]
        assert len(values) == len(set(values))


class TestActionResult:
    """Tests for ActionResult enum."""

    def test_success_value(self):
        assert ActionResult.SUCCESS.value == "success"

    def test_failed_value(self):
        assert ActionResult.FAILED.value == "failed"

    def test_skipped_value(self):
        assert ActionResult.SKIPPED.value == "skipped"

    def test_rate_limited_value(self):
        assert ActionResult.RATE_LIMITED.value == "rate_limited"

    def test_locked_value(self):
        assert ActionResult.LOCKED.value == "locked"


class TestAccountMode:
    """Tests for AccountMode enum."""

    def test_scanner_focused_value(self):
        assert AccountMode.SCANNER_FOCUSED.value == "scanner_focused"

    def test_organic_value(self):
        assert AccountMode.ORGANIC.value == "organic"

    def test_mixed_value(self):
        assert AccountMode.MIXED.value == "mixed"


class TestClaimStatus:
    """Tests for ClaimStatus enum."""

    def test_claimed_exists(self):
        assert ClaimStatus.CLAIMED is not None

    def test_already_claimed_exists(self):
        assert ClaimStatus.ALREADY_CLAIMED is not None

    def test_already_contacted_exists(self):
        assert ClaimStatus.ALREADY_CONTACTED is not None

    def test_all_statuses_distinct(self):
        """All claim statuses should be distinct."""
        statuses = list(ClaimStatus)
        assert len(statuses) == 3


class TestLead:
    """Tests for Lead dataclass."""

    def test_from_dict_basic(self):
        """Should create Lead from dictionary."""
        data = {
            "username": "testuser",
            "comment_text": "Test comment",
            "subreddit": "TestSub",
            "permalink": "/r/TestSub/comments/123/title/",
        }
        lead = Lead.from_dict(data)

        assert lead.username == "testuser"
        assert lead.comment_text == "Test comment"
        assert lead.subreddit == "TestSub"
        assert lead.permalink == "/r/TestSub/comments/123/title/"

    def test_from_dict_with_optional_fields(self):
        """Should handle optional fields."""
        data = {
            "username": "testuser",
            "comment_text": "Test comment",
            "subreddit": "TestSub",
            "permalink": "/r/TestSub/comments/123/title/",
            "post_title": "Test Post",
            "keyword_matched": "yuka",
        }
        lead = Lead.from_dict(data)

        assert lead.post_title == "Test Post"
        assert lead.keyword_matched == "yuka"

    def test_from_dict_missing_optional_fields(self):
        """Should use defaults for missing optional fields."""
        data = {
            "username": "testuser",
            "comment_text": "Test comment",
            "subreddit": "TestSub",
            "permalink": "/r/TestSub/comments/123/title/",
        }
        lead = Lead.from_dict(data)

        assert lead.post_title == ""
        assert lead.keyword_matched == ""

    def test_to_dict(self):
        """Should convert Lead back to dictionary."""
        lead = Lead(
            username="testuser",
            comment_text="Test comment",
            subreddit="TestSub",
            permalink="/r/TestSub/comments/123/title/",
            post_title="Test Post",
            keyword_matched="yuka",
        )
        data = lead.to_dict()

        assert data["username"] == "testuser"
        assert data["comment_text"] == "Test comment"
        assert data["subreddit"] == "TestSub"
        assert data["permalink"] == "/r/TestSub/comments/123/title/"
        assert data["post_title"] == "Test Post"
        assert data["keyword_matched"] == "yuka"

    def test_post_id_extraction(self):
        """Should extract post_id from permalink."""
        lead = Lead(
            username="testuser",
            permalink="/r/TestSub/comments/abc123/title/",
            subreddit="TestSub",
        )
        assert lead.post_id == "abc123"

    def test_post_id_none_for_invalid_permalink(self):
        """Should return None for invalid permalink."""
        lead = Lead(
            username="testuser",
            permalink="/invalid/path/",
            subreddit="TestSub",
        )
        assert lead.post_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
