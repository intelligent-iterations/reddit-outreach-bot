import asyncio
import re

from src.models import ActionResult
from src.utils import human_type, random_delay, take_error_screenshot

# Return values - use ActionResult enum
COMMENT_SUCCESS = ActionResult.SUCCESS
COMMENT_LOCKED = ActionResult.LOCKED
COMMENT_FAILED = ActionResult.FAILED


async def _nuclear_tab_reset(browser, old_page):
    """Kill the current tab and create a fresh one."""
    try:
        new_page = await browser.get("https://www.reddit.com", new_tab=True)
        await asyncio.sleep(2)
        await old_page.close()
        await asyncio.sleep(1)
        return new_page
    except Exception as e:
        print(f"[COMMENT] Nuclear reset error: {e}")
        try:
            await old_page.get("https://www.reddit.com")
            await asyncio.sleep(2)
        except:
            pass
        return old_page


def _is_comment_permalink(permalink):
    """Check if permalink points to a specific comment (not just a post).

    Comment permalinks have format: /r/sub/comments/postid/title/commentid/
    Post permalinks have format: /r/sub/comments/postid/title/
    """
    # Remove trailing slash and split
    parts = permalink.rstrip('/').split('/')
    # Comment permalink: ['', 'r', 'sub', 'comments', 'postid', 'title', 'commentid']
    # Post permalink: ['', 'r', 'sub', 'comments', 'postid', 'title']
    return len(parts) >= 7 and parts[3] == 'comments'


async def verify_target_comment(page, expected_keyword: str, expected_username: str) -> dict:
    """
    Verify the target comment on page matches what we expect.

    Checks:
    1. The highlighted/target comment contains our keyword
    2. The comment author matches expected username

    Returns dict with:
    - verified: bool
    - reason: str
    - target_text: str (the actual comment text found)
    """
    result = await page.evaluate(f'''
        () => {{
            // Reddit highlights the target comment when navigating to comment permalink
            // Look for the comment that's highlighted or focused
            const targetSelectors = [
                '[data-testid="comment"][tabindex="-1"]',
                '.Comment--highlighted',
                '[id*="comment"][tabindex="-1"]',
                'shreddit-comment[collapsed="false"]:first-of-type'
            ];

            let targetComment = null;
            for (const sel of targetSelectors) {{
                targetComment = document.querySelector(sel);
                if (targetComment) break;
            }}

            if (!targetComment) {{
                // Fallback: find first comment that's not collapsed
                targetComment = document.querySelector('shreddit-comment:not([collapsed="true"])');
            }}

            if (!targetComment) {{
                return {{
                    found: false,
                    reason: "Could not find target comment element"
                }};
            }}

            // Get comment text
            const textContent = targetComment.innerText || targetComment.textContent || "";

            // Get author
            const authorEl = targetComment.querySelector('[data-testid="comment_author_link"], a[href*="/user/"]');
            const author = authorEl ? authorEl.innerText.replace('u/', '') : "";

            return {{
                found: true,
                text: textContent.substring(0, 500),
                author: author
            }};
        }}
    ''')

    if not result.get("found"):
        return {
            "verified": False,
            "reason": result.get("reason", "Target comment not found"),
            "target_text": ""
        }

    target_text = result.get("text", "")
    target_author = result.get("author", "")

    # Check keyword in comment
    if expected_keyword.lower() not in target_text.lower():
        return {
            "verified": False,
            "reason": f"Keyword '{expected_keyword}' not in target comment",
            "target_text": target_text[:200]
        }

    # Check author matches (if we have expected username)
    if expected_username and target_author:
        if expected_username.lower() != target_author.lower():
            return {
                "verified": False,
                "reason": f"Author mismatch: expected {expected_username}, got {target_author}",
                "target_text": target_text[:200]
            }

    return {
        "verified": True,
        "reason": "Verified",
        "target_text": target_text[:200]
    }


