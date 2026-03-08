# Architecture Documentation

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Parse Args  │→ │ Load Config │→ │ For each account:       │  │
│  └─────────────┘  └─────────────┘  │  - Login (auth.py)      │  │
│                                     │  - For each strategy:   │  │
│                                     │    - Scrape all keywords│  │
│                                     │    - Grok 4 triage      │  │
│                                     │    - Execute approved   │  │
│                                     └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
┌────────────┐┌────────────┐┌────────────┐┌────────────┐┌────────────┐
│  auth.py   ││ search.py  ││ triage.py  ││ comment.py ││run_logger  │
│            ││            ││            ││   dm.py    ││   .py      │
│- Cookie    ││- HTML parse││- V2 workflow││           ││            │
│  load      ││- Lead      ││- Discovery ││- Pre-reply ││- Per-run   │
│- Fresh     ││  extract   ││- Context   ││  verify   ││  folders   │
│  login     ││- Keyword   ││  enrich    ││- Find     ││- Raw leads │
│- Session   ││  confirm   ││- Build     ││  editor   ││- Triage    │
│  mgmt      ││- Age filter││  prompt    ││- Type text││  results   │
└────────────┘└────────────┘└────────────┘│- Nuclear  ││- Actions   │
                                          │  reset    ││            │
                    │                     └────────────┘└────────────┘
                    │
                    ▼
            ┌──────────────┐
            │ reddit_api.py│
            │              │
            │- PRAW wrapper│
            │- Get context │
            │- Verify leads│
            │- Enrich batch│
            └──────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   state.py    │    │ templates.py  │    │rate_limiter.py│
│               │    │               │    │               │
│ - Atomic      │    │ - Archetype   │    │ - Day limits  │
│   claims      │    │   detection   │    │ - Ramp sched  │
│ - Action logs │    │ - Placeholder │    │ - Delays      │
│ - File lock   │    │   filling     │    │ - Status      │
│               │    │ - Grok fill   │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## Data Flow

### 1. Startup
```
config.json ──────────────────┐
templates.json ───────────────┼──→ main.py
data/cookies_*.json ──────────┤
.env (XAI_API_KEY) ───────────┘
```

### 2. Per-Account Session (with V2 Grok triage)
```
For each strategy (scanner_app, controversial_ingredient, ...):
  │
  ▼
PHASE 1: SCRAPE
  Search all keywords ──→ Extract leads ──→ Deduplicate ──→ Split by keyword
  │                                                              │
  │                                          ┌───────────────────┴───────────────────┐
  │                                          ▼                                       ▼
  │                                    CONFIRMED leads                          MAYBE leads
  │                                    (keyword found in                        (keyword in thread
  │                                     comment text)                            but not in comment)
  ▼
PHASE 2: DISCOVERY (for MAYBE leads)
  Maybe leads ──→ Grok Discovery Prompt ──→ Parse response
  │                                              │
  │                               ┌──────────────┴──────────────┐
  │                               ▼                             ▼
  │                         Relevant leads                 Not relevant
  │                         (added to candidates)          (discarded)
  ▼
PHASE 3: CONTEXT ENRICHMENT (via PRAW)
  All candidates ──→ Reddit API (PRAW) ──→ Enriched leads
  │                                            │
  │                                  Added for each lead:
  │                                  - parent_comment (text + author)
  │                                  - thread_title
  │                                  - is_locked/archived
  │                                  - verified flag
  ▼
PHASE 4: TRIAGE (context-aware)
  Enriched leads + V2 prompt ──→ Grok 4 API ──→ Parse response
  │                                              │
  │                               ┌──────────────┴──────────────┐
  │                               ▼                             ▼
  │                         Approved leads                 Denied leads
  │                         - archetype (question,         (with reason)
  │                           observation, frustration,
  │                           seeking_advice, sharing_exp)
  │                         - template + placeholders
  │                         - context_check reasoning
  ▼
PHASE 5: EXECUTE
  For each approved lead:
  │
  ├──→ Claim user (atomic) ──→ Fill template from Grok's decision
  │                                    │
  │                         ┌──────────┴──────────┐
  │                         ▼                     ▼
  │                   Post Comment            Send DM
  │                         │                     │
  │                   PRE-REPLY VERIFY            │
  │                   (check keyword +            │
  │                    author in target)          │
  │                         │                     │
  │                         ▼                     ▼
  │                   Log to state.py       Log to state.py
  │                         │                     │
  │                         ▼                     ▼
  │                   Rate Limit Wait       Nuclear Tab Reset
  │                                         + Rate Limit Wait
  ▼
  Log action to run-data/
```

