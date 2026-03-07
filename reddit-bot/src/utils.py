import asyncio
import json
import os
import random
import sys
from datetime import datetime

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================================
# BEAUTIFUL LOGGING SYSTEM
# ============================================================================

class Logger:
    """Beautiful detailed logging for the Reddit bot."""

    # ANSI color codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Colors
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Background
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

    @staticmethod
    def _timestamp():
        return datetime.now().strftime("%H:%M:%S")

    @classmethod
    def header(cls, text, char="═"):
        """Print a major section header."""
        width = 70
        line = char * width
        print(f"\n{cls.CYAN}{cls.BOLD}{line}{cls.RESET}")
        print(f"{cls.CYAN}{cls.BOLD}  {text}{cls.RESET}")
        print(f"{cls.CYAN}{cls.BOLD}{line}{cls.RESET}\n")

    @classmethod
    def subheader(cls, text):
        """Print a subsection header."""
        print(f"\n{cls.YELLOW}{cls.BOLD}▸ {text}{cls.RESET}")
        print(f"{cls.GRAY}{'─' * 50}{cls.RESET}")

    @classmethod
    def step(cls, emoji, text, detail=None):
        """Print a workflow step."""
        ts = cls._timestamp()
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {emoji} {cls.WHITE}{text}{cls.RESET}", end="")
        if detail:
            print(f" {cls.DIM}({detail}){cls.RESET}")
        else:
            print()

    @classmethod
    def progress(cls, current, total, label):
        """Print a progress indicator."""
        pct = (current / total * 100) if total > 0 else 0
        bar_len = 20
        filled = int(bar_len * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {cls.BLUE}[{bar}]{cls.RESET} {current}/{total} {label} ({pct:.0f}%)")

    @classmethod
    def success(cls, text):
        """Print a success message."""
        ts = cls._timestamp()
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {cls.GREEN}✓ {text}{cls.RESET}")

    @classmethod
    def warning(cls, text):
        """Print a warning message."""
        ts = cls._timestamp()
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {cls.YELLOW}⚠ {text}{cls.RESET}")

    @classmethod
    def error(cls, text):
        """Print an error message."""
        ts = cls._timestamp()
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {cls.RED}✗ {text}{cls.RESET}")

    @classmethod
    def info(cls, text):
        """Print an info message."""
        ts = cls._timestamp()
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {cls.CYAN}ℹ {text}{cls.RESET}")

    @classmethod
    def action(cls, action_type, target, status=None):
        """Print an action being taken."""
        ts = cls._timestamp()
        icon = "💬" if action_type == "comment" else "✉️" if action_type == "dm" else "🔍"
        status_str = ""
        if status == "success":
            status_str = f" {cls.GREEN}[SUCCESS]{cls.RESET}"
        elif status == "failed":
            status_str = f" {cls.RED}[FAILED]{cls.RESET}"
        elif status == "skipped":
            status_str = f" {cls.YELLOW}[SKIPPED]{cls.RESET}"
        print(f"{cls.GRAY}[{ts}]{cls.RESET} {icon} {cls.MAGENTA}{action_type.upper()}{cls.RESET} → {target}{status_str}")

    @classmethod
    def wait(cls, seconds, reason):
        """Print a waiting message."""
        ts = cls._timestamp()
        mins = seconds / 60
        if mins >= 1:
            time_str = f"{mins:.1f} minutes"
        else:
            time_str = f"{seconds:.0f} seconds"
        print(f"{cls.GRAY}[{ts}]{cls.RESET} ⏳ {cls.DIM}Waiting {time_str} ({reason}){cls.RESET}")

    @classmethod
    def stat(cls, label, value, color=None):
        """Print a statistic."""
        color = color or cls.WHITE
        print(f"  {cls.GRAY}•{cls.RESET} {label}: {color}{cls.BOLD}{value}{cls.RESET}")

    @classmethod
    def lead_table(cls, leads, max_show=5):
        """Print a summary table of leads."""
        if not leads:
            print(f"  {cls.GRAY}(no leads){cls.RESET}")
            return

        print(f"  {cls.GRAY}{'─' * 60}{cls.RESET}")
        for i, lead in enumerate(leads[:max_show]):
            username = lead.get("username", "?")[:20]
            subreddit = lead.get("subreddit", "?")[:15]
            text = lead.get("comment_text", lead.get("text", ""))[:40].replace("\n", " ")
            print(f"  {cls.GRAY}{i+1:2}.{cls.RESET} {cls.CYAN}u/{username:<20}{cls.RESET} r/{subreddit:<15} {cls.DIM}\"{text}...\"{cls.RESET}")

        if len(leads) > max_show:
            print(f"  {cls.GRAY}... and {len(leads) - max_show} more{cls.RESET}")
        print(f"  {cls.GRAY}{'─' * 60}{cls.RESET}")

    @classmethod
    def grok_response(cls, approved_count, denied_count):
        """Print Grok triage results."""
        print(f"\n  {cls.GREEN}▸ Approved: {approved_count}{cls.RESET}")
        print(f"  {cls.RED}▸ Denied: {denied_count}{cls.RESET}\n")

    @classmethod
    def account_banner(cls, account_name, day_number, dm_status, comment_status):
        """Print account session banner."""
        print(f"\n{cls.BG_BLUE}{cls.WHITE}{cls.BOLD}")
        print(f"  🤖 ACCOUNT: {account_name}  |  Day {day_number}  ")
        print(f"  DMs: {dm_status}  |  Comments: {comment_status}  ")
        print(f"{cls.RESET}\n")

    @classmethod
    def final_summary(cls, dms_sent, dms_failed, comments_sent, comments_failed):
        """Print final run summary."""
        print(f"\n{cls.CYAN}{'═' * 70}{cls.RESET}")
        print(f"{cls.CYAN}{cls.BOLD}  📊 SESSION SUMMARY{cls.RESET}")
        print(f"{cls.CYAN}{'═' * 70}{cls.RESET}")
        print(f"  {cls.GREEN}✓ DMs Sent:{cls.RESET}        {dms_sent}")
        print(f"  {cls.RED}✗ DMs Failed:{cls.RESET}      {dms_failed}")
        print(f"  {cls.GREEN}✓ Comments Posted:{cls.RESET} {comments_sent}")
        print(f"  {cls.RED}✗ Comments Failed:{cls.RESET} {comments_failed}")
        print(f"{cls.CYAN}{'═' * 70}{cls.RESET}\n")


# Global logger instance
log = Logger()

# Load .env from the reddit-bot directory
load_dotenv(os.path.join(BASE_DIR, ".env"))


def load_config():
    with open(os.path.join(BASE_DIR, "config.json"), "r") as f:
        return json.load(f)


def load_templates():
    with open(os.path.join(BASE_DIR, "templates.json"), "r") as f:
        return json.load(f)


async def human_type(element, text, config=None):
    min_ms = 50
    max_ms = 150
    if config and "delays" in config:
        min_ms = config["delays"].get("typing_delay_min_ms", 50)
        max_ms = config["delays"].get("typing_delay_max_ms", 150)

    for i, char in enumerate(text):
        await element.send_keys(char)
        delay = random.uniform(min_ms / 1000, max_ms / 1000)

        # Occasional thinking pause (every 20-40 chars, 0.5-2s)
        if i > 0 and random.random() < 0.03:
            delay += random.uniform(0.5, 2.0)

        await asyncio.sleep(delay)


async def random_delay(min_s, max_s):
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)
    return delay


async def take_error_screenshot(page, context="error"):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(BASE_DIR, "data", f"error_{context}_{timestamp}.png")
        await page.save_screenshot(filename)
        print(f"[SCREENSHOT] Saved: {filename}")
        return filename
    except Exception as e:
        print(f"[SCREENSHOT] Failed to save screenshot: {e}")
        return None
