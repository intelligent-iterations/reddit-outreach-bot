# INSTRUCTIONS FOR CLAUDE CODE Reddit Outreach Bot

Read `reddit-outreach-plan.md` fully before writing any code. That is the spec. This file contains rules you must follow.

---

## Credentials

```
email:gerardwaysleftbuttcheek@gmail.com
Reddit Username: This_Photo5976
Reddit Password: Looshlover333!
```

Use these for all testing. This is a throwaway alt account. Do NOT use any other account.

---

## Critical Rules

### 1. ZENDRIVER ONLY No Playwright, No Selenium
Reddit detects Playwright and Selenium. We use Zendriver which uses Chrome DevTools Protocol and is undetectable. If you don't know something about Zendriver's API, check the docs at https://zendriver.dev/ before guessing.

### 2. NEVER USE CSS SELECTORS
All element interaction must use `page.find("visible text", best_match=True)` and `.click()`. Never write CSS selectors, XPath, `querySelector`, or `data-testid` lookups. If the button says "Comments" on screen, we do `await page.find("Comments", best_match=True)`. This makes the bot resilient to Reddit redesigns.

### 3. BUILD ORDER IS STRICT Do Not Skip Ahead
Build and fully test each module before starting the next one:

```
1. auth.py       → run test_login.py       → must pass before continuing
2. search.py     → run test_search.py       → must pass before continuing
3. tracker.py    → run test_tracker.py      → must pass before continuing  
4. templates.py  → run test_templates.py    → must pass before continuing
5. rate_limiter.py → run test_rate_limiter.py → must pass before continuing
6. dm.py         → run test_dm.py           → must pass before continuing
7. comment.py    → run test_comment.py      → must pass before continuing
8. main.py       → run test_full_flow.py    → final integration test
```

Do NOT build main.py first. Do NOT build dm.py before search.py works. Each module must be independently runnable and testable.

### 4. SEARCH EXTRACTION IS EXPLORATORY
Phase 2 (search.py) is the hardest part. We do NOT know exactly what Zendriver returns from Reddit's search results page. Your job during this phase:

- Navigate to a search, click "Comments", click "New"
- Then PRINT EVERYTHING you can get from the page:
  - `await page.get_content()` → print raw HTML
  - `await page.select_all('a')` → print all links
  - Try `await page.find("u/")` → see if it finds usernames
  - Try `await page.find("r/")` → see if it finds subreddits
  - Try `await page.find("Go To Thread")` → see if it finds permalinks
- Based on what comes back, figure out the best extraction approach
- You may need to parse HTML with regex or string matching
- Do NOT assume a structure discover it, then build around it

Show me what you find before building the extraction logic. I may need to help you interpret it.

### 5. ALWAYS RUN WITH headless=False DURING DEVELOPMENT
I need to see what the browser is doing. Only switch to headless after everything works. Launch the browser like:

```python
browser = await zd.start(headless=False)
```

### 6. CHARACTER-BY-CHARACTER TYPING
Never paste text into fields instantly. Always type character by character with random delays between keystrokes (50-150ms). This is how humans type and Reddit's behavioral analysis watches for this.

```python
import random
import asyncio

async def human_type(element, text):
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.05, 0.15))
```

### 7. RANDOM DELAYS BETWEEN ALL ACTIONS
Never do two actions back to back. Always add a random sleep:
- Between DMs/comments: 3-8 minutes (randomized)
- Between search page loads: 30-90 seconds
- Between clicking tabs/buttons: 1-3 seconds
- Occasionally add a long pause of 10-20 minutes every 5-7 actions

### 8. NEVER CONTACT THE SAME USER TWICE
Before every DM or comment, check `data/contacted.json` and `data/commented.json`. If the username or permalink exists, skip. No exceptions.

### 9. --dry-run FLAG IS MANDATORY
main.py must support a `--dry-run` flag that does everything (search, filter, template selection, placeholder filling) EXCEPT actually sending DMs or posting comments. In dry-run mode, print to console:
```
[DRY RUN] Would DM u/username:
Subject: saw your post about yuka
Body: Hey username, I saw your comment on r/YukaApp about...

[DRY RUN] Would comment on /r/GutHealth/comments/abc123:
Body: I dealt with something similar...
```

I will always run --dry-run first and review before going live.

### 10. SCREENSHOT ON EVERY ERROR
If anything goes wrong element not found, page didn't load, rate limited, etc. take a screenshot before moving on:

```python
await page.save_screenshot(f"data/error_{timestamp}.png")
```

This lets me debug what happened without being there.

### 11. WRAP EVERYTHING IN TRY/EXCEPT
Every single action (login, search, click, type, send) must be wrapped in try/except. Never let one failed action crash the whole bot. Log the error, screenshot it, and move to the next lead.

### 12. STOP ON 3 CONSECUTIVE FAILURES
If 3 actions in a row fail, stop the bot and print a clear error message. Something is fundamentally wrong (shadow ban, captcha wall, account suspended) and continuing will make it worse.

---

## Testing Targets

### Phase 3 (DM test):
- First DM goes to: `_______________` (my main account I'll fill this in)
- Then DM these accounts to verify flow works on strangers (they'll never notice):
  - u/reddit
  - u/AutoModerator  
  - Any large brand account
- If any of these fail with "user doesn't accept DMs", that's fine log and skip

### Phase 4 (Comment test):
- Use r/test for all comment testing it's specifically meant for bot testing
- Create a post there, comment on it, reply to the comment
- Do NOT comment on real subreddits during testing

### Phase 5 (Full flow):
- Limit to 3 DMs + 3 comments max
- Use --dry-run first, show me the output
- Only go live after I review and approve

---

## File Structure for Reference

```
reddit-bot/
├── config.json
├── templates.json
├── data/
│   ├── contacted.json
│   ├── commented.json
│   ├── leads.json
│   └── logs.json
├── src/
│   ├── main.py
│   ├── auth.py
│   ├── search.py
│   ├── dm.py
│   ├── comment.py
│   ├── templates.py
│   ├── tracker.py
│   ├── rate_limiter.py
│   └── utils.py
├── tests/
│   ├── test_login.py
│   ├── test_search.py
│   ├── test_dm.py
│   ├── test_comment.py
│   └── test_full_flow.py
├── requirements.txt
└── README.md
```

---

## When In Doubt

- Check Zendriver docs: https://zendriver.dev/
- Use `page.find("text", best_match=True)` for everything
- Print what the page gives you before trying to parse it
- Ask me if something is ambiguous don't guess and build the wrong thing
- Keep it simple no overengineering, no abstractions we don't need yet
