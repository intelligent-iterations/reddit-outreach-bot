# Reddit Outreach Bot Full Build Plan

## Overview
A Python bot using Zendriver that searches Reddit for keywords related to ingredient scanners (Yuka, EWG, etc.) and health/ingredient topics, then automatically comments on relevant posts and DMs relevant users to promote thepom.app.

The bot uses Zendriver (NOT Playwright or Selenium) because Reddit detects those. Zendriver uses Chrome DevTools Protocol and is virtually undetectable.

All element interaction uses `page.find("Text", best_match=True)` and `page.click()` NO CSS selectors. If Reddit redesigns, the bot still works as long as the words on screen stay the same.

---

## Tech Stack
- **Python 3.11+**
- **Zendriver** browser automation (undetectable)
- **asyncio** Zendriver is async-first
- **JSON files** tracking contacted users, leads, logs
- **Optional: OpenAI/Anthropic API** for generating contextual comment variations (Phase 2, not MVP)

---

## Project Structure

```
reddit-bot/
├── config.json              # keywords, subreddits, ramp schedule, account creds
├── templates.json           # DM and comment message templates/archetypes
├── data/
│   ├── contacted.json       # users already DMed (never DM twice)
│   ├── commented.json       # posts/comments already replied to (never double comment)
│   ├── leads.json           # discovered leads with context (for review)
│   └── logs.json            # action log with timestamps
├── src/
│   ├── main.py              # entry point / orchestrator
│   ├── auth.py              # login + session/cookie persistence
│   ├── search.py            # keyword search + result scraping
│   ├── dm.py                # send DMs
│   ├── comment.py           # post comments/replies
│   ├── templates.py         # message template selector + filler
│   ├── tracker.py           # read/write contacted.json, commented.json, logs
│   ├── rate_limiter.py      # ramp schedule + random delays
│   └── utils.py             # shared helpers
├── tests/
│   ├── test_login.py        # Phase 1
│   ├── test_search.py       # Phase 2
│   ├── test_dm.py           # Phase 3
│   ├── test_comment.py      # Phase 4
│   └── test_full_flow.py    # Phase 5
├── requirements.txt
└── README.md
```

---

## config.json

```json
{
  "account": {
    "username": "YOUR_REDDIT_USERNAME",
    "password": "YOUR_REDDIT_PASSWORD"
  },
  "cookies_path": "data/cookies.json",
  
  "search": {
    "keywords_scanner": [
      "yuka app",
      "yuka alternative",
      "ewg app",
      "ingredient scanner",
      "ingredient checker",
      "ingredient scanner app",
      "clean beauty app",
      "food scanner app",
      "think dirty app",
      "inci beauty"
    ],
    "keywords_ingredients": [
      "propylene glycol",
      "sodium benzoate",
      "red 40",
      "allura red",
      "titanium dioxide",
      "natural flavors harmful",
      "food additives harmful",
      "carrageenan",
      "BHA BHT",
      "sodium nitrite"
    ],
    "subreddits_priority": [
      "YukaApp",
      "CleanBeauty",
      "GutHealth",
      "SkincareAddiction",
      "Dyshidrosis",
      "foodscience",
      "Allergies",
      "eczema",
      "HealthyFood",
      "nutrition",
      "PVCs_Treatment",
      "firsttimemom"
    ],
    "search_type": "comment",
    "sort": "new",
    "time_filter": "month"
  },

  "ramp_schedule": {
    "days_1_to_3": { "max_dms": 10, "max_comments": 10 },
    "days_4_to_6": { "max_dms": 15, "max_comments": 15 },
    "days_7_to_9": { "max_dms": 20, "max_comments": 20 },
    "days_10_plus": { "max_dms": 25, "max_comments": 25 }
  },

  "delays": {
    "between_actions_min_seconds": 180,
    "between_actions_max_seconds": 480,
    "between_searches_min_seconds": 30,
    "between_searches_max_seconds": 90,
    "page_load_wait_seconds": 3,
    "typing_delay_min_ms": 50,
    "typing_delay_max_ms": 150
  },

  "app_links": {
    "main": "thepom.app",
    "ingredient_search": "data.thepom.app"
  }
}
```

