#!/usr/bin/env python3
"""
Data Shifting Detection Script - Phase 3 of DB Investigation

Identifies cases where data from one decision appears in another (shifted data).

Algorithm:
For each government:
  Sort decisions by number (ascending)
  For each triplet (prev, curr, next):
    Extract keywords from titles (ignore stop words)
    Check if curr.summary contains keywords from prev or next title
    But NOT from curr.title itself

Usage:
    python bin/detect_shifting.py                    # Full scan
    python bin/detect_shifting.py --government 36    # Single government
    python bin/detect_shifting.py --limit 1000       # Limit records
    python bin/detect_shifting.py --verbose          # Detailed logging
"""

import sys
import os
import json
import re
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client

# Hebrew stop words (common words to ignore when extracting keywords)
HEBREW_STOP_WORDS = {
    'של', 'את', 'על', 'ב', 'ל', 'מ', 'ה', 'ו', 'כ', 'ש', 'אל', 'עם', 'או', 'זה', 'כי', 'לא',
    'בדבר', 'החלטה', 'החליטה', 'ממשלת', 'ממשלה', 'ישראל', 'מדינת', 'ביום', 'בתאריך',
    'לפי', 'בעד', 'נגד', 'אחרי', 'לפני', 'בין', 'יותר', 'פחות', 'בכל', 'לכל', 'כל',
    'הוא', 'היא', 'הם', 'הן', 'אני', 'אתה', 'את', 'אנחנו', 'אתם', 'אתן',
    'יהיה', 'תהיה', 'יהיו', 'תהיינה', 'היה', 'הייה', 'היו', 'הרבה', 'מעט', 'קצת'
}

def extract_keywords(text: str, num_keywords: int = 5) -> Set[str]:
    """Extract main keywords from Hebrew text, excluding stop words."""
    if not text:
        return set()

    # Remove punctuation and split into words
    # Keep Hebrew letters, numbers, and hyphens
    words = re.findall(r'[\u0590-\u05FF\w\-]+', text.lower())

    # Filter out stop words and short words
    significant_words = [
        word for word in words
        if len(word) >= 3 and word not in HEBREW_STOP_WORDS
    ]

    # Count word frequencies
    word_counts = defaultdict(int)
    for word in significant_words:
        word_counts[word] += 1

    # Return top keywords
    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    return {word for word, count in top_words[:num_keywords]}

def check_keyword_overlap(keywords: Set[str], text: str, min_matches: int = 2) -> Tuple[bool, Set[str]]:
    """Check if text contains enough keywords to suggest content overlap."""
    if not text or not keywords:
        return False, set()

    text_lower = text.lower()
    matched_keywords = {kw for kw in keywords if kw in text_lower}

    return len(matched_keywords) >= min_matches, matched_keywords

def analyze_government_shifts(government_num: int, records: List[Dict], verbose: bool = False) -> List[Dict]:
    """Analyze a single government for data shifts."""
    shifts_found = []

    # Sort by decision number
    def dec_sort_key(record):
        try:
            return int(record['decision_number'])
        except ValueError:
            return 999999

    sorted_records = sorted(records, key=dec_sort_key)

    if verbose:
        print(f"  Analyzing government {government_num}: {len(sorted_records)} decisions")

    # Check each decision against surrounding decisions (distances 1, 2, 3)
    for i in range(len(sorted_records)):
        curr_record = sorted_records[i]
        curr_key = curr_record['decision_key']
        curr_keywords = extract_keywords(curr_record['decision_title'])

        # Check distances 1, 2, 3 in both directions
        for distance in [1, 2, 3]:
            # Check backward (summary from future decision)
            if i + distance < len(sorted_records):
                source_record = sorted_records[i + distance]
                source_keywords = extract_keywords(source_record['decision_title'])

                if source_keywords:
                    has_match, matches = check_keyword_overlap(
                        source_keywords, curr_record.get('summary', ''), min_matches=1
                    )
                    # Exclude if current title strongly matches current summary (proper content)
                    curr_summary_matches_curr_title, curr_matches = check_keyword_overlap(
                        curr_keywords, curr_record.get('summary', ''), min_matches=2
                    )

                    if has_match and not curr_summary_matches_curr_title:
                        shift_data = {
                            'affected_decision': curr_key,
                            'shift_type': 'backward',
                            'shift_distance': distance,
                            'source_decision': source_record['decision_key'],
                            'field_affected': 'summary',
                            'matched_keywords': list(matches),
                            'confidence': len(matches),
                            'government_number': government_num,
                            'source_title': source_record['decision_title'],
                            'affected_title': curr_record['decision_title'],
                            'affected_summary': curr_record.get('summary', '')[:200] + '...' if curr_record.get('summary', '') else ''
                        }
                        shifts_found.append(shift_data)

                        if verbose:
                            print(f"    BACKWARD SHIFT (distance {distance}): {curr_key} <- {source_record['decision_key']}")
                            print(f"      Matched keywords: {matches}")

            # Check forward (summary from past decision)
            if i - distance >= 0:
                source_record = sorted_records[i - distance]
                source_keywords = extract_keywords(source_record['decision_title'])

                if source_keywords:
                    has_match, matches = check_keyword_overlap(
                        source_keywords, curr_record.get('summary', ''), min_matches=1
                    )
                    # Exclude if current title strongly matches current summary (proper content)
                    curr_summary_matches_curr_title, curr_matches = check_keyword_overlap(
                        curr_keywords, curr_record.get('summary', ''), min_matches=2
                    )

                    if has_match and not curr_summary_matches_curr_title:
                        shift_data = {
                            'affected_decision': curr_key,
                            'shift_type': 'forward',
                            'shift_distance': distance,
                            'source_decision': source_record['decision_key'],
                            'field_affected': 'summary',
                            'matched_keywords': list(matches),
                            'confidence': len(matches),
                            'government_number': government_num,
                            'source_title': source_record['decision_title'],
                            'affected_title': curr_record['decision_title'],
                            'affected_summary': curr_record.get('summary', '')[:200] + '...' if curr_record.get('summary', '') else ''
                        }
                        shifts_found.append(shift_data)

                        if verbose:
                            print(f"    FORWARD SHIFT (distance {distance}): {curr_key} -> {source_record['decision_key']}")
                            print(f"      Matched keywords: {matches}")

    return shifts_found

