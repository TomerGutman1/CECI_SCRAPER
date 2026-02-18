#!/usr/bin/env python3
"""
Database Investigation Script - Comprehensive statistics analysis for data integrity issues.

Usage:
    python bin/investigate_db.py                   # Full statistics analysis
    python bin/investigate_db.py --government 29   # Focus on specific government
    python bin/investigate_db.py --sample 1000     # Analyze sample size
    python bin/investigate_db.py --export          # Export detailed results

This script analyzes:
- Total records count by government
- Missing titles breakdown
- Missing summaries
- Missing/short content
- Missing/malformed dates
- Pattern analysis for data quality issues
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def fetch_basic_statistics() -> Dict:
    """Fetch basic database statistics."""
    client = get_supabase_client()

    print("Fetching basic database statistics...")

    # Total count
    response = client.table("israeli_government_decisions").select("decision_key", count="exact").execute()
    total_count = response.count

    print(f"Total records: {total_count:,}")

    return {"total_records": total_count}


def fetch_records_by_government() -> Dict[int, int]:
    """Fetch record counts by government number."""
    client = get_supabase_client()

    print("Analyzing records by government...")

    records_by_gov = defaultdict(int)
    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select("government_number").range(offset, offset + chunk_size - 1)
        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            gov_num = record.get("government_number")
            if gov_num is not None:
                records_by_gov[gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    return dict(records_by_gov)


def analyze_missing_titles() -> Dict:
    """Analyze missing and problematic titles."""
    client = get_supabase_client()

    print("Analyzing missing/problematic titles...")

    title_analysis = {
        "null_titles": defaultdict(int),
        "empty_titles": defaultdict(int),
        "placeholder_titles": defaultdict(int),
        "total_by_government": defaultdict(int)
    }

    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_key, decision_title, government_number"
        ).range(offset, offset + chunk_size - 1)
        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            gov_num = record.get("government_number")
            title = record.get("decision_title")

            title_analysis["total_by_government"][gov_num] += 1

            if title is None:
                title_analysis["null_titles"][gov_num] += 1
            elif title.strip() == "":
                title_analysis["empty_titles"][gov_num] += 1
            elif title.strip() in ["ללא כותרת", "ללא כותרת.", "ללא כותרת:"]:
                title_analysis["placeholder_titles"][gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    return title_analysis


def analyze_missing_summaries() -> Dict:
    """Analyze missing summaries by government."""
    client = get_supabase_client()

    print("Analyzing missing summaries...")

    summary_analysis = {
        "null_summaries": defaultdict(int),
        "empty_summaries": defaultdict(int),
        "total_by_government": defaultdict(int)
    }

    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_key, summary, government_number"
        ).range(offset, offset + chunk_size - 1)
        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            gov_num = record.get("government_number")
            summary = record.get("summary")

            summary_analysis["total_by_government"][gov_num] += 1

            if summary is None:
                summary_analysis["null_summaries"][gov_num] += 1
            elif summary.strip() == "":
                summary_analysis["empty_summaries"][gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    return summary_analysis


def analyze_content_issues() -> Dict:
    """Analyze missing or short content by government."""
    client = get_supabase_client()

    print("Analyzing content issues...")

    content_analysis = {
        "null_content": defaultdict(int),
        "empty_content": defaultdict(int),
        "short_content": defaultdict(int),  # Less than 100 chars
        "cloudflare_content": defaultdict(int),
        "total_by_government": defaultdict(int)
    }

    offset = 0
    chunk_size = 1000
    cloudflare_patterns = ["Just a moment", "Cloudflare", "Verify you are human", "Ray ID:", "Please enable JavaScript"]

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_key, decision_content, government_number"
        ).range(offset, offset + chunk_size - 1)
        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            gov_num = record.get("government_number")
            content = record.get("decision_content")

            content_analysis["total_by_government"][gov_num] += 1

            if content is None:
                content_analysis["null_content"][gov_num] += 1
            elif content.strip() == "":
                content_analysis["empty_content"][gov_num] += 1
            elif len(content.strip()) < 100:
                content_analysis["short_content"][gov_num] += 1

            # Check for Cloudflare issues
            if content and any(pattern in content for pattern in cloudflare_patterns):
                content_analysis["cloudflare_content"][gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    return content_analysis


def analyze_date_issues() -> Dict:
    """Analyze missing or malformed dates by government."""
    client = get_supabase_client()

    print("Analyzing date issues...")

    date_analysis = {
        "null_dates": defaultdict(int),
        "malformed_dates": defaultdict(int),
        "future_dates": defaultdict(int),
        "very_old_dates": defaultdict(int),  # Before 1948
        "total_by_government": defaultdict(int)
    }

    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_key, decision_date, government_number"
        ).range(offset, offset + chunk_size - 1)
        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            gov_num = record.get("government_number")
            date_str = record.get("decision_date")

            date_analysis["total_by_government"][gov_num] += 1

            if date_str is None:
                date_analysis["null_dates"][gov_num] += 1
            else:
                try:
                    # Parse date
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

                    # Check for future dates
                    if date_obj > datetime.now().date():
                        date_analysis["future_dates"][gov_num] += 1

                    # Check for very old dates (before Israel's establishment)
                    if date_obj.year < 1948:
                        date_analysis["very_old_dates"][gov_num] += 1

                except ValueError:
                    date_analysis["malformed_dates"][gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    return date_analysis


def print_statistics_report(
    basic_stats: Dict,
    records_by_gov: Dict[int, int],
    title_analysis: Dict,
    summary_analysis: Dict,
    content_analysis: Dict,
    date_analysis: Dict
):
    """Print comprehensive statistics report."""

    print("\n" + "=" * 80)
    print("DATABASE INTEGRITY STATISTICS REPORT")
    print("=" * 80)

    # Basic statistics
    print(f"\n📊 BASIC STATISTICS")
    print(f"Total Records: {basic_stats['total_records']:,}")
    print(f"Governments Represented: {len(records_by_gov)}")

    # Records by government (top 10)
    print(f"\n🏛️  RECORDS BY GOVERNMENT (Top 10)")
    sorted_govs = sorted(records_by_gov.items(), key=lambda x: x[1], reverse=True)
    for gov_num, count in sorted_govs[:10]:
        percentage = (count / basic_stats['total_records']) * 100
        print(f"  Government {gov_num}: {count:,} records ({percentage:.1f}%)")

    # Title issues
    print(f"\n📝 TITLE ANALYSIS")
    total_title_issues = 0

    # Calculate total issues per government
    title_issues_by_gov = defaultdict(int)
    for issue_type in ["null_titles", "empty_titles", "placeholder_titles"]:
        for gov_num, count in title_analysis[issue_type].items():
            title_issues_by_gov[gov_num] += count
            total_title_issues += count

    print(f"Total title issues: {total_title_issues:,}")

    # Focus on problematic governments
    worst_title_govs = sorted(title_issues_by_gov.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\nWorst title issues by government:")
    for gov_num, issues in worst_title_govs:
        total_records = title_analysis["total_by_government"][gov_num]
        percentage = (issues / total_records) * 100 if total_records > 0 else 0
        print(f"  Government {gov_num}: {issues:,} issues / {total_records:,} total ({percentage:.1f}%)")

        # Breakdown
        null_count = title_analysis["null_titles"][gov_num]
        empty_count = title_analysis["empty_titles"][gov_num]
        placeholder_count = title_analysis["placeholder_titles"][gov_num]

        if null_count > 0:
            print(f"    - NULL titles: {null_count:,}")
        if empty_count > 0:
            print(f"    - Empty titles: {empty_count:,}")
        if placeholder_count > 0:
            print(f"    - 'ללא כותרת' titles: {placeholder_count:,}")

    # Summary issues
    print(f"\n📄 SUMMARY ANALYSIS")
    total_summary_issues = 0

    summary_issues_by_gov = defaultdict(int)
    for issue_type in ["null_summaries", "empty_summaries"]:
        for gov_num, count in summary_analysis[issue_type].items():
            summary_issues_by_gov[gov_num] += count
            total_summary_issues += count

    print(f"Total summary issues: {total_summary_issues:,}")

    worst_summary_govs = sorted(summary_issues_by_gov.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\nWorst summary issues by government:")
    for gov_num, issues in worst_summary_govs:
        total_records = summary_analysis["total_by_government"][gov_num]
        percentage = (issues / total_records) * 100 if total_records > 0 else 0
        print(f"  Government {gov_num}: {issues:,} issues / {total_records:,} total ({percentage:.1f}%)")

    # Content issues
    print(f"\n📖 CONTENT ANALYSIS")
    total_content_issues = 0

    content_issues_by_gov = defaultdict(int)
    for issue_type in ["null_content", "empty_content", "short_content"]:
        for gov_num, count in content_analysis[issue_type].items():
            content_issues_by_gov[gov_num] += count
            total_content_issues += count

    print(f"Total content issues: {total_content_issues:,}")

    # Cloudflare issues
    total_cloudflare = sum(content_analysis["cloudflare_content"].values())
    if total_cloudflare > 0:
        print(f"Cloudflare-affected records: {total_cloudflare:,}")

    worst_content_govs = sorted(content_issues_by_gov.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\nWorst content issues by government:")
    for gov_num, issues in worst_content_govs:
        total_records = content_analysis["total_by_government"][gov_num]
        percentage = (issues / total_records) * 100 if total_records > 0 else 0
        print(f"  Government {gov_num}: {issues:,} issues / {total_records:,} total ({percentage:.1f}%)")

    # Date issues
    print(f"\n📅 DATE ANALYSIS")
    total_date_issues = 0

    date_issues_by_gov = defaultdict(int)
    for issue_type in ["null_dates", "malformed_dates", "future_dates", "very_old_dates"]:
        for gov_num, count in date_analysis[issue_type].items():
            date_issues_by_gov[gov_num] += count
            total_date_issues += count

    print(f"Total date issues: {total_date_issues:,}")

    if total_date_issues > 0:
        worst_date_govs = sorted(date_issues_by_gov.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"\nWorst date issues by government:")
        for gov_num, issues in worst_date_govs:
            total_records = date_analysis["total_by_government"][gov_num]
            percentage = (issues / total_records) * 100 if total_records > 0 else 0
            print(f"  Government {gov_num}: {issues:,} issues / {total_records:,} total ({percentage:.1f}%)")

    # KEY INSIGHTS
    print(f"\n💡 KEY INSIGHTS")

    # Government 29 specific analysis
    if 29 in title_issues_by_gov:
        gov29_title_issues = title_issues_by_gov[29]
        gov29_total = title_analysis["total_by_government"][29]
        gov29_placeholder = title_analysis["placeholder_titles"][29]

        print(f"Government 29 Analysis:")
        print(f"  - Total records: {gov29_total:,}")
        print(f"  - Title issues: {gov29_title_issues:,}")
        print(f"  - 'ללא כותרת' titles: {gov29_placeholder:,}")

        if gov29_placeholder == 815:
            print(f"  ✅ Confirms the reported 815 'ללא כותרת' records in Government 29")
        else:
            print(f"  ❌ Expected 815 'ללא כותרת' but found {gov29_placeholder}")

    # Pattern analysis
    placeholder_govs = [(gov, count) for gov, count in title_analysis["placeholder_titles"].items() if count > 0]
    if len(placeholder_govs) > 1:
        print(f"\nGovernments with 'ללא כותרת' titles: {len(placeholder_govs)}")
        for gov_num, count in sorted(placeholder_govs, key=lambda x: x[1], reverse=True):
            print(f"  - Government {gov_num}: {count:,} records")

    # Overall severity assessment
    total_critical_issues = total_title_issues + total_summary_issues + total_content_issues
    critical_percentage = (total_critical_issues / basic_stats['total_records']) * 100

    print(f"\n🚨 SEVERITY ASSESSMENT")
    print(f"Total critical issues: {total_critical_issues:,} ({critical_percentage:.1f}% of all records)")

    if critical_percentage > 20:
        print("❌ HIGH SEVERITY: More than 20% of records have critical issues")
    elif critical_percentage > 10:
        print("⚠️  MEDIUM SEVERITY: 10-20% of records have issues")
    else:
        print("✅ LOW SEVERITY: Less than 10% of records have issues")


def export_detailed_results(
    basic_stats: Dict,
    records_by_gov: Dict[int, int],
    title_analysis: Dict,
    summary_analysis: Dict,
    content_analysis: Dict,
    date_analysis: Dict,
    output_file: str
):
    """Export detailed results to JSON file."""

    timestamp = datetime.now().isoformat()

    detailed_results = {
        "metadata": {
            "timestamp": timestamp,
            "analysis_type": "database_integrity_statistics",
            "total_records": basic_stats['total_records']
        },
        "basic_statistics": basic_stats,
        "records_by_government": records_by_gov,
        "title_analysis": {
            "null_titles": dict(title_analysis["null_titles"]),
            "empty_titles": dict(title_analysis["empty_titles"]),
            "placeholder_titles": dict(title_analysis["placeholder_titles"]),
            "total_by_government": dict(title_analysis["total_by_government"])
        },
        "summary_analysis": {
            "null_summaries": dict(summary_analysis["null_summaries"]),
            "empty_summaries": dict(summary_analysis["empty_summaries"]),
            "total_by_government": dict(summary_analysis["total_by_government"])
        },
        "content_analysis": {
            "null_content": dict(content_analysis["null_content"]),
            "empty_content": dict(content_analysis["empty_content"]),
            "short_content": dict(content_analysis["short_content"]),
            "cloudflare_content": dict(content_analysis["cloudflare_content"]),
            "total_by_government": dict(content_analysis["total_by_government"])
        },
        "date_analysis": {
            "null_dates": dict(date_analysis["null_dates"]),
            "malformed_dates": dict(date_analysis["malformed_dates"]),
            "future_dates": dict(date_analysis["future_dates"]),
            "very_old_dates": dict(date_analysis["very_old_dates"]),
            "total_by_government": dict(date_analysis["total_by_government"])
        }
    }

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detailed_results, f, ensure_ascii=False, indent=2)

    print(f"\n📁 Detailed results exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Database Investigation - Comprehensive statistics analysis for data integrity issues",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--government", type=int, help="Focus analysis on specific government number")
    parser.add_argument("--sample", type=int, help="Analyze only a sample of records")
    parser.add_argument("--export", action="store_true", help="Export detailed results to JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    setup_logging(args.verbose)

    print("🔍 DATABASE INTEGRITY INVESTIGATION")
    print("=" * 50)

    try:
        # Run comprehensive analysis
        basic_stats = fetch_basic_statistics()
        records_by_gov = fetch_records_by_government()
        title_analysis = analyze_missing_titles()
        summary_analysis = analyze_missing_summaries()
        content_analysis = analyze_content_issues()
        date_analysis = analyze_date_issues()

        # Print report
        print_statistics_report(
            basic_stats, records_by_gov, title_analysis,
            summary_analysis, content_analysis, date_analysis
        )

        # Export if requested
        if args.export:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(PROJECT_ROOT, 'data', 'qa_reports', f'phase1_statistics_{timestamp}.json')
            export_detailed_results(
                basic_stats, records_by_gov, title_analysis,
                summary_analysis, content_analysis, date_analysis, output_file
            )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise


if __name__ == "__main__":
    main()