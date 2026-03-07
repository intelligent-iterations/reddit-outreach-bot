"""Phase 4 (reordered): Template selection and filling tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.templates import detect_archetype, select_and_fill, extract_app_mentioned, extract_ingredient
from src.utils import load_templates


def test_archetype_detection():
    print("TEST: Archetype detection...")

    # DM archetypes
    lead_yuka = {"comment_text": "I've been using yuka app for months", "keyword_matched": "yuka app"}
    assert detect_archetype(lead_yuka, "dm") == "fellow_user"

    lead_rec = {"comment_text": "Does anyone recommend a good app for checking labels?", "keyword_matched": "healthy eating"}
    assert detect_archetype(lead_rec, "dm") == "feedback_request"

    lead_ing = {"comment_text": "Worried about sodium benzoate in my food", "keyword_matched": "sodium benzoate"}
    assert detect_archetype(lead_ing, "dm") == "ingredient_specific"

    lead_generic = {"comment_text": "I check labels carefully", "keyword_matched": "healthy food"}
    assert detect_archetype(lead_generic, "dm") == "soft_tease"

    # Comment archetypes
    assert detect_archetype(lead_yuka, "comment") == "scanner_mention"

    lead_ing_q = {"comment_text": "Is titanium dioxide safe?", "keyword_matched": "titanium dioxide"}
    assert detect_archetype(lead_ing_q, "comment") == "ingredient_question"

    lead_health = {"comment_text": "My eczema has been getting worse", "keyword_matched": "eczema"}
    assert detect_archetype(lead_health, "comment") == "health_topic"

    lead_gen = {"comment_text": "What products do you use?", "keyword_matched": "clean products"}
    assert detect_archetype(lead_gen, "comment") == "general_recommendation"

    print("  PASSED")


def test_app_extraction():
    print("TEST: App name extraction...")
    lead = {"comment_text": "Yuka gave this product a 90/100"}
    assert extract_app_mentioned(lead) == "Yuka"

    lead2 = {"comment_text": "I use EWG's Skin Deep database"}
    assert extract_app_mentioned(lead2) == "EWG"

    lead3 = {"comment_text": "Think Dirty is my go-to"}
    assert extract_app_mentioned(lead3) == "Think Dirty"

    print("  PASSED")


def test_ingredient_extraction():
    print("TEST: Ingredient extraction...")
    lead = {"comment_text": "Is propylene glycol really that bad?", "keyword_matched": "propylene glycol"}
    assert extract_ingredient(lead) == "propylene glycol"

    lead2 = {"comment_text": "Red 40 is in everything", "keyword_matched": "red 40"}
    assert extract_ingredient(lead2) == "Red 40"

    print("  PASSED")


def test_template_filling():
    print("TEST: Template filling...")
    templates = load_templates()

    lead = {
        "username": "HealthyMom_2024",
        "comment_text": "I've been using yuka app and love it but wish it had more detail",
        "subreddit": "YukaApp",
        "permalink": "/r/YukaApp/comments/abc/post/",
        "keyword_matched": "yuka app",
        "source": "comment_search"
    }

    # Test DM
    filled, archetype, subject = select_and_fill(lead, "dm", templates)
    assert filled is not None, "Template should be filled"
    assert archetype == "fellow_user", f"Expected fellow_user, got {archetype}"
    assert "{username}" not in filled, f"Unfilled placeholder in: {filled}"
    assert "{app_mentioned}" not in filled, f"Unfilled placeholder in: {filled}"
    assert "HealthyMom" in filled, f"Username not filled correctly: {filled}"
    assert subject is not None, "Subject should be filled for DMs"
    print(f"  DM archetype: {archetype}")
    print(f"  DM subject: {subject}")
    print(f"  DM body preview: {filled[:100]}...")

    # Test comment
    filled_c, archetype_c, subject_c = select_and_fill(lead, "comment", templates)
    assert filled_c is not None
    assert archetype_c == "scanner_mention"
    assert "{app_mentioned}" not in filled_c
    assert subject_c is None, "Comments should not have subjects"
    print(f"  Comment archetype: {archetype_c}")
    print(f"  Comment preview: {filled_c[:100]}...")

    print("  PASSED")


def test_rotation():
    print("TEST: Template rotation...")
    templates = load_templates()

    lead = {
        "username": "user123",
        "comment_text": "Yuka is great",
        "subreddit": "YukaApp",
        "keyword_matched": "yuka app",
        "source": "comment_search"
    }

    # Generate several messages and check we get both variations
    seen_messages = set()
    for _ in range(10):
        filled, _, _ = select_and_fill(lead, "dm", templates)
        seen_messages.add(filled[:50])

    assert len(seen_messages) >= 2, f"Expected rotation between variations, only got {len(seen_messages)} unique"
    print(f"  Got {len(seen_messages)} unique variations in 10 iterations")
    print("  PASSED")


def test_ingredient_lead():
    print("TEST: Ingredient-specific lead...")
    templates = load_templates()

    lead = {
        "username": "ConcernedParent",
        "comment_text": "I'm worried about sodium benzoate in my kid's juice",
        "subreddit": "HealthyFood",
        "keyword_matched": "sodium benzoate",
        "source": "comment_search"
    }

    filled, archetype, subject = select_and_fill(lead, "dm", templates)
    assert archetype == "ingredient_specific"
    assert "sodium benzoate" in filled.lower()
    print(f"  Archetype: {archetype}")
    print(f"  Subject: {subject}")
    print(f"  Preview: {filled[:120]}...")

    print("  PASSED")


def main():
    print("=" * 60)
    print("Template Tests")
    print("=" * 60)

    test_archetype_detection()
    test_app_extraction()
    test_ingredient_extraction()
    test_template_filling()
    test_rotation()
    test_ingredient_lead()

    print("\n" + "=" * 60)
    print("ALL TEMPLATE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
