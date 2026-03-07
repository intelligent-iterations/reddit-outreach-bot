import random
import re

# Keywords for archetype detection
SCANNER_APPS = ["yuka", "ewg", "think dirty", "inci beauty", "clean beauty app", "ingredient scanner", "food scanner"]
HEALTH_TOPICS = ["bloating", "gut", "eczema", "rash", "allergy", "allergies", "migraine", "palpitation", "skin issue",
                 "stool", "digestion", "inflammation", "breakout", "irritation", "hives", "dermatitis"]
RECOMMENDATION_PHRASES = ["recommend", "looking for", "any suggestions", "alternative", "what app", "best app",
                          "anyone know", "does anyone"]

# Track rotation to avoid repeating same variation
_last_used = {}


def detect_archetype(lead, action_type):
    """Determine which template archetype to use based on lead context."""
    text = (lead.get("comment_text", "") + " " + lead.get("post_title", "")).lower()
    keyword = lead.get("keyword_matched", "").lower()

    if action_type == "dm":
        # Check for scanner app mentions
        for app in SCANNER_APPS:
            if app in text or app in keyword:
                return "fellow_user"

        # Check for recommendation requests
        for phrase in RECOMMENDATION_PHRASES:
            if phrase in text:
                return "feedback_request"

        # Check for specific ingredient mentions
        if _has_ingredient(text, lead):
            return "ingredient_specific"

        return "soft_tease"

    else:  # comment
        # Check for scanner app mentions
        for app in SCANNER_APPS:
            if app in text or app in keyword:
                return "scanner_mention"

        # Check for ingredient questions
        if _has_ingredient(text, lead) and ("?" in lead.get("comment_text", "")):
            return "ingredient_question"

        # Check for health topic mentions
        for topic in HEALTH_TOPICS:
            if topic in text:
                return "health_topic"

        return "general_recommendation"


def _has_ingredient(text, lead):
    """Check if the lead mentions a specific ingredient."""
    # Common ingredients to match against
    ingredients = ["propylene glycol", "sodium benzoate", "red 40", "allura red",
                   "titanium dioxide", "natural flavors", "carrageenan", "bha", "bht",
                   "sodium nitrite", "parabens", "sulfates", "phthalates", "formaldehyde",
                   "triclosan", "oxybenzone"]
    for ing in ingredients:
        if ing in text:
            return True
    return False


def extract_app_mentioned(lead):
    """Extract which app is mentioned in the lead."""
    text = (lead.get("comment_text", "") + " " + lead.get("post_title", "")).lower()
    app_names = {
        "yuka": "Yuka", "ewg": "EWG", "think dirty": "Think Dirty",
        "inci beauty": "INCI Beauty", "clean beauty": "Clean Beauty",
        "food scanner": "food scanner"
    }
    for key, name in app_names.items():
        if key in text:
            return name
    return "ingredient scanning apps"


def extract_ingredient(lead):
    """Extract which ingredient is mentioned in the lead."""
    text = (lead.get("comment_text", "") + " " + lead.get("post_title", "")).lower()
    ingredients = {
        "propylene glycol": "propylene glycol", "sodium benzoate": "sodium benzoate",
        "red 40": "Red 40", "allura red": "Allura Red", "titanium dioxide": "titanium dioxide",
        "natural flavors": "natural flavors", "carrageenan": "carrageenan",
        "bha": "BHA", "bht": "BHT", "sodium nitrite": "sodium nitrite",
        "parabens": "parabens", "sulfates": "sulfates", "phthalates": "phthalates"
    }
    for key, name in ingredients.items():
        if key in text:
            return name
    # Fall back to keyword
    return lead.get("keyword_matched", "ingredients")


def extract_topic(lead):
    """Extract the general topic from the lead."""
    text = lead.get("comment_text", "") or lead.get("post_title", "")
    # Use first 50 chars of their text as topic reference
    if len(text) > 50:
        # Try to cut at a word boundary
        cut = text[:50].rsplit(" ", 1)[0]
        return cut.lower().rstrip(".,!?")
    return text.lower().rstrip(".,!?") if text else "ingredient safety"


