#!/usr/bin/env python3
"""
Test script to validate summary-tag alignment improvements.

This script tests the enhanced AI processing system against known problematic cases
to measure improvement in summary-tag alignment accuracy.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.gov_scraper.processors.unified_ai import create_unified_processor
from src.gov_scraper.processors.alignment_validator import create_alignment_validator
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load authorized tags
def load_tags():
    """Load authorized policy areas and government bodies."""
    policy_areas = []
    government_bodies = []

    try:
        with open('new_tags.md', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' not in line:
                    policy_areas.append(line)
    except FileNotFoundError:
        logger.warning("new_tags.md not found, using default tags")
        policy_areas = ['שונות', 'חינוך', 'בריאות ורפואה']

    try:
        with open('new_departments.md', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' not in line:
                    government_bodies.append(line)
    except FileNotFoundError:
        logger.warning("new_departments.md not found, using default departments")
        government_bodies = ['משרד החינוך', 'משרד הבריאות']

    return policy_areas, government_bodies

# Test cases based on real problematic decisions
TEST_CASES = [
    {
        'name': 'Anti-prostitution law (major misalignment)',
        'title': 'טיוטת חוק איסור צריכת זנות, התשפ"ה-2025',
        'content': '''הממשלה החליטה לאשר את טיוטת חוק איסור צריכת זנות, התשפ"ה-2025.
החוק קובע איסור על צריכת שירותי זנות וקובע עונשים על עבריינים.
המטרה היא להגן על נשים ולחזק את המאבק בסחר בבני אדם.''',
        'expected_tags': ['חקיקה, משפט ורגולציה', 'נשים ומגדר'],
        'problematic_tags': ['תרבות וספורט']  # This was the original wrong tag
    },
    {
        'name': 'Administrative meeting (over-tagging)',
        'title': 'דיון בועדת השרים בנושא תכנון עירוני',
        'content': '''הממשלה החליטה על המשך הדיון בועדת השרים בנושא תכנון עירוני.
הדיון יכלול נציגי משרדי הפנים, השיכון והאוצר.
הועדה תגיש המלצותיה תוך 30 יום.''',
        'expected_tags': ['מנהלתי'],
        'problematic_tags': ['דיור, נדלן ותכנון', 'תכנון ובינוי', 'שלטון מקומי']
    },
    {
        'name': 'Appointment decision',
        'title': 'מינוי מנכ"ל חדש למשרד החינוך',
        'content': '''הממשלה החליטה למנות את ד"ר שרה כהן למנכ"לית משרד החינוך.
המינוי יכנס לתוקף החל מ-1 בינואר 2026.
ד"ר כהן תחליף את המנכ"ל היוצא.''',
        'expected_tags': ['מינויים'],
        'problematic_tags': ['חינוך', 'מנהל ציבורי ושירות המדינה']
    },
    {
        'name': 'Budget allocation (should align)',
        'title': 'הקצאת תקציב לשיפור תשתיות חינוכיות',
        'content': '''הממשלה החליטה להקצות 150 מיליון שקל לשיפור תשתיות חינוכיות.
התקציב יופנה לבניית בתי ספר חדשים ושיפוץ בתי ספר קיימים.
התוכנית תבוצע על פני שלוש שנים.''',
        'expected_tags': ['חינוך'],
        'problematic_tags': ['אנרגיה מים ותשתיות']  # Common confusion
    }
]

def test_alignment_improvements():
    """Test the alignment improvements on problematic cases."""
    policy_areas, government_bodies = load_tags()

    # Create processors
    processor = create_unified_processor(policy_areas, government_bodies)
    alignment_validator = create_alignment_validator(policy_areas)

    print("🔬 Testing Summary-Tag Alignment Improvements")
    print("=" * 60)
    print()

    results = {
        'total_tests': len(TEST_CASES),
        'improved_cases': 0,
        'alignment_scores': [],
        'detailed_results': []
    }

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Title: {test_case['title']}")
        print(f"Expected tags: {test_case['expected_tags']}")
        print(f"Problematic tags: {test_case['problematic_tags']}")
        print()

        try:
            # Process with enhanced AI
            result = processor.process_decision_unified(
                test_case['content'],
                test_case['title']
            )

            # Test alignment
            alignment = alignment_validator.validate_alignment(
                result.summary,
                result.policy_areas,
                test_case['title'],
                test_case['content']
            )

            print(f"✨ ENHANCED AI RESULTS:")
            print(f"   Summary: {result.summary}")
            print(f"   Tags Generated: {result.policy_areas}")
            print(f"   Core Theme: {result.core_theme}")
            print(f"   AI Alignment Check: {result.alignment_check}")
            print()

            print(f"📊 VALIDATION RESULTS:")
            print(f"   Alignment Score: {alignment.alignment_score:.2f}")
            print(f"   Is Aligned: {'✅ Yes' if alignment.is_aligned else '❌ No'}")
            if alignment.issues:
                print(f"   Issues Found: {alignment.issues}")
            if alignment.suggestions:
                print(f"   Suggestions: {alignment.suggestions}")
            if alignment.corrected_tags:
                print(f"   Suggested Tags: {alignment.corrected_tags}")
            print()

            # Check if tags match expected
            tags_improved = any(tag in result.policy_areas for tag in test_case['expected_tags'])
            problematic_avoided = not any(tag in result.policy_areas for tag in test_case['problematic_tags'])

            if tags_improved and problematic_avoided:
                results['improved_cases'] += 1
                print("✅ IMPROVEMENT SUCCESS: Generated appropriate tags and avoided problematic ones")
            elif tags_improved:
                print("🟡 PARTIAL SUCCESS: Generated good tags but may have extra ones")
            else:
                print("❌ NEEDS WORK: Still has alignment issues")

            results['alignment_scores'].append(alignment.alignment_score)
            results['detailed_results'].append({
                'test_name': test_case['name'],
                'generated_tags': result.policy_areas,
                'alignment_score': alignment.alignment_score,
                'is_aligned': alignment.is_aligned,
                'improvement_success': tags_improved and problematic_avoided
            })

        except Exception as e:
            print(f"❌ ERROR processing test case: {e}")
            results['detailed_results'].append({
                'test_name': test_case['name'],
                'error': str(e),
                'improvement_success': False
            })

        print("-" * 60)
        print()

    # Summary results
    improvement_rate = (results['improved_cases'] / results['total_tests']) * 100
    avg_alignment_score = sum(results['alignment_scores']) / len(results['alignment_scores']) if results['alignment_scores'] else 0

    print("🎯 FINAL RESULTS SUMMARY")
    print("=" * 60)
    print(f"Cases tested: {results['total_tests']}")
    print(f"Improved cases: {results['improved_cases']}")
    print(f"Improvement rate: {improvement_rate:.1f}%")
    print(f"Average alignment score: {avg_alignment_score:.3f}")
    print()

    if improvement_rate >= 75:
        print("🎉 SUCCESS: Major improvement in summary-tag alignment!")
        print("   The enhanced AI system successfully addresses the alignment issues.")
    elif improvement_rate >= 50:
        print("🟡 GOOD PROGRESS: Significant improvement achieved.")
        print("   Further refinement may be beneficial.")
    else:
        print("❌ MORE WORK NEEDED: Alignment issues persist.")
        print("   Additional improvements required.")

    # Save detailed results
    with open('alignment_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed results saved to: alignment_test_results.json")

    return improvement_rate, avg_alignment_score

if __name__ == "__main__":
    test_alignment_improvements()