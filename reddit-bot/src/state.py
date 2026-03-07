"""
Centralized state management for the Reddit outreach bot.

This module provides a SINGLE SOURCE OF TRUTH for all tracking data.
All user engagement, thread tracking, and action logging goes through here.

Key principles:
1. Atomic operations - claim before act, not after
2. Single file - state.json contains everything
3. File locking - prevents race conditions
4. Immutable history - actions are appended, never deleted
"""

import fcntl
import json
import os
from datetime import date, datetime
from typing import Optional

from src.models import (
    Action, ActionResult, ActionType, ClaimStatus,
    Lead, ThreadRecord, UserRecord
)

# Base directory for all data files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
LOCK_FILE = os.path.join(DATA_DIR, "state.lock")


def _ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_empty_state() -> dict:
    """Return empty state structure."""
    return {
        "meta": {
            "first_run_date": date.today().isoformat(),
            "version": 2,
        },
        "users": {},      # username -> UserRecord
        "threads": {},    # post_id -> ThreadRecord
        "leads": [],      # List of discovered leads
    }


def _read_state() -> dict:
    """Read state from file with shared lock."""
    _ensure_data_dir()

    if not os.path.exists(STATE_FILE):
        return _get_empty_state()

    with open(STATE_FILE, "r") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            data = json.load(f)
            # Migration: ensure all required keys exist
            if "meta" not in data:
                data["meta"] = {"first_run_date": date.today().isoformat(), "version": 2}
            if "users" not in data:
                data["users"] = {}
            if "threads" not in data:
                data["threads"] = {}
            if "leads" not in data:
                data["leads"] = []
            return data
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _write_state(data: dict):
    """Write state to file with exclusive lock."""
    _ensure_data_dir()

    with open(STATE_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _with_lock(func):
    """Decorator for atomic read-modify-write operations."""
    def wrapper(*args, **kwargs):
        _ensure_data_dir()

        # Use a separate lock file for atomic operations
        with open(LOCK_FILE, "w") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                return func(*args, **kwargs)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)

    return wrapper


# =============================================================================
# USER MANAGEMENT
# =============================================================================

def get_user(username: str) -> Optional[UserRecord]:
    """Get user record if exists."""
    state = _read_state()
    user_data = state["users"].get(username.lower())
    if user_data:
        return UserRecord.from_dict(username.lower(), user_data)
    return None


def can_engage_user(username: str) -> bool:
    """
    Check if ANY account can engage this user.

    Returns False if user has already been claimed by any account.
    """
    user = get_user(username)
    return user is None


def can_engage_user_for_account(username: str, account: str) -> bool:
    """
    Check if a specific account can engage this user.

    Returns True if:
    - User has never been contacted, OR
    - User was claimed by this same account (for retries)
    """
    user = get_user(username)
    if user is None:
        return True
    return user.claimed_by == account


@_with_lock
def claim_user(username: str, account: str) -> ClaimStatus:
    """
    Atomically claim a user for an account.

    This MUST be called BEFORE attempting any action.
    Returns ClaimStatus indicating whether claim succeeded.
    """
    state = _read_state()
    username_lower = username.lower()

    if username_lower in state["users"]:
        existing = state["users"][username_lower]
        if existing["claimed_by"] == account:
            return ClaimStatus.ALREADY_CONTACTED
        return ClaimStatus.ALREADY_CLAIMED

    # Claim the user
    state["users"][username_lower] = {
        "claimed_by": account,
        "claimed_at": datetime.now().isoformat(),
        "actions": [],
    }
    _write_state(state)
    return ClaimStatus.CLAIMED


@_with_lock
def record_action(
    username: str,
    account: str,
    action_type: ActionType,
    result: ActionResult,
    target: str,
    message_preview: str = "",
    error: Optional[str] = None,
):
    """
    Record an action taken on a user.

    This should be called AFTER the action completes (success or failure).
    The user should already be claimed via claim_user().
    """
    state = _read_state()
    username_lower = username.lower()

    # Ensure user record exists (should have been claimed first)
    if username_lower not in state["users"]:
        state["users"][username_lower] = {
            "claimed_by": account,
            "claimed_at": datetime.now().isoformat(),
            "actions": [],
        }

    action = Action(
        action_type=action_type,
        target=target,
        account=account,
        result=result,
        message_preview=message_preview,
        error=error,
    )
    state["users"][username_lower]["actions"].append(action.to_dict())
    _write_state(state)