---

## templates.json

These are based on real DMs and comments that have been sent before. The bot rotates between archetypes and picks a random variation within each archetype. Placeholders: `{username}`, `{subreddit}`, `{topic}`, `{app_mentioned}`, `{ingredient}`, `{their_text_snippet}`

```json
{
  "dm_templates": {
    "fellow_user": [
      "Hey {username}! I saw your {post_or_comment} about {app_mentioned}. I actually used to use it too and had similar frustrations. That's why I ended up building my own ingredient checker called the pom app. The main difference is you scan the ingredients list instead of the barcode, and every ingredient gets flagged based on actual research papers that are summarized for you. Still developing it would love your feedback if you're open to trying it!",
      
      "Hey {username}, saw you on r/{subreddit} talking about {app_mentioned}. I had the exact same issue about a year ago which is why I built the pom app. It focuses on flagging ingredients based on research papers which are summarized so you can actually understand what's going on. Would you be interested in checking it out? Still refining it and would love input from someone who cares about this stuff"
    ],
    
    "feedback_request": [
      "Hey {username}, I saw your comment on r/{subreddit} about {topic}. I was wondering if you would be open to giving me feedback on my app pom. It works by scanning the ingredients list instead of the barcode and associates research papers to each ingredient. Would really help to get perspective from someone like you",
      
      "Hey {username}, saw you on the {app_mentioned} subreddit, was wondering if I could ask you to try my App. For a year I developed an AI system that can associate research papers to ingredients. I created an App that allows you to scan any ingredient label and see the research associated in a summarized way. Its called the pom app. Wondering if you would be interested in helping me refine it and make it better"
    ],
    
    "soft_tease": [
      "Hey {username}, saw your {post_or_comment} about {topic}. I built an app that does exactly what you're describing scans ingredient lists and breaks down every ingredient with research paper summaries so you can see what's actually flagged and why. If this sounds interesting let me know and ill send you the link! Still in development so any wishes for features are welcome too",
      
      "Hey {username} I saw your post about {app_mentioned} and I think you might like this app I built. It's like {app_mentioned} but it gives you a breakdown of every ingredient in your products, and the product will always be available because you scan the ingredients list instead of the barcode. We're also adding symptom tracking so you can track side effects you might be experiencing, let me know if you're interested and ill send you the link"
    ],
    
    "ingredient_specific": [
      "Hey {username}, saw your comment about {ingredient}. Interesting stuff I actually built an app that has a full breakdown on ingredients like {ingredient} with research paper summaries. Its called the pom app. If you want to look into it more, data.thepom.app has a search engine for ingredients. Would love to know what you think",
      
      "Hey {username}, I saw you mention {ingredient} on r/{subreddit}. I've been deep into ingredient research myself and actually built an app that flags ingredients based on research papers. {ingredient} is one of those that definitely comes up. If youre into this stuff check out thepom.app would love your feedback on it"
    ]
  },

  "comment_templates": {
    "scanner_mention": [
      "I used to use {app_mentioned} too but found it missed some things like it would score something high but ignore a preservative that was actually causing me skin issues. I switched to the pom app which scans the ingredients list instead of the barcode and gives you a detailed breakdown of each ingredient with research paper summaries. Worth checking out if you want more detail on what's actually in your stuff",
      
      "Im iffy about {app_mentioned} because it doesn't really match specific nutritional preferences and sometimes ignores certain additives. I've been using the pom app the difference is you scan the ingredients list and each ingredient has its own details page with research papers summarized. Sometimes I don't agree with the flags but the overview on each ingredient helps me understand why it was flagged and make my own decision"
    ],
    
    "ingredient_question": [
      "Great question about {ingredient}! If you want to dig deeper into the research on it, data.thepom.app has a full breakdown with linked research papers really useful for stuff like this",
      
      "I actually looked into {ingredient} a while back. The research is pretty interesting data.thepom.app has summaries of the research papers associated with it if you wanna see what's been found"
    ],
    
    "health_topic": [
      "I dealt with something similar for me it turned out to be certain food additives triggering it. What helped was actually tracking what I was eating and scanning ingredient labels. I use the pom app for this since it flags ingredients based on research papers and has a symptom tracker. Hope you find your trigger!",
      
      "I was having similar issues and honestly tracking what I eat alongside my symptoms made a huge difference. I built the pom app for exactly this it scans ingredient labels and flags things based on research papers, and the symptom tracker lets you cross reference your scans to see if any ingredients might be linked to what you're logging"
    ],
    
    "general_recommendation": [
      "Have you tried scanning the actual ingredients list instead of the barcode? I use the pom app for this it breaks down every single ingredient and shows you research paper summaries for any that have been flagged. Way more thorough than barcode scanning since every product is available",
      
      "If you're really into checking what's in your products you should try the pom app you scan the ingredients list and it gives you a research paper backed breakdown of each ingredient. Its still in development but the ingredient analysis is pretty solid"
    ]
  }
}
```

