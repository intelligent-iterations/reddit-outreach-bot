import asyncio
import re
from datetime import datetime, timedelta

from src.state import can_engage_user
from src.utils import random_delay, take_error_screenshot

# Maximum age for posts to be considered (in days)
MAX_POST_AGE_DAYS = 180
# Target number of fresh (not already engaged) leads
TARGET_FRESH_LEADS = 50


def _extract_comment_id(permalink: str) -> str:
    """Extract comment ID from permalink if it's a comment-level link."""
    parts = permalink.rstrip('/').split('/')
    # Comment: ['', 'r', 'sub', 'comments', 'postid', 'title', 'commentid']
    if len(parts) >= 7 and parts[3] == 'comments':
        return parts[6]
    return ""


def _is_keyword_in_text(keyword: str, text: str) -> bool:
    """Check if keyword appears in text (case-insensitive)."""
    return keyword.lower() in text.lower()


# Subreddit suffixes/names that indicate non-English content
NON_ENGLISH_SUBREDDIT_PATTERNS = [
    'DE', 'FR', 'IT', 'NL', 'PL', 'RU', 'PT', 'BR', 'JP', 'KR', 'CN',
    'german', 'french', 'italian', 'dutch', 'polish', 'russian', 'portuguese',
    'japanese', 'korean', 'chinese', 'brasil', 'mexico', 'argentina',
    'deutschland', 'france', 'italia', 'espana', 'portugal',
]

# Common words that indicate non-English text (German, French, etc.)
NON_ENGLISH_INDICATORS = [
    # German
    'ich', 'und', 'das', 'ist', 'nicht', 'eine', 'auch', 'sehr', 'aber', 'wenn', 'dass',
    # French
    'je', 'est', 'une', 'les', 'des', 'que', 'pas', 'pour', 'avec', 'mais', 'vous',
    # Italian
    'che', 'sono', 'della', 'questo', 'anche', 'essere', 'molto', 'tutto',
    # Portuguese
    'não', 'para', 'uma', 'você', 'isso', 'como', 'está', 'muito', 'esse',
    # Dutch
    'het', 'een', 'van', 'zijn', 'dat', 'niet', 'maar', 'voor', 'hebben',
]


def _is_likely_english_or_spanish(text: str, subreddit: str = "") -> bool:
    """
    Check if text is likely English or Spanish.
    Returns False for clearly non-English content.
    """
    # Check subreddit for language indicators
    if subreddit:
        subreddit_upper = subreddit.upper()
        subreddit_lower = subreddit.lower()
        for pattern in NON_ENGLISH_SUBREDDIT_PATTERNS:
            if subreddit_upper.endswith(pattern.upper()) or pattern.lower() in subreddit_lower:
                return False

    # Check text for non-English indicators
    if text:
        text_lower = text.lower()
        words = set(text_lower.split())
        # If text contains multiple non-English indicator words, it's likely not English
        non_english_count = sum(1 for word in NON_ENGLISH_INDICATORS if word in words)
        if non_english_count >= 3:
            return False

    return True


def _extract_best_permalink(html_block: str, keyword: str = "") -> tuple[str, str]:
    """
    Extract the permalink for the comment that contains the keyword.

    If keyword is provided, tries to find the permalink closest to where
    the keyword appears in the HTML. Otherwise falls back to longest permalink.

    Returns (permalink, subreddit).
    """
    # Find all permalinks in the block with their positions
    all_matches = list(re.finditer(
        r'href="(/r/([A-Za-z0-9_]+)/comments/[A-Za-z0-9]+/[^"]*)"',
        html_block
    ))

    if not all_matches:
        return "", ""

    # If we have a keyword, find where it appears in the HTML and pick the closest permalink
    if keyword:
        keyword_lower = keyword.lower()
        # Find keyword position in the text (search in lowercase)
        keyword_pos = html_block.lower().find(keyword_lower)

        if keyword_pos != -1:
            # Find the permalink closest to (and before) the keyword
            # This is because Reddit usually puts the permalink link before or near the comment text
            best_match = None
            best_distance = float('inf')

            for match in all_matches:
                permalink = match.group(1)
                # Only consider comment-level permalinks (7+ segments)
                if permalink.count('/') >= 6:
                    pos = match.start()
                    # Prefer permalinks that appear before the keyword (context usually comes first)
                    distance = abs(keyword_pos - pos)
                    if distance < best_distance:
                        best_distance = distance
                        best_match = match

            if best_match:
                return best_match.group(1).rstrip('/'), best_match.group(2)

    # Fallback: sort by length (longer = more specific = comment-level)
    matches_list = [(m.group(1), m.group(2)) for m in all_matches]
    matches_list.sort(key=lambda x: len(x[0]), reverse=True)

    # Return the longest (most specific) permalink
    return matches_list[0][0].rstrip('/'), matches_list[0][1]


