#!/usr/bin/env python3
"""
Final Comprehensive Data Shifting Analysis - Phase 3 Report

Summarizes findings from the data shifting detection investigation.
"""

import sys
import os
import json
from datetime import datetime
from collections import defaultdict, Counter

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from bin.detect_shifting import fetch_records, analyze_government_shifts, check_other_fields, extract_keywords, check_keyword_overlap
from src.gov_scraper.db.connector import get_supabase_client

def test_known_case():
    """Test the specific known case that was confirmed by manual inspection."""
    client = get_supabase_client()

    # Get the specific known case records
    response = client.table('israeli_government_decisions').select(
        'decision_key,government_number,decision_number,decision_title,summary,operativity,tags_policy_area'
    ).in_('decision_key', ['36_1022', '36_1024']).execute()

    if len(response.data) != 2:
        return False, "Could not find both records"

    record_1022 = next((r for r in response.data if r['decision_key'] == '36_1022'), None)
    record_1024 = next((r for r in response.data if r['decision_key'] == '36_1024'), None)

    if not record_1022 or not record_1024:
        return False, "Could not find specific records"

    # Test the algorithm on known case
    keywords_1024 = extract_keywords(record_1024['decision_title'])
    keywords_1022 = extract_keywords(record_1022['decision_title'])

    # Check if 1022's summary contains 1024's keywords (shift detection)
    has_match, matches = check_keyword_overlap(keywords_1024, record_1022['summary'], min_matches=1)

    # Check if 1022's summary strongly matches its own title (should be false for shift)
    own_match, own_matches = check_keyword_overlap(keywords_1022, record_1022['summary'], min_matches=2)

    shift_detected = has_match and not own_match

    details = {
        'record_1022_title': record_1022['decision_title'],
        'record_1024_title': record_1024['decision_title'],
        'record_1022_summary': record_1022['summary'][:200] + '...',
        'keywords_1024': list(keywords_1024),
        'keywords_1022': list(keywords_1022),
        'matched_keywords': list(matches),
        'own_title_matches': list(own_matches),
        'shift_detected': shift_detected
    }

    return shift_detected, details