### 3. Cross-Account Isolation
```
Account A starts ──→ Engages user "john" ──→ Writes to state.json
                                                        │
                                                        ▼
Account B starts ──→ Finds user "john" ──→ Checks state.json ──→ SKIP
```

---

## Strategy System

Strategies define different acquisition campaigns. Each has its own keywords, templates, allowed actions, and Grok prompt.

### Configuration (config.json)
```json
{
  "strategies": {
    "scanner_app": {
      "enabled": true,
      "keywords": ["yuka app", "ewg app", ...],
      "allowed_actions": ["dm", "comment"],
      "templates_key": "scanner_app",
      "prompt_file": "prompts/scanner_app.txt"
    },
    "controversial_ingredient": {
      "enabled": true,
      "keywords": ["propylene glycol", "red 40", ...],
      "allowed_actions": ["comment"],
      "templates_key": "controversial_ingredient",
      "prompt_file": "prompts/controversial_ingredient.txt"
    }
  }
}
```

### Adding a New Strategy
1. Add entry to `config.json` under `strategies`
2. Create a prompt file in `prompts/` (e.g. `prompts/new_strategy.txt`)
3. Add templates under a new key in `templates.json`
4. Optionally add the enum value to `StrategyType` in `models.py`

### Templates (templates.json)
Templates are nested under strategy keys:
```json
{
  "scanner_app": {
    "dm_templates": { ... },
    "comment_templates": { ... },
    "dm_subjects": { ... }
  },
  "controversial_ingredient": {
    "comment_templates": { ... }
  }
}
```

---

## Grok 4 Triage System (V2)

### Overview
The V2 triage system adds context awareness to prevent wrong-target replies and template mismatches:

1. **Hybrid Lead Generation**: Splits leads into "confirmed" (keyword in comment) and "maybe" (keyword in thread only)
2. **Discovery Phase**: Grok reviews "maybe" leads to find genuinely relevant ones
3. **Context Enrichment**: PRAW fetches parent comment + thread title before triage
4. **Archetype Matching**: Ensures templates match user intent (question vs statement)
5. **Pre-Reply Verification**: Browser verifies target comment before posting

### Workflow Phases

#### Phase 1: Lead Splitting
```python
confirmed, maybe = split_leads_by_keyword_confirmation(leads)
# confirmed: keyword found in comment_text
# maybe: keyword was in thread but not confirmed in this comment
```

#### Phase 2: Discovery (prompts/discovery.txt)
Grok reviews "maybe" leads and identifies which are still relevant:
- User discussing ingredient safety without exact keyword
- Replying to someone who mentioned the keyword
- Tangentially related but good opportunity

#### Phase 3: Context Enrichment (reddit_api.py)
PRAW fetches full context for each lead:
```python
{
  "parent_comment": "That Yuka app is so confusing...",
  "parent_author": "other_user",
  "thread_title": "Best ingredient scanning apps?",
  "is_locked": false,
  "context_verified": true
}
```

#### Phase 4: V2 Triage (prompts/triage_v2.txt)
Context-aware prompt with archetypes:
- **question**: User asking a question → "Great question about..."
- **observation**: User making a statement → "Yeah {ingredient} is one of those..."
- **frustration**: User frustrated → "I dealt with something similar..."
- **seeking_advice**: User wants recommendations → "Have you tried..."
- **sharing_experience**: User sharing experience → "I had a similar experience..."

#### Phase 5: Pre-Reply Verification
Before posting, browser JS verifies:
1. Target comment contains expected keyword
2. Target comment author matches expected username
3. Fails gracefully if mismatch (skips instead of wrong reply)

