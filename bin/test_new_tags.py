#!/usr/bin/env python3
"""
Test script for new tag keyword matching.

Scans the database and calculates weighted scores for the 5 new tags:
- החברה הערבית
- החברה החרדית
- נשים ומגדר
- שיקום הצפון
- שיקום הדרום

Usage:
    python bin/test_new_tags.py                     # Scan all, show summary
    python bin/test_new_tags.py --tag "החברה הערבית"  # Scan specific tag
    python bin/test_new_tags.py --verbose           # Show detailed matches
    python bin/test_new_tags.py --count 1000        # Limit to N records
    python bin/test_new_tags.py --export            # Export results to JSON
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.processors.qa import (
    NEW_TAG_KEYWORDS,
    NEW_TAG_AUTO_THRESHOLD,
    NEW_TAG_AI_THRESHOLD,
    NEW_TAG_MANUAL_THRESHOLD,
    NEW_TAG_MIN_KEYWORDS,
    _word_in_text,
)


def calculate_tag_score(content: str, tag_keywords: Dict[str, int]) -> Tuple[int, int, List[Tuple[str, int]]]:
    """
    Calculate absolute score for a decision (sum of matched weights).

    Returns:
        Tuple[total_score, keyword_count, matched_keywords_with_weights]
    """
    matched = []
    total_score = 0

    for keyword, weight in tag_keywords.items():
        if _word_in_text(keyword, content):
            matched.append((keyword, weight))
            total_score += weight

    return total_score, len(matched), matched


def classify_decision(score: float, keyword_count: int,
                      auto_threshold: float = NEW_TAG_AUTO_THRESHOLD,
                      ai_threshold: float = NEW_TAG_AI_THRESHOLD,
                      manual_threshold: float = NEW_TAG_MANUAL_THRESHOLD,
                      min_keywords: int = NEW_TAG_MIN_KEYWORDS) -> str:
    """Classify decision based on score and keyword count."""
    if keyword_count < min_keywords:
        return "skip"
    elif score >= auto_threshold:
        return "auto_tag"
    elif score >= ai_threshold:
        return "ai_verify"
    elif score >= manual_threshold:
        return "manual_review"
    else:
        return "skip"


def fetch_decisions(client, limit: int = None, recent_first: bool = True) -> List[Dict]:
    """Fetch decisions from database."""
    print("Fetching decisions from database...")

    query = client.table("israeli_government_decisions").select(
        "decision_key, decision_title, decision_content, tags_policy_area, decision_date"
    )

    if recent_first:
        query = query.order("decision_date", desc=True)

    if limit:
        query = query.limit(limit)

    response = query.execute()
    print(f"Fetched {len(response.data)} decisions")
    return response.data


def scan_tag(decisions: List[Dict], tag_name: str, keywords: Dict[str, int],
             auto_threshold: float, ai_threshold: float,
             manual_threshold: float, min_keywords: int,
             verbose: bool = False) -> Dict:
    """Scan all decisions for a specific tag."""

    results = {
        "tag": tag_name,
        "total_weight": sum(keywords.values()),
        "auto_tag": [],
        "ai_verify": [],
        "manual_review": [],
        "skip": []
    }

    keyword_hit_counts = {kw: 0 for kw in keywords}

    for decision in decisions:
        content = (decision.get('decision_content') or '') + ' ' + (decision.get('decision_title') or '')

        score, count, matched = calculate_tag_score(content, keywords)

        classification = classify_decision(
            score, count, auto_threshold, ai_threshold, manual_threshold, min_keywords
        )

        # Update keyword hit counts
        for kw, _ in matched:
            keyword_hit_counts[kw] += 1

        record = {
            'key': decision['decision_key'],
            'title': decision['decision_title'][:80] if decision['decision_title'] else '',
            'score': round(score, 1),
            'keyword_count': count,
            'keywords': matched,
            'existing_tags': decision.get('tags_policy_area', '')
        }

        results[classification].append(record)

    # Sort by score descending
    for category in ['auto_tag', 'ai_verify', 'manual_review']:
        results[category].sort(key=lambda x: x['score'], reverse=True)

    # Add keyword stats
    results['keyword_stats'] = sorted(
        [(kw, weight, count) for kw, count in keyword_hit_counts.items()
         for w_kw, weight in keywords.items() if w_kw == kw],
        key=lambda x: x[2], reverse=True
    )

    return results


def print_results(results: Dict, verbose: bool = False, max_examples: int = 5):
    """Print formatted results."""

    print("\n" + "=" * 70)
    print(f"                     תגית: {results['tag']}")
    print("=" * 70)

    # Summary
    total = sum(len(results[cat]) for cat in ['auto_tag', 'ai_verify', 'manual_review', 'skip'])
    print(f"\nTotal decisions scanned: {total:,}")
    print(f"Total weight for tag: {results['total_weight']}")

    # Categories
    categories = [
        ('auto_tag', '✅ תיוג אוטומטי (>= 60 points)', 'green'),
        ('ai_verify', '⚠️ לאימות AI (30-59 points)', 'yellow'),
        ('manual_review', '🔍 לבדיקה ידנית (15-29 points)', 'blue'),
        ('skip', '❌ לא מתויג (< 15 points או < 2 מילים)', 'gray')
    ]

    for cat_key, cat_label, _ in categories:
        count = len(results[cat_key])
        pct = (count / total * 100) if total > 0 else 0
        print(f"\n{cat_label}: {count:,} ({pct:.2f}%)")

        if cat_key != 'skip' and count > 0:
            print("   " + "-" * 60)
            for record in results[cat_key][:max_examples]:
                print(f"   [{record['key']}] \"{record['title']}\" (score: {record['score']})")
                if verbose and record['keywords']:
                    kw_str = ", ".join([f"{kw} ({w})" for kw, w in record['keywords']])
                    print(f"      └─ {kw_str}")

    # Top keywords
    print("\n" + "=" * 70)
    print("                         סטטיסטיקת מילות מפתח")
    print("=" * 70)

    for kw, weight, count in results['keyword_stats'][:15]:
        if count > 0:
            print(f"   {kw} (weight: {weight}): {count} matches")


def main():
    parser = argparse.ArgumentParser(description='Test new tag keyword matching')
    parser.add_argument('--tag', type=str, help='Specific tag to scan (default: all)')
    parser.add_argument('--count', type=int, help='Limit number of records to scan')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed keyword matches')
    parser.add_argument('--export', action='store_true', help='Export results to JSON')
    parser.add_argument('--auto-threshold', type=float, default=NEW_TAG_AUTO_THRESHOLD,
                        help=f'Auto-tag threshold (default: {NEW_TAG_AUTO_THRESHOLD})')
    parser.add_argument('--ai-threshold', type=float, default=NEW_TAG_AI_THRESHOLD,
                        help=f'AI verification threshold (default: {NEW_TAG_AI_THRESHOLD})')
    parser.add_argument('--manual-threshold', type=float, default=NEW_TAG_MANUAL_THRESHOLD,
                        help=f'Manual review threshold (default: {NEW_TAG_MANUAL_THRESHOLD})')
    parser.add_argument('--min-keywords', type=int, default=NEW_TAG_MIN_KEYWORDS,
                        help=f'Minimum keyword matches (default: {NEW_TAG_MIN_KEYWORDS})')

    args = parser.parse_args()

    # Connect to database
    client = get_supabase_client()

    # Fetch decisions
    decisions = fetch_decisions(client, args.count)

    if not decisions:
        print("No decisions found!")
        return

    # Determine which tags to scan
    if args.tag:
        if args.tag not in NEW_TAG_KEYWORDS:
            print(f"Error: Tag '{args.tag}' not found. Available tags:")
            for tag in NEW_TAG_KEYWORDS.keys():
                print(f"  - {tag}")
            return
        tags_to_scan = {args.tag: NEW_TAG_KEYWORDS[args.tag]}
    else:
        tags_to_scan = NEW_TAG_KEYWORDS

    all_results = []

    # Scan each tag
    for tag_name, keywords in tags_to_scan.items():
        results = scan_tag(
            decisions, tag_name, keywords,
            args.auto_threshold, args.ai_threshold,
            args.manual_threshold, args.min_keywords,
            args.verbose
        )
        all_results.append(results)
        print_results(results, args.verbose)

    # Export to JSON if requested
    if args.export:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'new_tag_reports')
        os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, f"new_tags_scan_{timestamp}.json")

        # Prepare export data (limit keywords list for readability)
        export_data = []
        for results in all_results:
            export_results = {
                'tag': results['tag'],
                'total_weight': results['total_weight'],
                'auto_tag_count': len(results['auto_tag']),
                'ai_verify_count': len(results['ai_verify']),
                'manual_review_count': len(results['manual_review']),
                'skip_count': len(results['skip']),
                'auto_tag_examples': results['auto_tag'][:20],
                'ai_verify_examples': results['ai_verify'][:20],
                'manual_review_examples': results['manual_review'][:20],
                'keyword_stats': results['keyword_stats'],
            }
            export_data.append(export_results)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"\nResults exported to: {output_file}")

    # Print summary table
    print("\n" + "=" * 70)
    print("                         סיכום כללי")
    print("=" * 70)
    print(f"{'תגית':<25} {'Auto':<10} {'AI':<10} {'Manual':<10} {'Skip':<10}")
    print("-" * 70)
    for results in all_results:
        tag = results['tag']
        auto = len(results['auto_tag'])
        ai = len(results['ai_verify'])
        manual = len(results['manual_review'])
        skip = len(results['skip'])
        print(f"{tag:<25} {auto:<10} {ai:<10} {manual:<10} {skip:<10}")


if __name__ == "__main__":
    main()
