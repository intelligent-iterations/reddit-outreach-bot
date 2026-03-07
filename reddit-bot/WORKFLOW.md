# Reddit Bot Execution Workflow

## Overview

This workflow ensures quality control by separating the pipeline into two phases:
1. **Dry Run** - Search, triage, and generate actions without executing
2. **Verified Execution** - Execute approved actions one-by-one with screenshot verification

---

## Phase 1: Dry Run

Run the dry run to search for leads, triage them, and generate proposed actions without posting anything.

```bash
python3 -m src.dry_run
```

### What it does:
1. **Search Phase** - Searches Reddit for configured keywords, collects comments
2. **Split Phase** - Separates leads into keyword-confirmed vs needs-discovery
3. **Discovery Phase** - Uses Grok to filter ambiguous leads for relevance
4. **Triage Phase** - Uses Grok to generate personalized responses
5. **Action Generation** - Creates list of proposed comments/DMs

### Output:
- Creates timestamped folder in `run-data/YYYY-MM-DD_HH-MM-SS/`
- Generates `dry_run_report.html` with full pipeline visualization
- Saves `dry_run_data.json` with all data for execution

### Review:
Open the HTML report to review:
- Which keywords were searched
- Which leads were found and filtered
- What messages would be posted
- Target users and subreddits

---

## Phase 2: Verified Execution

After reviewing and approving actions from the dry run, execute them one-by-one.

### Setup

Edit `src/execute_verified.py` and populate the `ACTIONS` list with approved actions:

```python
ACTIONS = [
    {
        "username": "target_user",
        "subreddit": "target_subreddit",
        "permalink": "/r/subreddit/comments/xxx/title/comment_id",
        "action_type": "comment",
        "message": "Your message here...",
    },
    # ... more actions
]
```

### Execution

Run with index range to control batch size:

```bash
# Execute first 3 actions (indices 0, 1, 2)
START_INDEX=0 END_INDEX=3 python3 -m src.execute_verified

# Execute next 3 actions (indices 3, 4, 5)
START_INDEX=3 END_INDEX=6 python3 -m src.execute_verified

# Execute all actions
python3 -m src.execute_verified
```

### What it does:
1. Logs in with specified account
2. For each action:
   - Navigates to the target permalink
   - Types the message
   - Takes screenshot before submitting
   - Clicks submit
   - Takes screenshot after submitting
   - Updates tracker (claim_user, claim_thread, record_action)
   - Waits 30 seconds before next action
3. Prints summary of successes/failures

### Screenshots:
- Saved to `data/execution_screenshots/YYYYMMDD_HHMMSS/`
- `comment_{username}_{timestamp}.png` - Final state after posting
- `error_before_submit_{timestamp}.png` - State before clicking submit
- `error_after_reply_submit_{timestamp}.png` - State after clicking submit

### Verification:
After each batch, review screenshots to confirm:
- Comment was posted to correct thread
- Message content matches expected
- No errors or unexpected behavior

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `START_INDEX` | First action index to execute | 0 |
| `END_INDEX` | Last action index (exclusive) | 1 |

---

## Tracker Integration

The execution script automatically updates the tracker to prevent duplicates:

- `claim_user(username, account)` - Marks user as contacted
- `claim_thread(post_id, account, permalink)` - Marks thread as used
- `record_action(...)` - Logs the action with timestamp

---

## Troubleshooting

### JSON Serialization Error
```
TypeError: Object of type ActionResult is not JSON serializable
```
This is a cosmetic error at the end when saving results. Comments are still posted successfully.

### Browser Issues
The script uses "nuclear cleanup" between actions - kills the tab and creates a fresh one. This prevents stale state issues.

### Rate Limiting
30-second delay between actions. Adjust `asyncio.sleep(30)` in `execute_verified.py` if needed.

---

## Example Session

```bash
# 1. Run dry run
python3 -m src.dry_run

# 2. Review the HTML report
open run-data/2026-02-22_12-58-46/dry_run_report.html

# 3. Copy approved actions to execute_verified.py

# 4. Execute in batches
START_INDEX=0 END_INDEX=3 python3 -m src.execute_verified
# Review screenshots...

START_INDEX=3 END_INDEX=6 python3 -m src.execute_verified
# Review screenshots...

# Continue until all actions executed
```
