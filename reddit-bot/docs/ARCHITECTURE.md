# Architecture Documentation

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Parse Args  │→ │ Load Config │→ │ For each account:       │  │
│  └─────────────┘  └─────────────┘  │  - Login (auth.py)      │  │
│                                     │  - Search (search.py)   │  │
│                                     │  - Claim → Act → Record │  │
│                                     └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   auth.py     │    │  search.py    │    │  comment.py   │
│               │    │               │    │    dm.py      │
│ - Cookie load │    │ - HTML parse  │    │               │
│ - Fresh login │    │ - Lead extract│    │ - Find editor │
│ - Session mgmt│    │ - Age filter  │    │ - Type text   │
└───────────────┘    └───────────────┘    │ - Submit      │
                                          │ - Verify      │
                                          │ - Nuclear     │
                                          │   reset       │
                                          └───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   state.py    │    │  models.py    │    │rate_limiter.py│
│               │    │               │    │               │
│ - claim_user  │    │ - ActionType  │    │ - Day limits  │
│ - claim_thread│    │ - ActionResult│    │ - Ramp sched  │
│ - record_action│   │ - ClaimStatus │    │ - Delays      │
│ - get_stats   │    │ - Lead        │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## Data Flow

### 1. Startup
```
config.json ──────────────────┐
templates.json ───────────────┼──→ main.py
data/cookies_*.json ──────────┘
```

### 2. Per-Account Session
```
Login
  │
  ▼
Search Keywords ──→ Extract Leads ──→ Deduplicate
  │
  ▼
For each lead:
  │
  ├──→ claim_user(username, account)
  │         │
  │         ├── CLAIMED → proceed
  │         ├── ALREADY_CLAIMED → skip (other account owns)
  │         └── ALREADY_CONTACTED → skip (we already contacted)
  │
  ├──→ claim_thread(post_id, account)
  │         │
  │         └── (same logic)
  │
  ├──→ handle_comment() or handle_dm()
  │         │
  │         └── record_action()
  │
  └──→ Nuclear Tab Reset
            │
            ▼
      Rate Limit Wait
```

### 3. Atomic Claim-Before-Act Pattern
```
┌─────────────────────────────────────────────────────────┐
│  BEFORE (Race Condition)                                │
│                                                         │
│  Account A: check → act → write                         │
│  Account B: check → act → write  (overlaps!)            │
│                                                         │
│  Result: Both contact same user                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  AFTER (Atomic)                                         │
│                                                         │
│  Account A: claim_user() → CLAIMED → act → record       │
│  Account B: claim_user() → ALREADY_CLAIMED → skip       │
│                                                         │
│  Result: Only one account contacts user                 │
└─────────────────────────────────────────────────────────┘
```

---

## State File (state.json)

**Single source of truth** for all persistent state.

```json
{
  "users": {
    "johndoe": {
      "claimed_by": "another_user",
      "claimed_at": "2026-02-19T15:00:00",
      "actions": [
        {
          "type": "comment",
          "target": "/r/YukaApp/comments/...",
          "account": "another_user",
          "result": "success",
          "timestamp": "2026-02-19T15:00:00",
          "message_preview": "...",
          "error": null
        }
      ]
    }
  },
  "threads": {
    "abc123": {
      "claimed_by": "example_user",
      "claimed_at": "2026-02-19T14:00:00",
      "permalink": "/r/sub/comments/abc123/title/"
    }
  },
  "leads": [...],
  "logs": [...],
  "meta": {
    "first_run_date": "2026-02-14"
  }
}
```

---

## Enums (models.py)

### ActionType
```python
class ActionType(Enum):
    DM = "dm"
    COMMENT = "comment"
```

### ActionResult
```python
class ActionResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"       # e.g., existing conversation
    RATE_LIMITED = "rate_limited"
    LOCKED = "locked"         # thread locked
```

### ClaimStatus
```python
class ClaimStatus(Enum):
    CLAIMED = auto()           # Successfully claimed
    ALREADY_CLAIMED = auto()   # Another account owns this
    ALREADY_CONTACTED = auto() # We already contacted this user
```

### AccountMode (Future)
```python
class AccountMode(Enum):
    SCANNER_FOCUSED = "scanner_focused"  # Yuka-focused comments
    ORGANIC = "organic"                   # General ingredient advice
    MIXED = "mixed"                       # Both
```

---

## Rate Limiting System

### Ramp Schedule (from config.json)
| Days | Max DMs | Max Comments |
|------|---------|--------------|
| 1-3  | 5       | 10           |
| 4-7  | 8       | 15           |
| 8+   | 10      | 25           |

### Delays
| Action | Min | Max |
|--------|-----|-----|
| Between DMs | 12 min | 18 min |
| Between Comments | 3 min | 8 min |
| Between Searches | 30 sec | 90 sec |

### Day Calculation
```python
day_number = (today - first_run_date).days + 1
```

---

## Browser Automation

### zendriver (Chrome CDP)
- Based on undetected-chromedriver
- Uses Chrome DevTools Protocol
- Saves/loads cookies for session persistence

### Key Patterns

#### Element Finding
```python
# By text (fuzzy match)
element = await page.find("Reply", best_match=True, timeout=10)

# By CSS selector
element = await page.select("[contenteditable='true']", timeout=5)
```

#### Human-like Typing
```python
async def human_type(element, text, config):
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random_delay)
```

#### Nuclear Tab Reset
```python
# Only reliable way to clear Reddit's chat overlay
async def _nuclear_tab_reset(browser, old_page):
    new_page = await browser.get("https://www.reddit.com", new_tab=True)
    await old_page.close()
    return new_page
```

---

## Command Line Interface

```bash
# Normal run (all accounts)
python -m src.main

# Dry run (print actions without executing)
python -m src.main --dry-run

# Single account
python -m src.main --account another_user

# Override limits
python -m src.main --max-dms 5 --max-comments 10

# Override keywords
python -m src.main --keywords "yuka app" "ingredient scanner"

# View statistics
python -m src.main --stats

# Migrate from old format (one-time)
python -m src.main --migrate
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_state.py -v

# Run with coverage
pytest tests/ -v --cov=src
```
