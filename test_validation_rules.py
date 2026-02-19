#!/usr/bin/env python3
"""Test script for operativity validation rules (no AI calls)."""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.gov_scraper.processors.ai import validate_operativity_classification
from src.gov_scraper.db.connector import get_supabase_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_validation_rules():
    """Test operativity validation rules on real decision data."""
    print("🧪 TESTING OPERATIVITY VALIDATION RULES")
    print("=" * 60)

    # Get sample decisions from DB
    supabase = get_supabase_client()
    response = supabase.table('israeli_government_decisions').select(
        'decision_key, decision_title, decision_content, operativity'
    ).order('decision_date', desc=True).limit(20).execute()

    if not response.data:
        print("❌ No decisions found in database")
        return

    results = {
        'tested': 0,
        'corrections_made': 0,
        'operative_to_declarative': 0,
        'declarative_to_operative': 0,
        'unchanged': 0,
        'corrections': []
    }

    print(f"📊 Testing validation rules on {len(response.data)} decisions...")
    print()

    for decision in response.data:
        results['tested'] += 1

        decision_key = decision['decision_key']
        title = decision['decision_title']
        content = decision['decision_content']
        current_operativity = decision.get('operativity', 'אופרטיבית')  # Most are currently operative

        # Test rule-based validation
        validated_operativity = validate_operativity_classification(
            current_operativity, content, title
        )

        print(f"🔍 {decision_key}: {title[:50]}...")
        print(f"   Current: {current_operativity} → Validated: {validated_operativity}")

        # Track changes
        if current_operativity != validated_operativity:
            results['corrections_made'] += 1

            if current_operativity == 'אופרטיבית' and validated_operativity == 'דקלרטיבית':
                results['operative_to_declarative'] += 1
            elif current_operativity == 'דקלרטיבית' and validated_operativity == 'אופרטיבית':
                results['declarative_to_operative'] += 1

            results['corrections'].append({
                'decision_key': decision_key,
                'title': title[:60],
                'before': current_operativity,
                'after': validated_operativity
            })
            print(f"   ✅ CORRECTED!")
        else:
            results['unchanged'] += 1
            print(f"   ✓ No change")

        print()

    # Print results summary
    print("📊 VALIDATION RESULTS SUMMARY")
    print("=" * 60)

    if results['tested'] > 0:
        correction_pct = (results['corrections_made'] / results['tested']) * 100
        op_to_dec_pct = (results['operative_to_declarative'] / results['tested']) * 100

        print(f"📋 Decisions tested: {results['tested']}")
        print(f"🔧 Total corrections: {results['corrections_made']} ({correction_pct:.1f}%)")
        print(f"📉 Operative → Declarative: {results['operative_to_declarative']} ({op_to_dec_pct:.1f}%)")
        print(f"📈 Declarative → Operative: {results['declarative_to_operative']}")
        print(f"✅ Unchanged: {results['unchanged']}")

        print(f"\n🎯 BIAS REDUCTION ANALYSIS:")
        print(f"Rule-based corrections reduced operative bias by {op_to_dec_pct:.1f} percentage points")

        if results['corrections']:
            print(f"\n🔧 CORRECTIONS MADE ({len(results['corrections'])}):")
            for correction in results['corrections']:
                print(f"   • {correction['decision_key']}: {correction['before']} → {correction['after']}")
                print(f"     {correction['title']}...")

        print(f"\n🏆 EXPECTED IMPACT:")
        if results['operative_to_declarative'] > 0:
            print(f"✅ Validation rules will reduce operative bias")
            print(f"✅ {results['operative_to_declarative']} misclassified appointments/committees will be corrected")
        else:
            print("⚠️  No rule-based corrections found - may need enhanced patterns")

    print("\n🏁 Validation test completed!")
    return results

if __name__ == "__main__":
    test_validation_rules()