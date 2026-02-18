#!/usr/bin/env python3
"""
Fix URL Mismatches in Database

This script fixes the 26 records with URL mismatches by replacing the wrong
decision number in the URL with the correct one from the decision_key.

The issue appears to be digit confusion (OCR-like errors):
- 89 → 98
- 218 → 2018
- 759 → 579
etc.

Usage:
    python bin/fix_url_mismatches.py [--dry-run] [--verify-only]
"""

import sys
import os
import re
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# The 26 problematic decision keys (with duplicates removed)
PROBLEMATIC_KEYS = [
    "37_3789", "35_218", "37_2478", "37_2345", "35_759", "34_4684",
    "37_127", "37_373", "37_370", "36_1740", "36_1022", "36_1179", "37_3661"
]


def fix_url(url: str, correct_decision_num: str) -> str:
    """
    Fix a URL by replacing the wrong decision number with the correct one.

    Args:
        url: The current (wrong) URL
        correct_decision_num: The correct decision number from decision_key

    Returns:
        Fixed URL
    """
    if not url:
        return url

    # Pattern: /dec-?(\d+)[-_](\d{4})
    # We need to replace the first number group with the correct decision number

    # Try both patterns (with and without dash after 'dec')
    patterns = [
        (r'/dec-(\d+)-([\d]{4})', r'/dec-{}-\2'),  # /dec-XXXX-YYYY
        (r'/dec(\d+)-([\d]{4})', r'/dec{}-\2'),     # /decXXXX-YYYY
        (r'/dec(\d+)_([\d]{4})', r'/dec{}_\2'),     # /decXXXX_YYYY
        (r'/dec-(\d+)_([\d]{4})', r'/dec-{}_\2'),   # /dec-XXXX_YYYY
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, url):
            fixed_url = re.sub(pattern, replacement.format(correct_decision_num), url)
            logger.info(f"Fixed URL: {url} → {fixed_url}")
            return fixed_url

    logger.warning(f"Could not fix URL pattern: {url}")
    return url


def fetch_problematic_records(client) -> List[Dict]:
    """Fetch the problematic records from the database."""
    logger.info(f"Fetching {len(PROBLEMATIC_KEYS)} problematic records...")

    response = client.table("israeli_government_decisions").select(
        "decision_key, decision_url, decision_title, government_number, decision_number"
    ).in_("decision_key", PROBLEMATIC_KEYS).execute()

    if not response.data:
        logger.error("No records found")
        return []

    logger.info(f"Fetched {len(response.data)} records")
    return response.data


def update_record_url(client, decision_key: str, new_url: str, dry_run: bool = False) -> bool:
    """Update a single record's URL in the database."""
    if dry_run:
        logger.info(f"[DRY RUN] Would update {decision_key} with URL: {new_url}")
        return True

    try:
        response = client.table("israeli_government_decisions").update(
            {"decision_url": new_url}
        ).eq("decision_key", decision_key).execute()

        if response.data:
            logger.info(f"✓ Updated {decision_key} successfully")
            return True
        else:
            logger.error(f"✗ Failed to update {decision_key}")
            return False
    except Exception as e:
        logger.error(f"✗ Error updating {decision_key}: {e}")
        return False


def verify_fixes(client) -> Dict:
    """Verify that all URLs have been fixed correctly."""
    logger.info("\n=== VERIFYING FIXES ===")

    # Fetch the records again
    records = fetch_problematic_records(client)

    results = {
        'total': len(records),
        'fixed': 0,
        'still_broken': [],
        'missing_urls': []
    }

    for record in records:
        decision_key = record['decision_key']
        url = record.get('decision_url', '')
        decision_num = record.get('decision_number', '')

        if not url:
            results['missing_urls'].append(decision_key)
            continue

        # Extract decision number from URL
        url_match = re.search(r'/dec-?(\d+)[-_](\d{4})', url)
        if url_match:
            url_decision = url_match.group(1)
            if str(url_decision) == str(decision_num):
                results['fixed'] += 1
                logger.info(f"✓ {decision_key}: URL is correct (decision {decision_num})")
            else:
                results['still_broken'].append({
                    'key': decision_key,
                    'url_has': url_decision,
                    'should_be': decision_num
                })
                logger.warning(f"✗ {decision_key}: Still broken - URL has {url_decision}, should be {decision_num}")
        else:
            logger.warning(f"? {decision_key}: Could not parse URL pattern")

    return results


def main():
    """Main function."""
    import argparse
    parser = argparse.ArgumentParser(description="Fix URL mismatches in database")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--verify-only', action='store_true', help='Only verify current state without fixing')
    args = parser.parse_args()

    try:
        # Connect to database
        client = get_supabase_client()
        logger.info("Connected to database")

        # If verify only, just check current state
        if args.verify_only:
            results = verify_fixes(client)
            print(f"\n=== VERIFICATION RESULTS ===")
            print(f"Total records checked: {results['total']}")
            print(f"Correctly fixed: {results['fixed']}")
            print(f"Still broken: {len(results['still_broken'])}")
            print(f"Missing URLs: {len(results['missing_urls'])}")

            if results['still_broken']:
                print("\nRecords still needing fixes:")
                for item in results['still_broken']:
                    print(f"  - {item['key']}: URL has {item['url_has']}, should be {item['should_be']}")

            return 0 if len(results['still_broken']) == 0 else 1

        # Fetch problematic records
        records = fetch_problematic_records(client)

        if not records:
            logger.error("No problematic records found")
            return 1

        # Process each record
        logger.info(f"\n=== FIXING {len(records)} RECORDS ===")

        fixed_count = 0
        failed_count = 0

        for record in records:
            decision_key = record['decision_key']
            current_url = record.get('decision_url', '')
            decision_num = str(record.get('decision_number', ''))

            if not current_url:
                logger.warning(f"Skipping {decision_key}: No URL to fix")
                continue

            # Check if URL needs fixing
            url_match = re.search(r'/dec-?(\d+)[-_](\d{4})', current_url)
            if url_match:
                url_decision = url_match.group(1)
                if url_decision == decision_num:
                    logger.info(f"✓ {decision_key}: Already correct")
                    fixed_count += 1
                    continue

            # Fix the URL
            logger.info(f"\nFixing {decision_key}:")
            logger.info(f"  Current URL: {current_url}")

            fixed_url = fix_url(current_url, decision_num)
            logger.info(f"  Fixed URL: {fixed_url}")

            # Update in database
            if update_record_url(client, decision_key, fixed_url, dry_run=args.dry_run):
                fixed_count += 1
            else:
                failed_count += 1

        # Summary
        print(f"\n=== SUMMARY ===")
        print(f"Total processed: {len(records)}")
        print(f"Successfully fixed: {fixed_count}")
        print(f"Failed: {failed_count}")

        if not args.dry_run:
            # Verify the fixes
            print("\n=== VERIFYING ALL FIXES ===")
            verification = verify_fixes(client)

            print(f"\nFinal verification:")
            print(f"  Correct URLs: {verification['fixed']}/{verification['total']}")

            if verification['still_broken']:
                print(f"  Still broken: {len(verification['still_broken'])}")
                for item in verification['still_broken']:
                    print(f"    - {item['key']}")

            if verification['fixed'] == verification['total']:
                print("\n✓ All URLs have been successfully fixed!")
                return 0
            else:
                print(f"\n⚠ {len(verification['still_broken'])} records still need attention")
                return 1

        return 0

    except Exception as e:
        logger.error(f"Script failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())