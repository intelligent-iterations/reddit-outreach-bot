"""
Reddit API integration using PRAW for context enrichment and verification.

This module provides:
- Comment context fetching (parent comment, thread title)
- Comment verification (exists, not locked/archived)
- Comment ID extraction from permalinks

Note: We use PRAW for READ operations only. Write operations (posting comments)
are done via browser automation to avoid API rate limits on writes.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

import praw
from praw.exceptions import PRAWException


@dataclass
class CommentContext:
    """Rich context for a Reddit comment."""
    comment_id: str
    comment_body: str
    comment_author: str
    parent_id: str
    parent_body: str
    parent_author: str
    thread_title: str
    subreddit: str
    permalink: str
    is_locked: bool
    is_archived: bool
    is_top_level: bool  # True if replying to post, not another comment
    verified: bool  # True if we successfully fetched and verified


@dataclass
class VerificationResult:
    """Result of verifying a lead before engagement."""
    valid: bool
    reason: str
    context: Optional[CommentContext] = None


_reddit_client: Optional[praw.Reddit] = None


def _get_client() -> praw.Reddit:
    """Get or create Reddit API client."""
    global _reddit_client

    if _reddit_client is None:
        # PRAW can work in read-only mode without full OAuth
        # For read-only, we just need client_id and client_secret
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        user_agent = os.environ.get("REDDIT_USER_AGENT", "pom-app-bot/1.0")

        if client_id and client_secret:
            _reddit_client = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
        else:
            # Read-only mode without credentials (limited functionality)
            _reddit_client = praw.Reddit(
                client_id="",
                client_secret="",
                user_agent=user_agent,
            )
            print("[REDDIT_API] Warning: No API credentials, using limited read-only mode")

    return _reddit_client


def extract_comment_id(permalink: str) -> Optional[str]:
    """
    Extract comment ID from a Reddit permalink.

    Comment permalinks have format: /r/sub/comments/postid/title/commentid/
    Returns None if permalink is post-level (no comment ID).
    """
    # Remove trailing slash and split
    parts = permalink.rstrip('/').split('/')

    # Comment permalink: ['', 'r', 'sub', 'comments', 'postid', 'title', 'commentid']
    # Post permalink: ['', 'r', 'sub', 'comments', 'postid', 'title']
    if len(parts) >= 7 and parts[3] == 'comments':
        return parts[6]

    return None


def extract_post_id(permalink: str) -> Optional[str]:
    """Extract post ID from a Reddit permalink."""
    parts = permalink.rstrip('/').split('/')

    if len(parts) >= 5 and parts[3] == 'comments':
        return parts[4]

    return None


def get_comment_context(permalink: str) -> Optional[CommentContext]:
    """
    Fetch full context for a comment using PRAW API.

    Returns CommentContext with parent comment, thread title, etc.
    Returns None if comment cannot be fetched.
    """
    comment_id = extract_comment_id(permalink)

    if not comment_id:
        print(f"[REDDIT_API] No comment ID in permalink: {permalink}")
        return None

    try:
        reddit = _get_client()
        comment = reddit.comment(id=comment_id)

        # Force fetch the comment data
        comment._fetch()

        # Get comment details
        comment_body = comment.body or ""
        comment_author = comment.author.name if comment.author else "[deleted]"

        # Get parent info
        parent = comment.parent()
        is_top_level = isinstance(parent, praw.models.Submission)

        if is_top_level:
            # Parent is the post itself
            parent_id = parent.id
            parent_body = parent.selftext or parent.title
            parent_author = parent.author.name if parent.author else "[deleted]"
            thread_title = parent.title
        else:
            # Parent is another comment
            parent._fetch()
            parent_id = parent.id
            parent_body = parent.body or ""
            parent_author = parent.author.name if parent.author else "[deleted]"
            # Get thread title from submission
            thread_title = comment.submission.title

        # Check locked/archived status
        submission = comment.submission
        is_locked = getattr(comment, 'locked', False) or getattr(submission, 'locked', False)
        is_archived = getattr(submission, 'archived', False)

        return CommentContext(
            comment_id=comment_id,
            comment_body=comment_body,
            comment_author=comment_author,
            parent_id=parent_id,
            parent_body=parent_body,
            parent_author=parent_author,
            thread_title=thread_title,
            subreddit=comment.subreddit.display_name,
            permalink=comment.permalink,
            is_locked=is_locked,
            is_archived=is_archived,
            is_top_level=is_top_level,
            verified=True,
        )

    except PRAWException as e:
        print(f"[REDDIT_API] PRAW error fetching comment {comment_id}: {e}")
        return None
    except Exception as e:
        print(f"[REDDIT_API] Error fetching comment {comment_id}: {e}")
        return None


def verify_lead(
    permalink: str,
    expected_username: str,
    expected_keyword: str,
) -> VerificationResult:
    """
    Verify a lead is valid before engagement.

    Checks:
    1. Comment exists and is accessible
    2. Comment author matches expected username
    3. Comment contains the expected keyword
    4. Comment is not locked or archived

    Returns VerificationResult with context if valid.
    """
    context = get_comment_context(permalink)

    if context is None:
        return VerificationResult(
            valid=False,
            reason="Could not fetch comment context",
        )

    # Check author matches
    if context.comment_author.lower() != expected_username.lower():
        return VerificationResult(
            valid=False,
            reason=f"Author mismatch: expected {expected_username}, got {context.comment_author}",
            context=context,
        )

    # Check keyword in comment
    if expected_keyword.lower() not in context.comment_body.lower():
        return VerificationResult(
            valid=False,
            reason=f"Keyword '{expected_keyword}' not in comment body",
            context=context,
        )

    # Check not locked/archived
    if context.is_locked:
        return VerificationResult(
            valid=False,
            reason="Comment or thread is locked",
            context=context,
        )

    if context.is_archived:
        return VerificationResult(
            valid=False,
            reason="Thread is archived",
            context=context,
        )

    return VerificationResult(
        valid=True,
        reason="Verified",
        context=context,
    )


def enrich_leads_with_context(leads: list[dict]) -> list[dict]:
    """
    Enrich a list of leads with full comment context.

    Adds to each lead:
    - parent_body: Text of parent comment
    - parent_author: Author of parent comment
    - thread_title: Title of the thread
    - is_top_level: Whether comment is top-level
    - context_verified: Whether we successfully fetched context

    Leads that fail verification are marked but kept for fallback.
    """
    enriched = []

    for lead in leads:
        permalink = lead.get("permalink", "")

        context = get_comment_context(permalink)

        if context:
            lead["parent_body"] = context.parent_body[:500]  # Limit size
            lead["parent_author"] = context.parent_author
            lead["thread_title"] = context.thread_title
            lead["is_top_level"] = context.is_top_level
            lead["is_locked"] = context.is_locked
            lead["is_archived"] = context.is_archived
            lead["context_verified"] = True
            lead["full_comment_body"] = context.comment_body
        else:
            # Mark as unverified but keep for potential fallback
            lead["parent_body"] = ""
            lead["parent_author"] = ""
            lead["thread_title"] = ""
            lead["is_top_level"] = True
            lead["is_locked"] = False
            lead["is_archived"] = False
            lead["context_verified"] = False
            lead["full_comment_body"] = lead.get("comment_text", "")

        enriched.append(lead)

    return enriched


def check_keyword_in_comment(lead: dict) -> bool:
    """
    Check if the keyword is actually in the comment text (not just the thread).

    Returns True if keyword is confirmed in the comment body.
    """
    keyword = lead.get("keyword_matched", "").lower()
    comment_text = lead.get("comment_text", "").lower()
    full_body = lead.get("full_comment_body", "").lower()

    # Check both scraped text and full body (if available)
    return keyword in comment_text or keyword in full_body