def has_been_contacted(username: str, action_type: Optional[ActionType] = None) -> bool:
    """
    Check if user has been contacted (any attempt, success or failure).

    If action_type is specified, checks for that specific type only.
    """
    user = get_user(username)
    if user is None:
        return False

    if action_type is None:
        return len(user.actions) > 0

    return any(a.action_type == action_type for a in user.actions)


def has_successful_contact(username: str, action_type: ActionType) -> bool:
    """Check if user has received a SUCCESSFUL action of given type."""
    user = get_user(username)
    if user is None:
        return False
    return user.has_successful_action(action_type)


# =============================================================================
# THREAD MANAGEMENT
# =============================================================================

def get_thread(post_id: str) -> Optional[ThreadRecord]:
    """Get thread record if exists."""
    state = _read_state()
    thread_data = state["threads"].get(post_id)
    if thread_data:
        return ThreadRecord.from_dict(post_id, thread_data)
    return None


def can_comment_in_thread(post_id: str) -> bool:
    """Check if ANY account can comment in this thread."""
    if not post_id:
        return True
    return get_thread(post_id) is None


@_with_lock
def claim_thread(post_id: str, account: str, permalink: str = "") -> bool:
    """
    Atomically claim a thread for an account.

    Returns True if claimed, False if already claimed by another account.
    """
    if not post_id:
        return True

    state = _read_state()

    if post_id in state["threads"]:
        return state["threads"][post_id]["claimed_by"] == account

    state["threads"][post_id] = {
        "claimed_by": account,
        "claimed_at": datetime.now().isoformat(),
        "permalink": permalink,
    }
    _write_state(state)
    return True


# =============================================================================
# LEADS MANAGEMENT
# =============================================================================

@_with_lock
def save_lead(lead: Lead):
    """Save a discovered lead (deduped by username + permalink)."""
    state = _read_state()

    # Check for duplicate
    for existing in state["leads"]:
        if (existing.get("username") == lead.username and
            existing.get("permalink") == lead.permalink):
            return

    state["leads"].append(lead.to_dict())
    _write_state(state)


def get_leads() -> list[Lead]:
    """Get all saved leads."""
    state = _read_state()
    return [Lead.from_dict(l) for l in state["leads"]]


# =============================================================================
# STATISTICS
# =============================================================================

def get_first_run_date() -> date:
    """Get date of first bot run."""
    state = _read_state()
    date_str = state["meta"].get("first_run_date")
    if date_str:
        return date.fromisoformat(date_str)
    return date.today()


def get_todays_action_count(action_type: ActionType, account: str) -> int:
    """Count successful actions of given type for today."""
    state = _read_state()
    today = date.today().isoformat()
    count = 0

    for user_data in state["users"].values():
        for action in user_data.get("actions", []):
            if (action.get("type") == action_type.value and
                action.get("account") == account and
                action.get("result") == ActionResult.SUCCESS.value and
                action.get("timestamp", "").startswith(today)):
                count += 1

    return count


def get_stats(account: Optional[str] = None) -> dict:
    """Get statistics summary."""
    state = _read_state()
    today = date.today().isoformat()

    stats = {
        "total_users": len(state["users"]),
        "total_threads": len(state["threads"]),
        "total_leads": len(state["leads"]),
        "today": {
            "dms_success": 0,
            "dms_failed": 0,
            "comments_success": 0,
            "comments_failed": 0,
        },
        "all_time": {
            "dms_success": 0,
            "dms_failed": 0,
            "comments_success": 0,
            "comments_failed": 0,
        },
    }

    for user_data in state["users"].values():
        for action in user_data.get("actions", []):
            if account and action.get("account") != account:
                continue

            is_today = action.get("timestamp", "").startswith(today)
            is_success = action.get("result") == ActionResult.SUCCESS.value
            action_type = action.get("type")

            if action_type == ActionType.DM.value:
                key = "dms_success" if is_success else "dms_failed"
            elif action_type == ActionType.COMMENT.value:
                key = "comments_success" if is_success else "comments_failed"
            else:
                continue

            stats["all_time"][key] += 1
            if is_today:
                stats["today"][key] += 1

    return stats


