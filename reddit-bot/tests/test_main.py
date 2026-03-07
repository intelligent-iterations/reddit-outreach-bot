"""
Unit tests for src/main.py helper functions.
"""

import pytest
from src.main import deduplicate_leads


class TestDeduplicateLeads:
    """Tests for deduplicate_leads() function."""

    def test_empty_list(self):
        """Empty list should return empty list."""
        result = deduplicate_leads([])
        assert result == []

    def test_no_duplicates(self):
        """List with no duplicates should be unchanged."""
        leads = [
            {"username": "user1", "comment": "test1"},
            {"username": "user2", "comment": "test2"},
            {"username": "user3", "comment": "test3"},
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 3

    def test_removes_duplicates(self):
        """Should remove duplicate usernames, keeping first occurrence."""
        leads = [
            {"username": "user1", "comment": "first"},
            {"username": "user2", "comment": "unique"},
            {"username": "user1", "comment": "duplicate"},
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 2
        assert result[0]["comment"] == "first"  # First occurrence kept

    def test_case_insensitive(self):
        """Should treat usernames as case-insensitive."""
        leads = [
            {"username": "User1", "comment": "first"},
            {"username": "user1", "comment": "duplicate"},
            {"username": "USER1", "comment": "also duplicate"},
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 1
        assert result[0]["username"] == "User1"  # Original case preserved

    def test_preserves_order(self):
        """Should preserve order of first occurrences."""
        leads = [
            {"username": "alice", "order": 1},
            {"username": "bob", "order": 2},
            {"username": "alice", "order": 3},
            {"username": "charlie", "order": 4},
            {"username": "bob", "order": 5},
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 3
        assert result[0]["username"] == "alice"
        assert result[1]["username"] == "bob"
        assert result[2]["username"] == "charlie"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
