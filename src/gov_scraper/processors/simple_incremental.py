#!/usr/bin/env python3
"""
Simplified Incremental QA System - Works with existing Supabase table
No additional tables needed - uses file-based tracking
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict
import hashlib

from .qa import run_scan, QAScanResult
from ..db.connector import get_supabase_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChangeTracker:
    """Track changes to records using file-based storage."""
    last_scan: Optional[str] = None
    record_hashes: Dict[str, str] = None
    total_records: int = 0

    def __post_init__(self):
        if self.record_hashes is None:
            self.record_hashes = {}

class SimpleIncrementalQA:
    """
    Simplified incremental QA system that works with existing infrastructure.
    Uses file-based change tracking instead of database triggers.
    """

    def __init__(self, tracking_dir: str = "data/incremental_tracking"):
        self.tracking_dir = tracking_dir
        self.tracking_file = os.path.join(tracking_dir, "change_tracker.json")
        self.reports_dir = os.path.join(tracking_dir, "reports")

        # Ensure directories exist
        os.makedirs(tracking_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)

        self.client = get_supabase_client()
        self.change_tracker = self._load_tracker()

    def _load_tracker(self) -> ChangeTracker:
        """Load change tracker from file."""
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    data = json.load(f)
                    return ChangeTracker(**data)
            except Exception as e:
                logger.warning(f"Failed to load tracker: {e}")

        return ChangeTracker()

    def _save_tracker(self):
        """Save change tracker to file."""
        try:
            with open(self.tracking_file, 'w') as f:
                json.dump(asdict(self.change_tracker), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save tracker: {e}")

    def _get_record_hash(self, record: Dict) -> str:
        """Generate hash for record to detect changes."""
        # Use key fields that matter for QA
        key_fields = {
            'decision_key': record.get('decision_key', ''),
            'operativity': record.get('operativity', ''),
            'summary': record.get('summary', ''),
            'decision_content': record.get('decision_content', ''),
            'tags_policy_area': record.get('tags_policy_area', []),
            'tags_government_body': record.get('tags_government_body', []),
            'updated_at': record.get('updated_at', '')
        }

        # Create hash from JSON string
        content = json.dumps(key_fields, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def detect_changes(self, limit: Optional[int] = None) -> Dict[str, List[str]]:
        """
        Detect changed records by comparing hashes.
        Returns dict with 'new', 'changed', 'unchanged' lists of decision_keys.
        """
        logger.info("Detecting changes in records...")

        # Fetch current records
        query = self.client.table('israeli_government_decisions')\
            .select('decision_key,operativity,summary,decision_content,tags_policy_area,tags_government_body,updated_at')\
            .order('updated_at', desc=True)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        current_records = result.data

        new_records = []
        changed_records = []
        unchanged_records = []

        current_hashes = {}

        for record in current_records:
            decision_key = record['decision_key']
            current_hash = self._get_record_hash(record)
            current_hashes[decision_key] = current_hash

            old_hash = self.change_tracker.record_hashes.get(decision_key)

            if old_hash is None:
                new_records.append(decision_key)
            elif old_hash != current_hash:
                changed_records.append(decision_key)
            else:
                unchanged_records.append(decision_key)

        # Update tracker
        self.change_tracker.record_hashes.update(current_hashes)
        self.change_tracker.total_records = len(current_records)
        self.change_tracker.last_scan = datetime.now().isoformat()

        changes = {
            'new': new_records,
            'changed': changed_records,
            'unchanged': unchanged_records
        }

        logger.info(f"Change detection complete: {len(new_records)} new, "
                   f"{len(changed_records)} changed, {len(unchanged_records)} unchanged")

        return changes

    def run_incremental_scan(self, max_records: int = 1000) -> Dict:
        """
        Run QA scan only on changed/new records.
        """
        logger.info("Starting incremental QA scan...")

        # Detect changes
        changes = self.detect_changes(limit=max_records)

        # Get records that need QA checking
        records_to_check = changes['new'] + changes['changed']

        if not records_to_check:
            logger.info("No changes detected - skipping QA scan")
            return {
                'status': 'no_changes',
                'changes': changes,
                'qa_results': None,
                'timestamp': datetime.now().isoformat()
            }

        logger.info(f"Running QA on {len(records_to_check)} changed records...")

        # Fetch full records for QA
        records_query = self.client.table('israeli_government_decisions')\
            .select('*')\
            .in_('decision_key', records_to_check[:100])  # Limit to avoid timeout

        qa_records = records_query.execute().data

        # Run QA scan
        qa_results = run_scan(qa_records, checks=None)  # Use default checks

        # Save results
        report = {
            'status': 'completed',
            'changes': changes,
            'qa_results': qa_results,
            'timestamp': datetime.now().isoformat(),
            'records_checked': len(qa_records),
            'records_to_check': len(records_to_check)
        }

        # Save report
        report_file = os.path.join(self.reports_dir,
                                 f"incremental_qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Report saved to: {report_file}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

        # Update tracker
        self._save_tracker()

        return report

    def get_status(self) -> Dict:
        """Get current incremental QA status."""
        if not self.change_tracker.last_scan:
            return {
                'status': 'never_run',
                'message': 'Incremental QA has never been run'
            }

        last_scan = datetime.fromisoformat(self.change_tracker.last_scan)
        time_since = datetime.now() - last_scan

        return {
            'status': 'ready',
            'last_scan': self.change_tracker.last_scan,
            'hours_since_scan': round(time_since.total_seconds() / 3600, 1),
            'total_records_tracked': self.change_tracker.total_records,
            'tracking_file': self.tracking_file,
            'reports_dir': self.reports_dir
        }

    def reset_tracking(self):
        """Reset change tracking (force full scan on next run)."""
        self.change_tracker = ChangeTracker()
        self._save_tracker()
        logger.info("Change tracking reset - next scan will process all records")

def main():
    """CLI interface for simple incremental QA."""
    import argparse

    parser = argparse.ArgumentParser(description="Simple Incremental QA")
    parser.add_argument('command', choices=['run', 'status', 'reset'],
                       help='Command to execute')
    parser.add_argument('--max-records', type=int, default=1000,
                       help='Maximum records to check for changes')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    qa_system = SimpleIncrementalQA()

    if args.command == 'status':
        status = qa_system.get_status()
        print(f"Status: {status['status']}")
        if status['status'] != 'never_run':
            print(f"Last scan: {status['last_scan']}")
            print(f"Hours since scan: {status['hours_since_scan']}")
            print(f"Records tracked: {status['total_records_tracked']}")

    elif args.command == 'run':
        result = qa_system.run_incremental_scan(args.max_records)
        print(f"Incremental QA completed: {result['status']}")
        if result['status'] == 'completed':
            changes = result['changes']
            print(f"New records: {len(changes['new'])}")
            print(f"Changed records: {len(changes['changed'])}")
            print(f"QA issues found: {result['qa_results'].get('total_issues', 0)}")

    elif args.command == 'reset':
        qa_system.reset_tracking()
        print("Tracking reset successfully")

if __name__ == "__main__":
    main()