# =============================================================================
# MIGRATION & UTILITIES
# =============================================================================

@_with_lock
def migrate_from_old_format():
    """
    Migrate from old multi-file format to new single state.json.

    Reads from:
    - users_engaged.json
    - threads_touched.json
    - contacted.json
    - commented.json
    - logs.json

    And consolidates into state.json.
    """
    state = _get_empty_state()

    # Migrate users_engaged.json
    users_file = os.path.join(DATA_DIR, "users_engaged.json")
    if os.path.exists(users_file):
        with open(users_file) as f:
            old_users = json.load(f)
        for username, data in old_users.items():
            state["users"][username.lower()] = {
                "claimed_by": data.get("account", "unknown"),
                "claimed_at": data.get("timestamp", datetime.now().isoformat()),
                "actions": [{
                    "type": data.get("action", "dm"),
                    "target": username,
                    "account": data.get("account", "unknown"),
                    "result": "success",
                    "timestamp": data.get("timestamp", ""),
                    "message_preview": "",
                    "error": None,
                }],
            }
        print(f"[MIGRATE] Imported {len(old_users)} users from users_engaged.json")

    # Migrate threads_touched.json
    threads_file = os.path.join(DATA_DIR, "threads_touched.json")
    if os.path.exists(threads_file):
        with open(threads_file) as f:
            old_threads = json.load(f)
        for post_id, data in old_threads.items():
            state["threads"][post_id] = {
                "claimed_by": data.get("account", "unknown"),
                "claimed_at": data.get("timestamp", datetime.now().isoformat()),
                "permalink": "",
            }
        print(f"[MIGRATE] Imported {len(old_threads)} threads from threads_touched.json")

    # Get first_run_date from logs.json
    logs_file = os.path.join(DATA_DIR, "logs.json")
    if os.path.exists(logs_file):
        with open(logs_file) as f:
            old_logs = json.load(f)
        if old_logs.get("first_run_date"):
            state["meta"]["first_run_date"] = old_logs["first_run_date"]
        print(f"[MIGRATE] Imported first_run_date: {state['meta']['first_run_date']}")

    _write_state(state)
    print(f"[MIGRATE] Migration complete. State saved to {STATE_FILE}")


@_with_lock
def clear_state(archive: bool = True):
    """
    Clear all state.

    If archive=True, saves current state to archive folder first.
    """
    if archive:
        archive_dir = os.path.join(DATA_DIR, "archive")
        os.makedirs(archive_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = os.path.join(archive_dir, f"state_{timestamp}.json")

        if os.path.exists(STATE_FILE):
            state = _read_state()
            with open(archive_file, "w") as f:
                json.dump(state, f, indent=2)
            print(f"[STATE] Archived to {archive_file}")

    _write_state(_get_empty_state())
    print("[STATE] State cleared")


def print_state_summary():
    """Print a summary of current state."""
    stats = get_stats()
    print("\n=== STATE SUMMARY ===")
    print(f"Users tracked: {stats['total_users']}")
    print(f"Threads tracked: {stats['total_threads']}")
    print(f"Leads saved: {stats['total_leads']}")
    print(f"\nToday:")
    print(f"  DMs: {stats['today']['dms_success']} success, {stats['today']['dms_failed']} failed")
    print(f"  Comments: {stats['today']['comments_success']} success, {stats['today']['comments_failed']} failed")
    print(f"\nAll time:")
    print(f"  DMs: {stats['all_time']['dms_success']} success, {stats['all_time']['dms_failed']} failed")
    print(f"  Comments: {stats['all_time']['comments_success']} success, {stats['all_time']['comments_failed']} failed")
