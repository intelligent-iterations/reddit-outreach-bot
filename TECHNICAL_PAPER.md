# Technical Paper: Autonomous Reddit Outreach Bot

**Project:** reddit-outreach-bot
**Repository:** https://github.com/intelligent-iterations/reddit-outreach-bot
**Developer:** Intelligent Iterations
**Date:** March 2026

---

## Executive Summary

This document provides technical evidence of an autonomous Reddit outreach system that leverages large language models (Grok-4) for intelligent lead discovery, context-aware triage, and personalized engagement. The system demonstrates advanced capabilities in:

1. **Autonomous API interactions** with xAI's Grok-4 and Reddit's API
2. **Real-time lead discovery** across multiple subreddits
3. **AI-powered triage** that classifies user intent and selects optimal response templates
4. **Browser automation** for undetectable Reddit engagement
5. **State management** for multi-account coordination

---

## 1. System Architecture

### 1.1 Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     REDDIT OUTREACH BOT                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Search    │  │  Discovery  │  │   Triage    │             │
│  │   Module    │──▶│    Phase    │──▶│   Phase     │             │
│  │ (Zendriver) │  │   (Grok-4)  │  │  (Grok-4)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│         │                                   │                   │
│         ▼                                   ▼                   │
│  ┌─────────────┐                    ┌─────────────┐             │
│  │   Reddit    │                    │  Template   │             │
│  │  API (PRAW) │                    │  Selection  │             │
│  │   Context   │                    │  & Filling  │             │
│  └─────────────┘                    └─────────────┘             │
│                                            │                    │
│                                            ▼                    │
│                                     ┌─────────────┐             │
│                                     │  Execution  │             │
│                                     │ (Comment/DM)│             │
│                                     └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Lead Search | Zendriver (CDP) | Undetectable browser automation for Reddit scraping |
| AI Triage | Grok-4 (xAI) | Lead evaluation, intent classification, template selection |
| Context Enrichment | PRAW (Reddit API) | Fetch parent comments, thread titles, verify posts |
| State Management | JSON + File Locks | Atomic operations for multi-account coordination |
| Execution | Zendriver | Human-like typing, click delays, screenshot capture |

---

## 2. API Integration Evidence

### 2.1 Grok-4 Integration

The system makes structured API calls to xAI's Grok-4 model for two distinct phases:

**Discovery Phase Prompt (excerpt from `prompts/discovery.txt`):**
```
You are evaluating potential outreach leads from Reddit.
For each lead, determine if the user is genuinely interested in
ingredient scanning apps based on their comment context...
```

**Triage Phase Prompt (excerpt from `prompts/triage_v2.txt`):**
```
Classify the user's intent into one of these archetypes:
- question_asking: User is asking a question
- observation: User is making an observation
- frustration: User is expressing frustration
- seeking_advice: User is actively seeking recommendations
- sharing_experience: User is sharing their experience

Then select the most appropriate template...
```

**API Configuration (`config.json`):**
```json
{
  "grok": {
    "model": "grok-4",
    "base_url": "https://api.x.ai/v1",
    "temperature": 0.3,
    "max_tokens": 16384,
    "max_leads_per_batch": 50,
    "max_retries": 2
  }
}
```

### 2.2 Reddit API Integration

The system uses PRAW for context enrichment:

```python
# From src/reddit_api.py
def enrich_lead_context(lead: Lead) -> Lead:
    """Fetch parent comment and thread title for context."""
    submission = reddit.submission(url=lead.permalink)
    lead.thread_title = submission.title
    lead.parent_comment_text = get_parent_comment(lead.comment_id)
    return lead
```

---

## 3. Autonomous Execution Evidence

### 3.1 Run Data Logs

The system maintains detailed logs of every run. Example from `run-data/2026-02-27_14-32-22/actions.json`:

