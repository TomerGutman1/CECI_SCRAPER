#!/usr/bin/env python3
"""
Phase 1 Discovery Script - Full Catalog Pagination

Discovers ALL Israeli government decisions in the catalog using the full API pagination.
Creates a manifest file and supports checkpoint/resume functionality.

Usage:
    python bin/discover_all.py --no-headless                           # Full discovery (~258 pages)
    python bin/discover_all.py --max-pages 3 --no-headless           # Test with 3 pages
    python bin/discover_all.py --start-skip 25000 --max-pages 2 --no-headless  # Cross-era test
    python bin/discover_all.py --resume --no-headless                 # Resume from checkpoint
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from gov_scraper.scrapers.catalog import paginate_full_catalog
from gov_scraper.utils.selenium import SeleniumWebDriver

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/discover_all.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# File paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
MANIFEST_PATH = os.path.join(DATA_DIR, 'catalog_manifest.json')
CHECKPOINT_PATH = os.path.join(DATA_DIR, 'discovery_checkpoint.json')


class DiscoveryStats:
    """Track discovery statistics."""

    def __init__(self):
        self.total_entries = 0
        self.gov_breakdown = defaultdict(int)
        self.pm_breakdown = defaultdict(int)
        self.year_breakdown = defaultdict(int)
        self.missing_data = {
            'decision_number': 0,
            'decision_date': 0,
            'government_number': 0,
            'prime_minister': 0
        }
        self.entries_processed = 0
        self.pages_processed = 0

    def update_from_entry(self, entry: Dict):
        """Update statistics from a discovery entry."""
        self.total_entries += 1
        self.entries_processed += 1

        # Government breakdown
        gov_num = entry.get('government_number')
        if gov_num:
            self.gov_breakdown[gov_num] += 1
        else:
            self.missing_data['government_number'] += 1

        # Prime Minister breakdown
        pm = entry.get('prime_minister')
        if pm:
            self.pm_breakdown[pm] += 1
        else:
            self.missing_data['prime_minister'] += 1

        # Year breakdown
        decision_date = entry.get('decision_date')
        if decision_date and len(decision_date) >= 4:
            year = decision_date[:4]
            self.year_breakdown[year] += 1
        else:
            self.missing_data['decision_date'] += 1

        # Check for missing decision number
        if not entry.get('decision_number'):
            self.missing_data['decision_number'] += 1

    def print_summary(self):
        """Print comprehensive statistics summary."""
        print("\n" + "=" * 60)
        print("📊 DISCOVERY STATISTICS SUMMARY")
        print("=" * 60)
        print(f"📋 Total Entries: {self.total_entries:,}")
        print(f"📄 Pages Processed: {self.pages_processed}")
        print(f"🔄 Entries Processed This Session: {self.entries_processed}")

        # Government breakdown
        print(f"\n🏛️  Government Breakdown ({len(self.gov_breakdown)} governments):")
        for gov_num in sorted(self.gov_breakdown.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            count = self.gov_breakdown[gov_num]
            percentage = (count / self.total_entries * 100) if self.total_entries > 0 else 0
            print(f"   Government {gov_num}: {count:,} decisions ({percentage:.1f}%)")

        # Prime Minister breakdown (top 5)
        print(f"\n👤 Prime Ministers (top 5):")
        sorted_pms = sorted(self.pm_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
        for pm, count in sorted_pms:
            percentage = (count / self.total_entries * 100) if self.total_entries > 0 else 0
            print(f"   {pm}: {count:,} decisions ({percentage:.1f}%)")

        # Year breakdown (top 10)
        print(f"\n📅 Years (top 10):")
        sorted_years = sorted(self.year_breakdown.items(), key=lambda x: x[1], reverse=True)[:10]
        for year, count in sorted_years:
            percentage = (count / self.total_entries * 100) if self.total_entries > 0 else 0
            print(f"   {year}: {count:,} decisions ({percentage:.1f}%)")

        # Missing data analysis
        print(f"\n⚠️  Data Completeness:")
        for field, missing_count in self.missing_data.items():
            percentage = (missing_count / self.total_entries * 100) if self.total_entries > 0 else 0
            status = "✅" if percentage < 5 else "⚠️" if percentage < 20 else "❌"
            print(f"   {status} {field}: {missing_count:,} missing ({percentage:.1f}%)")

        print("=" * 60)


def load_checkpoint() -> Dict:
    """Load checkpoint data if it exists."""
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded checkpoint: skip={data.get('last_skip', 0)}, entries={data.get('total_entries', 0)}")
                return data
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
    return {}


def save_checkpoint(skip_value: int, stats: DiscoveryStats):
    """Save checkpoint data."""
    checkpoint_data = {
        'last_skip': skip_value,
        'total_entries': stats.total_entries,
        'pages_processed': stats.pages_processed,
        'timestamp': datetime.now().isoformat(),
        'gov_breakdown': dict(stats.gov_breakdown),
        'missing_data': dict(stats.missing_data)
    }

    try:
        with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved checkpoint: skip={skip_value}, entries={stats.total_entries}")
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")


def load_existing_manifest() -> List[Dict]:
    """Load existing manifest if it exists."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded existing manifest with {len(data)} entries")
                return data
        except Exception as e:
            logger.error(f"Failed to load existing manifest: {e}")
    return []


