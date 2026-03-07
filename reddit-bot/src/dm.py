"""
DM (Direct Message) sending for Reddit outreach bot.

Handles:
- Navigating to user profile
- Opening chat
- Detecting new vs existing conversations
- Typing and sending messages
- Verifying message was sent
- Error detection (rate limits, unable to invite)
"""

import asyncio
from typing import Tuple

from src.models import ActionResult
from src.utils import human_type, random_delay, take_error_screenshot


async def _get_full_page_text(page) -> str:
    """Get text from ALL elements including overlays, toasts, shadow DOM."""
    try:
        text = await page.evaluate("""
            () => {
                let text = '';
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT
                );
                while (walker.nextNode()) {
                    text += walker.currentNode.textContent + '\\n';
                }
                // Also check alert/toast elements specifically
                document.querySelectorAll(
                    '[role="alert"], [aria-live], .toast, [class*="toast"], ' +
                    '[class*="error"], [class*="snackbar"], [class*="notice"]'
                ).forEach(el => {
                    text += el.textContent + '\\n';
                });
                return text;
            }
        """)
        return text if isinstance(text, str) else str(text) if text else ""
    except Exception:
        return ""


async def _check_for_errors(page) -> str | None:
    """
    Check full DOM for error toasts.

    Returns error type string or None if no errors found.
    """
    full_text = await _get_full_page_text(page)
    full_text_lower = full_text.lower()

    if "unable to invite" in full_text_lower:
        return "unable_to_invite"
    if "sent a lot of invites" in full_text_lower or "take a break" in full_text_lower:
        return "rate_limited"
    if "try again later" in full_text_lower:
        return "rate_limited"

    return None


async def _is_new_conversation(page) -> bool:
    """
    Check if this is a NEW conversation (never messaged before).

    Looks for Reddit's "Send an invite message" or "start chatting" prompts.
    """
    indicators = ["Send an invite message", "start chatting", "invite to chat"]

    for indicator in indicators:
        try:
            element = await page.find(indicator, best_match=True, timeout=3)
            if element:
                return True
        except Exception:
            pass

    return False


async def _has_existing_messages(page) -> bool:
    """
    Check if there are existing messages in this conversation.

    This is a safety check - if we see messages, don't send again.
    """
    try:
        # Look for message containers that indicate an existing conversation
        result = await page.evaluate("""
            () => {
                // Look for message bubbles/containers
                const messageSelectors = [
                    '[class*="message-body"]',
                    '[class*="MessageBody"]',
                    '[data-testid="message"]',
                    '.message',
                ];

                for (const selector of messageSelectors) {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        return true;
                    }
                }

                return false;
            }
        """)
        return bool(result)
    except Exception:
        return False


async def _verify_message_sent(page, message_snippet: str) -> bool:
    """
    Verify that OUR message appears in the conversation.

    This is positive confirmation that the message was actually sent,
    not just that we clicked send.
    """
    try:
        # Wait a moment for message to appear
        await asyncio.sleep(2)

        # Look for our message text in the conversation
        snippet = message_snippet[:30].replace("'", "\\'").replace('"', '\\"')
        result = await page.evaluate(f"""
            () => {{
                const bodyText = document.body.innerText.toLowerCase();
                const snippet = "{snippet.lower()}";
                return bodyText.includes(snippet);
            }}
        """)
        return bool(result)
    except Exception:
        return False


async def _nuclear_tab_reset(browser, old_page):
    """
    Kill the current tab and create a fresh one.

    This is the ONLY reliable way to clear Reddit's chat overlay.
    """
    try:
        new_page = await browser.get("https://www.reddit.com", new_tab=True)
        await asyncio.sleep(2)
        await old_page.close()
        await asyncio.sleep(1)
        return new_page
    except Exception as e:
        print(f"[DM] Nuclear reset error: {e}")
        try:
            await old_page.get("https://www.reddit.com")
            await asyncio.sleep(2)
        except Exception:
            pass
        return old_page