```json
[
  {
    "username": "rhollien",
    "action_type": "comment",
    "result": "success",
    "template_name": "general_recommendation",
    "filled_message": "Good question about scanner apps for health data! Have you tried scanning the actual ingredients list instead of the barcode? I use the pom app for this and the thing that sets it apart is you customize how ingredients get flagged based on the severity of the research...",
    "permalink": "/r/dollartreebeauty/comments/1rdv0sp/la_mercerie_nail_cuticle_treatments/o7nko73",
    "strategy": "scanner_app",
    "timestamp": "2026-02-27T14:39:48.922535"
  },
  {
    "username": "celiactivism",
    "action_type": "comment",
    "result": "success",
    "template_name": "general_recommendation",
    "filled_message": "Totally get the frustration with scanner apps being unreliable or out of date. what changed the game for me was switching from apps that give you a generic score to one where you control the flagging...",
    "permalink": "/r/Celiac/comments/1re6ea4/any_apps_you_recommend_for_identifying_safe_foods/o7b5g0d",
    "strategy": "scanner_app",
    "timestamp": "2026-02-27T14:55:36.080440"
  }
]
```

### 3.2 Screenshot Evidence

The system captures screenshots of successful comment posts as verification:

```
data/execution_screenshots/
├── 20260222_203405/
│   └── comment_butterflyfrenchfry_20260222_203550.png
├── 20260222_204052/
│   ├── comment_Sunflower3586_20260222_204222.png
│   └── comment_Twilli88_20260222_204712.png
└── 20260222_204746/
    ├── comment_Far-Recording4321_20260222_205306.png
    └── comment_saskgrinder_20260222_205114.png
```

### 3.3 Multi-Strategy Execution

The system supports multiple targeting strategies:

| Strategy | Keywords | Subreddits | Actions |
|----------|----------|------------|---------|
| `scanner_app` | yuka app, ewg app, ingredient scanner, think dirty app | YukaApp, CleanBeauty, SkincareAddiction | DM, Comment |
| `controversial_ingredient` | propylene glycol, red 40, carrageenan, BHA BHT | nutrition, Allergies, foodscience | Comment only |

---

## 4. Template System

### 4.1 Archetype-Based Templates

The system maintains 100+ message templates organized by user archetype:

```json
{
  "scanner_app": {
    "comment": {
      "question_asking": [
        "Good question about {topic}! Have you tried scanning the actual ingredients list...",
        "That's a great point about {app_mentioned}. The thing that bugged me..."
      ],
      "frustration": [
        "Totally get the frustration with scanner apps being unreliable...",
        "Yeah the issue with scanners flagging even {topic} is super annoying..."
      ],
      "seeking_advice": [
        "If you're looking for ingredient analysis, you might want to check out...",
        "Those are solid options for ingredient analysis..."
      ]
    }
  }
}
```

### 4.2 Dynamic Placeholder Filling

Templates support dynamic placeholders filled by Grok's analysis:

- `{username}` - Reddit username
- `{subreddit}` - Target subreddit
- `{ingredient}` - Specific ingredient mentioned
- `{app_mentioned}` - Competitor app referenced
- `{topic}` - General topic of discussion

---

## 5. Rate Limiting & Safety

### 5.1 Ramp Schedule

The system implements a gradual ramp-up to avoid detection:

| Days | Max DMs/Day | Max Comments/Day |
|------|-------------|------------------|
| 1-3 | 5 | 10 |
| 4-7 | 8 | 15 |
| 8+ | 10 | 25 |

### 5.2 Delay Configuration

```json
{
  "delays": {
    "between_dms_min_seconds": 720,
    "between_dms_max_seconds": 1080,
    "between_actions_min_seconds": 180,
    "between_actions_max_seconds": 480,
    "typing_delay_min_ms": 50,
    "typing_delay_max_ms": 150
  }
}
```

### 5.3 State Isolation

The system uses atomic file-locked state management to coordinate multiple accounts:

```python
# From src/state.py
class StateManager:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.lock = FileLock(f"{state_path}.lock")

    def mark_user_contacted(self, username: str, account: str):
        with self.lock:
            state = self._load_state()
            state["contacted_users"].append({
                "username": username,
                "by_account": account,
                "timestamp": datetime.now().isoformat()
            })
            self._save_state(state)
```

---

## 6. Production Performance Data

> **Data Source:** Run logs from February 2026 outreach campaign

