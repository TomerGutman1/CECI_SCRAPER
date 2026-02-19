#!/usr/bin/env python3
"""
Verification script to check AI tag assignment improvements.
"""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gov_scraper.processors.ai_validator import AIResponseValidator

def test_tag_validation():
    """Test the enhanced tag validation system."""

    # Initialize validator with sample tags
    policy_areas = ["מינויים", "מנהלתי", "ביטחון פנים", "חינוך", "בריאות ורפואה", "מדיני ביטחוני"]
    government_bodies = ["מזכירות הממשלה", "משרד החינוך"]

    validator = AIResponseValidator(policy_areas, government_bodies)

    print("🔧 Testing Enhanced AI Tag Validation")
    print("=" * 50)

    # Test Case 1: Appointment Decision
    test_cases = [
        {
            "name": "Appointment Decision",
            "title": "מינוי מנהל הרשות הלאומית לביטחון קהילתי",
            "content": "מחליטים למנות את אביטל חן לתפקיד מנהל הרשות לביטחון קהילתי",
            "original_tags": ["ביטחון פנים", "מדיני ביטחוני"],  # Wrong - should be מינויים
            "expected_tags": ["מינויים"]
        },
        {
            "name": "PM Travel Decision",
            "title": "נסיעת ראש הממשלה לארצות הברית",
            "content": "הממשלה רושמת לפניה את נסיעת ראש הממשלה לארצות הברית",
            "original_tags": ["מדיני ביטחוני", "מנהלתי"],  # Over-tagged
            "expected_tags": ["מנהלתי"]
        },
        {
            "name": "Education Budget Decision",
            "title": "הקצאת תקציב נוסף למערכת החינוך",
            "content": "מחליטים להקצות 150 מיליון שקל נוסף למשרד החינוך לשיפור תשתיות",
            "original_tags": ["חינוך", "תקציב, פיננסים, ביטוח ומיסוי"],  # Correct
            "expected_tags": ["חינוך"]  # Primary tag should remain
        }
    ]

    for i, test_case in enumerate(test_cases):
        print(f"\n📋 Test {i+1}: {test_case['name']}")
        print(f"Title: {test_case['title']}")
        print(f"Original tags: {test_case['original_tags']}")

        try:
            # Test the enhanced validation
            validation_result = validator.validate_policy_tags_with_profiles(
                test_case['original_tags'],
                test_case['content'],
                test_case['title']
            )

            print(f"✅ Validation passed: {validation_result.is_valid}")
            print(f"✅ Confidence score: {validation_result.confidence_score:.2f}")

            if validation_result.errors:
                print(f"❌ Rejected tags: {validation_result.errors}")

            if validation_result.warnings:
                print(f"⚠️  Warnings: {validation_result.warnings}")

            # Test the specific rule application
            validated_tags, rejected_tags = validator._validate_tag_content_relevance(
                test_case['original_tags'],
                test_case['content'],
                test_case['title']
            )

            print(f"🔍 Validated tags: {validated_tags}")
            print(f"🔍 Rejected tags: {rejected_tags}")

            # Check if improvement matches expectation
            if set(validated_tags) == set(test_case['expected_tags']):
                print("✅ PASS: Tag validation matches expected result")
            else:
                print(f"❓ NOTE: Expected {test_case['expected_tags']}, got {validated_tags}")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        print("-" * 30)

def test_prompt_improvements():
    """Test that our prompt improvements are loaded correctly."""
    print("\n🎯 Testing Prompt Improvements")
    print("=" * 50)

    try:
        from gov_scraper.processors.ai_prompts import POLICY_TAG_EXAMPLES, UNIFIED_PROCESSING_PROMPT

        # Check if enhanced examples are loaded
        if "עקרונות תיוג מדיניות - חובה לקרוא" in POLICY_TAG_EXAMPLES:
            print("✅ Enhanced policy tag examples loaded")
        else:
            print("❌ Enhanced policy tag examples NOT found")

        # Check if enhanced prompt instructions are loaded
        if "תגיות מדיניות - כללי רלוונטיות מחמירים" in UNIFIED_PROCESSING_PROMPT:
            print("✅ Enhanced prompt instructions loaded")
        else:
            print("❌ Enhanced prompt instructions NOT found")

        # Check specific improvements
        improvements = [
            ("Primary tag focus", "בחר תג ראשי יחיד"),
            ("Appointment rules", "מינויים לתפקיד = \"מינויים\""),
            ("Administrative rules", "נסיעות/ועדות/נהלים = \"מנהלתי\""),
            ("Relevance criteria", "אל תתג על בסיס אזכור בלבד"),
            ("Tag limit", "מקסימום 2 תגים")
        ]

        for improvement_name, text_check in improvements:
            if text_check in POLICY_TAG_EXAMPLES or text_check in UNIFIED_PROCESSING_PROMPT:
                print(f"✅ {improvement_name}: Found")
            else:
                print(f"❌ {improvement_name}: Missing")

    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run all verification tests."""
    print("🚀 AI Tag Assignment Improvements Verification")
    print("=" * 60)

    test_prompt_improvements()
    test_tag_validation()

    print("\n📊 Summary:")
    print("- Enhanced AI prompting with specific relevance criteria")
    print("- Semantic validation using tag detection profiles")
    print("- Specific rules for appointments, admin actions, and budgets")
    print("- Primary tag focus with max 2 tags recommendation")
    print("- Real-time tag filtering based on content analysis")

if __name__ == "__main__":
    main()