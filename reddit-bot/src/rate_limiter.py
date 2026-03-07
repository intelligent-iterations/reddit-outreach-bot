"""
Rate limiting for Reddit outreach bot.

Handles:
- Daily action limits (DMs, comments)
- Ramp-up schedule for new accounts
- Delays between actions
- Long breaks to appear human
"""

import asyncio
import random
from datetime import date

from src.models import ActionType, AccountConfig
from src.state import get_first_run_date, get_todays_action_count


class RateLimiter:
    """
    Rate limiter for a single account session.

    Tracks limits, delays, and provides status information.
    """

    def __init__(self, config: dict, account: AccountConfig | dict):
        self.config = config
        self.delays = config["delays"]
        self.ramp = config.get("ramp_schedule", {})

        # Handle both AccountConfig and dict
        if isinstance(account, AccountConfig):
            self.account_username = account.username
            self.account_can_dm = account.can_dm
            self.account_can_comment = account.can_comment
        else:
            self.account_username = account["username"]
            self.account_can_dm = account.get("can_dm", True)
            self.account_can_comment = account.get("can_comment", True)

        # Session state
        self._action_count_since_long_pause = 0
        self.dms_stopped_for_session = False

    def get_day_number(self) -> int:
        """Get number of days since first run (1-indexed)."""
        first_run = get_first_run_date()
        return (date.today() - first_run).days + 1

    def get_todays_limits(self) -> dict:
        """Get limits for today based on ramp schedule."""
        day = self.get_day_number()

        if day <= 3:
            limits = self.ramp.get("days_1_to_3", {})
        elif day <= 7:
            limits = self.ramp.get("days_4_to_7", {})
        else:
            limits = self.ramp.get("days_8_plus", {})

        return {
            "max_dms": limits.get("max_dms", 10),
            "max_comments": limits.get("max_comments", 25),
        }

    def can_dm(self) -> bool:
        """Check if this account can still send DMs today."""
        if not self.account_can_dm:
            return False
        if self.dms_stopped_for_session:
            return False

        limits = self.get_todays_limits()
        current = get_todays_action_count(ActionType.DM, self.account_username)
        return current < limits["max_dms"]

    def can_comment(self) -> bool:
        """Check if this account can still post comments today."""
        if not self.account_can_comment:
            return False

        limits = self.get_todays_limits()
        current = get_todays_action_count(ActionType.COMMENT, self.account_username)
        return current < limits["max_comments"]

    def stop_dms(self):
        """Stop all DMs for the rest of this session (rate limit hit)."""
        self.dms_stopped_for_session = True
        print(f"[RATE] {self.account_username}: DMs stopped for remainder of session")

    def get_remaining_dms(self) -> int:
        """Get remaining DMs allowed today."""
        if not self.account_can_dm or self.dms_stopped_for_session:
            return 0
        limits = self.get_todays_limits()
        current = get_todays_action_count(ActionType.DM, self.account_username)
        return max(0, limits["max_dms"] - current)

    def get_remaining_comments(self) -> int:
        """Get remaining comments allowed today."""
        if not self.account_can_comment:
            return 0
        limits = self.get_todays_limits()
        current = get_todays_action_count(ActionType.COMMENT, self.account_username)
        return max(0, limits["max_comments"] - current)

    async def wait_between_dms(self) -> float:
        """Wait 12-18 minutes between DMs."""
        min_s = self.delays.get("between_dms_min_seconds", 720)
        max_s = self.delays.get("between_dms_max_seconds", 1080)
        delay = random.uniform(min_s, max_s)
        print(f"[RATE] Waiting {delay / 60:.1f} minutes between DMs")
        await asyncio.sleep(delay)
        return delay

    async def wait_between_actions(self) -> float:
        """Wait between major actions (comments)."""
        self._action_count_since_long_pause += 1

        # Every 5-7 actions, take a longer break
        if self._action_count_since_long_pause >= random.randint(5, 7):
            long_pause = random.uniform(15 * 60, 20 * 60)
            print(f"[RATE] Taking a long break: {long_pause / 60:.1f} minutes")
            await asyncio.sleep(long_pause)
            self._action_count_since_long_pause = 0
            return long_pause

        min_s = self.delays["between_actions_min_seconds"]
        max_s = self.delays["between_actions_max_seconds"]
        delay = random.uniform(min_s, max_s)
        print(f"[RATE] Waiting {delay:.0f}s between actions")
        await asyncio.sleep(delay)
        return delay

    async def wait_between_searches(self) -> float:
        """Wait between search page loads."""
        min_s = self.delays["between_searches_min_seconds"]
        max_s = self.delays["between_searches_max_seconds"]
        delay = random.uniform(min_s, max_s)
        print(f"[RATE] Waiting {delay:.0f}s between searches")
        await asyncio.sleep(delay)
        return delay

    async def wait_after_click(self):
        """Short wait after clicking a button."""
        min_s = self.delays.get("click_delay_min_seconds", 1)
        max_s = self.delays.get("click_delay_max_seconds", 3)
        await asyncio.sleep(random.uniform(min_s, max_s))

    def get_typing_delay(self) -> float:
        """Get a random typing delay in seconds."""
        min_ms = self.delays["typing_delay_min_ms"]
        max_ms = self.delays["typing_delay_max_ms"]
        return random.uniform(min_ms / 1000, max_ms / 1000)

    def status(self) -> str:
        """Return a status summary string."""
        day = self.get_day_number()
        limits = self.get_todays_limits()

        dm_count = get_todays_action_count(ActionType.DM, self.account_username)
        comment_count = get_todays_action_count(ActionType.COMMENT, self.account_username)

        dm_status = f"DMs: {dm_count}/{limits['max_dms']}"
        if not self.account_can_dm:
            dm_status += " (disabled)"
        elif self.dms_stopped_for_session:
            dm_status += " (stopped)"

        comment_status = f"Comments: {comment_count}/{limits['max_comments']}"
        if not self.account_can_comment:
            comment_status += " (disabled)"

        return f"{self.account_username} (day {day}) | {dm_status} | {comment_status}"