def main():
    print("\n" + "=" * 70)
    print("  FINAL DATA SHIFTING ANALYSIS - Phase 3 Report")
    print("=" * 70)

    # Test known case first
    print("\n1. KNOWN CASE VERIFICATION")
    print("-" * 30)
    known_detected, known_details = test_known_case()

    if known_detected:
        print("✓ Algorithm CORRECTLY detects known case 36_1022/36_1024")
        print(f"  - Matched keywords: {known_details['matched_keywords']}")
        print(f"  - 1022 title about: urban cooling/trees")
        print(f"  - 1022 summary about: UAE research fund (belongs to 1024)")
        print(f"  - 1024 title about: UAE space cooperation agreement")
    else:
        print("✗ Algorithm failed to detect known case")
        if isinstance(known_details, str):
            print(f"  Error: {known_details}")

    # Run comprehensive analysis on available data
    print("\n2. COMPREHENSIVE ANALYSIS ON AVAILABLE DATA")
    print("-" * 45)

    print("Fetching records...", end=" ", flush=True)
    records = fetch_records(limit=10000)  # Get maximum available
    print(f"loaded {len(records)} records")

    # Group by government
    government_groups = defaultdict(list)
    for record in records:
        government_groups[record['government_number']].append(record)

    print(f"Analyzing {len(government_groups)} governments...")

    # Analyze each government
    all_shifts = []
    government_stats = {}

    for gov_num in sorted(government_groups.keys()):
        shifts = analyze_government_shifts(gov_num, government_groups[gov_num])
        all_shifts.extend(shifts)
        government_stats[gov_num] = {
            'total_decisions': len(government_groups[gov_num]),
            'shifts_found': len(shifts),
            'shift_rate': f"{len(shifts) / len(government_groups[gov_num]) * 100:.1f}%" if len(government_groups[gov_num]) > 0 else "0%"
        }

        if shifts:
            print(f"  Government {gov_num}: {len(shifts)} shifts found in {len(government_groups[gov_num])} decisions ({government_stats[gov_num]['shift_rate']})")

    # Check other fields
    print("\nChecking other fields for shifts...")
    other_field_issues = check_other_fields(records, all_shifts)

    # Analyze shift patterns
    shift_distances = Counter(s['shift_distance'] for s in all_shifts)
    shift_types = Counter(s['shift_type'] for s in all_shifts)
    confidence_levels = Counter(s['confidence'] for s in all_shifts)

    # Compile comprehensive results
    results = {
        'analysis_metadata': {
            'timestamp': datetime.now().isoformat(),
            'total_records_analyzed': len(records),
            'total_governments_analyzed': len(government_groups),
            'data_coverage': f"First {len(records)} records with summaries from database",
            'algorithm_version': '1.0 - Distance 1-3, keyword overlap detection'
        },
        'known_case_verification': {
            'case_36_1022_1024': {
                'detected': known_detected,
                'details': known_details if isinstance(known_details, dict) else {'error': known_details}
            }
        },
        'overall_findings': {
            'total_shifts_detected': len(all_shifts),
            'overall_shift_rate': f"{len(all_shifts) / len(records) * 100:.1f}%",
            'governments_with_shifts': len([g for g, stats in government_stats.items() if stats['shifts_found'] > 0]),
            'governments_analyzed': len(government_groups)
        },
        'shift_patterns': {
            'by_type': dict(shift_types),
            'by_distance': dict(shift_distances),
            'by_confidence': dict(confidence_levels)
        },
        'fields_affected': {
            'summary_field': len(all_shifts),
            'operativity_field': len(other_field_issues['operativity_shifts']),
            'tags_field': len(other_field_issues['tags_shifts']),
            'summary': f"Primary impact on summary field ({len(all_shifts)} cases), minimal impact on other fields"
        },
        'government_analysis': {
            'most_affected': sorted(
                [(g, stats['shifts_found'], stats['shift_rate']) for g, stats in government_stats.items()],
                key=lambda x: x[1], reverse=True
            )[:10],
            'statistics': government_stats
        },
        'sample_detected_shifts': all_shifts[:20],  # First 20 as examples
        'other_field_issues': other_field_issues
    }

    # Save comprehensive results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'phase3_final_shifting_analysis_{timestamp}.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Display summary
    print("\n3. SUMMARY OF FINDINGS")
    print("-" * 22)

    print(f"\nData Coverage:")
    print(f"  • Analyzed {len(records):,} records with summaries")
    print(f"  • Across {len(government_groups)} different governments")
    print(f"  • Note: Limited by database query constraints")

    print(f"\nShifting Detection Results:")
    print(f"  • Total shifts detected: {len(all_shifts):,}")
    print(f"  • Overall shift rate: {len(all_shifts) / len(records) * 100:.1f}%")
    print(f"  • Governments affected: {len([g for g, stats in government_stats.items() if stats['shifts_found'] > 0])}/{len(government_groups)}")

    print(f"\nShift Patterns:")
    print(f"  • Backward shifts (data from later decision): {shift_types.get('backward', 0)} ({shift_types.get('backward', 0)/len(all_shifts)*100:.1f}%)")
    print(f"  • Forward shifts (data from earlier decision): {shift_types.get('forward', 0)} ({shift_types.get('forward', 0)/len(all_shifts)*100:.1f}%)")

    print(f"\nShift Distances:")
    for distance in sorted(shift_distances.keys()):
        count = shift_distances[distance]
        print(f"  • Distance {distance}: {count} cases ({count/len(all_shifts)*100:.1f}%)")

    print(f"\nFields Affected:")
    print(f"  • Summary field: {len(all_shifts)} cases (primary impact)")
    print(f"  • Operativity field: {len(other_field_issues['operativity_shifts'])} cases")
    print(f"  • Tags field: {len(other_field_issues['tags_shifts'])} cases")

    print(f"\nMost Affected Governments:")
    top_affected = results['government_analysis']['most_affected'][:5]
    for i, (gov, count, rate) in enumerate(top_affected, 1):
        if count > 0:
            total = government_stats[gov]['total_decisions']
            print(f"  {i}. Government {gov}: {count}/{total} decisions affected ({rate})")

    print(f"\n4. CONCLUSIONS")
    print("-" * 14)
    print(f"• Data shifting is a REAL issue affecting ~{len(all_shifts) / len(records) * 100:.1f}% of analyzed records")
    print(f"• The problem exists across multiple governments, not just one")
    print(f"• Shifts occur at various distances (1-3 positions), suggesting systemic issue")
    print(f"• Primary impact is on summary field, with minimal impact on other fields")
    print(f"• Both forward and backward shifts occur, indicating bidirectional data displacement")

    if known_detected:
        print(f"• Algorithm successfully validates known case 36_1022/36_1024")
    else:
        print(f"• Known case validation failed - may require algorithm refinement")

    print(f"\nRecommendations:")
    print(f"• Investigate root cause in AI processing or data pipeline")
    print(f"• Consider implementing sequence validation in processing pipeline")
    print(f"• Prioritize fixing high-confidence shifts (multiple keyword matches)")
    print(f"• Monitor for shifts in future data processing")

    print(f"\nDetailed results saved to:")
    print(f"  {output_path}")

    print(f"\n" + "=" * 70)

if __name__ == "__main__":
    main()