#!/usr/bin/env python3
"""
Complete URL Integrity Check for All Records

This script analyzes ALL ~25,000 records in the database to identify
every single URL mismatch so we can fix them before re-scraping.

Usage:
    python bin/check_all_urls.py
"""

import sys
import os
import re
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import Counter

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_decision_key_components(decision_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract government number and decision number from decision_key."""
    if not decision_key or '_' not in decision_key:
        return None, None

    parts = decision_key.split('_', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None


def extract_decision_from_url(url: str) -> Optional[str]:
    """Extract decision number from URL."""
    if not url:
        return None

    # Pattern: /dec-?(\d+)[-_](\d{4})
    match = re.search(r'/dec-?(\d+)[-_](\d{4})', url)
    if match:
        return match.group(1)

    return None


def fetch_all_records(client) -> List[Dict]:
    """Fetch ALL records from the database using pagination."""
    logger.info("Starting to fetch ALL records from database...")

    all_records = []
    batch_size = 1000
    offset = 0

    while True:
        try:
            # Fetch batch
            response = client.table("israeli_government_decisions").select(
                "decision_key, decision_url, decision_title, government_number, decision_number"
            ).range(offset, offset + batch_size - 1).execute()

            if not response.data:
                break

            all_records.extend(response.data)
            logger.info(f"Fetched {len(all_records)} records so far...")

            if len(response.data) < batch_size:
                break

            offset += batch_size

        except Exception as e:
            logger.error(f"Error fetching batch at offset {offset}: {e}")
            break

    logger.info(f"Successfully fetched {len(all_records)} total records")
    return all_records


def analyze_record(record: Dict) -> Optional[Dict]:
    """Analyze a single record for URL mismatches."""
    decision_key = record.get('decision_key', '')
    url = record.get('decision_url', '')
    title = record.get('decision_title', '')

    # Skip malformed keys with Hebrew characters
    if any(char in decision_key for char in ['/', 'רהמ', 'מח']):
        return None

    gov_num, decision_num = extract_decision_key_components(decision_key)
    url_decision = extract_decision_from_url(url)

    if not decision_num or not url_decision:
        if not url:
            return {
                'decision_key': decision_key,
                'issue': 'missing_url',
                'title': title[:100] if title else ''
            }
        return None

    # Check for mismatch
    try:
        if str(int(url_decision)) != str(int(decision_num)):
            diff = int(url_decision) - int(decision_num)
            return {
                'decision_key': decision_key,
                'url': url,
                'decision_from_key': decision_num,
                'decision_from_url': url_decision,
                'difference': diff,
                'title': title[:100] if title else '',
                'issue': 'url_mismatch'
            }
    except (ValueError, TypeError):
        return None

    return None


def main():
    """Main function to check all URLs."""
    try:
        # Connect to database
        client = get_supabase_client()
        logger.info("Connected to database")

        # Fetch ALL records
        all_records = fetch_all_records(client)

        if not all_records:
            logger.error("No records fetched")
            return 1

        # Analyze each record
        logger.info("Analyzing URL integrity for all records...")
        mismatches = []
        missing_urls = []

        for i, record in enumerate(all_records, 1):
            if i % 1000 == 0:
                logger.info(f"Progress: {i}/{len(all_records)} records analyzed...")

            result = analyze_record(record)
            if result:
                if result['issue'] == 'url_mismatch':
                    mismatches.append(result)
                elif result['issue'] == 'missing_url':
                    missing_urls.append(result)

        # Generate report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        report = {
            'metadata': {
                'timestamp': timestamp,
                'total_records': len(all_records),
                'total_mismatches': len(mismatches),
                'total_missing_urls': len(missing_urls),
                'mismatch_rate': round((len(mismatches) / len(all_records)) * 100, 2)
            },
            'mismatches': mismatches,
            'missing_urls': missing_urls,
            'statistics': {
                'by_government': Counter(m['decision_key'].split('_')[0] for m in mismatches),
                'by_difference': Counter(m['difference'] for m in mismatches),
                'difference_range': {
                    'min': min((m['difference'] for m in mismatches), default=0),
                    'max': max((m['difference'] for m in mismatches), default=0)
                }
            }
        }

        # Save full report
        output_dir = 'data/qa_reports'
        os.makedirs(output_dir, exist_ok=True)
        output_file = f'{output_dir}/complete_url_check_{timestamp}.json'

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Also save just the list of mismatched decision_keys for easy processing
        mismatch_keys_file = f'{output_dir}/url_mismatch_keys_{timestamp}.txt'
        with open(mismatch_keys_file, 'w') as f:
            for mismatch in mismatches:
                f.write(f"{mismatch['decision_key']}\n")

        # Print summary
        print(f"""
=== COMPLETE URL INTEGRITY CHECK ===
Timestamp: {timestamp}
Total Records: {len(all_records)}

RESULTS:
- URL Mismatches: {len(mismatches)} ({report['metadata']['mismatch_rate']}%)
- Missing URLs: {len(missing_urls)}

MISMATCH STATISTICS:
- Difference Range: {report['statistics']['difference_range']['min']} to {report['statistics']['difference_range']['max']}
- Most Common Differences: {Counter(m['difference'] for m in mismatches).most_common(5)}

BY GOVERNMENT:
{chr(10).join(f"- Government {gov}: {count} mismatches" for gov, count in report['statistics']['by_government'].most_common())}

FILES CREATED:
- Full Report: {output_file}
- Mismatch Keys List: {mismatch_keys_file}

EXAMPLE MISMATCHES:
""")

        for example in mismatches[:5]:
            print(f"- {example['decision_key']}: URL has {example['decision_from_url']} (should be {example['decision_from_key']}, diff: {example['difference']})")
            print(f"  Title: {example['title']}")

        if len(mismatches) > 5:
            print(f"\n... and {len(mismatches) - 5} more mismatches")

        logger.info(f"Analysis complete. {len(mismatches)} URL mismatches found.")
        return 0

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())