def save_manifest(entries: List[Dict]):
    """Save manifest data."""
    try:
        with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved manifest with {len(entries)} entries to {MANIFEST_PATH}")
    except Exception as e:
        logger.error(f"Failed to save manifest: {e}")


def create_decision_key(entry: Dict) -> str:
    """Create decision_key from entry data."""
    gov_num = entry.get('government_number', '')
    decision_num = entry.get('decision_number', '')
    if gov_num and decision_num:
        return f"{gov_num}_{decision_num}"
    return ""


def clean_entry_for_manifest(entry: Dict) -> Dict:
    """Clean and prepare entry for manifest (remove debug fields)."""
    # Create clean copy with required fields only
    clean_entry = {
        'url': entry.get('url', ''),
        'title': entry.get('title', ''),
        'decision_number': entry.get('decision_number', ''),
        'decision_date': entry.get('decision_date', ''),
        'government_number': entry.get('government_number', ''),
        'prime_minister': entry.get('prime_minister', ''),
        'committee': entry.get('committee', '') if entry.get('committee') else None,
        'description': entry.get('description', ''),
        'decision_key': create_decision_key(entry)
    }
    return clean_entry


def main():
    parser = argparse.ArgumentParser(description='Phase 1 Discovery - Full Catalog Pagination')
    parser.add_argument('--no-headless', action='store_true', required=True,
                       help='Run Chrome in visible mode (required to avoid Cloudflare blocks)')
    parser.add_argument('--max-pages', type=int, default=None,
                       help='Maximum number of pages to process (default: unlimited)')
    parser.add_argument('--start-skip', type=int, default=0,
                       help='Starting skip offset (default: 0)')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint')
    parser.add_argument('--page-size', type=int, default=100,
                       help='Entries per page (default: 100)')

    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    # Setup resume logic
    start_skip = args.start_skip
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            start_skip = checkpoint.get('last_skip', 0) + args.page_size  # Resume from next page
            logger.info(f"Resuming from skip={start_skip}")
        else:
            logger.warning("No checkpoint found, starting from beginning")

    # Initialize statistics
    stats = DiscoveryStats()

    # Load existing manifest
    all_entries = load_existing_manifest()
    existing_keys = set()

    # Update stats from existing entries
    for entry in all_entries:
        stats.update_from_entry(entry)
        if entry.get('decision_key'):
            existing_keys.add(entry['decision_key'])

    # Reset entries processed for this session
    stats.entries_processed = 0

    logger.info(f"Starting discovery with page_size={args.page_size}, start_skip={start_skip}")
    if args.max_pages:
        logger.info(f"Limited to {args.max_pages} pages")

    print("\n🚀 PHASE 1 DISCOVERY - FULL CATALOG PAGINATION")
    print("=" * 60)
    print(f"🔍 Starting Skip: {start_skip:,}")
    print(f"📄 Page Size: {args.page_size}")
    print(f"🎯 Max Pages: {args.max_pages if args.max_pages else 'Unlimited (~258 pages)'}")
    print(f"📁 Manifest: {MANIFEST_PATH}")
    print(f"💾 Checkpoint: {CHECKPOINT_PATH}")
    print("=" * 60)

    try:
        # Initialize Chrome WebDriver
        logger.info("Initializing Chrome WebDriver (no-headless mode)...")
        with SeleniumWebDriver(headless=False, timeout=30) as driver:

            # Visit gov.il to establish session
            logger.info("Establishing session at gov.il...")
            driver.navigate_to("https://www.gov.il/he", wait_time=5)

            # Paginate through catalog
            pages_processed_this_session = 0
            current_skip = start_skip
            new_entries = []

            def entry_callback(entry):
                """Callback for each discovered entry."""
                nonlocal new_entries, stats

                # Create decision key for deduplication
                decision_key = create_decision_key(entry)

                # Skip if we already have this entry
                if decision_key and decision_key in existing_keys:
                    logger.debug(f"Skipping duplicate entry: {decision_key}")
                    return

                # Clean entry and add to collection
                clean_entry = clean_entry_for_manifest(entry)
                new_entries.append(clean_entry)
                existing_keys.add(decision_key)

                # Update stats
                stats.update_from_entry(entry)

                # Progress logging
                if stats.entries_processed % 100 == 0:
                    logger.info(f"Processed {stats.entries_processed} entries this session (total: {stats.total_entries:,})")

            # Start pagination
            for entry in paginate_full_catalog(
                driver_instance=driver,
                page_size=args.page_size,
                start_skip=start_skip,
                callback=entry_callback
            ):
                # Check if we've processed enough pages
                if args.max_pages and stats.pages_processed >= args.max_pages:
                    logger.info(f"Reached max pages limit: {args.max_pages}")
                    break

                # Update page tracking
                if len(new_entries) > 0 and len(new_entries) % args.page_size == 0:
                    pages_processed_this_session += 1
                    stats.pages_processed += 1
                    current_skip = start_skip + (pages_processed_this_session * args.page_size)

                    # Save checkpoint after each page
                    save_checkpoint(current_skip, stats)

                    # Progress report
                    logger.info(f"Page {pages_processed_this_session} complete. "
                              f"New entries: {len(new_entries)}, Total: {stats.total_entries:,}")

            # Final statistics and save
            logger.info(f"Discovery complete! New entries: {len(new_entries)}")

            # Merge new entries into manifest
            if new_entries:
                all_entries.extend(new_entries)
                logger.info(f"Added {len(new_entries)} new entries to manifest")

            # Save final manifest
            save_manifest(all_entries)

            # Print comprehensive statistics
            stats.print_summary()

            # Validation check
            print(f"\n✅ VALIDATION:")
            print(f"   📁 Manifest saved: {len(all_entries):,} total entries")
            print(f"   💾 Checkpoint saved: skip={current_skip}")

            # Check for data quality issues
            total_missing = sum(stats.missing_data.values())
            missing_percentage = (total_missing / (stats.total_entries * 4)) * 100 if stats.total_entries > 0 else 0

            if missing_percentage < 5:
                print(f"   🎯 Data quality: Excellent ({missing_percentage:.1f}% missing)")
            elif missing_percentage < 15:
                print(f"   ⚠️  Data quality: Good ({missing_percentage:.1f}% missing)")
            else:
                print(f"   ❌ Data quality: Issues detected ({missing_percentage:.1f}% missing)")

            print("\n🎉 Phase 1 Discovery Complete!")

    except KeyboardInterrupt:
        logger.info("Discovery interrupted by user")
        print("\n⏸️  Discovery interrupted. Progress saved in checkpoint.")

        # Save progress
        if 'new_entries' in locals() and new_entries:
            all_entries.extend(new_entries)
            save_manifest(all_entries)
            logger.info(f"Saved {len(new_entries)} new entries before exit")

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        print(f"\n❌ Discovery failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()