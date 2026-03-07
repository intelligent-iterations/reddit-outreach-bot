"""
Data models and enums for the Reddit outreach bot.

This module defines the core types used throughout the application,
providing a single source of truth for action types, results, and account modes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class ActionType(Enum):
    """Types of outreach actions."""
    DM = "dm"
    COMMENT = "comment"


class ActionResult(Enum):
    """Possible outcomes of an outreach action."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"          # Already contacted or existing conversation
    RATE_LIMITED = "rate_limited"
    LOCKED = "locked"            # Thread locked (comments only)


class AccountMode(Enum):
    """
    Account operating modes for future expansion.

    SCANNER_FOCUSED: Responds to Yuka/scanner app mentions
    ORGANIC: General ingredient education, no app comparisons
    MIXED: Combination of both approaches
    """
    SCANNER_FOCUSED = "scanner_focused"
    ORGANIC = "organic"
    MIXED = "mixed"


class ClaimStatus(Enum):
    """Result of attempting to claim a user."""
    CLAIMED = auto()             # Successfully claimed
    ALREADY_CLAIMED = auto()     # Another account already has this user
    ALREADY_CONTACTED = auto()   # This account already contacted this user


@dataclass
class Action:
    """Record of a single outreach action."""
    action_type: ActionType
    target: str                  # Username for DM, permalink for comment
    account: str
    result: ActionResult
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message_preview: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.action_type.value,
            "target": self.target,
            "account": self.account,
            "result": self.result.value,
            "timestamp": self.timestamp,
            "message_preview": self.message_preview[:100],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        return cls(
            action_type=ActionType(data["type"]),
            target=data["target"],
            account=data["account"],
            result=ActionResult(data["result"]),
            timestamp=data.get("timestamp", ""),
            message_preview=data.get("message_preview", ""),
            error=data.get("error"),
        )


@dataclass
class UserRecord:
    """
    Record of engagement with a single user.

    This is the source of truth for whether we can contact a user.
    Once claimed by an account, no other account should contact them.
    """
    username: str
    claimed_by: str              # Account that owns this user
    claimed_at: str
    actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "actions": [a.to_dict() for a in self.actions],
        }

    @classmethod
    def from_dict(cls, username: str, data: dict) -> "UserRecord":
        return cls(
            username=username,
            claimed_by=data["claimed_by"],
            claimed_at=data["claimed_at"],
            actions=[Action.from_dict(a) for a in data.get("actions", [])],
        )

    def has_successful_action(self, action_type: ActionType) -> bool:
        """Check if user has received a successful action of given type."""
        return any(
            a.action_type == action_type and a.result == ActionResult.SUCCESS
            for a in self.actions
        )


@dataclass
class ThreadRecord:
    """Record of engagement with a Reddit thread."""
    post_id: str
    claimed_by: str
    claimed_at: str
    permalink: str = ""

    def to_dict(self) -> dict:
        return {
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "permalink": self.permalink,
        }

    @classmethod
    def from_dict(cls, post_id: str, data: dict) -> "ThreadRecord":
        return cls(
            post_id=post_id,
            claimed_by=data["claimed_by"],
            claimed_at=data["claimed_at"],
            permalink=data.get("permalink", ""),
        )


@dataclass
class Lead:
    """A potential outreach target found during search."""
    username: str
    permalink: str
    subreddit: str
    comment_text: str = ""
    post_title: str = ""
    keyword_matched: str = ""
    post_age: str = ""
    found_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "comment_search"

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "permalink": self.permalink,
            "subreddit": self.subreddit,
            "comment_text": self.comment_text,
            "post_title": self.post_title,
            "keyword_matched": self.keyword_matched,
            "post_age": self.post_age,
            "found_at": self.found_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        return cls(
            username=data.get("username", ""),
            permalink=data.get("permalink", ""),
            subreddit=data.get("subreddit", ""),
            comment_text=data.get("comment_text", ""),
            post_title=data.get("post_title", ""),
            keyword_matched=data.get("keyword_matched", ""),
            post_age=data.get("post_age", ""),
            found_at=data.get("found_at", ""),
            source=data.get("source", "comment_search"),
        )

    @property
    def post_id(self) -> Optional[str]:
        """Extract post ID from permalink."""
        parts = self.permalink.split('/comments/')
        if len(parts) > 1:
            return parts[1].split('/')[0]
        return None