def _parse_relative_time(time_str):
    """Parse Reddit's relative time strings like '2 hours ago', '3 days ago'.

    Returns a datetime object, or None if parsing fails.
    """
    if not time_str:
        return None

    time_str = time_str.lower().strip()
    now = datetime.now()

    patterns = [
        (r'(\d+)\s*(?:second|sec)s?\s*ago', 'seconds'),
        (r'(\d+)\s*(?:minute|min)s?\s*ago', 'minutes'),
        (r'(\d+)\s*(?:hour|hr)s?\s*ago', 'hours'),
        (r'(\d+)\s*days?\s*ago', 'days'),
        (r'(\d+)\s*weeks?\s*ago', 'weeks'),
        (r'(\d+)\s*months?\s*ago', 'months'),
        (r'(\d+)\s*years?\s*ago', 'years'),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, time_str)
        if match:
            value = int(match.group(1))
            if unit == 'seconds':
                return now - timedelta(seconds=value)
            elif unit == 'minutes':
                return now - timedelta(minutes=value)
            elif unit == 'hours':
                return now - timedelta(hours=value)
            elif unit == 'days':
                return now - timedelta(days=value)
            elif unit == 'weeks':
                return now - timedelta(weeks=value)
            elif unit == 'months':
                return now - timedelta(days=value * 30)  # Approximate
            elif unit == 'years':
                return now - timedelta(days=value * 365)  # Approximate

    return None


def _is_post_too_old(post_time, max_age_days=MAX_POST_AGE_DAYS):
    """Check if a post is older than the maximum allowed age.

    Args:
        post_time: datetime object or relative time string
        max_age_days: maximum age in days

    Returns True if post is too old, False otherwise.
    """
    if post_time is None:
        return False  # If we can't determine age, include it

    if isinstance(post_time, str):
        post_time = _parse_relative_time(post_time)

    if post_time is None:
        return False

    age = datetime.now() - post_time
    return age.days > max_age_days


