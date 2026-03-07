"""
Execute approved actions one-by-one with screenshot verification.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from src.auth import login
from src.comment import post_comment
from src.state import claim_user, claim_thread, record_action
from src.models import ActionType, ActionResult
from src.utils import load_config, take_error_screenshot, BASE_DIR

# Actions to execute (from dry run)
ACTIONS = [
    {
        "username": "butterflyfrenchfry",
        "subreddit": "tattooadvice",
        "permalink": "/r/tattooadvice/comments/1rb0wym/what_is_your_preferred_sun_screen_for_tattoos/o6sn0a6",
        "action_type": "comment",
        "message": "That's interesting about Native scoring highest on Yuka. I used Yuka for a while but the ratings felt kind of arbitrary to me like why is this a 7 and that a 4? the pom app lets you control the flagging yourself based on the severity of the research. You choose if you only care about large human studies or if you want animal and in vitro findings flagged too. Makes it feel way more transparent",
    },
    {
        "username": "RWLemon",
        "subreddit": "CleaningTips",
        "permalink": "/r/CleaningTips/comments/1qw3ry2/what_will_actually_clean_natural_soap_scum_in_the/o3nybwb",
        "action_type": "comment",
        "message": "Love that tip about scanning with Yuka to avoid bad ingredients. if you care about what's in your products the pom app is worth a look. you scan the ingredient list and set your own thresholds for how things get flagged based on the strength of the research. So you're not just trusting a number you're deciding what level of evidence matters to you",
    },
    {
        "username": "strawberryfields831",
        "subreddit": "finehair",
        "permalink": "/r/finehair/comments/1qugcy3/my_hair_got_worse_after_trying_to_grow_it_out_for/o3neuh6",
        "action_type": "comment",
        "message": "That's a smart idea to check products with Yuka for endocrine disruptors. Have you tried scanning the actual ingredients list instead of the barcode? I use the pom app for this and the thing that sets it apart is you customize how ingredients get flagged based on the severity of the research. So you choose if you care about in vitro findings or only large human studies. Way more personalized than a generic score",
    },
    {
        "username": "Sunflower3586",
        "subreddit": "bathandbodyworks",
        "permalink": "/r/bathandbodyworks/comments/w2di85/are_bath_and_body_works_products_toxic/o3k93vz",
        "action_type": "comment",
        "message": "Yeah it's eye-opening scanning those B&BW products with Yuka. I used Yuka for a while but the ratings felt kind of arbitrary to me like why is this a 7 and that a 4? the pom app lets you control the flagging yourself based on the severity of the research. You choose if you only care about large human studies or if you want animal and in vitro findings flagged too. Makes it feel way more transparent",
    },
    {
        "username": "Twilli88",
        "subreddit": "CostcoCanada",
        "permalink": "/r/CostcoCanada/comments/1qutybh/costco_rotisserie_chicken",
        "action_type": "comment",
        "message": "Interesting point about those Yuka scores on the Costco chicken. yeah Yuka is decent for a quick check but I wanted more control over what actually gets flagged. the pom app lets you set your own thresholds based on research severity like large human samples vs animal studies vs in vitro.",
    },
    {
        "username": "Imaginary_Cat_7611",
        "subreddit": "FoodToronto",
        "permalink": "/r/FoodToronto/comments/1qr8ebc/have_these_labels_impacted_your_grocery_choices/o3covw4",
        "action_type": "comment",
        "message": "Yuka sounds handy for quick food checks. you might want to check out the pom app it scans the ingredients list instead of a barcode so it works with any product. The main thing is you get to customize your own flagging based on research quality like large human studies vs animal vs in vitro. So it actually reflects what you care about instead of giving everyone the same score",
    },
    {
        "username": "saskgrinder",
        "subreddit": "BuyCanadian",
        "permalink": "/r/BuyCanadian/comments/1quqk40/looking_for_canadian_skincare_thats_gentle_and/o3c1stb",
        "action_type": "comment",
        "message": "Scanning with YUKA to check what's in products is a great tip. If you're really into checking what's in your products you should try the pom app you scan the ingredients list and you can set your own severity levels for how things get flagged. Like if a study was only done on animals you decide if that concerns you or not. Its still in development but the customization is pretty solid",
    },
    {
        "username": "Far-Recording4321",
        "subreddit": "Aging",
        "permalink": "/r/Aging/comments/1qtm0hr/what_should_stopstart_around_35/o39i1wm",
        "action_type": "comment",
        "message": "Smart call questioning sunscreen ingredients with yuka. if you care about what's in your products the pom app is worth a look. you scan the ingredient list and set your own thresholds for how things get flagged based on the strength of the research. So you're not just trusting a number you're deciding what level of evidence matters to you",
    },
    {
        "username": "TeaProfessional8891",
        "subreddit": "medicalmedium",
        "permalink": "/r/medicalmedium/comments/1qu51xg/sunbeds_fake_tan/o38n7ue",
        "action_type": "comment",
        "message": "That Beauty by Earth tan sounds like a solid clean option based on the Yuka score. Have you tried scanning the actual ingredients list instead of the barcode? I use the pom app for this and the thing that sets it apart is you customize how ingredients get flagged based on the severity of the research. So you choose if you care about in vitro findings or only large human studies. Way more personalized than a generic score",
    },
    {
        "username": "TriNel81",
        "subreddit": "Costco",
        "permalink": "/r/Costco/comments/1qtfkbt/sparkling_protein_zero_sugar_1_mg_130_calories/o34o6s0",
        "action_type": "comment",
        "message": "Totally get being on a health mission and checking things like Sucralose. what changed the game for me was switching from apps that give you a generic score to one where you control the flagging. the pom app lets you set severity levels based on research quality like human trials vs in vitro. Way more useful because everyone's risk tolerance is different",
    },
    {
        "username": "WhichJuice",
        "subreddit": "BabyBumpsCanada",
        "permalink": "/r/BabyBumpsCanada/comments/1rb5vqi/when_did_you_start_brushing_your_babys_teeth_with/o6shvpx",
        "action_type": "comment",
        "message": "Using Yuka to check for risky additives in toothpastes is a great approach. you might want to check out the pom app it scans the ingredients list instead of a barcode so it works with any product. The main thing is you get to customize your own flagging based on research quality like large human studies vs animal vs in vitro. So it actually reflects what you care about instead of giving everyone the same score",
    },
]


async def execute_one(browser, page, action, config, account_name, screenshot_dir):
    """Execute a single comment action with screenshot."""
    username = action["username"]
    permalink = action["permalink"]
    message = action["message"]
    subreddit = action["subreddit"]

    print(f"\n{'='*60}")
    print(f"ACTION: Comment on u/{username} in r/{subreddit}")
    print(f"PERMALINK: https://reddit.com{permalink}")
    print(f"MESSAGE:\n{message[:200]}...")
    print(f"{'='*60}")

    # Extract post_id for tracking
    post_id = None
    parts = permalink.split('/comments/')
    if len(parts) > 1:
        post_id = parts[1].split('/')[0]

    # Navigate and post
    try:
        new_page, success = await post_comment(
            browser, page, permalink, message, config,
            verify_keyword=None, verify_username=username
        )

        # Take screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = screenshot_dir / f"comment_{username}_{timestamp}.png"
        await new_page.save_screenshot(str(screenshot_path))
        print(f"[SCREENSHOT] Saved to: {screenshot_path}")

        if success:
            # Update tracker
            claim_user(username, account_name)
            if post_id:
                claim_thread(post_id, account_name, permalink)
            record_action(
                username=username,
                account=account_name,
                action_type=ActionType.COMMENT,
                result=ActionResult.SUCCESS,
                target=permalink,
                message_preview=message[:100],
            )
            print(f"[SUCCESS] Comment posted and tracked!")
        else:
            print(f"[FAILED] Comment may not have been posted")

        return new_page, success, screenshot_path

    except Exception as e:
        print(f"[ERROR] {e}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = screenshot_dir / f"error_{username}_{timestamp}.png"
        try:
            await page.save_screenshot(str(screenshot_path))
        except:
            pass
        return page, False, screenshot_path


async def main():
    config = load_config()

    # Use ilovereddidotcom account
    account = None
    for acc in config["accounts"]:
        if acc["username"] == "ilovereddidotcom":
            account = acc
            break

    if not account:
        print("Account 'ilovereddidotcom' not found!")
        return

    # Create screenshot directory
    screenshot_dir = Path(BASE_DIR) / "data" / "execution_screenshots" / datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"Screenshots will be saved to: {screenshot_dir}")

    # Login
    print(f"\n[AUTH] Logging in as {account['username']}...")
    browser, page = await login(config, account)
    if not page:
        print("[AUTH] Login failed!")
        return
    print("[AUTH] Login successful!")

    # Execute each action
    results = []
    start_index = int(os.environ.get("START_INDEX", 0))
    end_index = int(os.environ.get("END_INDEX", 1))

    for i, action in enumerate(ACTIONS[start_index:end_index], start=start_index):
        print(f"\n\n{'#'*60}")
        print(f"# ACTION {i+1}/{len(ACTIONS)}")
        print(f"{'#'*60}")

        page, success, screenshot = await execute_one(
            browser, page, action, config, account["username"], screenshot_dir
        )

        results.append({
            "action": action,
            "success": success,
            "screenshot": str(screenshot),
        })

        # Pause between actions
        if i < end_index - 1:
            print("\n[WAIT] Waiting 30 seconds before next action...")
            await asyncio.sleep(30)

    # Summary
    print(f"\n\n{'='*60}")
    print("EXECUTION SUMMARY")
    print(f"{'='*60}")
    success_count = sum(1 for r in results if r["success"])
    print(f"Success: {success_count}/{len(results)}")

    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} u/{r['action']['username']} in r/{r['action']['subreddit']}")

    # Save results
    results_path = screenshot_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")

    await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
