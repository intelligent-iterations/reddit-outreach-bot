"""
Unit tests for src/rate_limiter.py - rate limiting logic.

Tests cover:
- Daily limit checking
- Ramp schedule (days 1-3, 4-7, 8+)
- Account-level can_dm flag
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, date, timedelta

import src.state as state_module
from src.rate_limiter import RateLimiter
from src.models import ActionType


@pytest.fixture
def sample_config():
    """Sample config matching actual config.json structure."""
    return {
        "ramp_schedule": {
            "days_1_to_3": {"max_dms": 5, "max_comments": 10},
            "days_4_to_7": {"max_dms": 8, "max_comments": 15},
            "days_8_plus": {"max_dms": 10, "max_comments": 25}
        },
        "delays": {
            "between_dms_min_seconds": 720,
            "between_dms_max_seconds": 1080,
            "between_actions_min_seconds": 180,
            "between_actions_max_seconds": 480,
            "between_searches_min_seconds": 30,
            "between_searches_max_seconds": 90,
            "typing_delay_min_ms": 50,
            "typing_delay_max_ms": 150,
        }
    }


@pytest.fixture
def sample_account():
    """Sample account for testing."""
    return {
        "username": "TestAccount",
        "can_dm": True,
        "can_comment": True,
    }


@pytest.fixture
def temp_state_file():
    """Create a temporary state file for testing."""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)

    with open(path, 'w') as f:
        json.dump({
            "users": {},
            "threads": {},
            "leads": [],
            "logs": [],
            "meta": {"first_run_date": date.today().strftime("%Y-%m-%d")}
        }, f)

    original_path = state_module.STATE_FILE
    state_module.STATE_FILE = path

    yield path

    state_module.STATE_FILE = original_path
    if os.path.exists(path):
        os.unlink(path)


class TestRampSchedule:
    """Tests for ramp schedule calculations."""

    def test_day_1_limits(self, sample_config, sample_account, temp_state_file):
        """Day 1 should use days_1_to_3 limits."""
        limiter = RateLimiter(sample_config, sample_account)
        limits = limiter.get_todays_limits()

        assert limits["max_dms"] == 5
        assert limits["max_comments"] == 10

    def test_day_5_limits(self, sample_config, sample_account, temp_state_file):
        """Day 5 should use days_4_to_7 limits."""
        # Set first run to 4 days ago
        with open(temp_state_file, 'r') as f:
            state = json.load(f)
        state["meta"]["first_run_date"] = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
        with open(temp_state_file, 'w') as f:
            json.dump(state, f)

        limiter = RateLimiter(sample_config, sample_account)
        limits = limiter.get_todays_limits()

        assert limits["max_dms"] == 8
        assert limits["max_comments"] == 15

    def test_day_10_limits(self, sample_config, sample_account, temp_state_file):
        """Day 10+ should use days_8_plus limits."""
        # Set first run to 9 days ago
        with open(temp_state_file, 'r') as f:
            state = json.load(f)
        state["meta"]["first_run_date"] = (date.today() - timedelta(days=9)).strftime("%Y-%m-%d")
        with open(temp_state_file, 'w') as f:
            json.dump(state, f)

        limiter = RateLimiter(sample_config, sample_account)
        limits = limiter.get_todays_limits()

        assert limits["max_dms"] == 10
        assert limits["max_comments"] == 25


class TestCanDm:
    """Tests for can_dm() limit checking."""

    def test_can_dm_when_under_limit(self, sample_config, sample_account, temp_state_file):
        """Should be able to DM when under daily limit."""
        limiter = RateLimiter(sample_config, sample_account)
        assert limiter.can_dm() is True

    def test_cannot_dm_when_account_disabled(self, sample_config, temp_state_file):
        """Should not be able to DM when account has can_dm: false."""
        account = {"username": "NoDmAccount", "can_dm": False}
        limiter = RateLimiter(sample_config, account)
        assert limiter.can_dm() is False


class TestCanComment:
    """Tests for can_comment() limit checking."""

    def test_can_comment_when_under_limit(self, sample_config, sample_account, temp_state_file):
        """Should be able to comment when under daily limit."""
        limiter = RateLimiter(sample_config, sample_account)
        assert limiter.can_comment() is True

    def test_cannot_comment_when_account_disabled(self, sample_config, temp_state_file):
        """Should not be able to comment when account has can_comment: false."""
        account = {"username": "NoCommentAccount", "can_dm": True, "can_comment": False}
        limiter = RateLimiter(sample_config, account)
        assert limiter.can_comment() is False


class TestStopDms:
    """Tests for stop_dms() rate limit response."""

    def test_stop_dms_prevents_further_dms(self, sample_config, sample_account, temp_state_file):
        """After stop_dms(), can_dm should return False."""
        limiter = RateLimiter(sample_config, sample_account)
        assert limiter.can_dm() is True

        limiter.stop_dms()
        assert limiter.can_dm() is False


class TestStatus:
    """Tests for status() output."""

    def test_status_includes_account_name(self, sample_config, sample_account, temp_state_file):
        """Status should include account name."""
        limiter = RateLimiter(sample_config, sample_account)
        status = limiter.status()

        assert "TestAccount" in status

    def test_status_includes_counts(self, sample_config, sample_account, temp_state_file):
        """Status should include current counts."""
        limiter = RateLimiter(sample_config, sample_account)
        status = limiter.status()

        assert "DMs:" in status
        assert "Comments:" in status


class TestDelays:
    """Tests for delay methods."""

    def test_typing_delay_in_range(self, sample_config, sample_account, temp_state_file):
        """Typing delay should be within configured range."""
        limiter = RateLimiter(sample_config, sample_account)

        for _ in range(100):
            delay = limiter.get_typing_delay()
            # Config is in ms (50-150), function returns seconds (0.05-0.15)
            assert 0.05 <= delay <= 0.15


class TestDayNumber:
    """Tests for day number calculation."""

    def test_day_1_on_first_run(self, sample_config, sample_account, temp_state_file):
        """Day number should be 1 on first run date."""
        limiter = RateLimiter(sample_config, sample_account)
        assert limiter.get_day_number() == 1

    def test_day_increments(self, sample_config, sample_account, temp_state_file):
        """Day number should increment based on first run date."""
        with open(temp_state_file, 'r') as f:
            state = json.load(f)
        state["meta"]["first_run_date"] = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        with open(temp_state_file, 'w') as f:
            json.dump(state, f)

        limiter = RateLimiter(sample_config, sample_account)
        assert limiter.get_day_number() == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
