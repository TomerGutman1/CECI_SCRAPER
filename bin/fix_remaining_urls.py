#!/usr/bin/env python3
"""Fix the remaining 4 URL mismatches"""

import sys
import os
import re
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from gov_scraper.db.connector import get_supabase_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REMAINING_KEYS = ["37_2846", "37_2581", "37_2094", "37_2060"]

def fix_url(url: str, correct_decision_num: str) -> str:
    """Fix URL by replacing wrong decision number with correct one."""
    if not url:
        return url

    patterns = [
        (r'/dec-(\d+)-([\d]{4})', r'/dec-{}-\2'),
        (r'/dec(\d+)-([\d]{4})', r'/dec{}-\2'),
        (r'/dec(\d+)_([\d]{4})', r'/dec{}_\2'),
        (r'/dec-(\d+)_([\d]{4})', r'/dec-{}_\2'),
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, url):
            fixed = re.sub(pattern, replacement.format(correct_decision_num), url)
            logger.info(f"Fixed: {url} → {fixed}")
            return fixed

    return url

def main():
    try:
        client = get_supabase_client()
        logger.info("Connected to database")

        # Fetch and fix remaining records
        response = client.table("israeli_government_decisions").select(
            "decision_key, decision_url, decision_number"
        ).in_("decision_key", REMAINING_KEYS).execute()

        for record in response.data:
            decision_key = record['decision_key']
            current_url = record.get('decision_url', '')
            decision_num = str(record.get('decision_number', ''))

            logger.info(f"\nFixing {decision_key}:")
            logger.info(f"  Current: {current_url}")

            fixed_url = fix_url(current_url, decision_num)
            logger.info(f"  Fixed: {fixed_url}")

            # Update
            update_response = client.table("israeli_government_decisions").update(
                {"decision_url": fixed_url}
            ).eq("decision_key", decision_key).execute()

            if update_response.data:
                logger.info(f"✓ Updated {decision_key}")
            else:
                logger.error(f"✗ Failed to update {decision_key}")

        logger.info("\n✓ All remaining URLs fixed!")
        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())