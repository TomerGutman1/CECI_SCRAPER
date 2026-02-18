#!/usr/bin/env python3
"""
Incremental QA CLI - Efficient QA updates for GOV2DB with change tracking.

This script provides a command-line interface for the incremental QA processing
system, enabling efficient updates that only process changed records.

Usage:
    python bin/incremental_qa.py setup                           # Setup change tracking
    python bin/incremental_qa.py run                             # Run incremental QA
    python bin/incremental_qa.py run --since 2025-01-01         # Process changes since date
    python bin/incremental_qa.py run --max-changes 100          # Limit processing
    python bin/incremental_qa.py resume CHECKPOINT_ID           # Resume from checkpoint
    python bin/incremental_qa.py status                         # Show processing status
    python bin/incremental_qa.py report                         # Generate differential report
    python bin/incremental_qa.py report --since 2025-01-01      # Report since specific date
    python bin/incremental_qa.py cleanup --days 7               # Cleanup old checkpoints

Options:
    --since YYYY-MM-DD         Process changes since this date
    --max-changes N            Maximum number of changes to process
    --batch-size N             Batch size for processing (default: 50)
    --checkpoint-interval N    Save checkpoint every N changes (default: 100)
    --days N                   Number of days for cleanup operations
    --verbose                  Enable verbose logging
    --dry-run                  Show what would be processed without executing
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.processors.incremental import (
    IncrementalQAProcessor,
    setup_incremental_qa,
    run_incremental_qa_update
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, 'incremental_qa.log'),
                encoding='utf-8'
            )
        ]
    )


def cmd_setup(args):
    """Set up change tracking infrastructure."""
    print("\n" + "=" * 60)
    print("  INCREMENTAL QA SETUP — הגדרת מעקב שינויים")
    print("=" * 60)

    try:
        processor = IncrementalQAProcessor(
            batch_size=args.batch_size,
            checkpoint_interval=args.checkpoint_interval
        )

        print("🔧 Setting up change tracking infrastructure...")
        processor.setup_change_tracking()

        print("✅ Change tracking setup completed successfully!")
        print("\nInfrastructure created:")
        print("  - qa_audit_log table for tracking all changes")
        print("  - qa_checkpoints table for recovery points")
        print("  - Database triggers on israeli_government_decisions")
        print("  - Checkpoint storage directory")

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)


def cmd_run(args):
    """Run incremental QA processing."""
    print("\n" + "=" * 60)
    print("  INCREMENTAL QA RUN — הרצת בדיקה מצטברת")
    print("=" * 60)

    # Parse since date if provided
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, '%Y-%m-%d')
            print(f"📅 Processing changes since: {since_date.strftime('%Y-%m-%d')}")
        except ValueError:
            print(f"❌ Invalid date format: {args.since}. Use YYYY-MM-DD")
            sys.exit(1)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")

    try:
        if args.dry_run:
            # For dry run, just show what would be processed
            processor = setup_incremental_qa()
            changes = processor.fetch_pending_changes(since=since_date, limit=args.max_changes)

            print(f"📊 Found {len(changes)} pending changes to process:")

            # Group by operation and priority
            by_operation = {}
            by_priority = {}
            for change in changes:
                by_operation[change.operation] = by_operation.get(change.operation, 0) + 1
                by_priority[change.priority] = by_priority.get(change.priority, 0) + 1

            print(f"   By operation: {dict(by_operation)}")
            print(f"   By priority: {dict(by_priority)}")

            if changes:
                print("\n📋 Sample changes:")
                for i, change in enumerate(changes[:5]):
                    print(f"   {i+1}. {change.operation.upper()} on {change.record_key}")
                    print(f"      Fields: {', '.join(change.changed_fields)}")
                    print(f"      Priority: {change.priority} | Time: {change.timestamp}")
                if len(changes) > 5:
                    print(f"   ... and {len(changes) - 5} more changes")
        else:
            # Run actual processing
            result = run_incremental_qa_update(
                since=since_date,
                max_changes=args.max_changes
            )

            print("\n📈 Processing completed!")
            print(f"   Session ID: {result.session_id}")
            print(f"   Duration: {(result.end_time - result.start_time).total_seconds():.1f}s")
            print(f"   Total changes: {result.total_changes}")
            print(f"   ✅ Processed: {result.processed_changes}")
            print(f"   ❌ Failed: {result.failed_changes}")
            print(f"   ⏭️  Skipped: {result.skipped_changes}")
            print(f"   💾 Checkpoints: {len(result.checkpoints)}")

            if result.performance_metrics['changes_per_second'] > 0:
                print(f"   ⚡ Rate: {result.performance_metrics['changes_per_second']:.2f} changes/sec")

            # Show any errors
            if result.error_summary:
                print("\n❌ Errors encountered:")
                for error_type, count in result.error_summary.items():
                    print(f"   {error_type}: {count}")

    except Exception as e:
        print(f"❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_resume(args):
    """Resume processing from a checkpoint."""
    print("\n" + "=" * 60)
    print(f"  RESUME FROM CHECKPOINT — המשך מנקודת ביקורת")
    print("=" * 60)

    if not args.checkpoint_id:
        print("❌ Checkpoint ID is required")
        sys.exit(1)

    try:
        processor = setup_incremental_qa()
        result = processor.run_incremental_qa(resume_from_checkpoint=args.checkpoint_id)

        print("\n📈 Resume completed!")
        print(f"   Session ID: {result.session_id}")
        print(f"   Duration: {(result.end_time - result.start_time).total_seconds():.1f}s")
        print(f"   ✅ Processed: {result.processed_changes}")
        print(f"   ❌ Failed: {result.failed_changes}")

    except Exception as e:
        print(f"❌ Resume failed: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show current processing status."""
    print("\n" + "=" * 60)
    print("  INCREMENTAL QA STATUS — סטטוס בדיקה מצטברת")
    print("=" * 60)

    try:
        from src.gov_scraper.db.connector import get_supabase_client
        client = get_supabase_client()

        # Get pending changes
        pending_response = client.table('qa_audit_log').select('*').eq('processed', False).execute()
        pending_changes = pending_response.data

        # Get recent checkpoints
        checkpoints_response = (client.table('qa_checkpoints')
                               .select('*')
                               .order('timestamp', desc=True)
                               .limit(5)
                               .execute())
        recent_checkpoints = checkpoints_response.data

        # Get processing stats from last 24 hours
        yesterday = datetime.now() - timedelta(days=1)
        recent_response = (client.table('qa_audit_log')
                          .select('*')
                          .gte('timestamp', yesterday.isoformat())
                          .execute())
        recent_changes = recent_response.data

        print(f"📊 Current Status:")
        print(f"   Pending changes: {len(pending_changes)}")
        print(f"   Changes in last 24h: {len(recent_changes)}")
        print(f"   Recent checkpoints: {len(recent_checkpoints)}")

        if pending_changes:
            # Group by priority
            by_priority = {}
            by_table = {}
            for change in pending_changes:
                priority = change.get('priority', 1)
                by_priority[priority] = by_priority.get(priority, 0) + 1
                table = change.get('table_name', 'unknown')
                by_table[table] = by_table.get(table, 0) + 1

            print(f"\n📋 Pending changes breakdown:")
            print(f"   By priority: {dict(by_priority)}")
            print(f"   By table: {dict(by_table)}")

        if recent_checkpoints:
            print(f"\n💾 Recent checkpoints:")
            for cp in recent_checkpoints[:3]:
                timestamp = datetime.fromisoformat(cp['timestamp'].replace('Z', '+00:00'))
                print(f"   {cp['checkpoint_id']} - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        sys.exit(1)


def cmd_report(args):
    """Generate differential report."""
    print("\n" + "=" * 60)
    print("  DIFFERENTIAL REPORT — דו\"ח שינויים")
    print("=" * 60)

    # Parse since date if provided
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid date format: {args.since}. Use YYYY-MM-DD")
            sys.exit(1)

    try:
        processor = setup_incremental_qa()
        report = processor.generate_differential_report(since=since_date)

        if 'error' in report:
            print(f"❌ Report generation failed: {report['error']}")
            return

        print(f"📊 Differential Report")
        print(f"   Period: {report['period_start']} to {report['period_end']}")

        # Processing status
        status = report['processing_status']
        total = status['total']
        processed = status['processed']
        pending = status['pending']

        print(f"\n🔄 Processing Status:")
        print(f"   Total changes: {total}")
        print(f"   ✅ Processed: {processed}")
        print(f"   ⏳ Pending: {pending}")
        if total > 0:
            print(f"   Progress: {(processed/total)*100:.1f}%")

        # Change summary
        changes = report['change_summary']
        if changes:
            print(f"\n📈 Changes by type:")
            for operation, count in changes.items():
                print(f"   {operation.upper()}: {count}")

        # Field changes
        field_changes = report['field_changes']
        if field_changes:
            print(f"\n🏷️  Most changed fields:")
            sorted_fields = sorted(field_changes.items(), key=lambda x: x[1], reverse=True)
            for field, count in sorted_fields[:10]:
                print(f"   {field}: {count} changes")

        # Recommendations
        recommendations = report['recommendations']
        if recommendations:
            print(f"\n💡 Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")

        # Save report to file if requested
        if hasattr(args, 'output') and args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Report saved to: {args.output}")

    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        sys.exit(1)


def cmd_cleanup(args):
    """Clean up old checkpoints and audit logs."""
    print("\n" + "=" * 60)
    print("  CLEANUP — ניקוי קבצים ישנים")
    print("=" * 60)

    if not args.days:
        print("❌ Number of days is required (--days N)")
        sys.exit(1)

    cutoff_date = datetime.now() - timedelta(days=args.days)
    print(f"🗑️  Cleaning up data older than: {cutoff_date.strftime('%Y-%m-%d')}")

    try:
        from src.gov_scraper.db.connector import get_supabase_client
        client = get_supabase_client()

        # Clean up processed audit logs
        old_logs_response = (client.table('qa_audit_log')
                            .delete()
                            .eq('processed', True)
                            .lt('timestamp', cutoff_date.isoformat())
                            .execute())

        # Clean up old checkpoints
        old_checkpoints_response = (client.table('qa_checkpoints')
                                   .delete()
                                   .lt('timestamp', cutoff_date.isoformat())
                                   .execute())

        # Clean up checkpoint files
        processor = IncrementalQAProcessor()
        checkpoint_files_deleted = 0
        if os.path.exists(processor.checkpoint_dir):
            for filename in os.listdir(processor.checkpoint_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(processor.checkpoint_dir, filename)
                    try:
                        file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if file_time < cutoff_date:
                            os.remove(filepath)
                            checkpoint_files_deleted += 1
                    except Exception as e:
                        print(f"⚠️  Could not delete {filename}: {e}")

        print(f"✅ Cleanup completed:")
        print(f"   Audit logs cleaned: {len(old_logs_response.data) if old_logs_response.data else 0}")
        print(f"   Checkpoints cleaned: {len(old_checkpoints_response.data) if old_checkpoints_response.data else 0}")
        print(f"   Checkpoint files deleted: {checkpoint_files_deleted}")

    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Incremental QA CLI for efficient GOV2DB quality updates',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global options
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for processing')
    parser.add_argument('--checkpoint-interval', type=int, default=100, help='Checkpoint interval')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Set up change tracking infrastructure')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run incremental QA processing')
    run_parser.add_argument('--since', help='Process changes since this date (YYYY-MM-DD)')
    run_parser.add_argument('--max-changes', type=int, help='Maximum number of changes to process')
    run_parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')

    # Resume command
    resume_parser = subparsers.add_parser('resume', help='Resume from checkpoint')
    resume_parser.add_argument('checkpoint_id', help='Checkpoint ID to resume from')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show current processing status')

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate differential report')
    report_parser.add_argument('--since', help='Report changes since this date (YYYY-MM-DD)')
    report_parser.add_argument('--output', help='Save report to file')

    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old data')
    cleanup_parser.add_argument('--days', type=int, required=True, help='Clean data older than N days')

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Handle commands
    if args.command == 'setup':
        cmd_setup(args)
    elif args.command == 'run':
        cmd_run(args)
    elif args.command == 'resume':
        cmd_resume(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'report':
        cmd_report(args)
    elif args.command == 'cleanup':
        cmd_cleanup(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()