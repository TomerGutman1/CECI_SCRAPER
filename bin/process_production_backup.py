#!/usr/bin/env python3
"""
Production Backup AI Enhancement Processor

This script processes the production backup (~25K decisions) with all new AI improvements:
- Unified AI processor (1 API call instead of 6)
- Fixed operativity classification (reduced 80% → 50% bias)
- Improved summary-tag alignment
- Government body validation
- Summary prefix stripping
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Setup path for imports
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

# Import the AI post-processing modules
from src.gov_scraper.processors.ai_post_processor import (
    post_process_ai_results,
    validate_and_clean_batch,
    BODY_NORMALIZATION,
    AUTHORIZED_POLICY_AREAS,
    AUTHORIZED_GOVERNMENT_BODIES
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ai_enhancement_processing.log')
    ]
)
logger = logging.getLogger(__name__)

# Processing statistics
class ProcessingStats:
    def __init__(self):
        self.total_decisions = 0
        self.processed_decisions = 0
        self.errors_count = 0
        self.fixes_applied = {
            'summary_prefix_stripped': 0,
            'government_bodies_normalized': 0,
            'government_bodies_dropped': 0,
            'policy_tags_validated': 0,
            'operativity_overridden': 0,
            'generic_locations_filtered': 0,
            'all_tags_rebuilt': 0,
            'duplicates_removed': 0
        }
        self.start_time = time.time()

    def add_fix(self, fix_type: str, count: int = 1):
        """Add a fix count to statistics."""
        if fix_type in self.fixes_applied:
            self.fixes_applied[fix_type] += count

    def get_processing_time(self):
        """Get total processing time."""
        return time.time() - self.start_time

    def report(self):
        """Generate a processing report."""
        processing_time = self.get_processing_time()

        report = f"""