---

## Module Specifications

### src/auth.py Login & Session Management

```
PURPOSE: Login to Reddit, save cookies, reuse cookies on next run

FLOW:
1. Check if cookies file exists at config.cookies_path
2. If yes → start browser, load cookies, navigate to reddit.com
   → Check if still logged in (find username or avatar element)
   → If logged in: return browser + page
   → If not: delete stale cookies, go to step 3
3. If no cookies → start browser, navigate to reddit.com/login
   → find("Username") or find("Email") → type username
   → find("Password") → type password  
   → find("Log In", best_match=True) → click
   → wait for redirect / check for logged-in state
   → save cookies to file
   → return browser + page

COOKIE SAVE/LOAD:
- Zendriver has built-in cookie management
- Save: browser.cookies.save("data/cookies.json")  
- Load: browser.cookies.load("data/cookies.json")
- Check Zendriver docs for exact syntax may differ

IMPORTANT:
- Add random delay between typing username and password (human-like)
- Use character-by-character typing with random delays (config.delays.typing_delay)
- Handle 2FA if enabled (pause and wait for manual input)
- Handle captcha detection (pause and alert)
```

### src/search.py Keyword Search & Result Scraping

```
PURPOSE: Search Reddit for keywords, extract leads (username, text, subreddit, link)

FLOW:
1. Receive keyword from main.py
2. Navigate to: https://www.reddit.com/search/?q={keyword}
3. Wait for page load
4. Click "Comments" tab:
   → await page.find("Comments", best_match=True) → click
   → wait for results to load
5. Click "New" sort (to get recent results):
   → await page.find("New", best_match=True) → click
   → wait for results to reload
6. Scroll down 3-5 times to load more results (with random delays)
7. Extract results from the page:
   For each result visible on page, extract:
   - username (the "u/username" text)
   - comment text (the body of their comment)
   - subreddit (the "r/subreddit" text)
   - permalink / "Go To Thread" link
   - post title if visible
8. Return list of lead objects

LEAD OBJECT:
{
  "username": "string",
  "comment_text": "string", 
  "subreddit": "string",
  "permalink": "string",
  "post_title": "string",
  "keyword_matched": "string",
  "found_at": "ISO timestamp",
  "source": "comment_search" | "post_search"
}

EXTRACTION APPROACH:
- Don't rely on CSS selectors
- Use page.select_all() to get all text content from the results area
- Parse the text to identify patterns (u/username, r/subreddit, "Go To Thread")
- OR use page.get_content() to get full HTML and parse with regex/string matching
- The exact approach will need to be figured out during Phase 2 testing
- Key insight: we need to inspect what Zendriver gives us back and adapt

ALSO SEARCH POSTS (secondary):
- Same flow but click "Posts" tab instead of "Comments"
- Extract post author + title + subreddit
- These users get DMed but not commented on (we'd comment on their post directly)

PAGINATION:
- Reddit search uses infinite scroll
- Scroll down, wait, scrape new items, repeat
- Track already-seen results to avoid duplicates within same session
- Stop after collecting ~50 leads per keyword (configurable)
```

