#!/usr/bin/env python3
"""
Create production-ready backup with all QA improvements applied.

Reads an existing backup file, applies all algorithm improvements, and saves
the enhanced dataset as a production-ready backup file.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.gov_scraper.processors.ai_post_processor import post_process_ai_results
from src.gov_scraper.processors.qa import apply_inline_fixes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def apply_all_improvements(record):
    """Apply all QA improvements to a single record."""
    try:
        # Apply post-processor improvements
        improved_record = post_process_ai_results(record)

        # Apply inline QA fixes
        final_record = apply_inline_fixes(improved_record)

        return final_record, True
    except Exception as e:
        logger.error(f"Failed to improve record {record.get('decision_key', 'unknown')}: {e}")
        return record, False

def main():
    parser = argparse.ArgumentParser(description='Create production-ready backup with all improvements')
    parser.add_argument('--input', required=True, help='Input backup JSON file')
    parser.add_argument('--output', required=True, help='Output production-ready JSON file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("🚀 CREATING PRODUCTION-READY BACKUP")
    logger.info("=" * 60)
    logger.info(f"Input: {args.input}")
    logger.info(f"Output: {args.output}")
    logger.info("=" * 60)

    # Load input file
    logger.info(f"Loading input file: {args.input}")
    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        return False

    with open(args.input, 'r', encoding='utf-8') as f:
        records = json.load(f)

    logger.info(f"Loaded {len(records)} records from {args.input}")

    # Process all records
    logger.info("Applying all algorithm improvements...")
    improved_records = []
    success_count = 0
    failed_count = 0

    for i, record in enumerate(records, 1):
        if i % 1000 == 0:
            logger.info(f"Processing progress: {i}/{len(records)} ({i/len(records)*100:.1f}%)")

        improved_record, success = apply_all_improvements(record)
        improved_records.append(improved_record)

        if success:
            success_count += 1
        else:
            failed_count += 1

    logger.info("=" * 60)
    logger.info("PROCESSING COMPLETE")
    logger.info(f"Total records: {len(records)}")
    logger.info(f"Successfully improved: {success_count}")
    logger.info(f"Failed improvements: {failed_count}")
    logger.info(f"Success rate: {success_count/len(records)*100:.1f}%")

    # Create output metadata
    output_data = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'source_file': args.input,
            'total_records': len(records),
            'improved_records': success_count,
            'failed_improvements': failed_count,
            'success_rate': f"{success_count/len(records)*100:.1f}%",
            'algorithm_version': 'enhanced_production_2026_02_19',
            'improvements_applied': [
                'Government body whitelist enforcement',
                'Summary prefix stripping',
                'Policy tag whitelist enforcement',
                'All_tags deterministic rebuild',
                'Government body normalization',
                'Operativity pattern validation',
                'Content validation and cleanup'
            ]
        },
        'decisions': improved_records
    }

    # Create output directory
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Save production-ready file
    logger.info(f"Saving production-ready backup to: {args.output}")
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    file_size_mb = os.path.getsize(args.output) / (1024 * 1024)
    logger.info(f"✅ Production backup saved: {file_size_mb:.1f} MB")
    logger.info(f"🎯 Dataset ready for deployment with {success_count} enhanced decisions")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)