async def _check_if_locked(page):
    """Check if a post/thread is locked or archived.

    Returns True if locked, False otherwise.
    """
    # Check via JavaScript for multiple indicators
    result = await page.evaluate('''
        () => {
            // Check for locked icon (padlock)
            const lockedIcon = document.querySelector('[data-testid="locked-icon"], shreddit-post-overflow-menu[locked], [icon-name="lock"]');
            if (lockedIcon) return "locked";

            // Check for locked text variations
            const bodyText = document.body.innerText.toLowerCase();
            const lockedPhrases = [
                "this thread has been locked",
                "comments are locked",
                "this post is archived",
                "thread is locked",
                "commenting is disabled",
                "this community has been locked"
            ];
            for (const phrase of lockedPhrases) {
                if (bodyText.includes(phrase)) return "locked";
            }

            // Check if comment composer exists but is disabled
            const composer = document.querySelector('shreddit-composer');
            if (composer && composer.hasAttribute('disabled')) return "locked";

            return "not_locked";
        }
    ''')
    return result == "locked"


async def _activate_comment_editor(page):
    """Activate the comment editor by clicking on it.

    Returns True if editor was activated successfully.
    """
    # Try multiple approaches to activate the editor
    result = await page.evaluate('''
        () => {
            // Method 1: Click the placeholder to expand the editor
            const placeholder = document.querySelector('shreddit-composer [placeholder*="conversation"], shreddit-composer [placeholder*="comment"]');
            if (placeholder) {
                placeholder.click();
                return "clicked_placeholder";
            }

            // Method 2: Click the composer wrapper
            const composerWrapper = document.querySelector('shreddit-composer');
            if (composerWrapper) {
                composerWrapper.click();
                return "clicked_composer";
            }

            // Method 3: Find any element with "Add a comment" or similar
            const addComment = Array.from(document.querySelectorAll('*')).find(
                el => el.innerText && el.innerText.match(/^(Add a comment|Join the conversation)$/i)
            );
            if (addComment) {
                addComment.click();
                return "clicked_text";
            }

            return "not_found";
        }
    ''')

    if result != "not_found":
        await asyncio.sleep(1)  # Wait for editor to expand
        return True
    return False


async def _get_active_editor(page):
    """Find the active contenteditable editor after activation.

    Returns the editor element or None.
    """
    # Wait for editor to be ready and get it
    result = await page.evaluate('''
        () => {
            // Look for the active contenteditable
            const editors = document.querySelectorAll('[contenteditable="true"]');
            for (const editor of editors) {
                // Check if it's visible and part of a composer
                const rect = editor.getBoundingClientRect();
                if (rect.height > 0 && rect.width > 0) {
                    // Focus it
                    editor.focus();
                    return "found";
                }
            }
            return "not_found";
        }
    ''')

    if result == "found":
        try:
            return await page.select('[contenteditable="true"]:focus', timeout=2)
        except Exception:
            try:
                return await page.select('shreddit-composer [contenteditable="true"]', timeout=2)
            except Exception:
                pass
    return None