### src/dm.py Send Direct Messages

```
PURPOSE: Send a personalized DM to a Reddit user

FLOW:
1. Receive lead object + message text from main.py
2. Navigate to: https://www.reddit.com/message/compose/?to={username}
3. Wait for page load
4. Find the subject field:
   → await page.find("Subject") or find the input field
   → Type subject line (e.g., "saw your post about {topic}")
   → Use character-by-character typing with random delays
5. Find the message body field:
   → await page.find("Message") or find the textarea
   → Type the message body with character-by-character typing
6. Find and click send:
   → await page.find("Send", best_match=True) → click
7. Verify send succeeded:
   → Check for success message or redirect
   → Check for error messages ("you're doing that too much", captcha, etc.)
8. Return success/failure status

ALTERNATIVE DM METHOD (Reddit Chat):
- Reddit has two messaging systems: old-style messages and chat
- Old style: /message/compose/?to=username (more reliable, works for all users)
- Chat: clicking chat icon on profile (some users have chat disabled)
- START with old-style messages they're more predictable

ERROR HANDLING:
- "You're doing that too much" → return rate_limited, main.py will increase delay
- Captcha appears → pause, alert, wait for manual solve or skip user
- User not found → skip, log as failed
- User has DMs disabled → skip, log as blocked
- Any unknown error → screenshot page, log error, skip user
```

### src/comment.py Post Comments/Replies

```
PURPOSE: Post a comment on a relevant post or reply to a relevant comment

FLOW FOR REPLYING TO A COMMENT (primary use case):
1. Receive lead object + comment text from main.py
2. Navigate to the permalink (the "Go To Thread" link from search)
3. Wait for page load
4. Find the specific comment we want to reply to:
   → Use page.find() with a snippet of their comment text
   → Or navigate directly to the comment permalink
5. Find the reply button:
   → await page.find("Reply", best_match=True) → click
   → Wait for reply text box to appear
6. Type the comment:
   → Find the text input area
   → Type with character-by-character delays
7. Submit:
   → await page.find("Comment", best_match=True) → click
   → OR find("Submit") or find("Reply") whatever the button says
8. Verify posted:
   → Check for the comment appearing on page
   → Check for errors
9. Return success/failure

FLOW FOR COMMENTING ON A POST:
- Same but navigate to the post URL instead
- Find the main comment box (usually at the top)
- Type and submit

ERROR HANDLING:
- "You're doing that too much" → rate_limited
- Subreddit doesn't allow comments → skip
- Post is locked/archived → skip  
- Karma too low for subreddit → skip, log which subreddit
- Any error → screenshot, log, skip
```

### src/templates.py Message Template Selection & Filling

