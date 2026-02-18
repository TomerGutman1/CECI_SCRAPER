#!/usr/bin/env python3
"""
Agent 3: Comprehensive Duplicate Titles Analysis

Analyzes all 4,467 records with duplicate titles to prepare for efficient scraping.
Creates detailed categorization and priority list for scraping strategy.

Context:
- 675 records have identical title "נסיעות שרים" (Ministers' travels)
- Total of 1,161 duplicate title groups
- Need to distinguish real duplicates from data entry errors

Usage:
    python bin/analyze_duplicate_titles.py
    python bin/analyze_duplicate_titles.py --limit 1000  # Test on sample
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass, asdict

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.gov_scraper.db.connector import get_supabase_client

@dataclass
class DuplicateTitleGroup:
    """Enhanced duplicate title group with analysis"""
    title: str
    title_hash: str
    decision_keys: List[str]
    count: int
    government_numbers: List[str]
    decision_numbers: List[str]
    dates: List[str]
    urls: List[str]
    content_lengths: List[int]

    # Analysis fields
    is_sequential: bool
    same_government: bool
    date_spread_days: int
    likely_error: bool
    error_pattern: str  # 'systematic_error', 'sequential_batch', 'legitimate_repeat', 'suspicious'
    priority: str  # 'HIGH', 'MEDIUM', 'LOW'
    confidence_score: float  # 0-1, how confident we are this is an error

@dataclass
class DuplicateTitleAnalysis:
    """Complete analysis result"""
    timestamp: str
    total_records_analyzed: int
    total_duplicate_groups: int
    total_affected_records: int
    duplicate_groups: List[DuplicateTitleGroup]

    # Summary statistics
    high_priority_groups: int
    medium_priority_groups: int
    low_priority_groups: int

    # Pattern statistics
    systematic_errors: int
    sequential_batches: int
    legitimate_repeats: int
    suspicious_patterns: int

    # Top problematic titles
    largest_groups: List[Dict]
    most_suspicious: List[Dict]

def calculate_hash(text: str) -> str:
    """Calculate hash for text content"""
    if not text:
        return ""
    return hashlib.md5(text.strip().encode('utf-8')).hexdigest()[:16]

def fetch_all_records_and_find_duplicates(client, limit=None) -> List[Dict]:
    """Fetch all records and identify those with duplicate titles"""
    print("🔍 Fetching all records from database...")

    all_records = []
    page_size = 1000
    page = 0

    while True:
        print(f"  Fetching page {page + 1} (records {page * page_size + 1}-{(page + 1) * page_size})...")

        response = (
            client.table("israeli_government_decisions")
            .select("decision_key,decision_title,government_number,decision_number,decision_date,decision_url,decision_content")
            .neq("decision_title", None)
            .neq("decision_title", "")
            .neq("decision_title", "ללא כותרת")
            .range(page * page_size, (page + 1) * page_size - 1)
            .order("decision_date", desc=True)
            .execute()
        )

        if not response.data:
            break

        all_records.extend(response.data)
        page += 1

        # Break if we got less than a full page (end of data)
        if len(response.data) < page_size:
            break

        # Optional progress update
        if page % 10 == 0:
            print(f"  Fetched {len(all_records)} records so far...")

    print(f"📥 Fetched {len(all_records)} total records from database")

    # Find titles that appear more than once
    print("🔍 Identifying duplicate titles...")
    title_counts = defaultdict(list)

    for record in all_records:
        title = record.get('decision_title', '')
        if title and title != 'ללא כותרת':
            title_counts[title].append(record)

    # Filter to only duplicates
    duplicate_titles = {title: records for title, records in title_counts.items()
                       if len(records) > 1}

    # Sort by count descending and optionally limit
    sorted_duplicate_titles = sorted(duplicate_titles.items(),
                                   key=lambda x: len(x[1]), reverse=True)

    if limit:
        sorted_duplicate_titles = sorted_duplicate_titles[:limit]

    print(f"📊 Found {len(sorted_duplicate_titles)} titles with duplicates")

    if sorted_duplicate_titles:
        largest_title, largest_group = sorted_duplicate_titles[0]
        print(f"📊 Largest group: '{largest_title}' with {len(largest_group)} records")

    # Flatten back to list of records
    duplicate_records = []
    for title, records in sorted_duplicate_titles:
        duplicate_records.extend(records)

    print(f"✅ Total duplicate title records: {len(duplicate_records)}")
    return duplicate_records

def analyze_duplicate_group(title: str, records: List[Dict]) -> DuplicateTitleGroup:
    """Analyze a single group of duplicate titles"""

    # Basic data extraction
    decision_keys = [r.get('decision_key', '') for r in records]
    government_numbers = [str(r.get('government_number', '')) for r in records]
    decision_numbers = [str(r.get('decision_number', '')) for r in records]
    dates = [r.get('decision_date', '') for r in records]
    urls = [r.get('decision_url', '') for r in records]
    content_lengths = [len(r.get('decision_content', '') or '') for r in records]

    # Pattern analysis
    is_sequential = analyze_sequential_pattern(decision_numbers)
    same_government = len(set(government_numbers)) == 1
    date_spread_days = calculate_date_spread(dates)

    # Error detection logic
    likely_error, error_pattern, confidence_score = detect_error_pattern(
        title, records, is_sequential, same_government, date_spread_days
    )

    # Priority assignment
    priority = assign_priority(likely_error, len(records), confidence_score, error_pattern)

    return DuplicateTitleGroup(
        title=title,
        title_hash=calculate_hash(title),
        decision_keys=decision_keys,
        count=len(records),
        government_numbers=government_numbers,
        decision_numbers=decision_numbers,
        dates=dates,
        urls=urls,
        content_lengths=content_lengths,
        is_sequential=is_sequential,
        same_government=same_government,
        date_spread_days=date_spread_days,
        likely_error=likely_error,
        error_pattern=error_pattern,
        priority=priority,
        confidence_score=confidence_score
    )

def analyze_sequential_pattern(decision_numbers: List[str]) -> bool:
    """Check if decision numbers are sequential"""
    if len(decision_numbers) < 2:
        return False

    try:
        nums = [int(n) for n in decision_numbers if n.isdigit()]
        if len(nums) < 2:
            return False

        nums.sort()
        for i in range(1, len(nums)):
            if nums[i] - nums[i-1] != 1:
                return False
        return True
    except:
        return False

def calculate_date_spread(dates: List[str]) -> int:
    """Calculate spread of dates in days"""
    try:
        valid_dates = [datetime.fromisoformat(d) for d in dates if d]
        if len(valid_dates) < 2:
            return 0
        return (max(valid_dates) - min(valid_dates)).days
    except:
        return 0

def detect_error_pattern(title: str, records: List[Dict], is_sequential: bool,
                        same_government: bool, date_spread_days: int) -> Tuple[bool, str, float]:
    """Detect if this is likely an error and classify the pattern"""

    count = len(records)

    # Known problematic titles (from context)
    if title == "נסיעות שרים":
        return True, "systematic_error", 0.99

    # Very large groups are suspicious
    if count >= 50:
        return True, "systematic_error", 0.95

    # Sequential decisions on same day with identical content
    if (is_sequential and same_government and date_spread_days <= 1 and
        count >= 3):
        # Check if content is also identical
        contents = [r.get('decision_content', '') for r in records]
        if len(set(contents)) <= 1:  # All same content or empty
            return True, "sequential_batch", 0.9

    # Many duplicates with very short content
    avg_content_length = sum(len(r.get('decision_content', '') or '') for r in records) / count
    if count >= 10 and avg_content_length < 100:
        return True, "systematic_error", 0.85

    # Legitimate patterns
    routine_titles = [
        "הארכת", "הארכת גיוס", "מינוי", "נסיעת", "יישום הסכמים",
        "תיקון החלטת", "הכרזה על", "העברת סמכות"
    ]

    if any(pattern in title for pattern in routine_titles):
        if count <= 10 and date_spread_days > 30:
            return False, "legitimate_repeat", 0.2

    # Medium suspicion patterns
    if count >= 5 and same_government and date_spread_days <= 7:
        return True, "suspicious", 0.6

    if count >= 8:
        return True, "suspicious", 0.7

    # Default: likely legitimate
    return False, "legitimate_repeat", 0.3

def assign_priority(likely_error: bool, count: int, confidence_score: float,
                   error_pattern: str) -> str:
    """Assign scraping priority"""

    if likely_error and confidence_score >= 0.9:
        return "HIGH"

    if likely_error and confidence_score >= 0.6:
        return "HIGH" if count >= 10 else "MEDIUM"

    if count >= 20:  # Large groups always get attention
        return "MEDIUM"

    if likely_error:
        return "MEDIUM"

    return "LOW"

def generate_scraping_lists(groups: List[DuplicateTitleGroup]) -> Dict:
    """Generate prioritized lists for scraping"""

    high_priority = []
    medium_priority = []
    low_priority = []

    for group in groups:
        target_list = {
            "HIGH": high_priority,
            "MEDIUM": medium_priority,
            "LOW": low_priority
        }[group.priority]

        for decision_key in group.decision_keys:
            target_list.append({
                "decision_key": decision_key,
                "title": group.title,
                "priority": group.priority,
                "error_pattern": group.error_pattern,
                "confidence": group.confidence_score,
                "group_size": group.count
            })

    return {
        "high_priority": high_priority,
        "medium_priority": medium_priority,
        "low_priority": low_priority,
        "total_to_scrape": len(high_priority) + len(medium_priority) + len(low_priority)
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze duplicate titles for scraping strategy')
    parser.add_argument('--limit', type=int, help='Limit number of duplicate title groups to analyze')
    parser.add_argument('--output', default='data/qa_reports/duplicate_titles_analysis.json',
                       help='Output file path')
    args = parser.parse_args()

    print("🚀 Starting comprehensive duplicate titles analysis...")
    print("="*60)

    # Connect to database
    client = get_supabase_client()

    # Fetch duplicate records
    records = fetch_all_records_and_find_duplicates(client, args.limit)

    if not records:
        print("❌ No duplicate titles found")
        return

    # Group by title
    print("📊 Grouping records by title...")
    title_groups = defaultdict(list)
    for record in records:
        title = record.get('decision_title', '')
        if title and title != 'ללא כותרת':
            title_groups[title].append(record)

    print(f"✅ Found {len(title_groups)} unique titles with duplicates")

    # Analyze each group
    print("🔬 Analyzing duplicate patterns...")
    analyzed_groups = []

    for title, title_records in title_groups.items():
        if len(title_records) > 1:  # Only actual duplicates
            group = analyze_duplicate_group(title, title_records)
            analyzed_groups.append(group)

            if len(analyzed_groups) % 50 == 0:
                print(f"  Analyzed {len(analyzed_groups)} groups...")

    # Sort by priority and count
    analyzed_groups.sort(key=lambda g: (g.priority == "LOW", g.priority == "MEDIUM", -g.count))

    # Generate statistics
    total_affected_records = sum(g.count for g in analyzed_groups)
    priority_counts = Counter(g.priority for g in analyzed_groups)
    pattern_counts = Counter(g.error_pattern for g in analyzed_groups)

    # Generate scraping lists
    scraping_lists = generate_scraping_lists(analyzed_groups)

    # Create analysis result
    analysis = DuplicateTitleAnalysis(
        timestamp=datetime.now().isoformat(),
        total_records_analyzed=len(records),
        total_duplicate_groups=len(analyzed_groups),
        total_affected_records=total_affected_records,
        duplicate_groups=analyzed_groups,
        high_priority_groups=priority_counts.get("HIGH", 0),
        medium_priority_groups=priority_counts.get("MEDIUM", 0),
        low_priority_groups=priority_counts.get("LOW", 0),
        systematic_errors=pattern_counts.get("systematic_error", 0),
        sequential_batches=pattern_counts.get("sequential_batch", 0),
        legitimate_repeats=pattern_counts.get("legitimate_repeat", 0),
        suspicious_patterns=pattern_counts.get("suspicious", 0),
        largest_groups=[
            {
                "title": g.title,
                "count": g.count,
                "priority": g.priority,
                "error_pattern": g.error_pattern,
                "confidence": g.confidence_score
            }
            for g in sorted(analyzed_groups, key=lambda x: -x.count)[:10]
        ],
        most_suspicious=[
            {
                "title": g.title,
                "count": g.count,
                "priority": g.priority,
                "error_pattern": g.error_pattern,
                "confidence": g.confidence_score
            }
            for g in sorted(analyzed_groups, key=lambda x: -x.confidence_score)[:10]
        ]
    )

    # Prepare output
    output_data = {
        "analysis": asdict(analysis),
        "scraping_list": scraping_lists
    }

    # Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Print summary
    print("="*60)
    print("📋 DUPLICATE TITLES ANALYSIS SUMMARY")
    print("="*60)
    print(f"📊 Total records analyzed: {len(records):,}")
    print(f"📊 Duplicate title groups: {len(analyzed_groups):,}")
    print(f"📊 Total affected records: {total_affected_records:,}")
    print()
    print("🎯 PRIORITY DISTRIBUTION:")
    print(f"   HIGH:   {priority_counts.get('HIGH', 0):,} groups")
    print(f"   MEDIUM: {priority_counts.get('MEDIUM', 0):,} groups")
    print(f"   LOW:    {priority_counts.get('LOW', 0):,} groups")
    print()
    print("🔍 ERROR PATTERNS:")
    for pattern, count in pattern_counts.items():
        print(f"   {pattern}: {count:,} groups")
    print()
    print("📦 SCRAPING LISTS:")
    print(f"   High priority:   {len(scraping_lists['high_priority']):,} records")
    print(f"   Medium priority: {len(scraping_lists['medium_priority']):,} records")
    print(f"   Low priority:    {len(scraping_lists['low_priority']):,} records")
    print(f"   Total to scrape: {scraping_lists['total_to_scrape']:,} records")
    print()
    print("🔥 TOP PROBLEMATIC TITLES:")
    for i, group in enumerate(analysis.largest_groups[:5], 1):
        print(f"   {i}. '{group['title'][:50]}...' - {group['count']} records - {group['priority']} priority")

    print(f"\n✅ Analysis saved to: {args.output}")
    print("\n🚀 Ready for efficient scraping strategy!")

if __name__ == "__main__":
    main()