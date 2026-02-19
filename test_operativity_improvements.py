#!/usr/bin/env python3
"""Test script for operativity classification improvements."""

import os
import sys
import logging
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.processors.ai import generate_operativity, validate_operativity_classification

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_operativity_improvements():
    """Test operativity classification improvements on sample decisions."""
    print("🧪 TESTING OPERATIVITY CLASSIFICATION IMPROVEMENTS")
    print("=" * 60)

    # Get sample of recent decisions that were misclassified
    supabase = get_supabase_client()
    response = supabase.table('israeli_government_decisions').select(
        'decision_key, decision_title, decision_content, operativity, summary'
    ).order('decision_date', desc=True).limit(15).execute()

    if not response.data:
        print("❌ No decisions found in database")
        return

    results = {
        'tested': 0,
        'ai_operative': 0,
        'ai_declarative': 0,
        'final_operative': 0,
        'final_declarative': 0,
        'corrections_made': 0,
        'corrections': []
    }

    print(f"📊 Testing {len(response.data)} recent decisions...")
    print()

    for decision in response.data:
        results['tested'] += 1

        decision_key = decision['decision_key']
        title = decision['decision_title']
        content = decision['decision_content']
        current_operativity = decision.get('operativity', '')

        print(f"🔍 Testing: {decision_key}")
        print(f"   Title: {title[:60]}...")
        print(f"   Current DB: {current_operativity}")

        try:
            # Test new AI classification
            new_ai_operativity = generate_operativity(content)
            print(f"   New AI: {new_ai_operativity}")

            # Test rule-based validation
            final_operativity = validate_operativity_classification(
                new_ai_operativity, content, title
            )
            print(f"   Final: {final_operativity}")

            # Track statistics
            if new_ai_operativity == 'אופרטיבית':
                results['ai_operative'] += 1
            elif new_ai_operativity == 'דקלרטיבית':
                results['ai_declarative'] += 1

            if final_operativity == 'אופרטיבית':
                results['final_operative'] += 1
            elif final_operativity == 'דקלרטיבית':
                results['final_declarative'] += 1

            # Check for corrections
            if new_ai_operativity != final_operativity:
                results['corrections_made'] += 1
                results['corrections'].append({
                    'decision_key': decision_key,
                    'title': title[:60],
                    'ai_classification': new_ai_operativity,
                    'final_classification': final_operativity
                })
                print(f"   ✅ CORRECTED: {new_ai_operativity} → {final_operativity}")

            # Compare with current DB classification
            if current_operativity and current_operativity != final_operativity:
                print(f"   🔄 CHANGE FROM DB: {current_operativity} → {final_operativity}")

        except Exception as e:
            print(f"   ❌ ERROR: {e}")

        print()

    # Print results summary
    print("📊 RESULTS SUMMARY")
    print("=" * 60)

    if results['tested'] > 0:
        ai_operative_pct = (results['ai_operative'] / results['tested']) * 100
        final_operative_pct = (results['final_operative'] / results['tested']) * 100
        correction_pct = (results['corrections_made'] / results['tested']) * 100

        print(f"📋 Decisions tested: {results['tested']}")
        print(f"🤖 AI Classification:")
        print(f"   • Operative: {results['ai_operative']} ({ai_operative_pct:.1f}%)")
        print(f"   • Declarative: {results['ai_declarative']} ({100-ai_operative_pct:.1f}%)")
        print(f"🎯 Final Classification (after validation):")
        print(f"   • Operative: {results['final_operative']} ({final_operative_pct:.1f}%)")
        print(f"   • Declarative: {results['final_declarative']} ({100-final_operative_pct:.1f}%)")
        print(f"🔧 Rule-based corrections: {results['corrections_made']} ({correction_pct:.1f}%)")

        print("\n🎯 TARGET ANALYSIS:")
        if final_operative_pct > 75:
            print(f"⚠️  Still high operative bias: {final_operative_pct:.1f}% (target: 60-65%)")
        elif final_operative_pct < 50:
            print(f"⚠️  Too low operative rate: {final_operative_pct:.1f}% (target: 60-65%)")
        else:
            print(f"✅ Good operative rate: {final_operative_pct:.1f}% (target: 60-65%)")

        # Show corrections made
        if results['corrections']:
            print(f"\n🔧 CORRECTIONS MADE ({len(results['corrections'])}):")
            for correction in results['corrections'][:5]:  # Show first 5
                print(f"   • {correction['decision_key']}: {correction['ai_classification']} → {correction['final_classification']}")
                print(f"     {correction['title']}...")

    print("\n🏁 Test completed!")
    return results

if __name__ == "__main__":
    test_operativity_improvements()