```
PURPOSE: Pick the right message archetype and variation, fill in placeholders

FLOW:
1. Receive lead object + action type (dm or comment)
2. Determine archetype based on lead context:
   
   FOR DMs:
   - If lead mentions yuka/ewg/think dirty/inci → "fellow_user" archetype
   - If lead is asking for recommendations → "feedback_request" archetype  
   - If lead mentions a specific ingredient → "ingredient_specific" archetype
   - Otherwise → "soft_tease" archetype
   
   FOR COMMENTS:
   - If lead mentions a specific scanner app → "scanner_mention" archetype
   - If lead asks about a specific ingredient → "ingredient_question" archetype
   - If lead describes health symptoms/issues → "health_topic" archetype
   - Otherwise → "general_recommendation" archetype

3. Pick a random variation within the chosen archetype
4. Fill placeholders:
   - {username} → lead.username (first part only, e.g., "Motor" from "Motor_123")
   - {subreddit} → lead.subreddit
   - {topic} → extracted from lead.comment_text or lead.post_title
   - {app_mentioned} → detected app name from lead.comment_text
   - {ingredient} → detected ingredient from lead.comment_text
   - {post_or_comment} → "post" or "comment" based on lead.source
5. Return filled message

ARCHETYPE DETECTION (simple keyword matching):
- Scanner apps: ["yuka", "ewg", "think dirty", "inci beauty", "clean beauty app", "ingredient scanner"]
- Ingredients: match against config.search.keywords_ingredients list
- Health topics: ["bloating", "gut", "eczema", "rash", "allergy", "migraine", "palpitation", "skin", "stool", "digestion"]

ROTATION TRACKING:
- Keep track of which archetype + variation was last used
- Don't use the same variation twice in a row
- Cycle through all variations before repeating
```

### src/rate_limiter.py Ramp Schedule & Delays

```
PURPOSE: Control volume based on ramp schedule, add human-like random delays

FLOW:
1. On startup, check data/logs.json to determine:
   - What day are we on? (days since first bot run)
   - How many DMs sent today?
   - How many comments posted today?
2. Look up ramp_schedule in config to get today's limits
3. Expose functions:
   - can_dm() → bool (have we hit today's DM limit?)
   - can_comment() → bool (have we hit today's comment limit?)
   - wait_between_actions() → async sleep for random duration between min/max
   - wait_between_searches() → async sleep (shorter, for search pagination)
   - get_typing_delay() → random ms for character-by-character typing
4. After each action, update today's counts

RANDOM DELAY:
- Between actions (DM or comment): 3-8 minutes (config.delays.between_actions)
- Between search page loads: 30-90 seconds
- Typing: 50-150ms per character
- Add occasional "pause" of 10-30 seconds mid-typing (simulates thinking)
- Add occasional extra-long delay (15-20 min) every 5-7 actions (simulates break)

DAY TRACKING:
- Day 1 = first time the bot runs
- Store first_run_date in data/logs.json
- Calculate current day number from that
```

### src/tracker.py Persistence & Deduplication

```
PURPOSE: Track who we've contacted, what we've replied to, and log all actions

FILES:
- data/contacted.json → list of usernames we've DMed
- data/commented.json → list of permalinks we've commented on
- data/leads.json → all discovered leads with metadata
- data/logs.json → full action log

FUNCTIONS:
- has_been_dmed(username) → bool
- has_been_commented(permalink) → bool
- log_dm(username, message, success) → writes to contacted.json + logs.json
- log_comment(permalink, message, success) → writes to commented.json + logs.json
- save_lead(lead_object) → writes to leads.json
- get_todays_action_count(action_type) → int (for rate limiter)
- get_first_run_date() → date (for ramp schedule)

NEVER DM THE SAME USER TWICE.
NEVER COMMENT ON THE SAME POST/COMMENT TWICE.
Always check before acting.
```

### src/main.py Orchestrator