def check_other_fields(records: List[Dict], shifts_found: List[Dict], verbose: bool = False) -> Dict:
    """Check if shifting also affects operativity and tags fields."""
    other_field_issues = {
        'operativity_shifts': [],
        'tags_shifts': []
    }

    # Group records by government for efficient lookup
    records_by_gov = defaultdict(list)
    for record in records:
        records_by_gov[record['government_number']].append(record)

    # Check each shift to see if it affects other fields
    for shift in shifts_found:
        def dec_sort_key_check(record):
            try:
                return int(record['decision_number'])
            except ValueError:
                return 999999

        gov_records = sorted(records_by_gov[shift['government_number']], key=dec_sort_key_check)

        # Find the affected record and its neighbors
        affected_idx = next(
            (i for i, r in enumerate(gov_records)
             if r['decision_key'] == shift['affected_decision']), None
        )

        if affected_idx is None:
            continue

        curr_record = gov_records[affected_idx]

        # Get source record based on shift direction
        if shift['shift_type'] == 'backward' and affected_idx > 0:
            source_record = gov_records[affected_idx - 1]
        elif shift['shift_type'] == 'forward' and affected_idx < len(gov_records) - 1:
            source_record = gov_records[affected_idx + 1]
        else:
            continue

        # Check operativity field
        source_keywords = extract_keywords(source_record['decision_title'], 3)
        if source_keywords:
            has_op_match, op_matches = check_keyword_overlap(
                source_keywords, curr_record.get('operativity', ''), min_matches=1
            )
            if has_op_match:
                other_field_issues['operativity_shifts'].append({
                    'decision_key': shift['affected_decision'],
                    'shift_type': shift['shift_type'],
                    'matched_keywords': list(op_matches),
                    'operativity_text': curr_record.get('operativity', '')[:150] + '...'
                })

        # Check tags fields (look for policy area mismatch)
        source_title = source_record.get('decision_title', '') or ''
        curr_tags = curr_record.get('tags_policy_area', []) or []

        # This is a simplified check - in practice you'd want more sophisticated tag matching
        if source_title and curr_tags and any(tag for tag in curr_tags if len(tag) > 3):
            other_field_issues['tags_shifts'].append({
                'decision_key': shift['affected_decision'],
                'shift_type': shift['shift_type'],
                'current_tags': curr_tags,
                'note': 'Potential tag mismatch detected'
            })

    return other_field_issues

def fetch_records(government_filter: Optional[int] = None, limit: Optional[int] = None) -> List[Dict]:
    """Fetch records from database for analysis."""
    client = get_supabase_client()

    query = client.table('israeli_government_decisions').select(
        'decision_key,government_number,decision_number,decision_title,summary,operativity,tags_policy_area'
    ).not_.is_('summary', 'null').not_.eq('summary', '')

    if government_filter:
        query = query.eq('government_number', government_filter)

    if limit:
        query = query.limit(limit)
    else:
        # If no limit specified, use a reasonable limit to avoid memory issues
        query = query.limit(10000)

    response = query.execute()

    # Sort in Python to handle string/int conversion properly
    records = response.data

    def sort_key(record):
        gov_num = int(record['government_number'])
        try:
            dec_num = int(record['decision_number'])
        except ValueError:
            # Handle non-numeric decision numbers by putting them at the end
            dec_num = 999999
        return (gov_num, dec_num)

    records.sort(key=sort_key)
    return records