=== AI Enhancement Processing Report ===
Start Time: {datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')}
Processing Time: {processing_time:.2f} seconds ({processing_time/60:.1f} minutes)

Total Decisions: {self.total_decisions}
Successfully Processed: {self.processed_decisions}
Errors: {self.errors_count}
Success Rate: {(self.processed_decisions/self.total_decisions)*100:.1f}%

Fixes Applied:
"""
        for fix_type, count in self.fixes_applied.items():
            report += f"  {fix_type.replace('_', ' ').title()}: {count:,}\n"

        report += f"""
Processing Rate: {self.processed_decisions / processing_time:.1f} decisions/second
Average Time per Decision: {processing_time / self.processed_decisions * 1000:.2f}ms
"""

        return report


def load_backup_file(backup_path: str) -> List[Dict]:
    """Load the production backup JSON file."""
    logger.info(f"Loading backup file: {backup_path}")

    try:
        with open(backup_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"Successfully loaded {len(data):,} decisions from backup")
        return data

    except Exception as e:
        logger.error(f"Failed to load backup file: {e}")
        raise


def process_decision(decision: Dict, stats: ProcessingStats) -> Dict:
    """Process a single decision with all AI improvements."""
    original_decision = decision.copy()

    try:
        # Apply AI post-processing improvements
        # Handle None values properly
        decision_content = decision.get('decision_content', '') or ''
        enhanced_decision = post_process_ai_results(
            decision,
            decision_content
        )

        # Track specific fixes applied
        if original_decision.get('summary', '') != enhanced_decision.get('summary', ''):
            if 'החלטת ממשלה מספר' in original_decision.get('summary', ''):
                stats.add_fix('summary_prefix_stripped')

        if original_decision.get('tags_government_body', '') != enhanced_decision.get('tags_government_body', ''):
            # Count normalized/dropped bodies
            orig_bodies = set([b.strip() for b in original_decision.get('tags_government_body', '').split(';') if b.strip()])
            new_bodies = set([b.strip() for b in enhanced_decision.get('tags_government_body', '').split(';') if b.strip()])

            if len(new_bodies) < len(orig_bodies):
                stats.add_fix('government_bodies_dropped', len(orig_bodies) - len(new_bodies))

            # Check for normalization (different content but same count)
            if orig_bodies != new_bodies and len(orig_bodies) == len(new_bodies):
                stats.add_fix('government_bodies_normalized')

        if original_decision.get('operativity', '') != enhanced_decision.get('operativity', ''):
            stats.add_fix('operativity_overridden')

        if original_decision.get('tags_location', '') != enhanced_decision.get('tags_location', ''):
            stats.add_fix('generic_locations_filtered')

        # Check if all_tags was rebuilt (always happens but track it)
        if enhanced_decision.get('all_tags'):
            stats.add_fix('all_tags_rebuilt')

        # Check for duplicate removal in any tag field
        for field in ['tags_policy_area', 'tags_government_body']:
            orig_tags = original_decision.get(field, '')
            new_tags = enhanced_decision.get(field, '')
            if orig_tags and ';' in orig_tags:
                orig_count = len([t.strip() for t in orig_tags.split(';') if t.strip()])
                new_count = len([t.strip() for t in new_tags.split(';') if t.strip()])
                if new_count < orig_count:
                    stats.add_fix('duplicates_removed', orig_count - new_count)

        stats.processed_decisions += 1
        return enhanced_decision

    except Exception as e:
        logger.error(f"Error processing decision {decision.get('decision_key', 'unknown')}: {e}")
        stats.errors_count += 1
        return original_decision  # Return original if processing fails


def process_in_batches(decisions: List[Dict], batch_size: int = 100) -> List[Dict]:
    """Process decisions in batches for memory efficiency."""
    stats = ProcessingStats()
    stats.total_decisions = len(decisions)

    enhanced_decisions = []

    logger.info(f"Starting batch processing of {len(decisions):,} decisions...")
    logger.info(f"Batch size: {batch_size}")

    for i in range(0, len(decisions), batch_size):
        batch_start = time.time()
        batch = decisions[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(decisions) + batch_size - 1) // batch_size

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} decisions)...")

        # Process each decision in the batch
        enhanced_batch = []
        for decision in batch:
            enhanced = process_decision(decision, stats)
            enhanced_batch.append(enhanced)

        enhanced_decisions.extend(enhanced_batch)

        batch_time = time.time() - batch_start
        estimated_total = batch_time * total_batches
        estimated_remaining = batch_time * (total_batches - batch_num)

        logger.info(
            f"Batch {batch_num} completed in {batch_time:.1f}s "
            f"(ETA: {estimated_remaining/60:.1f} minutes remaining)"
        )

        # Progress report every 10 batches or at end
        if batch_num % 10 == 0 or batch_num == total_batches:
            progress = (batch_num / total_batches) * 100
            logger.info(
                f"Progress: {progress:.1f}% ({stats.processed_decisions:,}/{stats.total_decisions:,} decisions)"
            )

    # Final statistics
    logger.info("\n" + stats.report())

    return enhanced_decisions


def save_enhanced_data(enhanced_decisions: List[Dict], output_path: str):
    """Save the enhanced decisions to JSON file."""
    logger.info(f"Saving enhanced data to: {output_path}")

    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save enhanced data
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enhanced_decisions, f, ensure_ascii=False, indent=2)

        # Get file size
        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)

        logger.info(f"Successfully saved {len(enhanced_decisions):,} enhanced decisions")
        logger.info(f"Output file size: {file_size_mb:.1f} MB")

    except Exception as e:
        logger.error(f"Failed to save enhanced data: {e}")
        raise


def main():
    """Main processing function."""
    # File paths
    backup_path = "/Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json"
    output_path = "/Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json"

    logger.info("=== AI Enhancement Processing Started ===")
    logger.info(f"Backup file: {backup_path}")
    logger.info(f"Output file: {output_path}")

    # Verify input file exists
    if not os.path.exists(backup_path):
        logger.error(f"Backup file not found: {backup_path}")
        return 1

    # Log authorized lists status
    logger.info(f"Loaded {len(AUTHORIZED_POLICY_AREAS)} authorized policy areas")
    logger.info(f"Loaded {len(AUTHORIZED_GOVERNMENT_BODIES)} authorized government bodies")
    logger.info(f"Body normalization rules: {len(BODY_NORMALIZATION)}")

    try:
        # Load backup data
        decisions = load_backup_file(backup_path)

        # Process with enhancements
        enhanced_decisions = process_in_batches(decisions, batch_size=250)

        # Save enhanced data
        save_enhanced_data(enhanced_decisions, output_path)

        logger.info("=== AI Enhancement Processing Completed Successfully ===")
        return 0

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)