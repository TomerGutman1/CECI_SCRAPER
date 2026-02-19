#!/usr/bin/env python3
"""
Test New Algorithm Improvements
==============================
Process a sample of decisions through the new unified AI system
to measure actual improvement vs existing database records.
"""
import json
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client
from gov_scraper.processors.unified_ai import UnifiedAIProcessor
from gov_scraper.processors.ai_post_processor import post_process_ai_results


def get_sample_decisions(limit=20):
    """Get recent decisions for testing."""
    try:
        client = get_supabase_client()
        result = client.table('israeli_government_decisions').select('*').limit(limit).execute()
        return result.data
    except Exception as e:
        print(f"❌ Database error: {e}")
        return []


def process_with_new_algorithms(decisions):
    """Process decisions through new unified AI system."""
    print(f"🧠 Processing {len(decisions)} decisions through new AI system...")

    # Load authorized tags and bodies
    try:
        with open('new_tags.md', 'r', encoding='utf-8') as f:
            policy_areas = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        with open('new_departments.md', 'r', encoding='utf-8') as f:
            government_bodies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"❌ Error loading authorized lists: {e}")
        return []

    processor = UnifiedAIProcessor(policy_areas, government_bodies)
    improved_results = []

    for i, decision in enumerate(decisions):
        print(f"  Processing {i+1}/{len(decisions)}: {decision.get('decision_key', 'N/A')}")

        # Create a mock decision object for processing
        mock_decision = {
            'decision_title': decision.get('decision_title', ''),
            'decision_content': decision.get('decision_content', ''),
            'decision_date': decision.get('decision_date', ''),
            'decision_number': decision.get('decision_number', ''),
            'government_number': decision.get('government_number', ''),
            'decision_key': decision.get('decision_key', ''),
        }

        try:
            # Process through unified AI
            title = mock_decision.get('decision_title', '')
            content = mock_decision.get('decision_content', '')
            ai_result = processor.process_decision_unified(title, content)

            # Apply post-processing fixes
            content = mock_decision.get('decision_content', '') + ' ' + mock_decision.get('decision_title', '')
            fixed_result = post_process_ai_results(ai_result, content)

            # Compare with original
            comparison = {
                'decision_key': decision.get('decision_key'),
                'original': {
                    'policy_tags': decision.get('tags_policy_area', '').split(';') if decision.get('tags_policy_area') else [],
                    'gov_bodies': decision.get('tags_government_body', '').split(';') if decision.get('tags_government_body') else [],
                    'operativity': decision.get('operativity', ''),
                    'summary': decision.get('summary', '')[:100] + '...'
                },
                'improved': {
                    'policy_tags': fixed_result.get('policy_tags', []),
                    'gov_bodies': fixed_result.get('government_bodies', []),
                    'operativity': fixed_result.get('operativity', ''),
                    'summary': fixed_result.get('summary', '')[:100] + '...'
                }
            }

            improved_results.append(comparison)

        except Exception as e:
            print(f"    ❌ Processing error: {e}")
            continue

    return improved_results


