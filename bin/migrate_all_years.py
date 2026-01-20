#!/usr/bin/env python3
"""
Year-by-Year Migration Script

Runs tag migration for each year from 2024 back to 1993,
generating individual reports for each year and a final summary.

Usage:
    python bin/migrate_all_years.py                    # All years (2024-1993)
    python bin/migrate_all_years.py --start-year 2020  # From 2020 back
    python bin/migrate_all_years.py --end-year 2000    # Stop at 2000
    python bin/migrate_all_years.py --dry-run          # Preview only

Options:
    --start-year YYYY    Start from this year (default: 2024)
    --end-year YYYY      End at this year (default: 1993)
    --dry-run            Don't modify database, just generate reports
    --verbose            Enable verbose logging
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple
import time

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.processors.tag_migration import (
    run_dry_run,
    run_execute,
    MappingStats
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(PROJECT_ROOT, 'logs', 'migration_all_years.log'),
                encoding='utf-8'
            )
        ]
    )


def ensure_reports_directory():
    """Create reports directory if it doesn't exist."""
    reports_dir = os.path.join(PROJECT_ROOT, 'data', 'migration_reports')
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir


def stats_to_dict(stats: MappingStats) -> Dict:
    """Convert MappingStats to dictionary."""
    return {
        "exact": stats.exact,
        "substring": stats.substring,
        "word_overlap": stats.word_overlap,
        "ai_tag": stats.ai_tag,
        "ai_summary": stats.ai_summary,
        "fallback": stats.fallback,
        "fallback_records": stats.fallback_records[:20]  # Limit to first 20
    }