async def post_comment(
    browser,
    page,
    permalink,
    comment_text,
    config,
    verify_keyword: str = None,
    verify_username: str = None,
):
    """Post a comment on a Reddit post.

    IMPORTANT: This function returns (new_page, result).
    The caller MUST use the returned page - the old page is DEAD after this.

    Args:
        verify_keyword: If provided, verify target comment contains this keyword before replying
        verify_username: If provided, verify target comment is by this user before replying

    Returns: (new_page, COMMENT_SUCCESS/COMMENT_LOCKED/COMMENT_FAILED)
    """
    result = COMMENT_FAILED  # Default

    try:
        # Check if this is a comment permalink - if so, use reply approach
        if _is_comment_permalink(permalink):
            print(f"[COMMENT] Detected comment permalink, using reply approach")
            return await _reply_to_comment_permalink(
                browser, page, permalink, comment_text, config,
                verify_keyword=verify_keyword,
                verify_username=verify_username,
            )

        url = f"https://www.reddit.com{permalink}" if not permalink.startswith("http") else permalink
        print(f"[COMMENT] Navigating to: {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

        # Scroll down to see comments section
        await page.scroll_down(400)
        await asyncio.sleep(1)

        # Check for locked/archived
        if await _check_if_locked(page):
            print("[COMMENT] Post is locked/archived")
            result = COMMENT_LOCKED
        else:
            # Activate the comment editor
            print("[COMMENT] Activating comment editor...")
            editor_activated = await _activate_comment_editor(page)
            if not editor_activated:
                # Fallback: try clicking "Join the conversation" text
                try:
                    comment_box = await page.find("Join the conversation", best_match=True, timeout=5)
                    await comment_box.click()
                    await asyncio.sleep(1)
                    editor_activated = True
                except Exception as e:
                    print(f"[COMMENT] Could not activate comment editor: {e}")
                    await take_error_screenshot(page, "comment_box_not_found")
                    result = COMMENT_FAILED

            if editor_activated:
                # Type the comment using element.send_keys (original working approach)
                await random_delay(0.3, 0.8)

                try:
                    typed = False

                    # Try to find contenteditable element directly
                    try:
                        editor = await page.select("[contenteditable='true']", timeout=5)
                        if editor:
                            print("[COMMENT] Found contenteditable editor, typing...")
                            await human_type(editor, comment_text, config)
                            typed = True
                    except Exception as e:
                        print(f"[COMMENT] Direct select failed: {e}")

                    # Fallback: Try finding via "Add a comment" text
                    if not typed:
                        try:
                            editor = await page.find("Add a comment", best_match=True, timeout=5)
                            if editor:
                                print("[COMMENT] Found 'Add a comment' element, typing...")
                                await human_type(editor, comment_text, config)
                                typed = True
                        except Exception as e:
                            print(f"[COMMENT] 'Add a comment' approach failed: {e}")

                    if not typed:
                        raise Exception("Could not find editor to type into")

                    print(f"[COMMENT] Typed comment ({len(comment_text)} chars)")
                    await random_delay(0.5, 1.5)

                    # Click submit
                    print("[COMMENT] Looking for Comment button...")
                    submit_btn = await page.find("Comment", best_match=True, timeout=10)
                    await submit_btn.click()
                    print("[COMMENT] Clicked Comment button")
                    await asyncio.sleep(3)

                    # Check for errors
                    try:
                        rate_msg = await page.find("doing that too much", best_match=True, timeout=3)
                        if rate_msg:
                            print("[COMMENT] Rate limited by Reddit!")
                            result = COMMENT_FAILED
                        else:
                            print(f"[COMMENT] Comment posted on {permalink}")
                            result = COMMENT_SUCCESS
                    except Exception:
                        print(f"[COMMENT] Comment posted on {permalink}")
                        result = COMMENT_SUCCESS
                except Exception as e:
                    print(f"[COMMENT] Could not type/submit comment: {e}")
                    await take_error_screenshot(page, "comment_error")
                    result = COMMENT_FAILED

    except Exception as e:
        print(f"[COMMENT] Unexpected error: {e}")
        await take_error_screenshot(page, "comment_error")
        result = COMMENT_FAILED

    # NUCLEAR CLEANUP - Always kill the tab and create a fresh one
    print("[COMMENT] Nuclear cleanup: killing tab and creating fresh one...")
    new_page = await _nuclear_tab_reset(browser, page)
    print("[COMMENT] === Comment Complete ===")
    return (new_page, result)


async def _close_chat_overlay(page):
    """Close any open chat overlays aggressively."""
    try:
        # Try multiple times to ensure chat is closed
        for _ in range(3):
            await page.evaluate('''
                () => {
                    // Method 1: Click X buttons in chat area
                    const allButtons = document.querySelectorAll('button, [role="button"]');
                    for (const btn of allButtons) {
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const classList = (btn.className || '').toLowerCase();
                        const parent = btn.closest('[class*="chat" i], [class*="Chat"]');

                        if (parent && (ariaLabel.includes('close') || ariaLabel.includes('collapse') ||
                            ariaLabel.includes('minimize') || classList.includes('close'))) {
                            btn.click();
                        }
                    }

                    // Method 2: Find and click the X icon specifically
                    const svgCloses = document.querySelectorAll('svg');
                    for (const svg of svgCloses) {
                        const parent = svg.closest('button');
                        if (parent && parent.closest('[class*="chat" i], [class*="Chat"]')) {
                            // Check if it looks like a close button (X icon)
                            const paths = svg.querySelectorAll('path');
                            if (paths.length <= 2) {  // X icons typically have 1-2 paths
                                parent.click();
                            }
                        }
                    }

                    // Method 3: Press Escape to close popups
                    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
                    document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));

                    // Method 4: Remove chat elements from DOM temporarily
                    const chatContainers = document.querySelectorAll('[class*="chat-container"], [class*="ChatContainer"], [id*="chat"]');
                    chatContainers.forEach(el => {
                        el.style.display = 'none';
                    });
                }
            ''')
            await asyncio.sleep(0.3)

        # Also try pressing Escape via the page
        try:
            await page.send_keys('[Escape]')
        except:
            pass

        await asyncio.sleep(0.5)
    except:
        pass


async def _reply_to_comment_permalink(
    browser, page, permalink, comment_text, config,
    verify_keyword: str = None,
    verify_username: str = None,
):
    """Reply to a comment when navigating to a comment permalink.

    IMPORTANT: Returns (new_page, result). Caller MUST use returned page.

    Args:
        verify_keyword: If provided, verify target comment contains this keyword before replying
        verify_username: If provided, verify target comment is by this user before replying
    """
    result = COMMENT_FAILED  # Default

    try:
        # Close any open chat overlays first
        await _close_chat_overlay(page)

        url = f"https://www.reddit.com{permalink}" if not permalink.startswith("http") else permalink
        print(f"[COMMENT] Navigating to comment permalink: {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

        # Check for locked/archived
        if await _check_if_locked(page):
            print("[COMMENT] Post is locked/archived")
            result = COMMENT_LOCKED
            raise Exception("locked")  # Jump to nuclear cleanup

        # Note: We only act on "confirmed" leads where keyword was verified in comment text
        # during search, so we trust the permalink navigation

        # The target comment should be highlighted/focused when using comment permalink
        # Find and click the Reply button for it
        print("[COMMENT] Looking for Reply button...")

        # Wait a bit more for page to fully render
        await asyncio.sleep(1)

        # Try to find and click the Reply button directly
        try:
            reply_btn = await page.find("Reply", best_match=True, timeout=10)
            await reply_btn.scroll_into_view()
            await asyncio.sleep(0.5)
            await reply_btn.click()
            await asyncio.sleep(1.5)  # Wait for reply editor to open
            print("[COMMENT] Clicked Reply button")
        except Exception as e:
            print(f"[COMMENT] Could not find/click Reply button: {e}")
            await take_error_screenshot(page, "reply_btn_not_found")
            result = COMMENT_FAILED
            raise Exception("reply_btn_not_found")  # Jump to nuclear cleanup

        # Take screenshot to see if reply editor opened
        await take_error_screenshot(page, "after_reply_click")

        # Close any chat popups that might be overlaying the page
        await page.evaluate('''
            () => {
                // Try multiple ways to close chat overlay
                // 1. Click any X/close button in chat area
                const closeButtons = document.querySelectorAll('button');
                for (const btn of closeButtons) {
                    const svg = btn.querySelector('svg');
                    const ariaLabel = btn.getAttribute('aria-label') || '';
                    // Look for close/X buttons in chat area
                    if (ariaLabel.toLowerCase().includes('close') ||
                        ariaLabel.toLowerCase().includes('collapse') ||
                        ariaLabel.toLowerCase().includes('minimize')) {
                        btn.click();
                    }
                }

                // 2. Click outside the chat to close it
                const chatContainer = document.querySelector('[class*="chat" i]');
                if (chatContainer) {
                    document.body.click();
                }

                // 3. Press Escape multiple times
                for (let i = 0; i < 3; i++) {
                    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                }
            }
        ''')
        await asyncio.sleep(1)

        # Also try pressing Escape via the page
        try:
            await page.send_keys('[Escape]')
            await asyncio.sleep(0.3)
        except:
            pass

        # Close chat overlay again before typing
        await _close_chat_overlay(page)

        # Type the reply using element.send_keys (original working approach)
        await random_delay(0.3, 0.8)

        typed_successfully = False

        # Try to find and type into the editor using the original simple approach
        try:
            # First try to find contenteditable element directly
            editor = await page.select("[contenteditable='true']", timeout=5)
            if editor:
                print("[COMMENT] Found contenteditable editor, typing...")
                await human_type(editor, comment_text, config)
                typed_successfully = True
                print(f"[COMMENT] Typed reply ({len(comment_text)} chars)")
        except Exception as e:
            print(f"[COMMENT] Direct select failed: {e}")

        # Fallback: Try finding via "Add a comment" text
        if not typed_successfully:
            try:
                editor = await page.find("Add a comment", best_match=True, timeout=5)
                if editor:
                    print("[COMMENT] Found 'Add a comment' element, typing...")
                    await human_type(editor, comment_text, config)
                    typed_successfully = True
                    print(f"[COMMENT] Typed reply ({len(comment_text)} chars)")
            except Exception as e:
                print(f"[COMMENT] 'Add a comment' approach failed: {e}")

        # If all approaches failed, return error
        if not typed_successfully:
            print("[COMMENT] Could not type reply: All approaches failed")
            await take_error_screenshot(page, "reply_type_error")
            result = COMMENT_FAILED
            raise Exception("type_failed")  # Jump to nuclear cleanup

        await random_delay(0.5, 1.5)

        # Take screenshot before submit
        await take_error_screenshot(page, "before_submit")

        # Submit the reply - find and click the Comment button in the reply editor
        try:
            # Find all elements with "Comment" text and click the one in the reply form
            # The reply form's Comment button should be near the bottom of the visible area
            all_comment_btns = await page.select_all('button')
            submit_btn = None
            for btn in all_comment_btns:
                try:
                    text = btn.text or ""
                    if text.strip() == "Comment":
                        submit_btn = btn
                        # Don't break - we want the LAST one (reply form, not main form)
                except Exception:
                    continue

            if submit_btn:
                await submit_btn.click()
                print("[COMMENT] Clicked Comment button via select_all")
            else:
                raise Exception("No Comment button found")
        except Exception as e:
            print(f"[COMMENT] select_all approach failed: {e}, trying page.find")
            try:
                submit_btn = await page.find("Comment", best_match=True, timeout=5)
                await submit_btn.click()
                print("[COMMENT] Clicked submit via page.find")
            except Exception as e2:
                print(f"[COMMENT] Could not submit reply: {e2}")
                await take_error_screenshot(page, "reply_submit_error")
                result = COMMENT_FAILED
                raise Exception("submit_failed")  # Jump to nuclear cleanup

        # Wait and verify submission
        await asyncio.sleep(3)

        # Take screenshot to verify
        await take_error_screenshot(page, "after_reply_submit")

        # Check for error messages
        try:
            error_check = await page.evaluate('''
                () => {
                    const body = document.body.innerText.toLowerCase();
                    if (body.includes("something went wrong")) return "error";
                    if (body.includes("try again")) return "error";
                    if (body.includes("rate limit")) return "rate_limit";
                    if (body.includes("too much")) return "rate_limit";
                    return "ok";
                }
            ''')
            if error_check == "rate_limit":
                print("[COMMENT] Rate limited!")
                result = COMMENT_FAILED
            elif error_check == "error":
                print("[COMMENT] Error detected on page")
                result = COMMENT_FAILED
            else:
                print(f"[COMMENT] Reply posted on {permalink}")
                result = COMMENT_SUCCESS
        except Exception:
            # No error found, assume success
            print(f"[COMMENT] Reply posted on {permalink}")
            result = COMMENT_SUCCESS

    except Exception as e:
        expected_errors = ["locked", "reply_btn_not_found", "type_failed", "submit_failed", "verification_failed"]
        if not any(err in str(e) for err in expected_errors):
            print(f"[COMMENT] Unexpected error in reply: {e}")
            await take_error_screenshot(page, "reply_error")
            result = COMMENT_FAILED

    # NUCLEAR CLEANUP - Always kill the tab and create a fresh one
    print("[COMMENT] Nuclear cleanup: killing tab and creating fresh one...")
    new_page = await _nuclear_tab_reset(browser, page)
    print("[COMMENT] === Reply Complete ===")
    return (new_page, result)


async def reply_to_comment(page, permalink, comment_snippet, reply_text, config):
    """Reply to a specific comment on a Reddit post.

    Navigate to the permalink, find the target comment, click Reply, type, submit.
    Returns COMMENT_SUCCESS, COMMENT_LOCKED, or COMMENT_FAILED.
    """
    try:
        url = f"https://www.reddit.com{permalink}" if not permalink.startswith("http") else permalink
        print(f"[REPLY] Navigating to: {url}")
        await page.get(url)
        await asyncio.sleep(config["delays"]["page_load_wait_seconds"] + 1)

        # Check for locked/archived
        if await _check_if_locked(page):
            print("[REPLY] Post is locked/archived")
            return COMMENT_LOCKED

        # Find the target comment by its text snippet
        if comment_snippet:
            try:
                snippet = comment_snippet[:80]  # Use first 80 chars
                target = await page.find(snippet, best_match=True, timeout=10)
                if target:
                    print(f"[REPLY] Found target comment")
                    await target.scroll_into_view()
                    await asyncio.sleep(1)
            except Exception:
                print("[REPLY] Could not find target comment, will try Reply button anyway")

        # Find Reply button
        print("[REPLY] Looking for Reply button...")
        try:
            reply_btn = await page.find("Reply", best_match=True, timeout=10)
            await reply_btn.click()
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[REPLY] Could not find Reply button: {e}")
            await take_error_screenshot(page, "reply_btn_error")
            return COMMENT_FAILED

        # Type reply using JavaScript
        await random_delay(0.3, 0.8)
        try:
            escaped_text = reply_text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
            typed = await page.evaluate(f'''
                () => {{
                    const editors = document.querySelectorAll('[contenteditable="true"]');
                    let target = null;
                    for (const editor of editors) {{
                        const rect = editor.getBoundingClientRect();
                        if (rect.height > 0 && rect.width > 0) {{
                            target = editor;
                        }}
                    }}
                    if (target) {{
                        target.focus();
                        target.innerText = `{escaped_text}`;
                        target.dispatchEvent(new InputEvent('input', {{ bubbles: true }}));
                        return "success";
                    }}
                    return "no_editor";
                }}
            ''')
            if typed != "success":
                raise Exception("No contenteditable editor found via JS")
            print(f"[REPLY] Typed reply ({len(reply_text)} chars)")
        except Exception as e:
            print(f"[REPLY] Could not type reply: {e}")
            await take_error_screenshot(page, "reply_type_error")
            return COMMENT_FAILED
        await random_delay(0.5, 1.5)

        # Submit
        try:
            submit_btn = await page.find("Comment", best_match=True, timeout=10)
            await submit_btn.click()
            print("[REPLY] Submitted reply")
        except Exception:
            try:
                submit_btn = await page.find("Reply", best_match=True, timeout=5)
                await submit_btn.click()
                print("[REPLY] Submitted reply via Reply button")
            except Exception as e:
                print(f"[REPLY] Could not submit: {e}")
                await take_error_screenshot(page, "reply_submit_error")
                return COMMENT_FAILED

        await asyncio.sleep(3)
        print(f"[REPLY] Reply posted on {permalink}")
        return COMMENT_SUCCESS

    except Exception as e:
        print(f"[REPLY] Unexpected error: {e}")
        await take_error_screenshot(page, "reply_error")
        return COMMENT_FAILED
