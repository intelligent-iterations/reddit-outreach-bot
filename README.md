# Reddit Outreach Bot

An autonomous Reddit outreach bot that uses AI (Grok-4) to intelligently find and engage with relevant users through context-aware comments and DMs.

## Features

- **AI-Powered Lead Triage**: Uses Grok-4 to evaluate leads, classify user intent, and select appropriate response templates
- **Multi-Strategy Targeting**: Configure multiple keyword strategies with different actions (DM, comment)
- **Context-Aware Responses**: 100+ message templates organized by user archetype (question-asking, frustration, seeking advice, etc.)
- **Smart Rate Limiting**: Ramp-up schedule to avoid detection (configurable daily limits)
- **Multi-Account Support**: Operate multiple Reddit accounts with isolated state tracking
- **Browser Automation**: Uses Zendriver for undetectable browser automation
- **Dry Run Mode**: Preview proposed actions before execution

## How It Works

1. **Search Phase**: Scrapes Reddit for posts/comments matching your keywords
2. **Discovery Phase**: Grok evaluates "maybe" leads for relevance
3. **Context Enrichment**: Fetches parent comments and thread titles via Reddit API
4. **Triage Phase**: Grok classifies user intent and selects the best template
5. **Execution Phase**: Posts comments or sends DMs with human-like delays

## Setup

### Prerequisites

- Python 3.10+
- Chrome browser
- xAI API key (for Grok)

### Installation

```bash
cd reddit-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

1. Copy the example config:
```bash
cp config.example.json config.json
cp .env.example .env
```

2. Edit `config.json` with your Reddit account credentials and targeting strategy

3. Add your xAI API key to `.env`:
```
XAI_API_KEY=xai-your-key-here
```

4. Customize message templates in `templates.json`

5. Edit prompts in `prompts/` to match your use case

## Usage

### Dry Run (Preview Actions)
```bash
python src/dry_run.py
```

### Execute Verified Actions
```bash
python src/execute_verified.py
```

### Full Automated Run
```bash
python src/main.py
```

## Configuration

### config.json

| Field | Description |
|-------|-------------|
| `accounts` | Reddit account credentials |
| `ramp_schedule` | Daily limits that increase over time |
| `search.keywords_*` | Keywords to search for |
| `search.subreddits_priority` | Subreddits to target |
| `strategies` | Named strategies with keywords and allowed actions |
| `delays` | Timing configuration for human-like behavior |
| `grok` | Grok API configuration |

### Message Templates

Templates in `templates.json` are organized by:
- Strategy (e.g., `scanner_app`, `controversial_ingredient`)
- Action type (`dm`, `comment`)
- User archetype (`question_asking`, `frustration`, `seeking_advice`, etc.)

Templates support placeholders: `{username}`, `{subreddit}`, `{ingredient}`, `{app_mentioned}`, `{topic}`

## Project Structure

```
reddit-bot/
├── config.example.json    # Example configuration
├── templates.json         # Message templates
├── prompts/              # Grok prompt files
│   ├── base_system.txt
│   ├── triage_v2.txt
│   └── discovery.txt
├── src/
│   ├── main.py           # Main orchestration
│   ├── auth.py           # Session management
│   ├── search.py         # Lead discovery
│   ├── triage.py         # Grok-based evaluation
│   ├── comment.py        # Comment posting
│   ├── dm.py             # DM sending
│   ├── state.py          # Atomic state management
│   └── rate_limiter.py   # Rate limiting
└── data/                 # Runtime data (gitignored)
```

## Safety Features

- Atomic file-locked state to prevent race conditions
- Pre-reply verification before posting
- Screenshot capture for error logging
- Consecutive failure limits
- Never contacts the same user twice

## License

MIT
