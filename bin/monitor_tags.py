#!/usr/bin/env python3
"""
Monitor tagging quality - check validation stats from recent decisions.
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.gov_scraper.db.connector import get_supabase_client
from collections import Counter


def analyze_recent_tags(days=7):
    """Analyze tag quality from last N days."""
    supabase = get_supabase_client()

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    response = supabase.table('israeli_government_decisions')\
        .select('decision_key, decision_date, tags_policy_area, tags_government_body')\
        .gte('decision_date', cutoff_date)\
        .order('decision_date', desc=True)\
        .execute()

    decisions = response.data

    if not decisions:
        print(f"No decisions found in last {days} days")
        return

    # Count tag distribution
    policy_tags = []
    govt_tags = []

    multi_policy = 0
    multi_govt = 0
    fallback_policy = 0

    for dec in decisions:
        # Policy tags
        if dec.get('tags_policy_area'):
            tags = [t.strip() for t in dec['tags_policy_area'].split(';')]
            policy_tags.extend(tags)
            if len(tags) > 1:
                multi_policy += 1
            if 'שונות' in tags:
                fallback_policy += 1

        # Government tags
        if dec.get('tags_government_body'):
            tags = [t.strip() for t in dec['tags_government_body'].split(';')]
            govt_tags.extend(tags)
            if len(tags) > 1:
                multi_govt += 1

    # Print report
    print(f"\n📊 Tag Quality Report - Last {days} Days")
    print(f"=" * 60)
    print(f"Total Decisions: {len(decisions)}")
    print(f"Date Range: {cutoff_date} to {datetime.now().strftime('%Y-%m-%d')}")
    print()

    print("📌 Policy Area Tags:")
    print(f"  - Total tags: {len(policy_tags)}")
    print(f"  - Unique tags: {len(set(policy_tags))}")
    print(f"  - Multi-tag decisions: {multi_policy} ({multi_policy/len(decisions)*100:.1f}%)")
    print(f"  - Fallback to 'שונות': {fallback_policy} ({fallback_policy/len(decisions)*100:.1f}%)")
    print(f"  - Avg tags/decision: {len(policy_tags)/len(decisions):.2f}")
    print()

    print("  Top 5 policy tags:")
    for tag, count in Counter(policy_tags).most_common(5):
        print(f"    • {tag}: {count} ({count/len(decisions)*100:.1f}%)")
    print()

    print("🏛️ Government Body Tags:")
    print(f"  - Total tags: {len(govt_tags)}")
    print(f"  - Unique tags: {len(set(govt_tags))}")
    print(f"  - Multi-tag decisions: {multi_govt} ({multi_govt/len(decisions)*100:.1f}%)")
    print(f"  - Avg tags/decision: {len(govt_tags)/len(decisions):.2f}")
    print()

    print("  Top 5 government bodies:")
    for tag, count in Counter(govt_tags).most_common(5):
        print(f"    • {tag}: {count} ({count/len(decisions)*100:.1f}%)")
    print()

    # Quality indicators
    print("✅ Quality Indicators:")
    if fallback_policy / len(decisions) < 0.1:
        print(f"  ✅ Low fallback rate ({fallback_policy/len(decisions)*100:.1f}%)")
    else:
        print(f"  ⚠️  High fallback rate ({fallback_policy/len(decisions)*100:.1f}%)")

    if len(set(policy_tags)) > 15:
        print(f"  ✅ Good tag diversity ({len(set(policy_tags))} unique policy tags)")
    else:
        print(f"  ⚠️  Low tag diversity ({len(set(policy_tags))} unique policy tags)")

    if len(govt_tags) > 0:
        print(f"  ✅ Government tags present ({len(govt_tags)} tags)")
    else:
        print(f"  ⚠️  No government tags found")

    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Monitor tagging quality')
    parser.add_argument('--days', type=int, default=7, help='Days to analyze (default: 7)')

    args = parser.parse_args()

    analyze_recent_tags(days=args.days)
