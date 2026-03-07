"""
Dry-run workflow that logs EVERY step without executing any actions.

Generates an HTML report showing the full decision pipeline:
1. Search: Keywords used, comments collected
2. Split: Confirmed vs Maybe pile
3. Discovery: Grok prompt, response, decisions
4. Triage: Grok prompt, response, decisions
5. Final: What would have been posted (but wasn't)
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from src.auth import login
from src.search import search_comments, split_leads_by_keyword_confirmation
from src.triage import (
    build_discovery_prompt,
    build_triage_prompt_v2,
    _call_grok,
    _strip_code_fences,
    discover_relevant_leads,
)
from src.templates import fill_template_from_decision
from src.utils import load_config, load_templates, BASE_DIR, log

# Optional import for context enrichment
try:
    from src.reddit_api import enrich_leads_with_context
    HAS_REDDIT_API = True
except ImportError:
    HAS_REDDIT_API = False
    enrich_leads_with_context = None


def generate_html_report(data: dict, output_path: Path):
    """Generate an HTML report from the collected data."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Dry Run Report - {data['timestamp']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; line-height: 1.6; }}
        h1, h2, h3 {{ color: #00d4ff; }}
        .section {{ background: #16213e; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .step {{ background: #0f3460; border-radius: 8px; padding: 15px; margin: 15px 0; border-left: 4px solid #00d4ff; }}
        .step.error {{ border-left-color: #ff6b6b; }}
        .step.success {{ border-left-color: #00ff88; }}
        .step.warning {{ border-left-color: #ffd93d; }}
        .code {{ background: #0d1b2a; padding: 15px; border-radius: 4px; font-family: 'SF Mono', Monaco, monospace; white-space: pre-wrap; overflow-x: auto; font-size: 12px; margin: 10px 0; max-height: 400px; overflow-y: auto; }}
        .code-small {{ max-height: 200px; }}
        .error {{ color: #ff6b6b; }}
        .success {{ color: #00ff88; }}
        .warning {{ color: #ffd93d; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #0f3460; }}
        .lead-card {{ background: #0f3460; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .lead-header {{ display: flex; justify-content: space-between; align-items: center; }}
        .tag {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; margin-right: 5px; }}
        .tag-confirmed {{ background: #00ff8833; color: #00ff88; }}
        .tag-maybe {{ background: #ffd93d33; color: #ffd93d; }}
        .tag-approved {{ background: #00ff8833; color: #00ff88; }}
        .tag-denied {{ background: #ff6b6b33; color: #ff6b6b; }}
        .tag-dm {{ background: #00d4ff33; color: #00d4ff; }}
        .tag-comment {{ background: #9b59b633; color: #9b59b6; }}
        details {{ margin: 10px 0; }}
        summary {{ cursor: pointer; padding: 10px; background: #0f3460; border-radius: 4px; }}
        summary:hover {{ background: #1a4a7a; }}
        .action-preview {{ background: #0d1b2a; border: 2px solid #00ff88; border-radius: 8px; padding: 15px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>Dry Run Report</h1>
    <p><strong>Timestamp:</strong> {data['timestamp']}</p>
    <p><strong>Strategy:</strong> {data.get('strategy', 'N/A')}</p>
    <p><strong>Account:</strong> {data.get('account', 'N/A')}</p>
"""

    # Step 1: Search Phase
    html += """
    <div class="section">
        <h2>Step 1: Search Phase</h2>
"""
    for kw_data in data.get('search_results', []):
        html += f"""
        <div class="step">
            <h3>Keyword: "{kw_data['keyword']}"</h3>
            <p><strong>Comments found:</strong> {len(kw_data['leads'])}</p>
"""
        if kw_data['leads']:
            html += """<details><summary>View comments</summary><div class="code code-small">"""
            for lead in kw_data['leads'][:10]:  # Show first 10
                html += f"""u/{lead.get('username', '?')} in r/{lead.get('subreddit', '?')}
  keyword_confirmed: {lead.get('keyword_confirmed', '?')}
  comment: {lead.get('comment_text', '')[:150]}...
  permalink: {lead.get('permalink', '')}
---
"""
            if len(kw_data['leads']) > 10:
                html += f"... and {len(kw_data['leads']) - 10} more\n"
            html += """</div></details>"""
        html += "</div>"
    html += "</div>"

    # Step 2: Split Phase
    html += f"""
    <div class="section">
        <h2>Step 2: Lead Splitting</h2>
        <div class="step">
            <p><strong>Total leads:</strong> {data.get('total_leads', 0)}</p>
            <p><span class="tag tag-confirmed">Confirmed: {data.get('confirmed_count', 0)}</span> - keyword found directly in comment</p>
            <p><span class="tag tag-maybe">Maybe: {data.get('maybe_count', 0)}</span> - keyword in thread but not in comment (needs Discovery)</p>
        </div>
"""

    # Show confirmed leads
    if data.get('confirmed_leads'):
        html += """<details><summary>View Confirmed Leads</summary><div class="code code-small">"""
        for lead in data['confirmed_leads'][:10]:
            html += f"""u/{lead.get('username', '?')} in r/{lead.get('subreddit', '?')}
  comment: {lead.get('comment_text', '')[:150]}...
---
"""
        html += """</div></details>"""

    # Show maybe leads
    if data.get('maybe_leads'):
        html += """<details><summary>View Maybe Leads (sent to Discovery)</summary><div class="code code-small">"""
        for lead in data['maybe_leads'][:10]:
            html += f"""u/{lead.get('username', '?')} in r/{lead.get('subreddit', '?')}
  comment: {lead.get('comment_text', '')[:150]}...
---
"""
        html += """</div></details>"""

    html += "</div>"

    # Step 3: Discovery Phase
    if data.get('discovery'):
        disc = data['discovery']
        html += f"""
    <div class="section">
        <h2>Step 3: Discovery Phase (Grok V1)</h2>
        <p>Evaluating {disc.get('input_count', 0)} "maybe" leads to find relevant ones.</p>

        <div class="step">
            <h3>Prompt Sent to Grok</h3>
            <details><summary>View System Prompt</summary>
            <div class="code code-small">{disc.get('system_prompt', 'N/A')}</div>
            </details>
            <details><summary>View User Prompt (leads)</summary>
            <div class="code">{disc.get('user_prompt', 'N/A')}</div>
            </details>
        </div>

        <div class="step {'success' if disc.get('relevant_count', 0) > 0 else 'warning'}">
            <h3>Grok's Response</h3>
            <div class="code">{disc.get('raw_response', 'N/A')}</div>
        </div>

        <div class="step">
            <h3>Discovery Decisions</h3>
            <p><span class="tag tag-approved">Relevant: {disc.get('relevant_count', 0)}</span></p>
            <p><span class="tag tag-denied">Not Relevant: {disc.get('not_relevant_count', 0)}</span></p>
"""
        if disc.get('relevant_leads'):
            html += """<h4>Marked as Relevant:</h4>"""
            for item in disc['relevant_leads']:
                html += f"""<div class="lead-card">
                <p><strong>u/{item.get('username', '?')}</strong> in r/{item.get('subreddit', '?')}</p>
                <p><em>Reason:</em> {item.get('reason', 'N/A')}</p>
            </div>"""

        if disc.get('not_relevant_leads'):
            html += """<h4>Marked as Not Relevant:</h4>"""
            for item in disc['not_relevant_leads'][:5]:
                html += f"""<div class="lead-card">
                <p><strong>u/{item.get('username', '?')}</strong> in r/{item.get('subreddit', '?')}</p>
                <p><em>Reason:</em> {item.get('reason', 'N/A')}</p>
            </div>"""

        html += "</div></div>"

    # Step 4: Triage Phase
    if data.get('triage'):
        tri = data['triage']
        html += f"""
    <div class="section">
        <h2>Step 4: Triage Phase (Grok V2)</h2>
        <p>Evaluating {tri.get('input_count', 0)} candidates (confirmed + discovered).</p>

        <div class="step">
            <h3>Prompt Sent to Grok</h3>
            <details><summary>View System Prompt</summary>
            <div class="code">{tri.get('system_prompt', 'N/A')}</div>
            </details>
            <details><summary>View User Prompt (leads with context)</summary>
            <div class="code">{tri.get('user_prompt', 'N/A')}</div>
            </details>
        </div>

        <div class="step {'success' if tri.get('approved_count', 0) > 0 else 'warning'}">
            <h3>Grok's Response</h3>
            <div class="code">{tri.get('raw_response', 'N/A')}</div>
        </div>

        <div class="step">
            <h3>Triage Decisions</h3>
            <p><span class="tag tag-approved">Approved: {tri.get('approved_count', 0)}</span></p>
            <p><span class="tag tag-denied">Denied: {tri.get('denied_count', 0)}</span></p>
        </div>
    </div>
"""

    # Step 5: Final Actions (what would have been posted)
    if data.get('final_actions'):
        html += f"""
    <div class="section">
        <h2>Step 5: Final Actions (NOT EXECUTED)</h2>
        <p class="warning">These actions would have been executed but were NOT because this is a dry run.</p>
"""
        for action in data['final_actions']:
            action_type = action.get('action_type', 'comment')
            tag_class = 'tag-dm' if action_type == 'dm' else 'tag-comment'
            html += f"""
        <div class="action-preview">
            <div class="lead-header">
                <h3>u/{action.get('username', '?')}</h3>
                <span class="tag {tag_class}">{action_type.upper()}</span>
            </div>
            <p><strong>Subreddit:</strong> r/{action.get('subreddit', '?')}</p>
            <p><strong>Permalink:</strong> <a href="https://reddit.com{action.get('permalink', '')}" style="color: #00d4ff;">{action.get('permalink', 'N/A')}</a></p>
            <p><strong>Template:</strong> {action.get('template_name', 'N/A')}</p>
            <p><strong>Reasoning:</strong> {action.get('reasoning', 'N/A')}</p>
            <h4>Message that would be sent:</h4>
            <div class="code">{action.get('message', 'N/A')}</div>
            <h4>Original Comment:</h4>
            <div class="code code-small">{action.get('original_comment', 'N/A')}</div>
        </div>
"""
        html += "</div>"

    html += """
</body>
</html>
"""

    with open(output_path, 'w') as f:
        f.write(html)

    return output_path


async def run_dry_run(
    strategy_name: str,
    keywords: list[str] | None = None,
    max_keywords: int = 3,
):
    """Run the full pipeline in dry-run mode, logging everything."""

    config = load_config()
    templates = load_templates()

    # Get strategy config
    strategies = config.get("strategies", {})
    if strategy_name not in strategies:
        log.error(f"Strategy '{strategy_name}' not found")
        return

    strategy_config = strategies[strategy_name]
    strategy_templates_key = strategy_config.get("templates_key", strategy_name)
    strategy_templates = templates.get(strategy_templates_key, templates.get(strategy_name, {}))
    grok_config = config.get("grok", {})

    # Use provided keywords or get from config
    strategy_keywords = keywords or strategy_config.get("keywords", [])[:max_keywords]

    # Get first account
    accounts = config.get("accounts", [])
    if not accounts:
        log.error("No accounts configured")
        return
    account = accounts[0]

    # Data collector for HTML report
    report_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": strategy_name,
        "account": account["username"],
        "search_results": [],
        "confirmed_leads": [],
        "maybe_leads": [],
        "discovery": None,
        "triage": None,
        "final_actions": [],
    }

    log.header("DRY RUN MODE - LOGGING EVERYTHING")
    log.stat("Strategy", strategy_name)
    log.stat("Keywords", len(strategy_keywords))

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: SEARCH PHASE
    # ═══════════════════════════════════════════════════════════════════
    log.subheader("Step 1: Search Phase")

    browser, page = await login(config, account)
    if not page:
        log.error("Failed to login")
        return

    all_leads = []

    for keyword in strategy_keywords:
        log.step("🔎", f"Searching: '{keyword}'")
        leads = await search_comments(page, keyword, config)

        report_data["search_results"].append({
            "keyword": keyword,
            "leads": leads or [],
        })

        if leads:
            log.success(f"Found {len(leads)} comments")
            all_leads.extend(leads)
        else:
            log.info("No comments found")

        await asyncio.sleep(2)  # Rate limit

    await browser.stop()

    if not all_leads:
        log.warning("No leads found")
        return

    # Deduplicate
    seen = set()
    unique_leads = []
    for lead in all_leads:
        key = lead["username"].lower()
        if key not in seen:
            seen.add(key)
            unique_leads.append(lead)
    all_leads = unique_leads

    report_data["total_leads"] = len(all_leads)
    log.stat("Total unique leads", len(all_leads))

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: SPLIT PHASE
    # ═══════════════════════════════════════════════════════════════════
    log.subheader("Step 2: Split Phase")

    confirmed_leads, maybe_leads = split_leads_by_keyword_confirmation(all_leads)

    report_data["confirmed_count"] = len(confirmed_leads)
    report_data["maybe_count"] = len(maybe_leads)
    report_data["confirmed_leads"] = confirmed_leads
    report_data["maybe_leads"] = maybe_leads

    log.stat("Confirmed", len(confirmed_leads), log.GREEN)
    log.stat("Maybe", len(maybe_leads), log.YELLOW)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: DISCOVERY PHASE
    # ═══════════════════════════════════════════════════════════════════
    discovered_leads = []

    if maybe_leads:
        log.subheader("Step 3: Discovery Phase")
        log.step("🤖", "Calling Grok for discovery...")

        discovery_result = discover_relevant_leads(maybe_leads, grok_config)
        discovered_leads = discovery_result.relevant_leads

        report_data["discovery"] = {
            "input_count": len(discovery_result.input_leads),
            "system_prompt": discovery_result.system_prompt,
            "user_prompt": discovery_result.user_prompt,
            "raw_response": discovery_result.raw_response,
            "relevant_count": len(discovery_result.relevant_leads),
            "not_relevant_count": len(discovery_result.not_relevant_decisions),
            "relevant_leads": discovery_result.relevant_decisions,
            "not_relevant_leads": discovery_result.not_relevant_decisions,
        }

        log.stat("Marked relevant", len(discovery_result.relevant_leads), log.GREEN)
        log.stat("Marked not relevant", len(discovery_result.not_relevant_decisions), log.RED)

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: TRIAGE PHASE
    # ═══════════════════════════════════════════════════════════════════
    log.subheader("Step 4: Triage Phase")

    # Combine confirmed + discovered
    all_candidates = confirmed_leads + discovered_leads
    log.stat("Total candidates for triage", len(all_candidates))

    if not all_candidates:
        log.warning("No candidates to triage")
    else:
        # Enrich with context
        if HAS_REDDIT_API:
            log.step("📝", "Enriching leads with context...")
            enriched = enrich_leads_with_context(all_candidates)
        else:
            log.warning("Reddit API not available, skipping context enrichment")
            enriched = all_candidates

        # Build triage prompt
        system_prompt, user_prompt = build_triage_prompt_v2(
            enriched,
            strategy_config,
            strategy_templates,
        )

        log.step("🤖", "Calling Grok for triage...")

        try:
            raw_response, _ = _call_grok(system_prompt, user_prompt, grok_config)
        except Exception as e:
            log.error(f"Grok API error: {e}")
            raw_response = f"ERROR: {e}"

        # Parse response
        parsed = {}
        try:
            cleaned = _strip_code_fences(raw_response)
            parsed = json.loads(cleaned)
        except:
            pass

        approved = parsed.get("approved", [])
        denied = parsed.get("denied", [])

        report_data["triage"] = {
            "input_count": len(all_candidates),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_response": raw_response,
            "approved_count": len(approved),
            "denied_count": len(denied),
        }

        log.stat("Approved", len(approved), log.GREEN)
        log.stat("Denied", len(denied), log.RED)

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: BUILD FINAL ACTIONS
        # ═══════════════════════════════════════════════════════════════════
        log.subheader("Step 5: Final Actions (NOT EXECUTED)")

        for decision in approved:
            idx = decision.get("lead_index")
            if idx is None or idx >= len(all_candidates):
                continue

            lead = all_candidates[idx]

            # Get the message
            message = decision.get("custom_message", "")
            if not message:
                # Try to fill from template
                try:
                    message = fill_template_from_decision(decision, strategy_templates)
                except:
                    message = "[Could not generate message]"

            action = {
                "username": lead.get("username", "?"),
                "subreddit": lead.get("subreddit", "?"),
                "permalink": lead.get("permalink", ""),
                "action_type": decision.get("action_type", "comment"),
                "template_name": decision.get("template_name", "N/A"),
                "reasoning": decision.get("reasoning", "N/A"),
                "message": message,
                "original_comment": lead.get("comment_text", "N/A"),
            }

            report_data["final_actions"].append(action)

            log.step("✓" if decision.get("action_type") == "comment" else "✉",
                    f"Would {decision.get('action_type', 'comment')} u/{lead.get('username', '?')} in r/{lead.get('subreddit', '?')}")

    # ═══════════════════════════════════════════════════════════════════
    # GENERATE HTML REPORT
    # ═══════════════════════════════════════════════════════════════════
    log.subheader("Generating HTML Report")

    run_dir = Path(BASE_DIR) / "run-data" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save raw data
    with open(run_dir / "dry_run_data.json", "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    # Generate HTML
    html_path = run_dir / "dry_run_report.html"
    generate_html_report(report_data, html_path)

    log.success(f"Report saved to: {html_path}")
    print(f"\n📄 Open report: file://{html_path}")


def main():
    parser = argparse.ArgumentParser(description="Dry run the outreach pipeline")
    parser.add_argument("--strategy", "-s", default="scanner_app", help="Strategy to run")
    parser.add_argument("--keywords", "-k", nargs="+", help="Specific keywords to use")
    parser.add_argument("--max-keywords", "-m", type=int, default=3, help="Max keywords to search")

    args = parser.parse_args()

    asyncio.run(run_dry_run(
        strategy_name=args.strategy,
        keywords=args.keywords,
        max_keywords=args.max_keywords,
    ))


if __name__ == "__main__":
    main()
