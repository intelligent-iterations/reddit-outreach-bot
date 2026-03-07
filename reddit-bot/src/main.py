"""
Main entry point for Reddit outreach bot.

Coordinates:
- Loading configuration
- Running sessions for each account sequentially
- Searching for leads per strategy
- Triaging leads via Grok 4 (or falling back to keyword matching)
- Posting comments and sending DMs
- Rate limiting and state management
- Per-run data logging
"""

import argparse
import asyncio

from src.auth import login
from src.comment import post_comment
from src.dm import send_dm
from src.models import ActionResult, ActionType, ClaimStatus, Lead
from src.rate_limiter import RateLimiter
from src.run_logger import RunLogger
from src.search import search_comments, split_leads_by_keyword_confirmation
from src.state import (
    can_comment_in_thread,
    claim_user,
    claim_thread,
    record_action,
    save_lead,
    get_stats,
)
from src.templates import select_and_fill, fill_template_from_decision, fill_subject_from_decision
from src.triage import triage_leads, full_triage_workflow
from src.utils import load_config, load_templates, take_error_screenshot, BASE_DIR, log


def deduplicate_leads(leads: list[dict]) -> list[dict]:
    """Remove duplicate usernames from leads list (case-insensitive)."""
    seen = set()
    unique = []
    for lead in leads:
        key = lead["username"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


async def handle_comment(
    browser,
    page,
    lead: dict,
    account_name: str,
    config: dict,
    templates: dict,
    dry_run: bool,
    filled_message: str | None = None,
    archetype: str | None = None,
    verify_keyword: str | None = None,
    verify_username: str | None = None,
):
    """
    Handle comment logic for a single lead.

    If filled_message is provided (from Grok triage), use it directly.
    Otherwise fall back to keyword-based template selection.

    Returns: (new_page, success: bool)
    """
    username = lead.get("username", "")
    permalink = lead.get("permalink", "")

    if not permalink:
        return page, False

    # Extract post_id for thread tracking
    post_id = None
    parts = permalink.split('/comments/')
    if len(parts) > 1:
        post_id = parts[1].split('/')[0]

    # Generate comment from template (or use pre-filled)
    if filled_message:
        filled_comment = filled_message
    else:
        filled_comment, archetype, _ = select_and_fill(lead, "comment", templates, config)

    if not filled_comment:
        return page, False

    if dry_run:
        print(f"\n[DRY RUN] Would comment on {permalink}:")
        print(f"  Account: {account_name}")
        print(f"  Archetype: {archetype or 'grok-selected'}")
        print(f"  Body: {filled_comment[:200]}...")
        # Still claim to prevent other accounts in dry run
        claim_user(username, account_name)
        if post_id:
            claim_thread(post_id, account_name, permalink)
        record_action(
            username=username,
            account=account_name,
            action_type=ActionType.COMMENT,
            result=ActionResult.SUCCESS,
            target=permalink,
            message_preview=filled_comment,
        )
        return page, True

    # Actually post the comment
    page, result = await post_comment(
        browser, page, permalink, filled_comment, config,
        verify_keyword=verify_keyword,
        verify_username=verify_username,
    )

    # Record the action
    record_action(
        username=username,
        account=account_name,
        action_type=ActionType.COMMENT,
        result=result,
        target=permalink,
        message_preview=filled_comment,
    )

    # Claim thread on any attempt to prevent cross-account spam
    if post_id:
        claim_thread(post_id, account_name, permalink)

    return page, result == ActionResult.SUCCESS


async def handle_dm(
    browser,
    page,
    lead: dict,
    account_name: str,
    config: dict,
    templates: dict,
    dry_run: bool,
    filled_message: str | None = None,
    subject: str | None = None,
    archetype: str | None = None,
):
    """
    Handle DM logic for a single lead.

    If filled_message is provided (from Grok triage), use it directly.
    Otherwise fall back to keyword-based template selection.

    Returns: (new_page, result: ActionResult)
    """
    username = lead.get("username", "")

    # Generate DM from template (or use pre-filled)
    if filled_message:
        filled_dm = filled_message
        subject = subject or "hey"
    else:
        filled_dm, archetype, subject = select_and_fill(lead, "dm", templates, config)

    if not filled_dm:
        return page, ActionResult.FAILED

    if dry_run:
        print(f"\n[DRY RUN] Would DM u/{username}:")
        print(f"  Account: {account_name}")
        print(f"  Subject: {subject}")
        print(f"  Archetype: {archetype or 'grok-selected'}")
        print(f"  Body: {filled_dm[:200]}...")
        record_action(
            username=username,
            account=account_name,
            action_type=ActionType.DM,
            result=ActionResult.SUCCESS,
            target=username,
            message_preview=filled_dm,
        )
        return page, ActionResult.SUCCESS

    # Actually send the DM
    page, result = await send_dm(browser, page, username, subject or "hey", filled_dm, config)

    # Record the action
    record_action(
        username=username,
        account=account_name,
        action_type=ActionType.DM,
        result=result,
        target=username,
        message_preview=filled_dm,
    )

    return page, result


async def run_strategy_with_triage(
    browser,
    page,
    strategy_name: str,
    strategy_config: dict,
    strategy_templates: dict,
    account: dict,
    config: dict,
    rate_limiter: RateLimiter,
    run_logger: RunLogger,
    dry_run: bool,
    max_dms: int | None,
    max_comments: int | None,
    keywords_override: list[str] | None,
):
    """Run a single strategy using iterative search+triage+execute cycles."""
    acct_name = account["username"]
    strategy_keywords = list(keywords_override or strategy_config["keywords"])
    allowed_actions = strategy_config.get("allowed_actions", ["comment"])
    grok_config = config.get("grok", {})

    total_dms_sent = 0
    total_comments_posted = 0
    consecutive_failures = 0
    max_failures = config.get("max_consecutive_failures", 5)

    # Calculate quotas
    todays_limits = rate_limiter.get_todays_limits()
    comment_quota = max_comments if max_comments is not None else todays_limits.get("max_comments", 15)
    dm_quota = max_dms if max_dms is not None else todays_limits.get("max_dms", 10)

    log.header(f"STRATEGY: {strategy_name}")
    log.stat("Comment quota", comment_quota)
    log.stat("DM quota", dm_quota)
    log.stat("Available keywords", len(strategy_keywords))

    keyword_index = 0
    cycle = 0
    leads_per_cycle = 30  # Search for ~30 leads per cycle

    # ════════════════════════════════════════════════════════════════════
    # ITERATIVE CYCLE: Search → Triage → Execute → Repeat
    # ════════════════════════════════════════════════════════════════════
    while keyword_index < len(strategy_keywords):
        # Check if quota already filled
        remaining_comments = comment_quota - total_comments_posted
        remaining_dms = dm_quota - total_dms_sent

        if remaining_comments <= 0 and remaining_dms <= 0:
            log.success(f"Daily quota filled! ({total_comments_posted} comments, {total_dms_sent} DMs)")
            break

        if consecutive_failures >= max_failures:
            log.error(f"Stopping after {max_failures} consecutive failures")
            break

        cycle += 1
        log.subheader(f"Cycle {cycle}: Search → Triage → Execute")
        log.stat("Remaining quota", f"{remaining_comments} comments, {remaining_dms} DMs")

        # ── SEARCH PHASE ──
        log.step("🔍", "Searching for leads...")
        cycle_leads = []
        keywords_this_cycle = 0

        while len(cycle_leads) < leads_per_cycle and keyword_index < len(strategy_keywords):
            keyword = strategy_keywords[keyword_index]
            keyword_index += 1
            keywords_this_cycle += 1

            log.step("🔎", f"Keyword: '{keyword}'", f"{keyword_index}/{len(strategy_keywords)}")
            leads = await search_comments(page, keyword, config)
            if leads:
                log.success(f"Found {len(leads)} comments")
                cycle_leads.extend(leads)
            else:
                log.info(f"No comments found")

            if len(cycle_leads) >= leads_per_cycle:
                break

            await rate_limiter.wait_between_searches()

        cycle_leads = deduplicate_leads(cycle_leads)

        if not cycle_leads:
            log.warning("No leads found this cycle, trying next keywords...")
            continue

        log.step("📊", f"Cycle {cycle}: {len(cycle_leads)} unique leads from {keywords_this_cycle} keywords")

        # Save leads
        for lead in cycle_leads:
            save_lead(Lead.from_dict(lead))
        run_logger.save_raw_leads(cycle_leads, f"{strategy_name}_cycle{cycle}")

        # ── TRIAGE PHASE ──
        log.step("🤖", "Triaging leads with Grok...")

        confirmed_leads, maybe_leads = split_leads_by_keyword_confirmation(cycle_leads)
        log.stat("Confirmed", len(confirmed_leads), log.GREEN)
        log.stat("Maybe", len(maybe_leads), log.YELLOW)

        triage_result = full_triage_workflow(
            confirmed_leads=confirmed_leads,
            maybe_leads=maybe_leads,
            strategy_config=strategy_config,
            strategy_templates=strategy_templates,
            grok_config=grok_config,
            enrich_context=True,
        )
        run_logger.save_triage_result(triage_result, f"{strategy_name}_cycle{cycle}")
        # Also save discovery result separately for easy debugging
        if triage_result.discovery_result:
            run_logger.save_discovery_result(triage_result.discovery_result, f"{strategy_name}_cycle{cycle}")

        log.grok_response(len(triage_result.approved), len(triage_result.denied))

        if not triage_result.approved:
            log.warning("No leads approved this cycle, continuing...")
            continue

        log.success(f"{len(triage_result.approved)} leads approved for engagement")

        # ── EXECUTE PHASE ──
        log.step("🚀", "Executing approved actions...")

        for action_idx, decision in enumerate(triage_result.approved):
            # Check quota before each action
            remaining_comments = comment_quota - total_comments_posted
            remaining_dms = dm_quota - total_dms_sent

            if remaining_comments <= 0 and remaining_dms <= 0:
                log.success(f"Quota filled! Stopping execution.")
                break

            if consecutive_failures >= max_failures:
                log.error(f"Stopping after {max_failures} consecutive failures")
                break

            # Use triage_result.leads (the candidates array) for correct index lookup
            lead = triage_result.leads[decision.lead_index]
            username = lead.get("username", "")
            permalink = lead.get("permalink", "")
            subreddit = lead.get("subreddit", "?")

            log.step("👤", f"Action {action_idx + 1}/{len(triage_result.approved)}", f"u/{username} in r/{subreddit}")

            # Extract post_id
            post_id = None
            if permalink:
                parts = permalink.split('/comments/')
                if len(parts) > 1:
                    post_id = parts[1].split('/')[0]

            # Claim user atomically
            claim_status = claim_user(username, acct_name)
            if claim_status == ClaimStatus.ALREADY_CLAIMED:
                log.warning(f"SKIP u/{username} — claimed by another account")
                continue
            elif claim_status == ClaimStatus.ALREADY_CONTACTED:
                log.warning(f"SKIP u/{username} — already contacted")
                continue

            # Fill template from Grok's decision
            filled_message = fill_template_from_decision(decision, strategy_templates)
            if not filled_message:
                log.error(f"Failed to fill template for u/{username}")
                run_logger.log_error(
                    f"template_fill:{username}",
                    f"Could not fill {decision.template_name}[{decision.template_variation}]"
                )
                continue

            # Execute based on action type
            if decision.action_type == "comment":
                if remaining_comments <= 0:
                    log.warning(f"Comment quota reached, skipping")
                    continue

                if post_id and not can_comment_in_thread(post_id):
                    log.warning(f"SKIP thread {post_id} — already commented")
                    continue

                # Extract verification keyword from decision placeholders
                verify_keyword = None
                if decision.placeholders:
                    verify_keyword = decision.placeholders.get("ingredient")

                log.action("comment", f"u/{username} ({decision.template_name})")

                # In dry-run mode, show what would be posted
                if dry_run:
                    print(f"\n{'='*60}")
                    print(f"[DRY RUN] Would comment to: u/{username}")
                    print(f"[DRY RUN] Subreddit: r/{subreddit}")
                    print(f"[DRY RUN] Permalink: {permalink}")
                    print(f"[DRY RUN] Template: {decision.template_name}")
                    print(f"[DRY RUN] Message preview:")
                    print(f"---")
                    print(filled_message)
                    print(f"---")
                    # Check for unfilled placeholders
                    import re
                    unfilled = re.findall(r'\{(\w+)\}', filled_message)
                    if unfilled:
                        print(f"[DRY RUN] ⚠️ WARNING: UNFILLED PLACEHOLDERS: {unfilled}")
                    print(f"{'='*60}\n")

                page, success = await handle_comment(
                    browser, page, lead, acct_name, config, {},
                    dry_run, filled_message=filled_message, archetype=decision.template_name,
                    verify_keyword=verify_keyword, verify_username=username,
                )

                run_logger.log_action(
                    username=username,
                    action_type="comment",
                    result="success" if success else "failed",
                    template_name=decision.template_name,
                    filled_message=filled_message,
                    permalink=permalink,
                    strategy=strategy_name,
                )

                if success:
                    log.success(f"Comment posted to u/{username}")
                    total_comments_posted += 1
                    consecutive_failures = 0
                    log.progress(total_comments_posted, comment_quota, "comments")
                    wait_time = await rate_limiter.wait_between_actions()
                    if wait_time > 5:
                        log.wait(wait_time, "rate limit avoidance")
                else:
                    log.error(f"Comment failed for u/{username}")
                    consecutive_failures += 1

            elif decision.action_type == "dm":
                if remaining_dms <= 0:
                    log.warning(f"DM quota reached, skipping")
                    continue

                subject = fill_subject_from_decision(decision, strategy_templates)

                log.action("dm", f"u/{username} ({decision.template_name})")

                page, result = await handle_dm(
                    browser, page, lead, acct_name, config, {},
                    dry_run, filled_message=filled_message, subject=subject,
                    archetype=decision.template_name
                )

                run_logger.log_action(
                    username=username,
                    action_type="dm",
                    result=result.value,
                    template_name=decision.template_name,
                    filled_message=filled_message,
                    permalink=permalink,
                    strategy=strategy_name,
                )

                if result == ActionResult.SUCCESS:
                    log.success(f"DM sent to u/{username}")
                    total_dms_sent += 1
                    consecutive_failures = 0
                    log.progress(total_dms_sent, dm_quota, "DMs")
                    wait_time = await rate_limiter.wait_between_dms()
                    if wait_time > 5:
                        log.wait(wait_time, "DM rate limit avoidance")
                elif result == ActionResult.RATE_LIMITED:
                    rate_limiter.stop_dms()
                    log.warning(f"DMs rate limited, continuing with comments only")
                elif result == ActionResult.SKIPPED:
                    log.info(f"DM skipped for u/{username}")
                else:
                    log.error(f"DM failed for u/{username}")
                    consecutive_failures += 1

        # End of cycle - show progress
        log.step("📈", f"Cycle {cycle} complete", f"{total_comments_posted}/{comment_quota} comments, {total_dms_sent}/{dm_quota} DMs")

    # Strategy complete summary
    log.subheader(f"Strategy '{strategy_name}' Complete")
    log.stat("Comments posted", total_comments_posted, log.GREEN if total_comments_posted > 0 else log.GRAY)
    log.stat("DMs sent", total_dms_sent, log.GREEN if total_dms_sent > 0 else log.GRAY)
    log.stat("Keywords used", keyword_index, log.CYAN)
    log.stat("Cycles completed", cycle)

    return page, total_dms_sent, total_comments_posted


async def run_strategy_no_triage(
    browser,
    page,
    strategy_name: str,
    strategy_config: dict,
    strategy_templates: dict,
    account: dict,
    config: dict,
    rate_limiter: RateLimiter,
    run_logger: RunLogger,
    dry_run: bool,
    max_dms: int | None,
    max_comments: int | None,
    keywords_override: list[str] | None,
):
    """Run a single strategy using old keyword-based matching (--no-triage fallback)."""
    acct_name = account["username"]
    strategy_keywords = keywords_override or strategy_config["keywords"]
    allowed_actions = strategy_config.get("allowed_actions", ["comment"])

    total_dms_sent = 0
    total_comments_posted = 0
    consecutive_failures = 0
    max_failures = config.get("max_consecutive_failures", 5)

    print(f"\n[{acct_name}] Strategy: {strategy_name} [NO TRIAGE] ({len(strategy_keywords)} keywords)")

    for keyword in strategy_keywords:
        if consecutive_failures >= max_failures:
            print(f"\n[{acct_name}] {max_failures} consecutive failures, stopping")
            break

        if (max_dms is not None and total_dms_sent >= max_dms) and \
           (max_comments is not None and total_comments_posted >= max_comments):
            break

        print(f"\n{'─' * 40}")
        print(f"[{acct_name}] Searching: '{keyword}'")
        print(f"[{acct_name}] {rate_limiter.status()}")

        leads = await search_comments(page, keyword, config)
        if not leads:
            await rate_limiter.wait_between_searches()
            continue

        leads = deduplicate_leads(leads)

        for lead in leads:
            if consecutive_failures >= max_failures:
                break

            username = lead["username"]
            permalink = lead.get("permalink", "")
            post_id = None
            if permalink:
                parts = permalink.split('/comments/')
                if len(parts) > 1:
                    post_id = parts[1].split('/')[0]

            save_lead(Lead.from_dict(lead))

            claim_status = claim_user(username, acct_name)
            if claim_status == ClaimStatus.ALREADY_CLAIMED:
                continue
            elif claim_status == ClaimStatus.ALREADY_CONTACTED:
                continue

            if post_id and not can_comment_in_thread(post_id):
                continue

            # Comment
            if "comment" in allowed_actions:
                can_comment_now = rate_limiter.can_comment() and \
                                  (max_comments is None or total_comments_posted < max_comments)

                if can_comment_now and permalink:
                    page, success = await handle_comment(
                        browser, page, lead, acct_name, config, strategy_templates, dry_run
                    )
                    if success:
                        total_comments_posted += 1
                        consecutive_failures = 0
                        await rate_limiter.wait_between_actions()
                    else:
                        consecutive_failures += 1

            # DM
            if "dm" in allowed_actions:
                can_dm_now = rate_limiter.can_dm() and \
                             (max_dms is None or total_dms_sent < max_dms)

                if can_dm_now:
                    page, result = await handle_dm(
                        browser, page, lead, acct_name, config, strategy_templates, dry_run
                    )
                    if result == ActionResult.SUCCESS:
                        total_dms_sent += 1
                        consecutive_failures = 0
                        await rate_limiter.wait_between_dms()
                    elif result == ActionResult.RATE_LIMITED:
                        rate_limiter.stop_dms()
                    elif result == ActionResult.SKIPPED:
                        pass
                    else:
                        consecutive_failures += 1

        await rate_limiter.wait_between_searches()

    return page, total_dms_sent, total_comments_posted


async def run_account_session(
    config: dict,
    account: dict,
    templates: dict,
    rate_limiter: RateLimiter,
    run_logger: RunLogger,
    dry_run: bool,
    max_dms: int | None,
    max_comments: int | None,
    keywords: list[str] | None,
    only_strategy: str | None,
    no_triage: bool,
):
    """Run a full session for one account. Opens and closes its own browser."""
    acct_name = account["username"]

    # Display account banner
    day_num = rate_limiter.get_day_number() if hasattr(rate_limiter, 'get_day_number') else "?"
    dm_status = rate_limiter.status().split("|")[0].strip() if rate_limiter.status() else "?"
    comment_status = rate_limiter.status().split("|")[1].strip() if "|" in rate_limiter.status() else "?"
    log.account_banner(acct_name, day_num, dm_status, comment_status)

    log.step("🔐", "Logging in to Reddit...")
    browser, page = await login(config, account, headless=False)
    log.success("Login successful")

    total_dms = 0
    total_comments = 0

    try:
        strategies = config.get("strategies", {})

        for strategy_name, strategy_config in strategies.items():
            if not strategy_config.get("enabled", True):
                continue

            if only_strategy and strategy_name != only_strategy:
                continue

            templates_key = strategy_config.get("templates_key", strategy_name)
            strategy_templates = templates.get(templates_key, {})

            if not strategy_templates:
                log.warning(f"No templates found for strategy '{templates_key}'")
                continue

            run_func = run_strategy_no_triage if no_triage else run_strategy_with_triage

            page, dms, comments = await run_func(
                browser, page,
                strategy_name, strategy_config, strategy_templates,
                account, config, rate_limiter, run_logger,
                dry_run, max_dms, max_comments, keywords,
            )

            total_dms += dms
            total_comments += comments

            # Adjust remaining limits
            if max_dms is not None:
                max_dms = max(0, max_dms - dms)
            if max_comments is not None:
                max_comments = max(0, max_comments - comments)

    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        raise
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        run_logger.log_error(f"session:{acct_name}", str(e))
        try:
            await take_error_screenshot(page, f"error_{acct_name}")
        except Exception:
            pass
    finally:
        log.final_summary(total_dms, 0, total_comments, 0)
        try:
            await browser.stop()
        except Exception:
            pass


async def run(
    dry_run: bool = False,
    max_dms: int | None = None,
    max_comments: int | None = None,
    keywords: list[str] | None = None,
    only_account: str | None = None,
    only_strategy: str | None = None,
    no_triage: bool = False,
):
    """Main bot loop. Runs accounts sequentially."""
    config = load_config()
    templates = load_templates()
    accounts = config["accounts"]

    # Filter to specific account if requested
    if only_account:
        accounts = [a for a in accounts if a["username"].lower() == only_account.lower()]
        if not accounts:
            log.error(f"Account '{only_account}' not found in config")
            return

    # Initialize run logger
    run_logger = RunLogger(BASE_DIR)
    strategy_names = [
        name for name, cfg in config.get("strategies", {}).items()
        if cfg.get("enabled", True) and (not only_strategy or name == only_strategy)
    ]
    run_logger.save_meta(
        accounts=[a["username"] for a in accounts],
        strategies=strategy_names,
        dry_run=dry_run,
    )

    mode_label = "DRY RUN" if dry_run else "LIVE"
    triage_label = "NO TRIAGE" if no_triage else "GROK V2 TRIAGE"

    # Beautiful startup banner
    log.header("🤖 REDDIT OUTREACH BOT")
    log.stat("Mode", mode_label, log.YELLOW if dry_run else log.GREEN)
    log.stat("Triage", triage_label, log.CYAN)
    log.stat("Accounts", len(accounts))
    log.stat("Strategies", ", ".join(strategy_names))
    print()

    for i, account in enumerate(accounts):
        acct_name = account["username"]
        rate_limiter = RateLimiter(config, account)

        # Skip if this account is exhausted for today
        if not rate_limiter.can_dm() and not rate_limiter.can_comment():
            log.warning(f"{acct_name}: Daily limits reached, skipping")
            continue

        try:
            await run_account_session(
                config, account, templates, rate_limiter, run_logger,
                dry_run, max_dms, max_comments, keywords,
                only_strategy, no_triage,
            )
        except KeyboardInterrupt:
            log.warning("Interrupted by user, stopping all accounts")
            break
        except Exception as e:
            log.error(f"{acct_name} session error: {e}")
            run_logger.log_error(f"main:{acct_name}", str(e))
            continue

    # Finalize run log
    run_logger.finalize()
    log.info(f"Run data saved to: {run_logger.run_dir_path}")

    # Print final stats
    stats = get_stats()
    log.header("🏁 ALL ACCOUNTS COMPLETE")
    log.stat("Mode", mode_label, log.YELLOW if dry_run else log.GREEN)
    log.stat("Triage", triage_label, log.CYAN)
    print()
    log.subheader("Today's Totals")
    log.stat("DMs sent", stats['today']['dms_success'], log.GREEN)
    log.stat("DMs failed", stats['today']['dms_failed'], log.RED if stats['today']['dms_failed'] > 0 else log.GRAY)
    log.stat("Comments posted", stats['today']['comments_success'], log.GREEN)
    log.stat("Comments failed", stats['today']['comments_failed'], log.RED if stats['today']['comments_failed'] > 0 else log.GRAY)
    print()


def main():
    parser = argparse.ArgumentParser(description="Reddit Outreach Bot")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent without actually sending")
    parser.add_argument("--max-dms", type=int, default=None,
                        help="Override max DMs for this run")
    parser.add_argument("--max-comments", type=int, default=None,
                        help="Override max comments for this run")
    parser.add_argument("--keywords", nargs="+", default=None,
                        help="Override search keywords")
    parser.add_argument("--account", type=str, default=None,
                        help="Run only this specific account (case-insensitive)")
    parser.add_argument("--strategy", type=str, default=None,
                        help="Run only this strategy (e.g. scanner_app, controversial_ingredient)")
    parser.add_argument("--no-triage", action="store_true",
                        help="Skip Grok triage, use keyword-based archetype detection")
    parser.add_argument("--migrate", action="store_true",
                        help="Migrate from old format to new state.json")
    parser.add_argument("--stats", action="store_true",
                        help="Print stats and exit")

    args = parser.parse_args()

    if args.migrate:
        from src.state import migrate_from_old_format
        migrate_from_old_format()
        return

    if args.stats:
        from src.state import print_state_summary
        print_state_summary()
        return

    asyncio.run(run(
        dry_run=args.dry_run,
        max_dms=args.max_dms,
        max_comments=args.max_comments,
        keywords=args.keywords,
        only_account=args.account,
        only_strategy=args.strategy,
        no_triage=args.no_triage,
    ))


if __name__ == "__main__":
    main()