```
PURPOSE: Tie everything together, run the main loop

FLOW:
1. Load config.json and templates.json
2. Initialize tracker (load all JSON data files)
3. Initialize rate_limiter (determine today's limits)
4. Call auth.login() → get browser + page
5. Main loop for each keyword in config.search.keywords_scanner:
   a. Call search.search_comments(keyword) → list of leads
   b. For each lead:
      - Check tracker: already DMed? already commented? → skip
      - Check rate_limiter: can_dm()? can_comment()? → stop if limits hit
      
      - IF lead mentions a scanner app (yuka, ewg, etc.):
        → COMMENT: generate comment via templates, post via comment.py
        → DM: generate DM via templates, send via dm.py
        → (Both actions on scanner mentions)
      
      - IF lead mentions ingredient / health topic:
        → COMMENT ONLY: generate comment, post via comment.py
        → (No DM for general ingredient discussions too cold)
      
      - Log action via tracker
      - Wait via rate_limiter.wait_between_actions()
   
   c. Wait via rate_limiter.wait_between_searches() before next keyword

6. After scanner keywords done, do ingredient keywords:
   - Same flow but COMMENT ONLY (no DMs)
   - These link to data.thepom.app/{ingredient_name}

7. Log session summary (total DMs sent, comments posted, leads found)
8. Close browser

DAILY RUN:
- The bot is meant to be run once per day (via cron or manually)
- Each run processes all keywords, respecting daily limits
- If limits are hit mid-run, it stops gracefully

ACTION PRIORITY:
- DMs to scanner-app complainers (highest conversion potential)
- Comments on scanner-app threads (public visibility)
- Comments on ingredient threads (SEO + brand awareness)
```

---

## Testing Plan

### Phase 1: Login & Session (test_login.py)

```
TEST OBJECTIVES:
- Can we launch Zendriver and navigate to Reddit?
- Can we log in with username/password?
- Can we save cookies after login?
- Can we reuse cookies on next run without logging in again?

STEPS:
1. Create a throwaway Reddit account for testing
2. Write test that:
   a. Launches Zendriver browser
   b. Navigates to reddit.com/login
   c. Finds and fills username field using page.find()
   d. Finds and fills password field
   e. Clicks login button
   f. Waits for redirect
   g. Verifies logged in (can we find the username on page?)
   h. Saves cookies
3. Write second test that:
   a. Launches fresh browser
   b. Loads saved cookies
   c. Navigates to reddit.com
   d. Verifies still logged in WITHOUT entering credentials
4. Run both tests, verify cookies persist across sessions

PASS CRITERIA:
- Login completes without captcha (if captcha appears, note it)
- Cookie file is created and is non-empty
- Second run detects logged-in state from cookies
- No errors or Reddit blocks

NOTES:
- If Reddit shows captcha on new account login, may need to manually
  log in once first, save cookies, then let bot reuse them going forward
- Test with headless=False first so you can watch what happens
```

### Phase 2: Search & Scrape (test_search.py)

```
TEST OBJECTIVES:
- Can we search Reddit for a keyword?
- Can we click "Comments" tab using find()?
- Can we click "New" sort?
- Can we extract lead data from search results?
- Can we scroll to load more results?

STEPS:
1. Log in using auth.py (from Phase 1)
2. Navigate to reddit.com/search/?q=yuka+app
3. Print page text/content to see what we're working with
4. Find and click "Comments" tab:
   → comments_tab = await page.find("Comments", best_match=True)
   → await comments_tab.click()
5. Find and click "New" sort:
   → new_btn = await page.find("New", best_match=True)
   → await new_btn.click()
6. Wait for results to load
7. NOW THE HARD PART figure out how to extract data:
   → Try page.get_content() to see raw HTML
   → Try page.select_all('a') to get all links
   → Try page.find("u/") to find username patterns
   → Try page.find("r/") to find subreddit patterns
   → Try page.find("Go To Thread") to find permalinks
   → PRINT EVERYTHING this phase is exploratory
8. Scroll down, wait, check if new results loaded
9. Try extracting at least: username, comment snippet, subreddit
10. Print 5-10 leads to verify data quality

PASS CRITERIA:
- "Comments" tab click works
- "New" sort click works
- We can extract at least username + subreddit + some text from results
- Scrolling loads more results

NOTES:
- This is the most uncertain phase we don't know exactly what Zendriver
  gives us back from the search results page
- Be prepared to try multiple extraction approaches
- May need to get page HTML and parse it rather than using find()
- Document whatever works this becomes the basis for search.py
- Try different keywords to make sure extraction is consistent
```

