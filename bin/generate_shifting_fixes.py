#!/usr/bin/env python3
"""
Data Shifting Fixes Generator

Based on existing shift detection analysis, generates specific fix recommendations
for correcting summaries that belong to wrong decisions.

Focus: High-confidence matches only (>0.8 confidence threshold)
Output: JSON file with specific database update instructions

Usage:
    python bin/generate_shifting_fixes.py
    python bin/generate_shifting_fixes.py --confidence-threshold 0.9
    python bin/generate_shifting_fixes.py --max-distance 2
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from bin.detect_shifting import (
    fetch_records, analyze_government_shifts, extract_keywords,
    check_keyword_overlap, HEBREW_STOP_WORDS
)
from src.gov_scraper.db.connector import get_supabase_client

def calculate_match_confidence(title_keywords: set, summary_text: str, matched_keywords: set) -> float:
    """Calculate confidence score for a keyword match."""
    if not title_keywords or not summary_text or not matched_keywords:
        return 0.0

    # Base confidence from match ratio
    match_ratio = len(matched_keywords) / len(title_keywords)

    # Bonus for multiple matches
    multi_match_bonus = min(0.3, (len(matched_keywords) - 1) * 0.1)

    # Penalty for very short keywords
    short_keyword_penalty = 0.0
    for kw in matched_keywords:
        if len(kw) <= 3:
            short_keyword_penalty += 0.05

    confidence = match_ratio + multi_match_bonus - short_keyword_penalty
    return max(0.0, min(1.0, confidence))

def find_correct_summary_mapping(shifts: List[Dict], records: List[Dict]) -> List[Dict]:
    """
    For each shifted decision, try to find which other decision's summary should be there.
    """
    # Create lookup for records by decision_key
    records_by_key = {r['decision_key']: r for r in records}

    fix_mappings = []

    for shift in shifts:
        affected_key = shift['affected_decision']
        source_key = shift['source_decision']

        if affected_key not in records_by_key or source_key not in records_by_key:
            continue

        affected_record = records_by_key[affected_key]
        source_record = records_by_key[source_key]

        # Calculate confidence for this shift detection
        affected_keywords = extract_keywords(affected_record['decision_title'])
        source_keywords = extract_keywords(source_record['decision_title'])
        matched_keywords = set(shift['matched_keywords'])

        confidence = calculate_match_confidence(source_keywords,
                                              affected_record.get('summary', ''),
                                              matched_keywords)

        # Check if the affected decision should actually have the source's summary
        # This is likely if:
        # 1. Strong keyword match between source title and affected summary (already detected)
        # 2. Weak or no match between affected title and affected summary

        affected_self_match, affected_self_keywords = check_keyword_overlap(
            affected_keywords, affected_record.get('summary', ''), min_matches=1
        )

        # Check if source record has the summary that should go to affected
        source_self_match, source_self_keywords = check_keyword_overlap(
            affected_keywords, source_record.get('summary', ''), min_matches=1
        )

        fix_mapping = {
            'affected_decision_key': affected_key,
            'affected_title': affected_record['decision_title'],
            'current_summary': affected_record.get('summary', ''),
            'should_have_summary_from': source_key,
            'source_title': source_record['decision_title'],
            'source_summary': source_record.get('summary', ''),
            'shift_type': shift['shift_type'],
            'shift_distance': shift['shift_distance'],
            'matched_keywords': list(matched_keywords),
            'confidence': confidence,
            'analysis': {
                'source_keywords_in_affected_summary': len(matched_keywords),
                'affected_keywords_in_affected_summary': len(affected_self_keywords) if affected_self_match else 0,
                'affected_keywords_in_source_summary': len(source_self_keywords) if source_self_match else 0,
                'likely_bidirectional_swap': source_self_match and len(source_self_keywords) >= 1
            }
        }

        fix_mappings.append(fix_mapping)

    return fix_mappings

def detect_bidirectional_swaps(fix_mappings: List[Dict]) -> List[Dict]:
    """Identify cases where two decisions have swapped summaries."""

    # Group by potential swap pairs
    potential_swaps = {}

    for mapping in fix_mappings:
        affected = mapping['affected_decision_key']
        source = mapping['should_have_summary_from']

        # Create a consistent key for the pair
        pair_key = tuple(sorted([affected, source]))

        if pair_key not in potential_swaps:
            potential_swaps[pair_key] = []
        potential_swaps[pair_key].append(mapping)

    # Find actual bidirectional swaps
    confirmed_swaps = []

    for pair_key, mappings in potential_swaps.items():
        if len(mappings) >= 2:
            # Check if both directions exist
            decision_a, decision_b = pair_key

            a_to_b = next((m for m in mappings if m['affected_decision_key'] == decision_a
                          and m['should_have_summary_from'] == decision_b), None)
            b_to_a = next((m for m in mappings if m['affected_decision_key'] == decision_b
                          and m['should_have_summary_from'] == decision_a), None)

            if a_to_b and b_to_a:
                swap_confidence = (a_to_b['confidence'] + b_to_a['confidence']) / 2

                confirmed_swaps.append({
                    'type': 'bidirectional_swap',
                    'decision_a': decision_a,
                    'decision_b': decision_b,
                    'confidence': swap_confidence,
                    'mappings': [a_to_b, b_to_a]
                })

    return confirmed_swaps

def main():
    parser = argparse.ArgumentParser(description='Generate data shifting fix recommendations')
    parser.add_argument('--confidence-threshold', type=float, default=0.8,
                       help='Minimum confidence for including fixes (default: 0.8)')
    parser.add_argument('--max-distance', type=int, default=3,
                       help='Maximum shift distance to consider (default: 3)')
    parser.add_argument('--limit', type=int, help='Limit records analyzed (for testing)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  DATA SHIFTING FIXES GENERATOR")
    print("=" * 70)

    # Fetch records with summaries
    print(f"Fetching records...", end=" ", flush=True)
    records = fetch_records(limit=args.limit)
    print(f"loaded {len(records)} records")

    if not records:
        print("No records found!")
        return

    # Group by government and detect shifts
    government_groups = {}
    for record in records:
        gov_num = record['government_number']
        if gov_num not in government_groups:
            government_groups[gov_num] = []
        government_groups[gov_num].append(record)

    print(f"Analyzing shifts in {len(government_groups)} governments...")

    all_shifts = []
    for gov_num in sorted(government_groups.keys()):
        gov_shifts = analyze_government_shifts(gov_num, government_groups[gov_num], args.verbose)

        # Filter by distance
        filtered_shifts = [s for s in gov_shifts if s['shift_distance'] <= args.max_distance]
        all_shifts.extend(filtered_shifts)

        if filtered_shifts:
            print(f"  Government {gov_num}: {len(filtered_shifts)} shifts found")

    print(f"\nTotal shifts detected: {len(all_shifts)}")

    # Generate fix mappings
    print("Generating fix mappings...")
    fix_mappings = find_correct_summary_mapping(all_shifts, records)

    # Filter by confidence threshold
    high_confidence_fixes = [f for f in fix_mappings if f['confidence'] >= args.confidence_threshold]

    print(f"High-confidence fixes (>={args.confidence_threshold}): {len(high_confidence_fixes)}")

    # Detect bidirectional swaps
    print("Detecting bidirectional swaps...")
    bidirectional_swaps = detect_bidirectional_swaps(high_confidence_fixes)

    print(f"Bidirectional swaps detected: {len(bidirectional_swaps)}")

    # Compile results
    results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'confidence_threshold': args.confidence_threshold,
            'max_distance': args.max_distance,
            'total_records_analyzed': len(records),
            'total_shifts_detected': len(all_shifts),
            'high_confidence_fixes': len(high_confidence_fixes),
            'bidirectional_swaps': len(bidirectional_swaps)
        },
        'summary': {
            'total_fixes_recommended': len(high_confidence_fixes),
            'confidence_distribution': {
                '0.8-0.85': len([f for f in high_confidence_fixes if 0.8 <= f['confidence'] < 0.85]),
                '0.85-0.90': len([f for f in high_confidence_fixes if 0.85 <= f['confidence'] < 0.90]),
                '0.90-0.95': len([f for f in high_confidence_fixes if 0.90 <= f['confidence'] < 0.95]),
                '0.95-1.00': len([f for f in high_confidence_fixes if f['confidence'] >= 0.95])
            },
            'shift_types': {
                'forward': len([f for f in high_confidence_fixes if f['shift_type'] == 'forward']),
                'backward': len([f for f in high_confidence_fixes if f['shift_type'] == 'backward'])
            },
            'shift_distances': {
                '1': len([f for f in high_confidence_fixes if f['shift_distance'] == 1]),
                '2': len([f for f in high_confidence_fixes if f['shift_distance'] == 2]),
                '3': len([f for f in high_confidence_fixes if f['shift_distance'] == 3])
            }
        },
        'shifts_found': high_confidence_fixes,
        'bidirectional_swaps': bidirectional_swaps,
        'instructions': {
            'note': 'DO NOT UPDATE DATABASE - This is analysis only',
            'next_steps': [
                'Review high-confidence fixes manually',
                'Verify sample cases by reading actual summaries',
                'Create database update script after manual verification',
                'Apply fixes in batches with rollback capability'
            ],
            'sql_template': '''
            -- Example fix template (DO NOT RUN YET):
            UPDATE israeli_government_decisions
            SET summary = (
                SELECT summary FROM israeli_government_decisions
                WHERE decision_key = '{should_have_summary_from}'
            )
            WHERE decision_key = '{affected_decision_key}';
            '''
        }
    }

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'data_shifting_fixes.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Display summary
    print("\n" + "=" * 70)
    print("  FIX RECOMMENDATIONS SUMMARY")
    print("=" * 70)

    print(f"\nAnalysis Results:")
    print(f"  • Records analyzed: {len(records):,}")
    print(f"  • Shifts detected: {len(all_shifts):,}")
    print(f"  • High-confidence fixes: {len(high_confidence_fixes):,} (≥{args.confidence_threshold})")
    print(f"  • Bidirectional swaps: {len(bidirectional_swaps):,}")

    if high_confidence_fixes:
        print(f"\nConfidence Distribution:")
        conf_dist = results['summary']['confidence_distribution']
        for range_key, count in conf_dist.items():
            if count > 0:
                print(f"  • {range_key}: {count} fixes")

        print(f"\nShift Patterns:")
        shift_types = results['summary']['shift_types']
        for shift_type, count in shift_types.items():
            print(f"  • {shift_type.capitalize()} shifts: {count}")

        print(f"\nSample High-Confidence Fixes:")
        for i, fix in enumerate(high_confidence_fixes[:3]):
            print(f"\n  {i+1}. Decision {fix['affected_decision_key']} (confidence: {fix['confidence']:.3f})")
            print(f"     Title: {fix['affected_title'][:80]}...")
            print(f"     Should get summary from: {fix['should_have_summary_from']}")
            print(f"     Keywords matched: {fix['matched_keywords']}")

    if bidirectional_swaps:
        print(f"\nBidirectional Swaps (likely complete summary swaps):")
        for i, swap in enumerate(bidirectional_swaps[:3]):
            print(f"  {i+1}. {swap['decision_a']} ↔ {swap['decision_b']} (confidence: {swap['confidence']:.3f})")

    print(f"\nOutput saved to: {output_path}")

    print(f"\nNEXT STEPS:")
    print(f"1. Review the JSON file for specific fix recommendations")
    print(f"2. Manually verify a sample of high-confidence fixes")
    print(f"3. Create database update script (DO NOT update database yet)")
    print(f"4. Test fixes on a small batch first")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()