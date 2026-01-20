#!/usr/bin/env python3
"""
Tag Migration Script - Migrate old tags to new standardized values.

Usage:
    python bin/migrate_tags.py preview               # Preview on 10 records
    python bin/migrate_tags.py dry-run               # Full dry-run (no changes)
    python bin/migrate_tags.py execute               # Execute migration

Options:
    --count N              Limit to N records
    --start-date YYYY-MM-DD   Filter from this date
    --end-date YYYY-MM-DD     Filter until this date
    --prefix PREFIX        Filter by decision_key prefix (e.g., "37_")
    --batch-size N         Batch size for updates (default: 10)
    --verbose              Enable verbose logging

Examples:
    python bin/migrate_tags.py preview --count 20
    python bin/migrate_tags.py dry-run --start-date 2024-01-01 --count 100
    python bin/migrate_tags.py execute --start-date 2024-06-01 --end-date 2024-12-31
"""

import sys
import os
import argparse
import logging
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.processors.tag_migration import (
    run_preview,
    run_dry_run,
    run_execute,
    generate_report,
    export_report_json
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(PROJECT_ROOT, 'logs', 'migration.log'),
                encoding='utf-8'
            )
        ]
    )


def print_preview_results(results, policy_stats, dept_stats):
    """Print preview results in a readable format."""
    print("\n" + "=" * 70)
    print("  בדיקת מיגרציה - תצוגה מקדימה")
    print("=" * 70)

    for i, result in enumerate(results, 1):
        print(f"\nרשומה {i}: decision_key={result['decision_key']}")
        print("  tags_policy_area:")
        print(f"    ישן: \"{result.get('old_policy', '')}\"")
        print(f"    חדש: \"{result.get('new_policy', '')}\"")

        print("  tags_government_body:")
        print(f"    ישן: \"{result.get('old_dept', '')}\"")
        print(f"    חדש: \"{result.get('new_dept', '')}\"")

    # Print summary stats
    print("\n" + "=" * 70)
    print("  סיכום שיטות מיפוי")
    print("=" * 70)

    print("\ntags_policy_area:")
    print(f"  Exact Match:       {policy_stats.exact}")
    print(f"  Substring Match:   {policy_stats.substring}")
    print(f"  Word Overlap:      {policy_stats.word_overlap}")
    print(f"  AI Tag Match:      {policy_stats.ai_tag}")
    print(f"  AI Summary:        {policy_stats.ai_summary}")
    print(f"  Fallback (שונות):  {policy_stats.fallback}")

    print("\ntags_government_body:")
    print(f"  Exact Match:       {dept_stats.exact}")
    print(f"  Substring Match:   {dept_stats.substring}")
    print(f"  Word Overlap:      {dept_stats.word_overlap}")
    print(f"  AI Tag Match:      {dept_stats.ai_tag}")
    print(f"  AI Summary:        {dept_stats.ai_summary}")
    print(f"  Fallback (שונות):  {dept_stats.fallback}")


def cmd_preview(args):
    """Run preview mode."""
    print(f"\n🔍 Running preview on {args.count} records...")

    results, policy_stats, dept_stats = run_preview(
        num_records=args.count,
        start_date=args.start_date,
        end_date=args.end_date,
        decision_key_prefix=args.prefix
    )

    print_preview_results(results, policy_stats, dept_stats)

    print("\n" + "=" * 70)
    print("  Preview complete. Review the mappings above.")
    print("  Run 'make migrate-dry' for a full dry-run.")
    print("=" * 70)


def cmd_dry_run(args):
    """Run full dry-run."""
    print("\n📋 Running full dry-run (no changes will be made)...")

    results, policy_stats, dept_stats = run_dry_run(
        start_date=args.start_date,
        end_date=args.end_date,
        max_records=args.count,
        decision_key_prefix=args.prefix
    )

    # Count changes
    changed = sum(
        1 for r in results
        if r.get('old_policy') != r.get('new_policy') or
           r.get('old_dept') != r.get('new_dept')
    )

    # Generate and print report
    report = generate_report(policy_stats, dept_stats, len(results), changed)
    print(report)

    # Export report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(PROJECT_ROOT, 'data', f'dry_run_report_{timestamp}.json')
    export_report_json(policy_stats, dept_stats, results, report_path)

    print(f"\n📁 Report exported to: {report_path}")
    print("\n" + "=" * 70)
    print(f"  Dry-run complete. {changed}/{len(results)} records would change.")
    print("  Review the report, then run 'make migrate-execute' to apply.")
    print("=" * 70)


def cmd_execute(args):
    """Execute the migration."""
    print("\n⚠️  WARNING: This will modify the database!")
    print("=" * 70)

    # Show filters
    filters = []
    if args.start_date:
        filters.append(f"  Start date: {args.start_date}")
    if args.end_date:
        filters.append(f"  End date: {args.end_date}")
    if args.count:
        filters.append(f"  Max records: {args.count}")
    if args.prefix:
        filters.append(f"  Prefix: {args.prefix}")

    if filters:
        print("Filters applied:")
        for f in filters:
            print(f)
    else:
        print("No filters - will process ALL records")

    print("=" * 70)

    # Confirmation
    if not args.yes:
        response = input("\nProceed with migration? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Migration cancelled.")
            return

    print("\n🚀 Starting migration...")

    success, total, errors = run_execute(
        batch_size=args.batch_size,
        start_date=args.start_date,
        end_date=args.end_date,
        max_records=args.count,
        decision_key_prefix=args.prefix
    )

    print("\n" + "=" * 70)
    print(f"  Migration complete!")
    print(f"  Successfully updated: {success}/{total} records")
    if errors:
        print(f"  Errors: {len(errors)}")
        for err in errors[:5]:
            print(f"    - {err}")
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Tag Migration Script - Migrate old tags to new standardized values',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        '--count', '-n',
        type=int,
        default=None,
        help='Limit number of records to process'
    )
    common.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='Filter records from this date (YYYY-MM-DD)'
    )
    common.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='Filter records until this date (YYYY-MM-DD)'
    )
    common.add_argument(
        '--prefix',
        type=str,
        default=None,
        help='Filter by decision_key prefix (e.g., "37_")'
    )
    common.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    # Preview command
    preview_parser = subparsers.add_parser(
        'preview',
        parents=[common],
        help='Preview migration on sample records'
    )
    preview_parser.set_defaults(func=cmd_preview)
    preview_parser.set_defaults(count=10)  # Default for preview

    # Dry-run command
    dry_parser = subparsers.add_parser(
        'dry-run',
        parents=[common],
        help='Full dry-run (no database changes)'
    )
    dry_parser.set_defaults(func=cmd_dry_run)

    # Execute command
    exec_parser = subparsers.add_parser(
        'execute',
        parents=[common],
        help='Execute migration (modifies database)'
    )
    exec_parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=10,
        help='Number of records per batch (default: 10)'
    )
    exec_parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt'
    )
    exec_parser.set_defaults(func=cmd_execute)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure logs directory exists
    os.makedirs(os.path.join(PROJECT_ROOT, 'logs'), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, 'data'), exist_ok=True)

    # Setup logging
    setup_logging(args.verbose)

    # Run the command
    args.func(args)


if __name__ == '__main__':
    main()