async def search_comments(page, keyword, config, target_fresh=TARGET_FRESH_LEADS):
    """Search Reddit for a keyword, extract leads from Comments tab.

    Scrolls until we have target_fresh untouched leads OR no more results.
    Only returns leads that can be engaged (not already contacted).

    Returns list of lead dicts (only fresh/engageable leads).
    """
    fresh_leads = []
    seen_usernames = set()
    max_age_days = config.get("search", {}).get("max_post_age_days", MAX_POST_AGE_DAYS)
    max_scrolls = 10  # Safety limit

    try:
        # Navigate to search
        encoded = keyword.replace(" ", "+")
        url = f"https://www.reddit.com/search/?q={encoded}&type=comment&sort=new"
        print(f"[SEARCH] Navigating to: {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

        # Scroll until we have enough fresh leads
        scroll_count = 0
        last_lead_count = 0
        stale_scrolls = 0

        while len(fresh_leads) < target_fresh and scroll_count < max_scrolls:
            scroll_count += 1
            print(f"[SEARCH] Scrolling... ({scroll_count}/{max_scrolls}) - {len(fresh_leads)} fresh leads so far")
            await page.scroll_down(2000)
            await asyncio.sleep(2)

            # Extract all leads from current page state
            all_leads = await _extract_leads_from_page(page, keyword, seen_usernames, max_age_days)

            # Filter to only fresh leads (not already engaged)
            for lead in all_leads:
                username = lead.get("username", "")
                if username.lower() not in [l["username"].lower() for l in fresh_leads]:
                    if can_engage_user(username):
                        fresh_leads.append(lead)

            # Check if we're getting new results
            if len(fresh_leads) == last_lead_count:
                stale_scrolls += 1
                if stale_scrolls >= 2:
                    print(f"[SEARCH] No new fresh leads after {stale_scrolls} scrolls, stopping")
                    break
            else:
                stale_scrolls = 0
                last_lead_count = len(fresh_leads)

        print(f"[SEARCH] Found {len(fresh_leads)} fresh leads for '{keyword}' (after {scroll_count} scrolls)")

    except Exception as e:
        print(f"[SEARCH] Error searching '{keyword}': {e}")
        await take_error_screenshot(page, f"search_{keyword.replace(' ', '_')}")

    return fresh_leads[:target_fresh]  # Cap at target


async def search_posts(page, keyword, config):
    """Search Reddit for a keyword, extract leads from Posts tab.

    Returns list of lead dicts.
    """
    leads = []
    seen_usernames = set()
    max_age_days = config.get("search", {}).get("max_post_age_days", MAX_POST_AGE_DAYS)

    try:
        encoded = keyword.replace(" ", "+")
        url = f"https://www.reddit.com/search/?q={encoded}&type=link&sort=new"
        print(f"[SEARCH] Navigating to posts: {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

        # Scroll
        for i in range(3):
            await page.scroll_down(2000)
            await asyncio.sleep(2)

        leads = await _extract_post_leads_from_page(page, keyword, seen_usernames, max_age_days)
        print(f"[SEARCH] Found {len(leads)} post leads for '{keyword}' (max age: {max_age_days} days)")

    except Exception as e:
        print(f"[SEARCH] Error searching posts '{keyword}': {e}")
        await take_error_screenshot(page, f"search_posts_{keyword.replace(' ', '_')}")

    return leads


async def _extract_leads_from_page(page, keyword, seen_usernames, max_age_days=MAX_POST_AGE_DAYS):
    """Extract lead data from comment search results page.

    This is the exploratory part we parse the HTML to find usernames,
    subreddits, comment text, and permalinks.
    """
    leads = []

    try:
        html = await page.get_content()

        # Find comment result blocks
        # Reddit comment search results typically have patterns like:
        # - u/username links
        # - r/subreddit links
        # - Comment text
        # - Permalink/thread links

        # Extract all u/username patterns
        usernames = re.findall(r'(?:href=")?/user/([A-Za-z0-9_-]+)', html)
        # Extract all r/subreddit patterns
        subreddits = re.findall(r'/r/([A-Za-z0-9_]+)', html)

        # Try to extract comment blocks with more structure
        # Look for comment result containers
        # Reddit search results have comment-id patterns
        comment_blocks = re.findall(
            r'<faceplate-search-partial[^>]*>.*?</faceplate-search-partial>',
            html, re.DOTALL
        )

        if comment_blocks:
            for block in comment_blocks:
                lead = _parse_comment_block(block, keyword, max_age_days)
                if lead and lead["username"] not in seen_usernames:
                    seen_usernames.add(lead["username"])
                    leads.append(lead)
        else:
            # Fallback: try to find shreddit-comment elements
            comment_blocks = re.findall(
                r'<shreddit-comment[^>]*>.*?</shreddit-comment>',
                html, re.DOTALL
            )

            if comment_blocks:
                for block in comment_blocks:
                    lead = _parse_comment_block(block, keyword, max_age_days)
                    if lead and lead["username"] not in seen_usernames:
                        seen_usernames.add(lead["username"])
                        leads.append(lead)

        # If structured parsing didn't work, fall back to basic extraction
        if not leads:
            print("[SEARCH] Structured parsing didn't find blocks, trying basic extraction...")
            leads = _basic_extraction(html, keyword, seen_usernames, max_age_days)

    except Exception as e:
        print(f"[SEARCH] Extraction error: {e}")

    return leads


def _parse_comment_block(block_html, keyword, max_age_days=MAX_POST_AGE_DAYS):
    """Parse a single comment result block to extract lead data."""
    try:
        # Extract username
        username_match = re.search(r'/user/([A-Za-z0-9_-]+)', block_html)
        if not username_match:
            return None
        username = username_match.group(1)

        # Skip bot/automoderator
        if username.lower() in ("automoderator", "bot", "[deleted]"):
            return None

        # Extract timestamp - look for relative time patterns
        time_match = re.search(r'(\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s*ago)', block_html, re.IGNORECASE)
        post_time_str = time_match.group(1) if time_match else None

        # Filter out old posts
        if _is_post_too_old(post_time_str, max_age_days):
            return None

        # Extract subreddit
        subreddit_match = re.search(r'/r/([A-Za-z0-9_]+)', block_html)
        subreddit = subreddit_match.group(1) if subreddit_match else ""

        # Extract permalink - find the one closest to the keyword
        permalink, _ = _extract_best_permalink(block_html, keyword)
        if not permalink:
            permalink_match = re.search(r'href="(/r/[^"]+/comments/[^"]+)"', block_html)
            permalink = permalink_match.group(1) if permalink_match else ""

        # Extract comment ID from permalink
        comment_id = _extract_comment_id(permalink)

        # Extract comment text (strip HTML tags)
        text_clean = re.sub(r'<[^>]+>', ' ', block_html)
        text_clean = re.sub(r'\s+', ' ', text_clean).strip()
        # Try to get just the comment body skip metadata
        comment_text = text_clean[:500]

        # Filter out non-English/Spanish content
        if not _is_likely_english_or_spanish(comment_text, subreddit):
            return None

        # Check if keyword is confirmed in this specific comment
        keyword_confirmed = _is_keyword_in_text(keyword, comment_text)

        return {
            "username": username,
            "comment_text": comment_text,
            "subreddit": subreddit,
            "comment_id": comment_id,
            "keyword_confirmed": keyword_confirmed,
            "permalink": permalink,
            "post_title": "",
            "keyword_matched": keyword,
            "found_at": datetime.now().isoformat(),
            "post_age": post_time_str,
            "source": "comment_search"
        }
    except Exception:
        return None


def _basic_extraction(html, keyword, seen_usernames, max_age_days=MAX_POST_AGE_DAYS):
    """Extract leads from search results by parsing search-telemetry-tracker blocks.

    Each comment result is wrapped in a search-telemetry-tracker element containing
    the user, subreddit, and comment text in a structured way.
    """
    leads = []
    skipped_old = 0

    # Find all search result blocks (separated by <hr> dividers)
    # Each block contains: user info, comment text, and permalink

    # Split by the comment unit marker
    comment_units = re.split(r'data-testid="search-sdui-comment-unit"', html)

    for unit in comment_units[1:]:  # Skip first segment (before first result)
        try:
            # Extract timestamp - look for relative time patterns
            time_match = re.search(r'(\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s*ago)', unit, re.IGNORECASE)
            post_time_str = time_match.group(1) if time_match else None

            # Filter out old posts
            if _is_post_too_old(post_time_str, max_age_days):
                skipped_old += 1
                continue

            # Extract username from the faceplate-hovercard for user
            # Pattern: label="username details"
            user_match = re.search(r'label="([A-Za-z0-9_-]+) details"', unit)
            if not user_match:
                # Try alternate pattern
                user_match = re.search(r'href="/user/([A-Za-z0-9_-]+)/"', unit)

            if not user_match:
                continue

            username = user_match.group(1)

            if username.lower() in ("automoderator", "bot", "[deleted]"):
                continue
            if username in seen_usernames:
                continue

            # Extract comment text from the comment content div
            # Pattern: <div id="search-comment-...-post-rtjson-content" ...>text</div>
            comment_match = re.search(
                r'id="search-comment-[^"]*-post-rtjson-content"[^>]*>(.*?)</div>',
                unit, re.DOTALL
            )
            comment_text = ""
            if comment_match:
                # Strip HTML tags from comment
                comment_text = re.sub(r'<[^>]+>', ' ', comment_match.group(1))
                comment_text = re.sub(r'\s+', ' ', comment_text).strip()[:500]

            # Extract permalink - find the one closest to the keyword
            permalink, subreddit = _extract_best_permalink(unit, keyword)

            if not permalink:
                continue

            # Filter out non-English/Spanish content
            if not _is_likely_english_or_spanish(comment_text, subreddit):
                continue

            # Extract comment ID from permalink
            comment_id = _extract_comment_id(permalink)

            # Check if keyword is confirmed in this specific comment
            keyword_confirmed = _is_keyword_in_text(keyword, comment_text)

            seen_usernames.add(username)
            leads.append({
                "username": username,
                "comment_text": comment_text,
                "subreddit": subreddit,
                "comment_id": comment_id,
                "keyword_confirmed": keyword_confirmed,
                "permalink": permalink,
                "post_title": "",
                "keyword_matched": keyword,
                "found_at": datetime.now().isoformat(),
                "post_age": post_time_str,
                "source": "comment_search"
            })

        except Exception as e:
            continue

    if skipped_old > 0:
        print(f"[SEARCH] Skipped {skipped_old} posts older than {max_age_days} days")

    return leads


async def _extract_post_leads_from_page(page, keyword, seen_usernames, max_age_days=MAX_POST_AGE_DAYS):
    """Extract leads from post search results."""
    leads = []
    skipped_old = 0

    try:
        html = await page.get_content()

        # Find post blocks with author and subreddit info
        segments = html.split('/user/')
        for i, segment in enumerate(segments[1:], 1):
            username_match = re.match(r'([A-Za-z0-9_-]+)', segment)
            if not username_match:
                continue
            username = username_match.group(1)
            if username.lower() in ("automoderator", "bot", "[deleted]"):
                continue
            if username in seen_usernames:
                continue

            context = segments[max(0, i - 1)] + segment[:3000]

            # Extract timestamp
            time_match = re.search(r'(\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s*ago)', context, re.IGNORECASE)
            post_time_str = time_match.group(1) if time_match else None

            # Filter out old posts
            if _is_post_too_old(post_time_str, max_age_days):
                skipped_old += 1
                continue

            subreddit_match = re.search(r'/r/([A-Za-z0-9_]+)', context)
            permalink_match = re.search(r'(/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+[^"\'>\s]*)', context)

            # Try to get post title
            title_match = re.search(r'aria-label="([^"]+)"', context)
            post_title = title_match.group(1) if title_match else ""

            seen_usernames.add(username)
            leads.append({
                "username": username,
                "comment_text": "",
                "subreddit": subreddit_match.group(1) if subreddit_match else "",
                "permalink": permalink_match.group(1) if permalink_match else "",
                "post_title": post_title,
                "keyword_matched": keyword,
                "found_at": datetime.now().isoformat(),
                "post_age": post_time_str,
                "source": "post_search"
            })

    except Exception as e:
        print(f"[SEARCH] Post extraction error: {e}")

    if skipped_old > 0:
        print(f"[SEARCH] Skipped {skipped_old} posts older than {max_age_days} days")

    return leads


async def explore_search_page(page, keyword, config):
    """Exploratory function for Phase 2 testing.

    Prints everything we can find on the search results page.
    """
    encoded = keyword.replace(" ", "+")
    url = f"https://www.reddit.com/search/?q={encoded}&type=comment&sort=new"
    print(f"\n[EXPLORE] Navigating to: {url}")
    await page.get(url)
    await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 2)

    # 1. Get raw HTML
    html = await page.get_content()
    print(f"\n[EXPLORE] Page HTML length: {len(html)} chars")
    # Save first 5000 chars for inspection
    print(f"\n[EXPLORE] First 2000 chars of HTML:")
    print(html[:2000])

    # 2. Find all links
    print(f"\n[EXPLORE] Looking for all links...")
    try:
        links = await page.select_all("a")
        print(f"[EXPLORE] Found {len(links)} links")
        for link in links[:30]:
            href = link.attrs.get("href", "")
            text = link.text or ""
            if href and ("/user/" in href or "/r/" in href or "/comments/" in href):
                print(f"  {text[:50]:50s} → {href}")
    except Exception as e:
        print(f"[EXPLORE] Link extraction error: {e}")

    # 3. Find usernames
    print(f"\n[EXPLORE] Searching for 'u/' patterns...")
    usernames = re.findall(r'/user/([A-Za-z0-9_-]+)', html)
    unique_users = list(dict.fromkeys(usernames))  # dedup preserving order
    print(f"[EXPLORE] Found {len(unique_users)} unique usernames:")
    for u in unique_users[:20]:
        print(f"  u/{u}")

    # 4. Find subreddits
    subreddits = re.findall(r'/r/([A-Za-z0-9_]+)', html)
    unique_subs = list(dict.fromkeys(subreddits))
    print(f"\n[EXPLORE] Found {len(unique_subs)} unique subreddits:")
    for s in unique_subs[:20]:
        print(f"  r/{s}")

    # 5. Find permalinks
    permalinks = re.findall(r'/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+[^"\'>\s]*', html)
    unique_permas = list(dict.fromkeys(permalinks))
    print(f"\n[EXPLORE] Found {len(unique_permas)} permalinks:")
    for p in unique_permas[:10]:
        print(f"  {p}")

    # 6. Try page.find for common elements
    for text in ["Comments", "New", "Go To Thread", "Reply"]:
        try:
            el = await page.find(text, best_match=True, timeout=3)
            if el:
                print(f"\n[EXPLORE] Found '{text}': {el.text[:100] if el.text else 'no text'}")
        except Exception:
            print(f"\n[EXPLORE] '{text}' not found")

    return html


def split_leads_by_keyword_confirmation(leads: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split leads into confirmed vs maybe based on keyword presence.

    Confirmed: Keyword is definitely in this specific comment's text
    Maybe: Keyword was in search but not confirmed in this comment (might be in thread title, parent, etc.)

    Returns: (confirmed_leads, maybe_leads)
    """
    confirmed = []
    maybe = []

    for lead in leads:
        if lead.get("keyword_confirmed", False):
            confirmed.append(lead)
        else:
            maybe.append(lead)

    return confirmed, maybe


def filter_leads_with_comment_id(leads: list[dict]) -> list[dict]:
    """
    Filter to only leads that have a valid comment ID (comment-level permalinks).

    This ensures we can reply directly to the specific comment.
    """
    return [lead for lead in leads if lead.get("comment_id")]
