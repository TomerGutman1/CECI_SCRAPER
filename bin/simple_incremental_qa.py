#!/usr/bin/env python3
"""
Simple Incremental QA CLI - Works with existing Supabase setup
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.processors.simple_incremental import SimpleIncrementalQA
import logging
import argparse

def main():
    print("=" * 60)
    print("  SIMPLE INCREMENTAL QA — מערכת QA מצטברת פשוטה")
    print("=" * 60)

    parser = argparse.ArgumentParser(description="Simple Incremental QA for GOV2DB")
    parser.add_argument('command', choices=['run', 'status', 'reset'],
                       help='Command to execute')
    parser.add_argument('--max-records', type=int, default=1000,
                       help='Maximum records to check for changes')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        qa_system = SimpleIncrementalQA()

        if args.command == 'status':
            print("📊 Checking incremental QA status...")
            status = qa_system.get_status()

            print(f"\n🎯 Status: {status['status']}")

            if status['status'] != 'never_run':
                print(f"📅 Last scan: {status['last_scan']}")
                print(f"⏰ Hours since scan: {status['hours_since_scan']}")
                print(f"📊 Records tracked: {status['total_records_tracked']:,}")
                print(f"📁 Tracking file: {status['tracking_file']}")
                print(f"📁 Reports directory: {status['reports_dir']}")
            else:
                print("ℹ️  Run 'simple_incremental_qa.py run' to start tracking")

        elif args.command == 'run':
            print(f"🔍 Running incremental QA scan (max {args.max_records:,} records)...")
            result = qa_system.run_incremental_scan(args.max_records)

            print(f"\n✅ Incremental QA completed: {result['status']}")

            if result['status'] == 'completed':
                changes = result['changes']
                print(f"📈 New records: {len(changes['new'])}")
                print(f"📝 Changed records: {len(changes['changed'])}")
                print(f"➡️  Unchanged records: {len(changes['unchanged'])}")
                print(f"🔍 Records QA checked: {result['records_checked']}")

                if result['qa_results']:
                    qa_data = result['qa_results']
                    # Handle both dict and QAReport object
                    if hasattr(qa_data, 'total_issues'):
                        total_issues = qa_data.total_issues
                        severity = qa_data.issues_by_severity if hasattr(qa_data, 'issues_by_severity') else {}
                    else:
                        total_issues = qa_data.get('total_issues', 0)
                        severity = qa_data.get('issues_by_severity', {})

                    print(f"⚠️  QA issues found: {total_issues}")

                    if total_issues > 0:
                        print(f"   High: {severity.get('high', 0)}, "
                              f"Medium: {severity.get('medium', 0)}, "
                              f"Low: {severity.get('low', 0)}")

            elif result['status'] == 'no_changes':
                changes = result['changes']
                print(f"ℹ️  No changes detected in {len(changes['unchanged'])} records")
                print("   Skipping QA scan - all records unchanged")

        elif args.command == 'reset':
            print("🔄 Resetting change tracking...")
            qa_system.reset_tracking()
            print("✅ Tracking reset successfully")
            print("   Next 'run' command will process all records")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())