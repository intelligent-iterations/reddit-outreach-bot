import json
import os
import fcntl
from datetime import datetime, date

from src.utils import BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")


_DICT_FILES = {"logs.json", "users_engaged.json", "threads_touched.json"}
_DICT_DEFAULTS = {
    "logs.json": lambda: {"first_run_date": None, "actions": []},
    "users_engaged.json": dict,
    "threads_touched.json": dict,
}


def _read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        if filename in _DICT_DEFAULTS:
            return _DICT_DEFAULTS[filename]()
        return []
    with open(path, "r") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            data = json.load(f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return data


def _write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def has_been_dmed(username):
    """Check if user has been DMed (any attempt, not just successful).

    This prevents duplicate DMs when verification fails but DM was actually sent.
    """
    contacted = _read_json("contacted.json")
    username_lower = username.lower()
    return any(
        entry["username"].lower() == username_lower
        for entry in contacted
    )


def has_been_commented(permalink):
    """Check if we've attempted to comment on this permalink (any attempt).

    This prevents duplicate comments when verification fails but comment was posted.
    """
    commented = _read_json("commented.json")
    return any(
        entry["permalink"] == permalink
        for entry in commented
    )


def log_dm(username, message, success, account=None):
    # Add to contacted list
    contacted = _read_json("contacted.json")
    contacted.append({
        "username": username,
        "message_preview": message[:100],
        "success": success,
        "account": account,
        "timestamp": datetime.now().isoformat()
    })
    _write_json("contacted.json", contacted)

    # Add to action log
    _log_action("dm", username, message, success, account)


def log_comment(permalink, message, success, account=None):
    # Add to commented list
    commented = _read_json("commented.json")
    commented.append({
        "permalink": permalink,
        "message_preview": message[:100],
        "success": success,
        "account": account,
        "timestamp": datetime.now().isoformat()
    })
    _write_json("commented.json", commented)

    # Add to action log
    _log_action("comment", permalink, message, success, account)


def save_lead(lead):
    leads = _read_json("leads.json")
    # Dedup by username + permalink
    for existing in leads:
        if existing.get("username") == lead.get("username") and existing.get("permalink") == lead.get("permalink"):
            return  # Already saved
    leads.append(lead)
    _write_json("leads.json", leads)


def get_todays_action_count(action_type, account=None):
    """Count actions of a given type for today, optionally filtered by account."""
    logs = _read_json("logs.json")
    today = date.today().isoformat()
    count = 0
    for action in logs.get("actions", []):
        if action.get("type") == action_type and action.get("timestamp", "").startswith(today):
            if action.get("success", False):
                if account is None or action.get("account") == account:
                    count += 1
    return count


def get_first_run_date():
    """Get date of first bot run, or set it if not yet set."""
    logs = _read_json("logs.json")
    if logs.get("first_run_date"):
        return date.fromisoformat(logs["first_run_date"])

    # First run set it now
    today = date.today()
    logs["first_run_date"] = today.isoformat()
    _write_json("logs.json", logs)
    return today


def get_total_action_count():
    """Get total number of successful actions ever."""
    logs = _read_json("logs.json")
    return sum(1 for a in logs.get("actions", []) if a.get("success", False))


def _log_action(action_type, target, message, success, account=None):
    logs = _read_json("logs.json")

    # Ensure first_run_date is set
    if not logs.get("first_run_date"):
        logs["first_run_date"] = date.today().isoformat()

    logs.setdefault("actions", []).append({
        "type": action_type,
        "target": target,
        "message_preview": message[:100],
        "success": success,
        "account": account,
        "timestamp": datetime.now().isoformat()
    })
    _write_json("logs.json", logs)


# --- Cross-Account Isolation ---

def extract_post_id(permalink):
    """Extract the post ID from a Reddit permalink.

    /r/YukaApp/comments/abc123/post_title/def456/ → abc123
    """
    parts = permalink.split('/comments/')
    if len(parts) > 1:
        return parts[1].split('/')[0]
    return None


def can_engage_user(username):
    """Check if ANY account has already interacted with this user."""
    engaged = _read_json("users_engaged.json")
    return username.lower() not in engaged


def can_comment_in_thread(post_id):
    """Check if ANY account has already commented in this thread."""
    if not post_id:
        return True
    threads = _read_json("threads_touched.json")
    return post_id not in threads


def log_user_engaged(username, account, action):
    """Record that an account interacted with a user. One user = one account forever."""
    engaged = _read_json("users_engaged.json")
    engaged[username.lower()] = {
        "account": account,
        "action": action,
        "timestamp": datetime.now().isoformat()
    }
    _write_json("users_engaged.json", engaged)


def log_thread_touched(post_id, account):
    """Record that an account commented in a thread. One thread = one account."""
    if not post_id:
        return
    threads = _read_json("threads_touched.json")
    threads[post_id] = {
        "account": account,
        "timestamp": datetime.now().isoformat()
    }
    _write_json("threads_touched.json", threads)
