# Code Review & Architecture Audit

## Executive Summary

This codebase is a Reddit outreach bot that searches for leads, posts comments, and sends DMs. After the February 2026 refactoring, the code now follows best practices around **single source of truth**, **type safety**, and **atomic operations**.

---

## Architecture Overview

```
reddit-bot/
├── config.json          # Account credentials, delays, keywords
├── templates.json       # DM and comment message templates
├── src/
│   ├── main.py          # Entry point, orchestrates everything
│   ├── models.py        # Enums and dataclasses (NEW)
│   ├── state.py         # Single source of truth (NEW)
│   ├── auth.py          # Login/cookie handling
│   ├── search.py        # Reddit search scraping
│   ├── comment.py       # Comment posting
│   ├── dm.py            # DM sending
│   ├── templates.py     # Template selection/filling
│   ├── rate_limiter.py  # Rate limiting logic
│   └── utils.py         # Shared utilities
├── data/
│   ├── state.json       # Single state file
│   └── *.png            # Error screenshots
├── tests/               # Unit tests
└── docs/                # Documentation
```

---

## Issues Status

### ✅ FIXED: No Single Source of Truth for Tracking

**Was**: User engagement tracked in MULTIPLE places (4 JSON files + memory)

**Now**: Single `state.json` with atomic operations via `src/state.py`

```python
# src/state.py provides atomic operations
claim_user(username, account) -> ClaimStatus
claim_thread(post_id, account, permalink) -> ClaimStatus
record_action(username, account, action_type, result, ...)
get_stats() -> dict
```

---

### ✅ FIXED: Duplicate Code in main.py

**Was**: Comment posting logic duplicated in Phase 1 and Phase 2

**Now**: Extracted to helper functions

```python
async def handle_comment(browser, page, lead, account_name, config, templates, dry_run):
    """Handle comment logic for a single lead. Returns (new_page, success)."""

async def handle_dm(browser, page, lead, account_name, config, templates, dry_run):
    """Handle DM logic for a single lead. Returns (new_page, result)."""
```

---

### ✅ FIXED: No Type Hints / Type Safety

**Was**: String literals scattered throughout

**Now**: Proper enums in `src/models.py`

```python
class ActionType(Enum):
    DM = "dm"
    COMMENT = "comment"

class ActionResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RATE_LIMITED = "rate_limited"
    LOCKED = "locked"

class ClaimStatus(Enum):
    CLAIMED = auto()
    ALREADY_CLAIMED = auto()
    ALREADY_CONTACTED = auto()
```

---

### ✅ FIXED: Race Condition in Cross-Account Isolation

**Was**: Check-then-act pattern with no locking

**Now**: Atomic claim-or-fail with file locking

```python
@_with_lock
def claim_user(username: str, account: str) -> ClaimStatus:
    """Atomically claim a user. File lock prevents race conditions."""
    state = _read_state()
    if username_lower in state["users"]:
        if existing["claimed_by"] == account:
            return ClaimStatus.ALREADY_CONTACTED
        return ClaimStatus.ALREADY_CLAIMED
    # Claim the user
    state["users"][username_lower] = {...}
    _write_state(state)
    return ClaimStatus.CLAIMED
```

---

## Remaining Minor Issues

### 1. Hardcoded Values (Low Priority)

Some magic numbers still scattered:
- `timeout=5`, `timeout=10` in various places
- Sleep durations in dm.py, comment.py

**Recommendation**: Move to config.json when time permits.

### 2. JavaScript in Python (Low Priority)

`page.evaluate()` JS strings embedded in Python code.

**Recommendation**: Could extract to separate .js files, but current approach works.

### 3. No Logging Framework (Low Priority)

All output is `print()` statements.

**Recommendation**: Consider `logging` module for structured logs.

---

## Positive Aspects

- ✅ Clear function naming and docstrings
- ✅ Nuclear tab reset is a pragmatic solution to Reddit's overlay issues
- ✅ Rate limiting is well-structured with ramp schedule
- ✅ Template system with archetype detection is flexible
- ✅ File locking prevents concurrent access issues
- ✅ **NEW**: Single source of truth in state.json
- ✅ **NEW**: Type-safe enums for actions and results
- ✅ **NEW**: Atomic claim-before-act pattern
- ✅ **NEW**: Unit tests for critical logic

---

## Test Coverage

```bash
# Run all tests
pytest tests/ -v

# Key test files
tests/test_state.py      # Atomic claim logic
tests/test_models.py     # Enum values
tests/test_main.py       # Deduplication
tests/test_rate_limiter.py  # Rate limiting
```

---

## Summary

The main improvements implemented:

| Area | Before | After |
|------|--------|-------|
| State management | 4 JSON files | Single `state.json` |
| User claiming | Check-then-act | Atomic claim-before-act |
| Type safety | String literals | Enums |
| Code reuse | Duplicated blocks | Helper functions |
| Testing | Manual | Unit tests |