def main():
    parser = argparse.ArgumentParser(description='Detect data shifting in government decisions')
    parser.add_argument('--government', type=int, help='Filter by specific government number')
    parser.add_argument('--limit', type=int, help='Limit number of records to analyze')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  DATA SHIFTING DETECTION - Phase 3")
    print("=" * 60)

    # Fetch records
    print("Fetching records...", end=" ", flush=True)
    records = fetch_records(args.government, args.limit)
    print(f"loaded {len(records)} records")

    if not records:
        print("No records found!")
        return

    # Group by government
    government_groups = defaultdict(list)
    for record in records:
        government_groups[record['government_number']].append(record)

    print(f"Analyzing {len(government_groups)} governments...")

    # Analyze each government
    all_shifts = []
    government_stats = {}

    for gov_num in sorted(government_groups.keys()):
        shifts = analyze_government_shifts(gov_num, government_groups[gov_num], args.verbose)
        all_shifts.extend(shifts)
        government_stats[gov_num] = {
            'total_decisions': len(government_groups[gov_num]),
            'shifts_found': len(shifts),
            'shift_rate': f"{len(shifts) / len(government_groups[gov_num]) * 100:.1f}%" if len(government_groups[gov_num]) > 0 else "0%"
        }

        if shifts and not args.verbose:
            print(f"  Government {gov_num}: {len(shifts)} shifts found in {len(government_groups[gov_num])} decisions")

    # Check other fields
    print("\nChecking other fields for shifts...")
    other_field_issues = check_other_fields(records, all_shifts, args.verbose)

    # Compile results
    results = {
        'timestamp': datetime.now().isoformat(),
        'total_records_analyzed': len(records),
        'total_governments_analyzed': len(government_groups),
        'total_shifts_found': len(all_shifts),
        'summary': {
            'shift_patterns': {
                'backward': len([s for s in all_shifts if s['shift_type'] == 'backward']),
                'forward': len([s for s in all_shifts if s['shift_type'] == 'forward'])
            },
            'fields_affected': {
                'summary': len(all_shifts),
                'operativity': len(other_field_issues['operativity_shifts']),
                'tags': len(other_field_issues['tags_shifts'])
            },
            'governments_with_issues': len([g for g, stats in government_stats.items() if stats['shifts_found'] > 0])
        },
        'government_stats': government_stats,
        'detected_shifts': all_shifts,
        'other_field_issues': other_field_issues,
        'verified_cases': {
            'known_case_36_1022_1024': any(
                s['affected_decision'] == '36_1022' and s['source_decision'] == '36_1024'
                for s in all_shifts
            )
        }
    }

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'phase3_shifting_{timestamp}.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Display summary
    print("\n" + "=" * 60)
    print("  SHIFTING DETECTION RESULTS")
    print("=" * 60)

    print(f"\nTotal records analyzed: {len(records)}")
    print(f"Total governments analyzed: {len(government_groups)}")
    print(f"Total shifts detected: {len(all_shifts)}")

    print(f"\nShift patterns:")
    print(f"  - Backward shifts (data from previous decision): {results['summary']['shift_patterns']['backward']}")
    print(f"  - Forward shifts (data from next decision): {results['summary']['shift_patterns']['forward']}")

    print(f"\nFields affected:")
    print(f"  - Summary field: {results['summary']['fields_affected']['summary']} cases")
    print(f"  - Operativity field: {results['summary']['fields_affected']['operativity']} cases")
    print(f"  - Tags field: {results['summary']['fields_affected']['tags']} cases")

    print(f"\nGovernments with shifts: {results['summary']['governments_with_issues']} out of {len(government_groups)}")

    # Verify known case
    if results['verified_cases']['known_case_36_1022_1024']:
        print(f"\n✓ Confirmed known case 36_1022/36_1024 detected")
    else:
        print(f"\n✗ Known case 36_1022/36_1024 NOT detected - algorithm may need adjustment")

    # Show top affected governments
    top_affected = sorted(
        [(g, stats['shifts_found']) for g, stats in government_stats.items()],
        key=lambda x: x[1], reverse=True
    )[:10]

    if top_affected and top_affected[0][1] > 0:
        print(f"\nTop affected governments:")
        for gov_num, shift_count in top_affected[:5]:
            if shift_count > 0:
                total = government_stats[gov_num]['total_decisions']
                rate = government_stats[gov_num]['shift_rate']
                print(f"  Government {gov_num}: {shift_count} shifts in {total} decisions ({rate})")

    print(f"\nDetailed results saved to: {output_path}")

    # Show sample shifts for verification
    if all_shifts and args.verbose:
        print(f"\nSample detected shifts:")
        for i, shift in enumerate(all_shifts[:3]):
            print(f"\n{i+1}. {shift['affected_decision']} ({shift['shift_type']} shift)")
            print(f"   Source: {shift['source_decision']}")
            print(f"   Keywords: {shift['matched_keywords']}")
            print(f"   Confidence: {shift['confidence']}")

if __name__ == "__main__":
    main()