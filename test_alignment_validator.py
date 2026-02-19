#!/usr/bin/env python3
"""
Test the alignment validator component independently.

This tests the core alignment validation logic without API calls.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.gov_scraper.processors.alignment_validator import create_alignment_validator

# Test cases with known alignment issues
TEST_CASES = [
    {
        'name': 'Major misalignment - Anti-prostitution law tagged as culture',
        'summary': 'הממשלה אישרה את טיוטת חוק איסור צריכת זנות לשנת 2025',
        'tags': ['תרבות וספורט'],
        'expected_aligned': False,
        'expected_corrected': ['חקיקה, משפט ורגולציה']
    },
    {
        'name': 'Good alignment - Education budget for education tag',
        'summary': 'הקצאת 150 מיליון שקל לשיפור בתי ספר ותשתיות חינוכיות',
        'tags': ['חינוך'],
        'expected_aligned': True,
        'expected_corrected': []
    },
    {
        'name': 'Over-tagging - Administrative meeting with domain tags',
        'summary': 'הקמת ועדה לבחינת נושא התחבורה הציבורית',
        'tags': ['תחבורה ובטיחות בדרכים', 'ועדות', 'תכנון ובינוי'],
        'expected_aligned': False,
        'expected_corrected': ['מנהלתי']
    },
    {
        'name': 'Appointment misalignment',
        'summary': 'מינוי ד"ר כהן למנכ"לית משרד החינוך החל מינואר',
        'tags': ['חינוך', 'מנהל ציבורי ושירות המדינה'],
        'expected_aligned': False,
        'expected_corrected': ['מינויים']
    },
    {
        'name': 'Mixed content alignment',
        'summary': 'החלטת הממשלה על המשך הדיון במתווה יציאה מסגר הקורונה כולל פתיחת מערכת החינוך',
        'tags': ['חינוך', 'בריאות ורפואה', 'משבר הקורונה'],
        'expected_aligned': True,  # Should be aligned as summary mentions education explicitly
        'expected_corrected': []
    }
]

def load_policy_areas():
    """Load policy areas for the validator."""
    try:
        with open('new_tags.md', 'r', encoding='utf-8') as f:
            tags = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' not in line:
                    tags.append(line)
            return tags
    except FileNotFoundError:
        # Default tags for testing
        return [
            'שונות', 'חינוך', 'בריאות ורפואה', 'מדיני ביטחוני',
            'תחבורה ובטיחות בדרכים', 'אנרגיה מים ותשתיות',
            'חקיקה, משפט ורגולציה', 'מינויים', 'מנהלתי', 'תרבות וספורט',
            'דיור, נדלן ותכנון', 'תעשייה מסחר ומשק', 'נשים ומגדר',
            'משבר הקורונה', 'מנהל ציבורי ושירות המדינה'
        ]

def test_alignment_validator():
    """Test the alignment validator component."""
    print("🔬 Testing Summary-Tag Alignment Validator")
    print("=" * 60)
    print()

    policy_areas = load_policy_areas()
    validator = create_alignment_validator(policy_areas)

    results = {
        'total_tests': len(TEST_CASES),
        'correct_predictions': 0,
        'good_corrections': 0
    }

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Summary: {test_case['summary']}")
        print(f"Tags: {test_case['tags']}")
        print()

        # Validate alignment
        validation = validator.validate_alignment(
            test_case['summary'],
            test_case['tags']
        )

        print(f"📊 VALIDATOR RESULTS:")
        print(f"   Alignment Score: {validation.alignment_score:.3f}")
        print(f"   Is Aligned: {'✅ Yes' if validation.is_aligned else '❌ No'}")
        print(f"   Expected Aligned: {'✅ Yes' if test_case['expected_aligned'] else '❌ No'}")
        print()

        if validation.issues:
            print(f"   Issues Detected: {validation.issues}")
        if validation.suggestions:
            print(f"   Suggestions: {validation.suggestions}")
        if validation.corrected_tags:
            print(f"   Corrected Tags: {validation.corrected_tags}")
        print()

        # Check prediction accuracy
        prediction_correct = validation.is_aligned == test_case['expected_aligned']
        if prediction_correct:
            results['correct_predictions'] += 1
            print("✅ PREDICTION: Correct alignment assessment")
        else:
            print("❌ PREDICTION: Incorrect alignment assessment")

        # Check correction quality
        if not test_case['expected_aligned'] and validation.corrected_tags:
            # Check if suggested corrections are reasonable
            suggested_reasonable = any(
                expected in validation.corrected_tags
                for expected in test_case['expected_corrected']
            )
            if suggested_reasonable:
                results['good_corrections'] += 1
                print("✅ CORRECTION: Good tag suggestions provided")
            else:
                print("🟡 CORRECTION: Tag suggestions could be better")
        elif test_case['expected_aligned'] and validation.is_aligned:
            results['good_corrections'] += 1

        print("-" * 60)
        print()

    # Summary
    prediction_accuracy = (results['correct_predictions'] / results['total_tests']) * 100
    correction_quality = (results['good_corrections'] / results['total_tests']) * 100

    print("🎯 VALIDATOR TEST RESULTS")
    print("=" * 60)
    print(f"Cases tested: {results['total_tests']}")
    print(f"Correct predictions: {results['correct_predictions']}")
    print(f"Prediction accuracy: {prediction_accuracy:.1f}%")
    print(f"Good corrections: {results['good_corrections']}")
    print(f"Correction quality: {correction_quality:.1f}%")
    print()

    if prediction_accuracy >= 80 and correction_quality >= 70:
        print("🎉 SUCCESS: Alignment validator is working well!")
        print("   The validator correctly identifies alignment issues and suggests good corrections.")
    elif prediction_accuracy >= 60:
        print("🟡 GOOD PROGRESS: Validator shows promise but needs refinement.")
    else:
        print("❌ NEEDS IMPROVEMENT: Validator logic requires adjustment.")

    return prediction_accuracy, correction_quality

if __name__ == "__main__":
    test_alignment_validator()