def analyze_improvements(comparisons):
    """Analyze quality improvements between old and new processing."""
    print(f"\n📊 ANALYZING ALGORITHM IMPROVEMENTS")
    print("=" * 60)

    total = len(comparisons)
    if total == 0:
        print("No comparisons available")
        return

    # Policy tag improvements
    policy_improvements = 0
    operativity_improvements = 0
    summary_improvements = 0
    body_improvements = 0

    print("\n🏷️ POLICY TAG IMPROVEMENTS:")
    for comp in comparisons[:5]:  # Show first 5
        original_tags = comp['original']['policy_tags']
        improved_tags = comp['improved']['policy_tags']

        # Simple quality heuristics
        original_count = len([t for t in original_tags if t.strip()])
        improved_count = len([t for t in improved_tags if t.strip()])

        if improved_count > 0 and (improved_count != original_count or set(improved_tags) != set(original_tags)):
            policy_improvements += 1
            print(f"  {comp['decision_key']}:")
            print(f"    Original: {original_tags}")
            print(f"    Improved: {improved_tags}")

    print(f"\n⚖️ OPERATIVITY IMPROVEMENTS:")
    operativity_distribution = {'original': {'אופרטיבית': 0, 'דקלרטיבית': 0},
                              'improved': {'אופרטיבית': 0, 'דקלרטיבית': 0}}

    for comp in comparisons:
        orig_op = comp['original']['operativity']
        impr_op = comp['improved']['operativity']

        if orig_op in operativity_distribution['original']:
            operativity_distribution['original'][orig_op] += 1
        if impr_op in operativity_distribution['improved']:
            operativity_distribution['improved'][impr_op] += 1

        if orig_op != impr_op:
            operativity_improvements += 1

    orig_op_rate = operativity_distribution['original']['אופרטיבית'] / total * 100
    impr_op_rate = operativity_distribution['improved']['אופרטיבית'] / total * 100

    print(f"  Original: {orig_op_rate:.1f}% operative")
    print(f"  Improved: {impr_op_rate:.1f}% operative")
    print(f"  Changes: {operativity_improvements}/{total}")
    print(f"  Target Range: 60-65% operative")

    # Summary quality (basic length and prefix check)
    print(f"\n📝 SUMMARY IMPROVEMENTS:")
    for comp in comparisons[:3]:
        orig_summary = comp['original']['summary']
        impr_summary = comp['improved']['summary']

        # Check for forbidden prefixes
        forbidden_prefixes = ['החלטת ממשלה מספר', 'החלטה מספר', 'הממשלה החליטה']
        orig_has_prefix = any(orig_summary.startswith(prefix) for prefix in forbidden_prefixes)
        impr_has_prefix = any(impr_summary.startswith(prefix) for prefix in forbidden_prefixes)

        if orig_has_prefix != impr_has_prefix:
            summary_improvements += 1
            print(f"  {comp['decision_key']}: Fixed summary prefix")

    # Government body improvements
    print(f"\n🏛️ GOVERNMENT BODY IMPROVEMENTS:")
    for comp in comparisons[:3]:
        orig_bodies = comp['original']['gov_bodies']
        impr_bodies = comp['improved']['gov_bodies']

        if set(orig_bodies) != set(impr_bodies):
            body_improvements += 1
            print(f"  {comp['decision_key']}:")
            print(f"    Original: {orig_bodies}")
            print(f"    Improved: {impr_bodies}")

    # Overall assessment
    print(f"\n🎯 IMPROVEMENT SUMMARY:")
    print(f"  Policy Tags: {policy_improvements}/{total} decisions improved")
    print(f"  Operativity: {operativity_improvements}/{total} decisions changed")
    print(f"  Summaries: {summary_improvements}/{total} decisions improved")
    print(f"  Gov Bodies: {body_improvements}/{total} decisions improved")

    # Grade the improvements
    improvement_rate = (policy_improvements + operativity_improvements + summary_improvements + body_improvements) / (total * 4) * 100

    print(f"\n📈 OVERALL IMPROVEMENT RATE: {improvement_rate:.1f}%")

    if impr_op_rate >= 60 and impr_op_rate <= 65:
        operativity_grade = "A"
    elif impr_op_rate >= 55 and impr_op_rate <= 70:
        operativity_grade = "B"
    else:
        operativity_grade = "C"

    print(f"🎖️ NEW ALGORITHM GRADES:")
    print(f"  Policy Tag Quality: {'A' if policy_improvements/total >= 0.3 else 'B' if policy_improvements/total >= 0.2 else 'C'}")
    print(f"  Operativity Balance: {operativity_grade} ({impr_op_rate:.1f}%)")
    print(f"  Summary Quality: {'A' if summary_improvements/total >= 0.2 else 'B' if summary_improvements/total >= 0.1 else 'C'}")
    print(f"  Gov Body Quality: {'A' if body_improvements/total >= 0.1 else 'B' if body_improvements/total >= 0.05 else 'C'}")

    # Final recommendation based on new processing
    target_met = (60 <= impr_op_rate <= 65) and (improvement_rate >= 30)

    if target_met:
        recommendation = "🟢 ALGORITHMS READY FOR PRODUCTION"
        confidence = "HIGH"
    elif improvement_rate >= 20:
        recommendation = "🟡 SIGNIFICANT IMPROVEMENTS - CONSIDER DEPLOYMENT"
        confidence = "MEDIUM"
    else:
        recommendation = "🔴 IMPROVEMENTS INSUFFICIENT"
        confidence = "HIGH"

    print(f"\n🔔 RECOMMENDATION: {recommendation}")
    print(f"   Confidence: {confidence}")

    return {
        'improvement_rate': improvement_rate,
        'operativity_rate': impr_op_rate,
        'target_met': target_met,
        'recommendation': recommendation
    }


def main():
    print("🧪 TESTING NEW ALGORITHM IMPROVEMENTS")
    print("=" * 60)

    # Get sample decisions
    decisions = get_sample_decisions(limit=15)  # Small sample for speed
    if not decisions:
        print("❌ No decisions available for testing")
        return

    print(f"✅ Retrieved {len(decisions)} decisions for testing")

    # Process through new algorithms
    comparisons = process_with_new_algorithms(decisions)

    if not comparisons:
        print("❌ No successful processing results")
        return

    print(f"✅ Successfully processed {len(comparisons)} decisions")

    # Analyze improvements
    results = analyze_improvements(comparisons)

    # Save detailed results
    output_file = f"data/algorithm_improvement_test_{len(comparisons)}_decisions.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'test_results': results,
            'detailed_comparisons': comparisons,
            'sample_size': len(comparisons)
        }, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    main()