### Prompt Structure
```
System prompt = prompts/base_system.txt + prompts/triage_v2.txt

User prompt includes:
  ## PRODUCT INFO
  - "the pom app" is the main product (ingredient scanning app)
  - data.thepom.app is supplementary search engine
  - NEVER mention other websites/apps

  ## Available Templates (by archetype)
  ...

  ## Leads to Triage (with full context)
  [
    {
      "index": 0,
      "username": "healthy_mom",
      "target_comment": "I've been worried about carrageenan...",
      "parent_comment": "What ingredients do you avoid?",
      "thread_title": "Checking food additives",
      "keyword_matched": "carrageenan"
    }
  ]
```

### Response Format (JSON)
```json
{
  "approved": [
    {
      "lead_index": 0,
      "username": "healthy_mom",
      "permalink": "/r/Costco/comments/abc123/title/xyz789/",
      "action_type": "comment",
      "archetype": "observation",
      "template_name": "ingredient_question",
      "template_variation": 2,
      "placeholders": {
        "username": "healthy",
        "subreddit": "Costco",
        "ingredient": "carrageenan",
        "topic": "checking food additives"
      },
      "context_check": "Target comment discusses carrageenan directly",
      "reasoning": "User made observation about carrageenan - using observation-style template"
    }
  ],
  "denied": [
    {
      "lead_index": 5,
      "username": "other_user",
      "reason": "Keyword in parent comment but not in target - our reply wouldn't make sense"
    }
  ]
}
```

### Validation Rules
- `lead_index` must be within bounds and unique
- `action_type` must be in the strategy's `allowed_actions`
- `archetype` must be valid (question, observation, frustration, seeking_advice, sharing_experience)
- `template_name` must exist for the chosen action type
- `template_variation` must be a valid index
- All `{placeholder}` slots in the template must be covered
- `context_check` must demonstrate target comment was verified

### Fallback (--no-triage)
When `--no-triage` is passed, the old keyword-based archetype detection is used instead of Grok. This skips all V2 features (discovery, enrichment, verification).

---

## Run Data Logging

Each bot run creates a timestamped folder:
```
run-data/
  2026-02-20_15-30-00/
    meta.json                    # Run config, timing, totals
    raw_leads_scanner_app.json   # All scraped leads before triage
    triage_scanner_app.json      # Grok's full response + parsed decisions
    actions.json                 # Actual actions taken and results
    errors.json                  # Any errors (only if errors occurred)
```

### meta.json
```json
{
  "run_id": "2026-02-20_15-30-00",
  "started_at": "2026-02-20T15:30:00",
  "completed_at": "2026-02-20T16:45:00",
  "accounts": ["example_user"],
  "strategies_run": ["scanner_app"],
  "dry_run": false,
  "total_actions": 15,
  "total_errors": 0
}
```

### triage_{strategy}.json
Includes Grok's raw response string (for debugging prompt issues), parsed approved/denied lists, and token usage for cost tracking.

---

## State Files

### data/state.json (primary)
Centralized state with atomic file locking via `fcntl.flock()`.

```json
{
  "meta": { "first_run_date": "2026-02-14", "version": 2 },
  "users": {
    "username_lowercase": {
      "claimed_by": "account_name",
      "claimed_at": "2026-02-20T15:07:56",
      "actions": [
        {
          "type": "dm",
          "target": "username",
          "account": "account_name",
          "result": "success",
          "timestamp": "...",
          "message_preview": "first 100 chars"
        }
      ]
    }
  },
  "threads": {
    "post_id": { "claimed_by": "account_name", "claimed_at": "...", "permalink": "..." }
  },
  "leads": [ ... ]
}
```

### data/leads.json
Raw array of all discovered leads (for analytics/historical reference).

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
| Long Break (every 5-7 actions) | 15 min | 20 min |

### Day Calculation
```python
day_number = (today - first_run_date).days + 1
```

---

## Reddit API Integration (PRAW)

### Purpose
PRAW (Python Reddit API Wrapper) is used for context enrichment - fetching parent comment text, thread titles, and verifying leads before triage.

### Configuration
Add Reddit API credentials to `.env`:
```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=pom-outreach/1.0
```

Or to `config.json`:
```json
{
  "reddit_api": {
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "user_agent": "pom-outreach/1.0"
  }
}
```

### Key Functions (reddit_api.py)