@dataclass
class AccountConfig:
    """Configuration for a single account."""
    username: str
    password: str
    cookies_path: str
    can_dm: bool = True
    can_comment: bool = True
    mode: AccountMode = AccountMode.MIXED

    @classmethod
    def from_dict(cls, data: dict) -> "AccountConfig":
        mode_str = data.get("mode", "mixed")
        try:
            mode = AccountMode(mode_str)
        except ValueError:
            mode = AccountMode.MIXED

        return cls(
            username=data["username"],
            password=data["password"],
            cookies_path=data.get("cookies_path", f"data/cookies_{data['username']}.json"),
            can_dm=data.get("can_dm", True),
            can_comment=data.get("can_comment", True),
            mode=mode,
        )


class StrategyType(Enum):
    """Types of acquisition strategies."""
    SCANNER_APP = "scanner_app"
    CONTROVERSIAL_INGREDIENT = "controversial_ingredient"


@dataclass
class TriageDecision:
    """Grok's decision for a single lead."""
    lead_index: int
    username: str
    permalink: str
    action_type: str           # "dm" or "comment"
    template_name: str         # e.g. "scanner_mention"
    template_variation: int    # index into the template list
    placeholders: dict = field(default_factory=dict)
    reasoning: str = ""
    custom_message: str = ""   # Grok's customized version of the template

    @classmethod
    def from_dict(cls, data: dict) -> "TriageDecision":
        return cls(
            lead_index=data["lead_index"],
            username=data.get("username", ""),
            permalink=data.get("permalink", ""),
            action_type=data["action_type"],
            template_name=data["template_name"],
            template_variation=data.get("template_variation", 0),
            placeholders=data.get("placeholders", {}),
            reasoning=data.get("reasoning", ""),
            custom_message=data.get("custom_message", ""),
        )

    def to_dict(self) -> dict:
        return {
            "lead_index": self.lead_index,
            "username": self.username,
            "permalink": self.permalink,
            "action_type": self.action_type,
            "template_name": self.template_name,
            "template_variation": self.template_variation,
            "placeholders": self.placeholders,
            "reasoning": self.reasoning,
            "custom_message": self.custom_message,
        }


@dataclass
class DiscoveryResult:
    """Full discovery result from Grok."""
    input_leads: list[dict] = field(default_factory=list)
    relevant_leads: list[dict] = field(default_factory=list)
    relevant_decisions: list[dict] = field(default_factory=list)  # With reasons
    not_relevant_decisions: list[dict] = field(default_factory=list)  # With reasons
    system_prompt: str = ""
    user_prompt: str = ""
    raw_response: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "input_count": len(self.input_leads),
            "input_leads": self.input_leads,
            "relevant_count": len(self.relevant_leads),
            "relevant_leads": self.relevant_leads,
            "relevant_decisions": self.relevant_decisions,
            "not_relevant_decisions": self.not_relevant_decisions,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "raw_response": self.raw_response,
            "model": self.model,
            "usage": self.usage,
        }


@dataclass
class TriageResult:
    """Full triage result from Grok."""
    approved: list[TriageDecision] = field(default_factory=list)
    denied: list[dict] = field(default_factory=list)
    raw_response: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    leads: list[dict] = field(default_factory=list)  # The candidates array used for indexing
    system_prompt: str = ""  # Added for logging
    user_prompt: str = ""  # Added for logging
    discovery_result: DiscoveryResult | None = None  # Include discovery data

    def to_dict(self) -> dict:
        result = {
            "approved": [d.to_dict() for d in self.approved],
            "denied": self.denied,
            "raw_response": self.raw_response,
            "model": self.model,
            "usage": self.usage,
            "approved_count": len(self.approved),
            "denied_count": len(self.denied),
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
        }
        if self.discovery_result:
            result["discovery"] = self.discovery_result.to_dict()
        return result
