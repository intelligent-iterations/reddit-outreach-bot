# Reddit Bot - Known Issues & Status

## Current Status (Feb 2026)

### Working ✓
- **Comment posting**: Uses `element.send_keys()` via `human_type()` after finding `[contenteditable='true']` element
- **Cookie-based login**: Working for all accounts
- **Cross-account isolation**: Single `state.json` with atomic claim-before-act pattern ✓ REFACTORED
- **Thread isolation**: Atomic thread claiming prevents multiple accounts in same thread ✓ REFACTORED
- **Nuclear tab reset**: After every DM/comment, kills tab and creates fresh one
- **Ramp scheduling**: Days 1-3, 4-7, 8+ have different limits
- **Single source of truth**: All state in `data/state.json` ✓ NEW

### Partially Working
- **DM sending**: Works mechanically but has account restrictions
  - `This_Photo5976`: "Unable to invite" error (account too new)
  - `ilovereddidotcom`: Works but hits rate limits quickly

### Known Issues

#### 1. "Unable to invite the selected invitee(s)" Error
- **Account**: This_Photo5976
- **Cause**: Account too new / low karma for chat invites
- **Workaround**: Account has `can_dm: false` in config, comment-only mode

#### 2. DM Rate Limits
- **Account**: ilovereddidotcom
- **Trigger**: After 3-5 DMs in a session
- **Current mitigation**: 12-18 minute delays, 5-10 DM daily cap
- **Detection**: Checks for "sent a lot of invites" / "take a break" text

#### 3. Error Detection Limitations
- Reddit's toast errors appear in overlay DOM, sometimes missed by text parsing
- **Mitigation**: Full DOM tree walker + alert/toast element queries
- **Fallback**: Screenshots saved after every action for manual review

---

## Data Files

| File | Purpose | Format |
|------|---------|--------|
| `state.json` | **Single source of truth** for all state | See below |

### state.json Structure
```json
{
  "users": {
    "username": {
      "claimed_by": "account_name",
      "claimed_at": "ISO timestamp",
      "actions": [...]
    }
  },
  "threads": {
    "post_id": {
      "claimed_by": "account_name",
      "claimed_at": "ISO timestamp",
      "permalink": "..."
    }
  },
  "leads": [...],
  "logs": [...],
  "meta": {
    "first_run_date": "YYYY-MM-DD"
  }
}
```

### Legacy Files (No longer used)
- ~~`users_engaged.json`~~ → Migrated to `state.json`
- ~~`threads_touched.json`~~ → Migrated to `state.json`
- ~~`contacted.json`~~ → Migrated to `state.json`
- ~~`commented.json`~~ → Migrated to `state.json`
- ~~`logs.json`~~ → Migrated to `state.json`

---

## Code Locations

| Feature | File | Function |
|---------|------|----------|
| Main loop | `src/main.py` | `run_account_session()` |
| Comment posting | `src/comment.py` | `post_comment()` |
| DM sending | `src/dm.py` | `send_dm()` |
| **State management** | `src/state.py` | `claim_user()`, `claim_thread()`, `record_action()` |
| **Enums/Models** | `src/models.py` | `ActionType`, `ActionResult`, `ClaimStatus` |
| Rate limiting | `src/rate_limiter.py` | `RateLimiter` class |
| Template selection | `src/templates.py` | `select_and_fill()` |
| Search/scraping | `src/search.py` | `search_comments()` |
| Authentication | `src/auth.py` | `login()` |

---

## CLI Commands

```bash
# Normal run
python -m src.main

# Dry run
python -m src.main --dry-run

# Single account
python -m src.main --account This_Photo5976

# View stats
python -m src.main --stats

# Migrate from old format (one-time)
python -m src.main --migrate
```

---

## Testing Checklist

### Before Running Live
- [ ] Verify account cookies are fresh (`data/cookies_*.json`)
- [ ] Check daily limits: `python -m src.main --stats`
- [ ] Run tests: `pytest tests/ -v`

### After Running
- [ ] Check screenshot files in `data/` for errors
- [ ] Verify comments actually posted on Reddit
- [ ] Review stats: `python -m src.main --stats`