async def send_dm(
    browser,
    page,
    username: str,
    subject: str,
    body: str,
    config: dict
) -> Tuple[object, ActionResult]:
    """
    Send a DM to a Reddit user via the Chat system.

    IMPORTANT: This function returns (new_page, result).
    The caller MUST use the returned page - the old page may be closed.

    Returns:
        Tuple of (new_page, ActionResult)
    """
    result = ActionResult.FAILED

    try:
        print(f"[DM] === Starting DM to u/{username} ===")

        # Step 1: Navigate to user profile
        url = f"https://www.reddit.com/user/{username}"
        print(f"[DM] Step 1: Navigating to {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 2)

        # Step 2: Verify we're on the correct profile
        current_url = await page.evaluate("window.location.href")
        print(f"[DM] Step 2: Verifying URL")

        if username.lower() not in str(current_url).lower():
            print(f"[DM] ERROR: Not on correct profile! URL: {current_url}")
            await take_error_screenshot(page, f"dm_wrong_profile_{username}")
            result = ActionResult.FAILED

        else:
            # Check for suspended/deleted user
            page_text = await page.evaluate("document.body.innerText")
            page_text = str(page_text) if page_text else ""

            if "page not found" in page_text.lower() or "suspended" in page_text.lower():
                print(f"[DM] User u/{username} not found or suspended")
                result = ActionResult.FAILED

            else:
                # Step 3: Find and click "Start Chat" button
                print("[DM] Step 3: Looking for Start Chat button...")
                try:
                    chat_btn = await page.find("Start Chat", best_match=True, timeout=10)
                    if chat_btn:
                        await chat_btn.click()
                        print("[DM] Clicked Start Chat")
                        await asyncio.sleep(4)

                        # Step 4: Check if new conversation
                        print("[DM] Step 4: Checking conversation state...")

                        is_new = await _is_new_conversation(page)
                        has_messages = await _has_existing_messages(page)

                        if has_messages and not is_new:
                            print(f"[DM] SKIP: Existing conversation with u/{username}")
                            await take_error_screenshot(page, f"dm_existing_{username}")
                            result = ActionResult.SKIPPED

                        elif is_new:
                            print("[DM] Confirmed new conversation")

                            # Step 5: Find message input and type
                            print("[DM] Step 5: Finding message input...")
                            try:
                                msg_input = await page.find("Message", best_match=True, timeout=10)
                                if msg_input:
                                    await msg_input.click()
                                    await asyncio.sleep(0.5)

                                    await human_type(msg_input, body, config)
                                    print(f"[DM] Typed message ({len(body)} chars)")

                                    await random_delay(0.5, 1.0)

                                    # Step 6: Send the message
                                    print("[DM] Step 6: Sending message...")
                                    try:
                                        send_btn = await page.find("Send", best_match=True, timeout=5)
                                        if send_btn:
                                            await send_btn.click()
                                            print("[DM] Clicked Send button")
                                    except Exception:
                                        # Fallback: try Enter key
                                        try:
                                            await page.evaluate("""
                                                () => {
                                                    document.activeElement.dispatchEvent(
                                                        new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})
                                                    );
                                                }
                                            """)
                                            print("[DM] Pressed Enter to send")
                                        except Exception:
                                            pass

                                    # Step 7: Verify send
                                    await asyncio.sleep(3)
                                    print("[DM] Step 7: Verifying send...")
                                    await take_error_screenshot(page, f"dm_after_send_{username}")

                                    # Check for errors first
                                    error = await _check_for_errors(page)
                                    if error == "rate_limited":
                                        print("[DM] RATE LIMITED!")
                                        result = ActionResult.RATE_LIMITED
                                    elif error == "unable_to_invite":
                                        print(f"[DM] Unable to invite u/{username}")
                                        result = ActionResult.FAILED
                                    else:
                                        # Verify our message appears
                                        confirmed = await _verify_message_sent(page, body)
                                        if confirmed:
                                            print(f"[DM] SUCCESS: Message confirmed sent to u/{username}")
                                            result = ActionResult.SUCCESS
                                        else:
                                            # Double-check for errors after delay
                                            await asyncio.sleep(2)
                                            error = await _check_for_errors(page)
                                            if error == "rate_limited":
                                                result = ActionResult.RATE_LIMITED
                                            else:
                                                print(f"[DM] WARNING: Could not confirm message sent")
                                                await take_error_screenshot(page, f"dm_unconfirmed_{username}")
                                                result = ActionResult.FAILED
                                else:
                                    print("[DM] Could not find message input")
                                    result = ActionResult.FAILED

                            except Exception as e:
                                print(f"[DM] Error typing/sending: {e}")
                                await take_error_screenshot(page, f"dm_error_{username}")
                                result = ActionResult.FAILED

                        else:
                            # Ambiguous state - not clearly new, but no messages visible
                            print(f"[DM] SKIP: Ambiguous conversation state with u/{username}")
                            await take_error_screenshot(page, f"dm_ambiguous_{username}")
                            result = ActionResult.SKIPPED

                    else:
                        print("[DM] Could not find Start Chat button")
                        await take_error_screenshot(page, f"dm_no_chat_btn_{username}")
                        result = ActionResult.FAILED

                except Exception as e:
                    print(f"[DM] Error with chat button: {e}")
                    await take_error_screenshot(page, f"dm_error_{username}")
                    result = ActionResult.FAILED

    except Exception as e:
        print(f"[DM] Unexpected error: {e}")
        await take_error_screenshot(page, f"dm_error_{username}")
        result = ActionResult.FAILED

    # Always do nuclear cleanup
    print("[DM] Nuclear cleanup: killing tab and creating fresh one...")
    new_page = await _nuclear_tab_reset(browser, page)
    print(f"[DM] === DM Complete: {result.value} ===\n")

    return (new_page, result)