```python
# Get full context for a single comment
context = get_comment_context(comment_id)
# Returns: CommentContext dataclass with parent_body, thread_title, etc.

# Verify a lead is still valid (not locked/archived)
is_valid = verify_lead(permalink)

# Batch enrich leads with context
enriched = enrich_leads_with_context(leads)
# Adds: parent_comment, parent_author, thread_title, context_verified
```

### Rate Limiting
PRAW has built-in rate limiting (60 requests/minute for OAuth). The bot handles this automatically.

---

## Pre-Reply Verification

### Purpose
Prevents replying to wrong comments when Reddit's permalink navigation doesn't highlight the expected target.

### How It Works
1. Navigate to comment permalink
2. Run JS to find highlighted/focused comment
3. Extract comment text and author
4. Verify keyword is in text and author matches
5. Fail gracefully if mismatch

### Implementation (comment.py)
```python
async def verify_target_comment(page, expected_keyword, expected_username):
    # Returns: {"verified": bool, "reason": str, "target_text": str}
```

### Failure Handling
If verification fails:
- Screenshot captured for debugging
- Comment skipped (not posted to wrong target)
- Logged as COMMENT_FAILED
- Next lead processed

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

# All matching elements
elements = await page.select_all("button")
```

#### Typing
```python
# Human-like typing with random delays
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

## Error Handling

### Screenshot Capture
Every error saves screenshot to `data/error_{context}_{timestamp}.png`

### Error Detection (DMs)
```python
# Check full DOM for error toasts
if "unable to invite" in page_text:
    return DM_FAILED
if "sent a lot of invites" in page_text:
    return DM_RATE_LIMITED
```

### Consecutive Failure Limit
After `max_consecutive_failures` (default: 3), account session ends.

---

## Command Line Interface

```bash
# Normal run with Grok triage (all accounts, all strategies)
python -m src.main

# Dry run (print actions without executing)
python -m src.main --dry-run

# Single account
python -m src.main --account another_user

# Single strategy
python -m src.main --strategy scanner_app

# Override limits
python -m src.main --max-dms 5 --max-comments 10

# Override keywords
python -m src.main --keywords "yuka app" "ingredient scanner"

# Skip Grok triage (use old keyword-based matching)
python -m src.main --no-triage

# Combine flags
python -m src.main --dry-run --strategy scanner_app --account example_user

# Print stats
python -m src.main --stats

# Migrate from old state format
python -m src.main --migrate
```

---

## File Structure

```
reddit-bot/
├── src/
│   ├── main.py            # Entry point & orchestration
│   ├── auth.py            # Reddit login/session management
│   ├── search.py          # Lead scraping + keyword confirmation
│   ├── triage.py          # Grok V2 triage (discovery, enrich, triage)
│   ├── reddit_api.py      # PRAW wrapper for context enrichment
│   ├── comment.py         # Comment posting + pre-reply verification
│   ├── dm.py              # Direct message sending
│   ├── state.py           # Centralized state management (file-locked)
│   ├── templates.py       # Template selection & filling
│   ├── rate_limiter.py    # Rate limiting & delays
│   ├── run_logger.py      # Per-run data logging
│   ├── models.py          # Data models & enums
│   └── utils.py           # Utilities (typing, delays, screenshots)
├── prompts/
│   ├── base_system.txt    # Shared Grok system prompt
│   ├── scanner_app.txt    # Scanner app strategy prompt
│   ├── controversial_ingredient.txt  # Ingredient strategy prompt
│   ├── triage_v2.txt      # Context-aware V2 triage prompt
│   └── discovery.txt      # Discovery prompt for "maybe" leads
├── data/
│   ├── state.json         # Centralized state
│   ├── leads.json         # All discovered leads
│   └── cookies_*.json     # Browser sessions
├── run-data/              # Per-run debug logs (auto-created)
│   └── YYYY-MM-DD_HH-MM-SS/
│       ├── meta.json
│       ├── raw_leads_*.json
│       ├── triage_*.json
│       ├── actions.json
│       └── errors.json
├── config.json            # Accounts, strategies, grok, PRAW credentials
├── templates.json         # Message templates (nested by strategy)
├── .env                   # API keys (XAI_API_KEY, REDDIT_CLIENT_ID, etc.)
└── requirements.txt       # Dependencies (praw added)
```