### 6.1 Engagement Summary

| Metric | Value |
|--------|-------|
| **Comments Posted** | 18 |
| **Unique Subreddits** | 15 |
| **DMs Attempted** | 12 |
| **DMs Successful** | 8 (67%) |
| **Account Bans** | 0 |

### 6.2 Subreddits Engaged

| Subreddit | Comments | Category |
|-----------|----------|----------|
| r/Celiac | 3 | Food/Health |
| r/dollartreebeauty | 2 | Beauty |
| r/ultraprocessedfood | 1 | Food |
| r/Naturalhair | 1 | Beauty |
| r/tretinoin | 1 | Skincare |
| r/Allergies | 1 | Health |
| r/ChronicPain | 1 | Health |
| r/tressless | 1 | Haircare |
| r/CatAdvice | 1 | Pets |
| r/Dryeyes | 1 | Health |
| r/SkinbarrierLovers | 1 | Skincare |
| r/Dyshidrosis | 1 | Health |
| r/finehair | 1 | Haircare |
| r/mildlyinfuriating | 1 | General |
| r/kayandtaysnark | 1 | General |

### 6.3 Template Performance

| Template | Uses | Purpose |
|----------|------|---------|
| `general_recommendation` | 6 | Generic app suggestion |
| `scanner_mention` | 6 | Response to scanner app discussions |
| `ingredient_question` | 4 | Answer ingredient-specific questions |
| `health_topic` | 2 | Health-focused conversations |

### 6.4 Comment Engagement

> **Note:** Comments were posted in late February 2026. Engagement metrics are early-stage.

| Metric | Value |
|--------|-------|
| Comments with upvotes | 18 (100% not downvoted) |
| Comments with replies | 0 |
| Comments removed/deleted | 0 |
| Account restrictions | 0 |

The low reply rate is expected for recommendation-style comments that don't invite direct responses. The key success metric is **zero removals or bans**, indicating the AI-generated content passes as authentic user engagement.

### 6.5 DM Performance

| Metric | Value |
|--------|-------|
| DMs Attempted | 12 |
| DMs Delivered | 8 (67%) |
| DMs Failed | 4 (33%) |
| DM Replies Received | 0 |

**Failure Reasons:**
- User has DMs disabled
- Account too new for DM privileges
- Rate limiting by Reddit

The 67% delivery rate demonstrates effective targeting of users with open DM settings.

---

## 7. Code Quality

### 7.1 Modular Architecture

```
src/
├── auth.py           # Session management with cookie persistence
├── search.py         # Keyword scraping and lead extraction
├── triage.py         # Grok-based lead evaluation
├── reddit_api.py     # PRAW wrapper for context enrichment
├── comment.py        # Comment posting handlers
├── dm.py             # DM sending handlers
├── state.py          # Atomic state management
├── rate_limiter.py   # Schedule-based rate limiting
├── templates.py      # Template selection and filling
└── run_logger.py     # Per-run data logging
```

### 7.2 Test Coverage

The project includes comprehensive test suites:

```
tests/
├── test_comment.py
├── test_dm.py
├── test_full_flow.py
├── test_login.py
├── test_models.py
├── test_rate_limiter.py
├── test_search.py
├── test_state.py
└── test_templates.py
```

---

## 8. Conclusion

This Reddit Outreach Bot demonstrates advanced capabilities in:

1. **Autonomous AI-powered decision making** using Grok-4 for lead triage
2. **Real-time API interactions** with Reddit and xAI
3. **Production-grade architecture** with atomic state management
4. **Safety-first design** with rate limiting and multi-account coordination
5. **Measurable results:**
   - **18 comments** posted across 15 subreddits
   - **8 successful DMs** (67% success rate)
   - **4 template types** with context-aware selection
   - **Zero account bans** from rate limiting

The system has been deployed in production since February 2026 and has successfully engaged users across multiple subreddits with context-aware, personalized messages.

---

**Repository:** https://github.com/intelligent-iterations/reddit-outreach-bot
**Developer:** Intelligent Iterations
**Contact:** support@intelligentiterations.com
