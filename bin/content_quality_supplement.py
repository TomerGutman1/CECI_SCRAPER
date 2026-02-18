#!/usr/bin/env python3
"""
Supplementary Content Quality Analysis

Focus on specific patterns not covered in the main anomaly detection.
"""

import os
import sys
import json
import re
import logging
from datetime import datetime
from collections import Counter

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_recent_content_patterns():
    """Analyze content patterns in recent decisions for specific issues."""
    client = get_supabase_client()

    # Fetch recent decisions (2023-2026) with content
    logger.info("Fetching recent decisions...")
    response = client.table("israeli_government_decisions").select(
        "decision_key, decision_date, decision_content, decision_title, decision_url"
    ).gte("decision_date", "2023-01-01").limit(200).execute()

    if not response.data:
        logger.error("No recent decisions found")
        return

    records = response.data
    logger.info(f"Analyzing {len(records)} recent decisions")

    issues = {
        'very_long_content': [],
        'content_length_stats': Counter(),
        'common_truncation_patterns': Counter(),
        'url_content_mismatch': [],
        'suspicious_repetition': []
    }

    for record in records:
        key = record['decision_key']
        content = record.get('decision_content', '') or ''
        title = record.get('decision_title', '') or ''
        url = record.get('decision_url', '') or ''

        content_len = len(content)

        # Track content length distribution
        if content_len > 10000:
            issues['very_long_content'].append((key, content_len, content[:200]))

        # Bin lengths for statistics
        if content_len < 100:
            issues['content_length_stats']['very_short'] += 1
        elif content_len < 500:
            issues['content_length_stats']['short'] += 1
        elif content_len < 2000:
            issues['content_length_stats']['medium'] += 1
        elif content_len < 10000:
            issues['content_length_stats']['long'] += 1
        else:
            issues['content_length_stats']['very_long'] += 1

        # Check for specific truncation patterns
        if content:
            if content.strip().endswith('ב'):
                issues['common_truncation_patterns']['ends_with_b'] += 1
            if 'נמצא ב' in content and not content.strip().endswith('.'):
                issues['common_truncation_patterns']['incomplete_reference'] += 1
            if re.search(r'להלן\s*-[^)]*$', content.strip()):
                issues['common_truncation_patterns']['incomplete_parenthetical'] += 1

        # Check for URL-content mismatch (simple heuristic)
        if url and content and len(content) > 100:
            # Extract decision number from URL
            url_match = re.search(r'/([^/]+)\.pdf', url)
            if url_match:
                url_decision = url_match.group(1)
                # Check if this appears anywhere in the content
                if url_decision.lower() not in content.lower():
                    issues['url_content_mismatch'].append((key, url_decision, content[:100]))

        # Check for suspicious repetition patterns
        if content and len(content) > 200:
            # Look for repeated phrases
            words = content.split()
            if len(words) > 10:
                for i in range(len(words) - 10):
                    phrase = ' '.join(words[i:i+5])  # 5-word phrases
                    if content.count(phrase) > 2:  # Repeated more than twice
                        issues['suspicious_repetition'].append((key, phrase, content.count(phrase)))
                        break

    # Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'analyzed_records': len(records),
        'findings': {
            'content_length_distribution': dict(issues['content_length_stats']),
            'very_long_content_count': len(issues['very_long_content']),
            'truncation_patterns': dict(issues['common_truncation_patterns']),
            'url_content_mismatches': len(issues['url_content_mismatch']),
            'suspicious_repetitions': len(issues['suspicious_repetition'])
        },
        'examples': {
            'very_long_content': issues['very_long_content'][:5],
            'url_content_mismatches': issues['url_content_mismatch'][:5],
            'suspicious_repetition': issues['suspicious_repetition'][:5]
        }
    }

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join('/Users/tomergutman/Downloads/GOV2DB/data/qa_reports')
    os.makedirs(report_dir, exist_ok=True)

    report_file = os.path.join(report_dir, f'content_quality_supplement_{timestamp}.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=== RECENT CONTENT QUALITY ANALYSIS ===")
    print(f"Analyzed: {len(records)} recent decisions")
    print(f"\nContent Length Distribution:")
    for category, count in issues['content_length_stats'].items():
        pct = count / len(records) * 100
        print(f"  {category}: {count} ({pct:.1f}%)")

    print(f"\nTruncation Patterns:")
    for pattern, count in issues['common_truncation_patterns'].items():
        print(f"  {pattern}: {count}")

    print(f"\nQuality Issues:")
    print(f"  Very long content (>10K chars): {len(issues['very_long_content'])}")
    print(f"  URL-content mismatches: {len(issues['url_content_mismatch'])}")
    print(f"  Suspicious repetitions: {len(issues['suspicious_repetition'])}")

    print(f"\nReport saved to: {report_file}")
    return report_file


if __name__ == '__main__':
    analyze_recent_content_patterns()