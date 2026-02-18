#!/usr/bin/env python3
"""
Orchestrated Database Fixes
Applies all agent-prepared fixes in a safe, sequential manner
"""

import sys
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from gov_scraper.db.connector import get_supabase_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OrchestatedFixer:
    def __init__(self, dry_run=False):
        self.client = get_supabase_client()
        self.dry_run = dry_run
        self.stats = {
            'malformed_keys_fixed': 0,
            'data_shifts_fixed': 0,
            'errors': []
        }

    def load_fixes(self):
        """Load all prepared fixes from JSON files"""
        fixes = {}

        # Load malformed keys fixes
        malformed_path = 'data/qa_reports/malformed_keys_fixes.json'
        if os.path.exists(malformed_path):
            with open(malformed_path, 'r', encoding='utf-8') as f:
                fixes['malformed_keys'] = json.load(f)
                logger.info(f"Loaded {len(fixes['malformed_keys']['malformed_keys'])} malformed key fixes")

        # Load data shifting fixes
        shifting_path = 'data/qa_reports/data_shifting_fixes.json'
        if os.path.exists(shifting_path):
            with open(shifting_path, 'r', encoding='utf-8') as f:
                fixes['data_shifts'] = json.load(f)
                logger.info(f"Loaded {len(fixes['data_shifts']['shifts_found'])} data shifting fixes")

        return fixes

    def fix_malformed_keys(self, malformed_data: Dict) -> Tuple[int, List]:
        """Fix malformed decision keys"""
        logger.info("\n=== FIXING MALFORMED KEYS ===")

        fixed = 0
        errors = []

        for item in malformed_data['malformed_keys']:
            current_key = item['current_key']
            new_key = item['new_key']

            if self.dry_run:
                logger.info(f"[DRY RUN] Would update {current_key} → {new_key}")
                fixed += 1
                continue

            try:
                # First check if new_key already exists
                check = self.client.table("israeli_government_decisions").select(
                    "decision_key"
                ).eq("decision_key", new_key).execute()

                if check.data:
                    logger.warning(f"Key {new_key} already exists, skipping {current_key}")
                    errors.append(f"Duplicate key: {new_key}")
                    continue

                # Update the key
                response = self.client.table("israeli_government_decisions").update({
                    "decision_key": new_key
                }).eq("decision_key", current_key).execute()

                if response.data:
                    logger.info(f"✓ Fixed: {current_key} → {new_key} ({item.get('hebrew_meaning', '')})")
                    fixed += 1
                else:
                    logger.error(f"✗ Failed to fix: {current_key}")
                    errors.append(f"Update failed: {current_key}")

            except Exception as e:
                logger.error(f"✗ Error fixing {current_key}: {e}")
                errors.append(f"Error on {current_key}: {str(e)}")

        return fixed, errors

    def fix_data_shifts(self, shifting_data: Dict) -> Tuple[int, List]:
        """Fix data shifting issues"""
        logger.info("\n=== FIXING DATA SHIFTS ===")

        fixed = 0
        errors = []

        # Only process high-confidence fixes
        high_confidence = [s for s in shifting_data['shifts_found']
                          if s.get('confidence', 0) >= 0.5]

        logger.info(f"Processing {len(high_confidence)} high-confidence fixes")

        # First, fetch all summaries we'll need
        decision_keys = list(set(
            [s['affected_decision_key'] for s in high_confidence] +
            [s['should_have_summary_from'] for s in high_confidence]
        ))

        # Fetch in batches
        summaries = {}
        for i in range(0, len(decision_keys), 50):
            batch = decision_keys[i:i+50]
            response = self.client.table("israeli_government_decisions").select(
                "decision_key, summary"
            ).in_("decision_key", batch).execute()

            for record in response.data:
                summaries[record['decision_key']] = record.get('summary', '')

        # Apply fixes
        for shift in high_confidence:
            decision_key = shift['affected_decision_key']
            source_key = shift['should_have_summary_from']
            confidence = shift['confidence']

            if source_key not in summaries:
                logger.warning(f"Source summary not found for {source_key}")
                errors.append(f"Missing source: {source_key}")
                continue

            correct_summary = summaries[source_key]

            if self.dry_run:
                logger.info(f"[DRY RUN] Would update {decision_key} with summary from {source_key} (confidence: {confidence})")
                fixed += 1
                continue

            try:
                response = self.client.table("israeli_government_decisions").update({
                    "summary": correct_summary
                }).eq("decision_key", decision_key).execute()

                if response.data:
                    logger.info(f"✓ Fixed: {decision_key} ← summary from {source_key} (confidence: {confidence})")
                    fixed += 1
                else:
                    logger.error(f"✗ Failed to fix: {decision_key}")
                    errors.append(f"Update failed: {decision_key}")

            except Exception as e:
                logger.error(f"✗ Error fixing {decision_key}: {e}")
                errors.append(f"Error on {decision_key}: {str(e)}")

        return fixed, errors

    def create_scraping_list(self) -> str:
        """Create prioritized scraping list from duplicate titles analysis"""
        logger.info("\n=== CREATING SCRAPING LIST ===")

        dup_path = 'data/qa_reports/duplicate_titles_analysis.json'
        if not os.path.exists(dup_path):
            logger.warning("Duplicate titles analysis not found")
            return None

        with open(dup_path, 'r', encoding='utf-8') as f:
            dup_data = json.load(f)

        # Add missing titles (815 records)
        missing_titles = []

        # Fetch records with NULL titles
        response = self.client.table("israeli_government_decisions").select(
            "decision_key, decision_url"
        ).is_("decision_title", "null").execute()

        missing_titles = [r['decision_key'] for r in response.data if r.get('decision_url')]

        # Combine all scraping needs
        scraping_list = {
            'timestamp': datetime.now().isoformat(),
            'high_priority': {
                'duplicate_titles': dup_data['scraping_list']['high_priority'],
                'missing_titles': missing_titles[:400],  # First batch
                'total': len(dup_data['scraping_list']['high_priority']) + len(missing_titles[:400])
            },
            'medium_priority': {
                'duplicate_titles': dup_data['scraping_list']['medium_priority'],
                'missing_titles': missing_titles[400:600],  # Second batch
                'total': len(dup_data['scraping_list']['medium_priority']) + len(missing_titles[400:600])
            },
            'low_priority': {
                'duplicate_titles': dup_data['scraping_list']['low_priority'],
                'missing_titles': missing_titles[600:],  # Rest
                'truncated_content': [],  # Add the 19 truncated records here
                'total': len(dup_data['scraping_list']['low_priority']) + len(missing_titles[600:])
            },
            'grand_total': len(dup_data['scraping_list']['high_priority']) +
                          len(dup_data['scraping_list']['medium_priority']) +
                          len(dup_data['scraping_list']['low_priority']) +
                          len(missing_titles)
        }

        # Save scraping list
        output_path = f'data/qa_reports/scraping_list_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(scraping_list, f, ensure_ascii=False, indent=2)

        logger.info(f"Scraping list saved to: {output_path}")
        logger.info(f"Total items to scrape: {scraping_list['grand_total']}")

        return output_path

    def run(self):
        """Execute all fixes in order"""
        logger.info("=== ORCHESTRATED DATABASE FIXES ===")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE UPDATES'}")

        # Load all fixes
        fixes = self.load_fixes()

        # Phase 1: Fix malformed keys (must be done first)
        if 'malformed_keys' in fixes:
            fixed, errors = self.fix_malformed_keys(fixes['malformed_keys'])
            self.stats['malformed_keys_fixed'] = fixed
            self.stats['errors'].extend(errors)

        # Phase 2: Fix data shifts
        if 'data_shifts' in fixes:
            fixed, errors = self.fix_data_shifts(fixes['data_shifts'])
            self.stats['data_shifts_fixed'] = fixed
            self.stats['errors'].extend(errors)

        # Phase 3: Create scraping list (no DB updates)
        scraping_file = self.create_scraping_list()

        # Final report
        logger.info("\n=== FINAL SUMMARY ===")
        logger.info(f"Malformed keys fixed: {self.stats['malformed_keys_fixed']}")
        logger.info(f"Data shifts fixed: {self.stats['data_shifts_fixed']}")
        logger.info(f"Total errors: {len(self.stats['errors'])}")

        if self.stats['errors']:
            logger.warning("Errors encountered:")
            for error in self.stats['errors'][:10]:
                logger.warning(f"  - {error}")

        if scraping_file:
            logger.info(f"\nScraping list created: {scraping_file}")
            logger.info("Use this list for efficient title/content scraping")

        return self.stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Apply orchestrated database fixes")
    parser.add_argument('--dry-run', action='store_true', help='Simulate without updating DB')
    parser.add_argument('--skip-malformed', action='store_true', help='Skip malformed keys fix')
    parser.add_argument('--skip-shifts', action='store_true', help='Skip data shifts fix')
    args = parser.parse_args()

    try:
        fixer = OrchestatedFixer(dry_run=args.dry_run)
        stats = fixer.run()

        if stats['errors']:
            return 1
        return 0

    except Exception as e:
        logger.error(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())