### Phase 3: DM Test (test_dm.py)

```
TEST OBJECTIVES:
- Can we navigate to the message compose page?
- Can we fill in recipient, subject, and body?
- Can we send the message?
- Does the recipient actually receive it?

STEPS:
1. Log in with throwaway account
2. Navigate to: https://www.reddit.com/message/compose/?to=YOUR_MAIN_ACCOUNT
3. Find subject field → type a test subject
4. Find message body field → type "test message from bot"
5. Find "Send" button → click
6. Check for success (redirect to sent messages?)
7. Log into YOUR_MAIN_ACCOUNT and verify you received the DM
8. THEN test with 3-5 big/celebrity accounts:
   → u/reddit, u/spez, brand accounts like u/Google
   → These accounts get thousands of messages, won't notice
   → Verifies the flow works with different user types
9. Test character-by-character typing with delays
10. Test sending 3 messages in a row with delays between them

PASS CRITERIA:
- Message compose page loads
- Fields can be found and filled using page.find()
- Send button works
- Your main account receives the test DM
- No rate-limit or error messages after 3 sends with delays
- Character-by-character typing looks natural

NOTES:
- If Reddit uses chat instead of messages for some users, note this
- old.reddit.com/message/compose may be more reliable test both
- Watch for "this user doesn't accept DMs" type errors
```

### Phase 4: Comment Test (test_comment.py)

```
TEST OBJECTIVES:
- Can we navigate to a post and leave a comment?
- Can we navigate to a specific comment and reply to it?
- Does the comment actually appear?

STEPS:
1. Log in with throwaway account
2. Create a test post on a test subreddit (r/test exists for this):
   → Navigate to r/test
   → Find "Create Post" or "Create a post" → click
   → Type a title and body
   → Submit
3. Navigate to that post
4. Find the comment box → type a test comment
5. Find "Comment" button → click
6. Verify comment appears on the post
7. Now test REPLYING to the comment:
   → Find the "Reply" link under the comment → click
   → Type a reply in the reply box
   → Submit
   → Verify reply appears nested under original comment
8. Test on a real post (find any recent low-traffic post):
   → Navigate to it
   → Leave a harmless comment like "interesting, thanks for sharing"
   → Verify it appears

PASS CRITERIA:
- Can create post on r/test
- Can comment on a post
- Can reply to a specific comment
- Comments actually appear (check from different browser/incognito)
- No errors

NOTES:
- Some subreddits have minimum karma requirements throwaway may be blocked
- The throwaway needs some karma first may need to manually engage
  on a few posts before the bot can comment freely
- Test subreddits: r/test, r/SandboxTest, r/NewToReddit
```

### Phase 5: Full Flow Integration (test_full_flow.py)

```
TEST OBJECTIVES:
- Does the complete pipeline work end-to-end?
- Search → filter → template selection → action → logging

STEPS:
1. Configure bot with just 1 keyword: "yuka app"
2. Set ramp limit to 3 DMs + 3 comments for this test
3. Run main.py in test mode:
   a. Login ✓
   b. Search "yuka app" → click Comments → click New ✓
   c. Extract leads ✓
   d. For first 3 leads:
      - Check tracker (should all be new) ✓
      - Select template archetype ✓
      - Fill placeholders ✓
      - PRINT the filled message (don't send yet) ✓
      - Log to leads.json ✓
4. Review printed messages do they make sense? Are placeholders filled correctly?
5. If messages look good, run again with actual sending enabled:
   - Send 2 DMs (to safe targets your own accounts or brand accounts)
   - Post 1 comment (on r/test or a low-traffic relevant post)
6. Verify:
   - contacted.json updated with DMed usernames
   - commented.json updated with commented permalinks
   - logs.json has full action log with timestamps
   - Rate limiter waited correct amount between actions
7. Run AGAIN verify it skips already-contacted users

PASS CRITERIA:
- Full pipeline executes without crashes
- Templates fill correctly with real data from search results
- Tracker prevents duplicate contacts
- Rate limiter respects limits
- Delays are random and within configured range
- Messages are coherent and personalized

DRY RUN MODE:
- Add a --dry-run flag to main.py that does everything EXCEPT send
- Prints what it WOULD send to who
- Essential for reviewing before going live
```