def save_yearly_report(
    year: int,
    total_records: int,
    updated_records: int,
    policy_stats: MappingStats,
    dept_stats: MappingStats,
    execution_time: float,
    reports_dir: str
) -> str:
    """
    Save a yearly migration report.

    Returns:
        Path to the saved report file
    """
    report = {
        "year": year,
        "timestamp": datetime.now().isoformat(),
        "total_records": total_records,
        "records_updated": updated_records,
        "records_unchanged": total_records - updated_records,
        "update_rate_percent": round((updated_records / total_records * 100), 1) if total_records > 0 else 0,
        "execution_time_seconds": round(execution_time, 1),
        "stats": {
            "policy_area": stats_to_dict(policy_stats),
            "government_body": stats_to_dict(dept_stats)
        }
    }

    filepath = os.path.join(reports_dir, f"{year}_migration_report.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return filepath


def generate_summary_report(all_years_stats: Dict, reports_dir: str) -> str:
    """
    Generate a summary report across all years.

    Returns:
        Path to the saved summary file
    """
    total_records = sum(s['total_records'] for s in all_years_stats.values())
    total_updated = sum(s['records_updated'] for s in all_years_stats.values())
    total_time = sum(s['execution_time'] for s in all_years_stats.values())

    # Aggregate stats
    policy_totals = {
        "exact": 0, "substring": 0, "word_overlap": 0,
        "ai_tag": 0, "ai_summary": 0, "fallback": 0
    }
    dept_totals = {
        "exact": 0, "substring": 0, "word_overlap": 0,
        "ai_tag": 0, "ai_summary": 0, "fallback": 0
    }

    for year_stats in all_years_stats.values():
        for key in policy_totals:
            policy_totals[key] += year_stats['policy_stats'].get(key, 0)
            dept_totals[key] += year_stats['dept_stats'].get(key, 0)

    # Calculate percentages
    policy_total = sum(policy_totals.values())
    dept_total = sum(dept_totals.values())

    summary = {
        "migration_completed": datetime.now().isoformat(),
        "total_records": total_records,
        "total_updated": total_updated,
        "total_unchanged": total_records - total_updated,
        "update_rate_percent": round((total_updated / total_records * 100), 1) if total_records > 0 else 0,
        "years_processed": len(all_years_stats),
        "total_execution_time_seconds": round(total_time, 1),
        "total_execution_time_formatted": f"{int(total_time // 3600)}h {int((total_time % 3600) // 60)}m",
        "by_year": {
            year: {
                "records": stats['total_records'],
                "updated": stats['records_updated'],
                "fallbacks_policy": stats['policy_stats'].get('fallback', 0),
                "fallbacks_dept": stats['dept_stats'].get('fallback', 0)
            }
            for year, stats in sorted(all_years_stats.items(), reverse=True)
        },
        "overall_stats": {
            "policy_area": {
                "exact": policy_totals["exact"],
                "exact_percent": round(policy_totals["exact"] / policy_total * 100, 1) if policy_total > 0 else 0,
                "substring": policy_totals["substring"],
                "word_overlap": policy_totals["word_overlap"],
                "ai_tag": policy_totals["ai_tag"],
                "ai_percent": round((policy_totals["ai_tag"] + policy_totals["ai_summary"]) / policy_total * 100, 1) if policy_total > 0 else 0,
                "ai_summary": policy_totals["ai_summary"],
                "fallback": policy_totals["fallback"],
                "fallback_percent": round(policy_totals["fallback"] / policy_total * 100, 1) if policy_total > 0 else 0
            },
            "government_body": {
                "exact": dept_totals["exact"],
                "exact_percent": round(dept_totals["exact"] / dept_total * 100, 1) if dept_total > 0 else 0,
                "substring": dept_totals["substring"],
                "word_overlap": dept_totals["word_overlap"],
                "ai_tag": dept_totals["ai_tag"],
                "ai_percent": round((dept_totals["ai_tag"] + dept_totals["ai_summary"]) / dept_total * 100, 1) if dept_total > 0 else 0,
                "ai_summary": dept_totals["ai_summary"],
                "fallback": dept_totals["fallback"],
                "fallback_percent": round(dept_totals["fallback"] / dept_total * 100, 1) if dept_total > 0 else 0
            }
        }
    }

    filepath = os.path.join(reports_dir, "summary_all_years.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return filepath


def print_year_summary(year: int, total: int, updated: int, policy_stats: MappingStats, dept_stats: MappingStats, elapsed: float):
    """Print a summary for a completed year."""
    print(f"\n{'─' * 60}")
    print(f"  Year {year} Complete")
    print(f"{'─' * 60}")
    print(f"  Records: {total} | Updated: {updated} ({updated/total*100:.1f}%)" if total > 0 else "  No records")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Policy Area  - Exact: {policy_stats.exact}, AI: {policy_stats.ai_tag + policy_stats.ai_summary}, Fallback: {policy_stats.fallback}")
    print(f"  Departments  - Exact: {dept_stats.exact}, AI: {dept_stats.ai_tag + dept_stats.ai_summary}, Fallback: {dept_stats.fallback}")
    print(f"{'─' * 60}")


def migrate_year(year: int, dry_run: bool = False) -> Tuple[int, int, MappingStats, MappingStats, float]:
    """
    Run migration for a single year.

    Returns:
        Tuple of (total_records, updated_records, policy_stats, dept_stats, execution_time)
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    start_time = time.time()

    if dry_run:
        mappings, policy_stats, dept_stats = run_dry_run(
            start_date=start_date,
            end_date=end_date,
            max_records=None
        )
        total = len(mappings)
        updated = sum(
            1 for m in mappings
            if m.get('old_policy') != m.get('new_policy') or
               m.get('old_dept') != m.get('new_dept')
        )
    else:
        # Run execute returns (success_count, total_attempted, errors)
        success, attempted, errors = run_execute(
            start_date=start_date,
            end_date=end_date,
            max_records=None,
            batch_size=10
        )
        # For execute, we need to get stats separately
        # The stats are printed during execute, but we need them for the report
        # Re-run dry-run just to get stats (this is inefficient but ensures accuracy)
        mappings, policy_stats, dept_stats = run_dry_run(
            start_date=start_date,
            end_date=end_date,
            max_records=None
        )
        total = len(mappings)
        updated = success

    elapsed = time.time() - start_time

    return total, updated, policy_stats, dept_stats, elapsed


def main():
    parser = argparse.ArgumentParser(
        description='Year-by-Year Tag Migration Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--start-year',
        type=int,
        default=2024,
        help='Start from this year (default: 2024)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        default=1993,
        help='End at this year (default: 1993)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Don't modify database, just generate reports"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt'
    )

    args = parser.parse_args()

    # Validate years
    if args.start_year < args.end_year:
        print(f"Error: start-year ({args.start_year}) must be >= end-year ({args.end_year})")
        sys.exit(1)

    # Setup
    os.makedirs(os.path.join(PROJECT_ROOT, 'logs'), exist_ok=True)
    setup_logging(args.verbose)
    reports_dir = ensure_reports_directory()

    # Generate list of years
    years = list(range(args.start_year, args.end_year - 1, -1))

    print("\n" + "=" * 70)
    print("  Year-by-Year Tag Migration")
    print("=" * 70)
    print(f"  Years: {args.start_year} → {args.end_year} ({len(years)} years)")
    print(f"  Mode: {'DRY-RUN (no DB changes)' if args.dry_run else 'EXECUTE (will modify DB)'}")
    print(f"  Reports: {reports_dir}")
    print("=" * 70)

    if not args.dry_run and not args.yes:
        response = input("\nProceed with migration? This will modify the database. [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Migration cancelled.")
            return

    # Track all stats
    all_years_stats = {}
    total_start_time = time.time()

    for i, year in enumerate(years, 1):
        print(f"\n{'=' * 70}")
        print(f"  Processing Year {year} ({i}/{len(years)})")
        print(f"{'=' * 70}")

        try:
            total, updated, policy_stats, dept_stats, elapsed = migrate_year(year, args.dry_run)

            # Save yearly report
            report_path = save_yearly_report(
                year, total, updated, policy_stats, dept_stats, elapsed, reports_dir
            )

            # Store for summary
            all_years_stats[year] = {
                'total_records': total,
                'records_updated': updated,
                'execution_time': elapsed,
                'policy_stats': stats_to_dict(policy_stats),
                'dept_stats': stats_to_dict(dept_stats)
            }

            print_year_summary(year, total, updated, policy_stats, dept_stats, elapsed)
            print(f"  Report saved: {os.path.basename(report_path)}")

        except Exception as e:
            logging.error(f"Error processing year {year}: {e}")
            print(f"\n  ERROR: Failed to process year {year}: {e}")
            print("  Continuing to next year...")
            continue

    # Generate summary report
    print("\n" + "=" * 70)
    print("  Generating Summary Report")
    print("=" * 70)

    summary_path = generate_summary_report(all_years_stats, reports_dir)
    total_elapsed = time.time() - total_start_time

    # Print final summary
    total_records = sum(s['total_records'] for s in all_years_stats.values())
    total_updated = sum(s['records_updated'] for s in all_years_stats.values())

    print(f"\n{'=' * 70}")
    print("  MIGRATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Years processed: {len(all_years_stats)}")
    print(f"  Total records: {total_records:,}")
    print(f"  Total updated: {total_updated:,} ({total_updated/total_records*100:.1f}%)" if total_records > 0 else "")
    print(f"  Total time: {int(total_elapsed // 3600)}h {int((total_elapsed % 3600) // 60)}m {int(total_elapsed % 60)}s")
    print(f"\n  Summary report: {summary_path}")
    print(f"  Individual reports: {reports_dir}/[YEAR]_migration_report.json")
    print(f"{'=' * 70}\n")


if __name__ == '__main__':
    main()