def select_and_fill(lead, action_type, templates, config=None):
    """Select a template archetype, pick a variation, fill placeholders.

    Returns (filled_message, archetype, subject) for DMs or (filled_message, archetype, None) for comments.
    """
    archetype = detect_archetype(lead, action_type)

    # Get templates for this action type + archetype
    if action_type == "dm":
        template_list = templates.get("dm_templates", {}).get(archetype, [])
        subject_template = templates.get("dm_subjects", {}).get(archetype, "hey")
    else:
        template_list = templates.get("comment_templates", {}).get(archetype, [])
        subject_template = None

    if not template_list:
        return None, archetype, None

    # Pick a variation avoid repeating the same one consecutively
    rotation_key = f"{action_type}_{archetype}"
    last_index = _last_used.get(rotation_key, -1)

    available = list(range(len(template_list)))
    if len(available) > 1 and last_index in available:
        available.remove(last_index)

    chosen_index = random.choice(available)
    _last_used[rotation_key] = chosen_index

    template = template_list[chosen_index]

    # Build placeholder values
    username = lead.get("username", "there")
    # Use first part of username for a friendlier tone
    if "_" in username:
        friendly_name = username.split("_")[0]
    elif "-" in username:
        friendly_name = username.split("-")[0]
    else:
        friendly_name = username

    placeholders = {
        "username": friendly_name,
        "subreddit": lead.get("subreddit", "").lstrip("r/"),
        "topic": extract_topic(lead),
        "app_mentioned": extract_app_mentioned(lead),
        "ingredient": extract_ingredient(lead),
        "post_or_comment": "comment" if lead.get("source") == "comment_search" else "post",
        "their_text_snippet": (lead.get("comment_text", "")[:80] + "...") if lead.get("comment_text", "") else ""
    }

    # Fill placeholders
    filled = template
    for key, value in placeholders.items():
        filled = filled.replace("{" + key + "}", value)

    # Fill subject for DMs
    subject = None
    if subject_template:
        subject = subject_template
        for key, value in placeholders.items():
            subject = subject.replace("{" + key + "}", value)

    return filled, archetype, subject


def fill_template_from_decision(decision, strategy_templates: dict) -> str | None:
    """Fill a template using Grok's chosen template + placeholders.

    If Grok provided a custom_message, use it (after filling any remaining placeholders).
    Otherwise, fall back to filling the template with placeholders.
    """
    # If Grok provided a custom message, use it but still fill placeholders
    if decision.custom_message:
        filled = decision.custom_message
        for key, value in decision.placeholders.items():
            filled = filled.replace("{" + key + "}", str(value))

        # Warn about unfilled placeholders
        remaining = re.findall(r'\{(\w+)\}', filled)
        if remaining:
            print(f"[TEMPLATES] WARNING: Unfilled placeholders in custom_message: {remaining}")

        return filled

    # Fall back to template filling
    action_key = "dm_templates" if decision.action_type == "dm" else "comment_templates"
    template_list = strategy_templates.get(action_key, {}).get(decision.template_name, [])

    if not template_list:
        return None

    if decision.template_variation >= len(template_list):
        return None

    template = template_list[decision.template_variation]

    filled = template
    for key, value in decision.placeholders.items():
        filled = filled.replace("{" + key + "}", str(value))

    # Warn about unfilled placeholders
    remaining = re.findall(r'\{(\w+)\}', filled)
    if remaining:
        print(f"[TEMPLATES] WARNING: Unfilled placeholders: {remaining}")

    return filled


def fill_subject_from_decision(decision, strategy_templates: dict) -> str:
    """Fill a DM subject line using Grok's placeholders."""
    subject_template = strategy_templates.get("dm_subjects", {}).get(decision.template_name, "hey")
    subject = subject_template
    for key, value in decision.placeholders.items():
        subject = subject.replace("{" + key + "}", str(value))
    return subject