### Phase 6: Live Soft Launch (manual monitoring)

```
NOT A CODE TEST this is the first real deployment

STEPS:
1. Switch from throwaway to your real account (ii_social or new dedicated account)
2. Set ramp to Day 1 levels: 10 DMs, 10 comments
3. Run bot with --dry-run first, review all messages
4. If satisfied, run for real
5. Monitor throughout the day:
   - Check inbox for any replies
   - Check profile from incognito are comments visible? (shadow ban check)
   - Check if any comments got removed by mods
6. Run for 3 days at this level
7. Check metrics:
   - How many DM replies did you get?
   - How many comment upvotes?
   - Did any comments get removed?
   - Any warnings from Reddit?
8. If clean after 3 days, bump to Day 4-6 levels (15/day)
9. Continue monitoring and adjusting

SHADOW BAN CHECK:
- Log out, open incognito, go to reddit.com/u/YOUR_USERNAME
- If profile loads and comments are visible → not shadow banned
- If "page not found" → shadow banned, need new account
- Automate this check: add a function that opens incognito and verifies
```

---

## Edge Cases & Error Handling

```
MUST HANDLE:
1. "You're doing that too much" → increase delays, reduce volume
2. Captcha appears → pause bot, alert user, wait for manual solve
3. Reddit login redirect loop → clear cookies, re-login
4. User doesn't exist or deleted account → skip
5. User has DMs/chat disabled → skip, log
6. Post is locked/archived → skip
7. Subreddit requires minimum karma → skip, log which subreddit
8. Search returns 0 results → move to next keyword
9. Page doesn't load (timeout) → retry once, then skip
10. Rate limited by Reddit (429) → stop all actions, wait 10+ minutes
11. Account suspended → stop immediately, alert user
12. Element not found by find() → try alternative text, retry, then skip

RESILIENCE:
- Wrap every action in try/except
- Log every error with screenshot (page.save_screenshot)
- Never crash the whole bot because one action failed
- If 3+ consecutive errors → stop and alert, something is wrong
```

---

## Future Enhancements (Not MVP)

```
PHASE 2 ADDITIONS:
- AI-generated messages using Claude/GPT API for truly unique responses
  (pass the lead's comment as context, get a natural reply back)
- Multi-account rotation (2-3 accounts, alternate between them)
- Proxy rotation per account
- Scheduled runs via cron (run every day at random time)
- Dashboard showing metrics (DMs sent, replies received, conversion)
- Integration with thepom.app analytics (track which Reddit users signed up)
- X (Twitter) and Instagram versions using same architecture
- Auto-warmup: bot does regular Reddit activity (upvote, browse, join subs)
  to keep the account looking natural between outreach sessions
```

---

## Quick Start for Claude Code

```bash
# 1. Create project
mkdir reddit-bot && cd reddit-bot

# 2. Set up Python environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install zendriver asyncio

# 4. Create project structure
mkdir -p src data tests

# 5. Start with Phase 1: test_login.py
# Build auth.py first, test it, then move to Phase 2

# 6. Run tests sequentially don't skip ahead
python tests/test_login.py
python tests/test_search.py
python tests/test_dm.py
python tests/test_comment.py
python tests/test_full_flow.py
```

**BUILD ORDER: auth.py → search.py → tracker.py → templates.py → rate_limiter.py → dm.py → comment.py → main.py**

Each module should be independently testable before wiring into main.py.
