#!/usr/bin/env python3
"""Test script to verify the post-deployment improvements."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.gov_scraper.processors.ai_post_processor import (
    post_process_ai_results,
    deduplicate_tags,
    fix_truncated_summary,
    filter_generic_locations,
    validate_ministry_context
)
from config.committee_mappings import normalize_committee_name

def test_duplicate_tags():
    """Test tag deduplication."""
    print("Testing duplicate tag removal...")

    # Test case 1: Duplicate tags
    test_tags = "משטרת ישראל; משטרת ישראל; משרד העבודה"
    result = deduplicate_tags(test_tags)
    print(f"  Input:  {test_tags}")
    print(f"  Output: {result}")
    assert result == "משטרת ישראל; משרד העבודה", f"Expected deduplicated tags, got: {result}"
    print("  ✅ Duplicate removal works")

    # Test case 2: No duplicates
    test_tags = "משרד האוצר; משרד החינוך"
    result = deduplicate_tags(test_tags)
    print(f"  Input:  {test_tags}")
    print(f"  Output: {result}")
    assert result == "משרד האוצר; משרד החינוך", f"Expected unchanged, got: {result}"
    print("  ✅ Non-duplicates preserved")

def test_truncated_summary():
    """Test summary truncation fix."""
    print("\nTesting summary truncation fix...")

    # Test case: Truncated summary
    truncated = "ההחלטה מאשרת את התקציב ומבקשת מוועדת הכ"
    result = fix_truncated_summary(truncated)
    print(f"  Input:  {truncated}")
    print(f"  Output: {result}")
    assert result.endswith("..."), f"Expected ellipsis ending, got: {result}"
    print("  ✅ Truncation fixed")

    # Test case: Complete summary
    complete = "ההחלטה מאשרת את התקציב."
    result = fix_truncated_summary(complete)
    print(f"  Input:  {complete}")
    print(f"  Output: {result}")
    assert result == complete, f"Expected unchanged, got: {result}"
    print("  ✅ Complete summary preserved")

def test_committee_mapping():
    """Test committee name normalization."""
    print("\nTesting committee mapping...")

    # Test case: Committee name variation
    variation = "וועדת שרים לתיקוני חקיקה (תחק)"
    canonical = normalize_committee_name(variation)
    print(f"  Input:  {variation}")
    print(f"  Output: {canonical}")
    assert canonical == "וועדת שרים לתיקוני חקיקה", f"Expected canonical form, got: {canonical}"
    print("  ✅ Committee normalization works")

def test_generic_location_filter():
    """Test generic location filtering."""
    print("\nTesting generic location filter...")

    # Test case: Generic locations
    locations = ["ישראל", "ירושלים", "תל אביב", "Israel"]
    result = filter_generic_locations(locations)
    print(f"  Input:  {locations}")
    print(f"  Output: {result}")
    assert "ישראל" not in result, f"Expected 'ישראל' to be filtered, got: {result}"
    assert "ירושלים" in result, f"Expected 'ירושלים' to be kept, got: {result}"
    print("  ✅ Generic locations filtered")

def test_ministry_context_validation():
    """Test ministry context validation."""
    print("\nTesting ministry context validation...")

    # Test case 1: Military content should not trigger police tag
    military_content = "החלטה בנושא גלי צה\"ל והתחנה הצבאית"
    is_valid = validate_ministry_context(military_content, "משטרת ישראל")
    print(f"  Military content + Police tag: {is_valid}")
    assert not is_valid, "Expected False for police tag on military content"
    print("  ✅ Military content excludes police tag")

    # Test case 2: Finance content should not trigger media tag
    finance_content = "החלטה בנושא קרנות גידור והשקעות בשוק ההון"
    is_valid = validate_ministry_context(finance_content, "תקשורת ומדיה")
    print(f"  Finance content + Media tag: {is_valid}")
    assert not is_valid, "Expected False for media tag on finance content"
    print("  ✅ Finance content excludes media tag")

def test_full_post_processing():
    """Test complete post-processing flow."""
    print("\nTesting full post-processing...")

    # Sample decision with issues
    decision_data = {
        'decision_key': '37_3861',
        'summary': 'החלטה על תקציב ומבקשת מוועדת הכ',
        'tags_policy_area': 'ביטחון פנים; ביטחון פנים',
        'tags_government_body': 'משטרת ישראל; משטרת ישראל; וועדת שרים לתיקוני חקיקה (תחק)',
        'tags_location': 'ישראל, ירושלים',
        'all_tags': 'ביטחון פנים; ביטחון פנים; משטרת ישראל; משטרת ישראל'
    }

    military_content = "החלטה בנושא גלי צה\"ל והרדיו הצבאי"

    result = post_process_ai_results(decision_data, military_content)

    print(f"  Original policy tags: {decision_data['tags_policy_area']}")
    print(f"  Cleaned policy tags:  {result['tags_policy_area']}")
    assert result['tags_policy_area'] == "ביטחון פנים", "Expected deduplication"

    print(f"  Original govt bodies: {decision_data['tags_government_body']}")
    print(f"  Cleaned govt bodies:  {result['tags_government_body']}")
    assert "משטרת ישראל" not in result['tags_government_body'], "Expected police exclusion for military content"
    assert "ועדת השרים" in result['tags_government_body'], "Expected committee normalization to ועדת השרים"

    print(f"  Original locations:   {decision_data['tags_location']}")
    print(f"  Cleaned locations:    {result['tags_location']}")
    assert "ישראל" not in result['tags_location'], "Expected generic location removal"

    print(f"  Original summary:     {decision_data['summary']}")
    print(f"  Cleaned summary:      {result['summary']}")
    assert result['summary'].endswith('...'), "Expected truncation fix"

    # Verify all_tags is rebuilt correctly from cleaned fields
    assert "ביטחון פנים" in result['all_tags'], "Expected policy tag in all_tags"
    assert "ועדת השרים" in result['all_tags'], "Expected gov body in all_tags"
    assert "ירושלים" in result['all_tags'], "Expected location in all_tags"
    assert "משטרת ישראל" not in result['all_tags'], "Excluded body should not be in all_tags"

    print("  ✅ Full post-processing works correctly")

def main():
    """Run all tests."""
    print("=" * 60)
    print("POST-DEPLOYMENT IMPROVEMENTS TEST SUITE")
    print("=" * 60)

    try:
        test_duplicate_tags()
        test_truncated_summary()
        test_committee_mapping()
        test_generic_location_filter()
        test_ministry_context_validation()
        test_full_post_processing()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())