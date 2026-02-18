#!/usr/bin/env python3
"""
Phase 2: Comprehensive Duplicate Detection Script

This script analyzes the Israeli government decisions database to identify various types of duplicates:
- Duplicate summaries (beyond the 22 pairs already reported)
- Duplicate content (decision_content field)
- Duplicate titles (excluding "ללא כותרת")
- Pattern analysis (sequential vs random duplicates)

Usage:
    python bin/detect_duplicates.py
    python bin/detect_duplicates.py --sample 1000  # Test on sample
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
class DuplicateGroup:
    """Group of duplicate records"""
    hash_value: str
    field_type: str  # 'summary', 'content', 'title'
    decision_keys: List[str]
    sample_value: str  # First 200 chars of the duplicated content
    government_numbers: List[int]
    decision_numbers: List[int]
    dates: List[str]

    @property
    def count(self) -> int:
        return len(self.decision_keys)

    @property
    def is_sequential(self) -> bool:
        """Check if decision numbers are sequential"""
        if len(self.decision_numbers) < 2:
            return False

        # Convert to integers and filter out None values
        valid_nums = []
        for num in self.decision_numbers:
            if num is not None:
                try:
                    valid_nums.append(int(num))
                except (ValueError, TypeError):
                    pass

        if len(valid_nums) < 2:
            return False

        sorted_nums = sorted(valid_nums)
        for i in range(1, len(sorted_nums)):
            if sorted_nums[i] != sorted_nums[i-1] + 1:
                return False
        return True

    @property
    def same_government(self) -> bool:
        """Check if all duplicates are from same government"""
        return len(set(self.government_numbers)) == 1

@dataclass
class DuplicateAnalysisReport:
    """Complete duplicate analysis report"""
    timestamp: str
    total_records_analyzed: int

    # Summary duplicates
    duplicate_summary_groups: List[DuplicateGroup]
    total_summary_duplicates: int
    summary_affected_records: int

    # Content duplicates
    duplicate_content_groups: List[DuplicateGroup]
    total_content_duplicates: int
    content_affected_records: int

    # Title duplicates
    duplicate_title_groups: List[DuplicateGroup]
    total_title_duplicates: int
    title_affected_records: int

    # Pattern analysis
    sequential_patterns: int
    cross_government_duplicates: int
    largest_duplicate_group: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "total_records_analyzed": self.total_records_analyzed,
            "summary": {
                "total_duplicate_groups": len(self.duplicate_summary_groups) + len(self.duplicate_content_groups) + len(self.duplicate_title_groups),
                "total_affected_records": self.summary_affected_records + self.content_affected_records + self.title_affected_records,
                "sequential_patterns": self.sequential_patterns,
                "cross_government_duplicates": self.cross_government_duplicates,
                "largest_duplicate_group": self.largest_duplicate_group
            },
            "duplicate_summaries": {
                "total_groups": len(self.duplicate_summary_groups),
                "total_duplicates": self.total_summary_duplicates,
                "affected_records": self.summary_affected_records,
                "groups": [
                    {
                        "hash": group.hash_value[:16],
                        "count": group.count,
                        "decision_keys": group.decision_keys,
                        "sample_value": group.sample_value,
                        "is_sequential": group.is_sequential,
                        "same_government": group.same_government,
                        "government_numbers": group.government_numbers,
                        "decision_numbers": group.decision_numbers,
                        "dates": group.dates
                    }
                    for group in self.duplicate_summary_groups
                ]
            },
            "duplicate_content": {
                "total_groups": len(self.duplicate_content_groups),
                "total_duplicates": self.total_content_duplicates,
                "affected_records": self.content_affected_records,
                "groups": [
                    {
                        "hash": group.hash_value[:16],
                        "count": group.count,
                        "decision_keys": group.decision_keys,
                        "sample_value": group.sample_value,
                        "is_sequential": group.is_sequential,
                        "same_government": group.same_government,
                        "government_numbers": group.government_numbers,
                        "decision_numbers": group.decision_numbers,
                        "dates": group.dates
                    }
                    for group in self.duplicate_content_groups
                ]
            },
            "duplicate_titles": {
                "total_groups": len(self.duplicate_title_groups),
                "total_duplicates": self.total_title_duplicates,
                "affected_records": self.title_affected_records,
                "groups": [
                    {
                        "hash": group.hash_value[:16],
                        "count": group.count,
                        "decision_keys": group.decision_keys,
                        "sample_value": group.sample_value,
                        "is_sequential": group.is_sequential,
                        "same_government": group.same_government,
                        "government_numbers": group.government_numbers,
                        "decision_numbers": group.decision_numbers,
                        "dates": group.dates
                    }
                    for group in self.duplicate_title_groups
                ]
            }
        }

def hash_text(text: str) -> str:
    """Create MD5 hash of text"""
    if not text:
        return ""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def fetch_all_records(limit: int = None) -> List[Dict]:
    """Fetch all records from database"""
    client = get_supabase_client()

    if limit:
        print(f"Fetching records from database (limit: {limit})...")
        query = client.table("israeli_government_decisions").select(
            "decision_key, decision_title, decision_content, summary, "
            "government_number, decision_number, decision_date"
        ).order("decision_date", desc=True).limit(limit)

        response = query.execute()
        if not response.data:
            print("❌ No records found")
            return []

        print(f"✅ Fetched {len(response.data)} records")
        return response.data

    else:
        print("Fetching ALL records from database (this may take a while)...")
        all_records = []
        batch_size = 1000
        offset = 0

        while True:
            query = client.table("israeli_government_decisions").select(
                "decision_key, decision_title, decision_content, summary, "
                "government_number, decision_number, decision_date"
            ).order("decision_date", desc=True).range(offset, offset + batch_size - 1)

            response = query.execute()

            if not response.data:
                break

            all_records.extend(response.data)
            print(f"  Fetched {len(response.data)} records (total: {len(all_records)})")

            if len(response.data) < batch_size:
                break

            offset += batch_size

        print(f"✅ Fetched {len(all_records)} total records")
        return all_records

def detect_duplicate_summaries(records: List[Dict]) -> Tuple[List[DuplicateGroup], int, int]:
    """Detect duplicate summaries"""
    print("🔍 Analyzing duplicate summaries...")

    summary_hashes = defaultdict(list)

    for record in records:
        summary = record.get('summary', '') or ''
        summary = summary.strip()
        if not summary or summary == "":
            continue

        hash_val = hash_text(summary)
        summary_hashes[hash_val].append(record)

    # Find duplicates (groups with more than 1 record)
    duplicate_groups = []
    total_duplicates = 0
    affected_records = 0

    for hash_val, group_records in summary_hashes.items():
        if len(group_records) > 1:
            group = DuplicateGroup(
                hash_value=hash_val,
                field_type='summary',
                decision_keys=[r['decision_key'] for r in group_records],
                sample_value=group_records[0]['summary'][:200],
                government_numbers=[r['government_number'] for r in group_records],
                decision_numbers=[r['decision_number'] for r in group_records],
                dates=[r['decision_date'] for r in group_records]
            )
            duplicate_groups.append(group)
            total_duplicates += len(group_records) - 1  # All but one are duplicates
            affected_records += len(group_records)

    print(f"  Found {len(duplicate_groups)} groups with duplicate summaries")
    print(f"  Total duplicate records: {total_duplicates}")
    print(f"  Total affected records: {affected_records}")

    return duplicate_groups, total_duplicates, affected_records

def detect_duplicate_content(records: List[Dict]) -> Tuple[List[DuplicateGroup], int, int]:
    """Detect duplicate content"""
    print("🔍 Analyzing duplicate content...")

    content_hashes = defaultdict(list)

    for record in records:
        content = record.get('decision_content', '') or ''
        content = content.strip()
        if not content or content == "" or content == "המשך התוכן...":
            continue

        hash_val = hash_text(content)
        content_hashes[hash_val].append(record)

    # Find duplicates
    duplicate_groups = []
    total_duplicates = 0
    affected_records = 0

    for hash_val, group_records in content_hashes.items():
        if len(group_records) > 1:
            group = DuplicateGroup(
                hash_value=hash_val,
                field_type='content',
                decision_keys=[r['decision_key'] for r in group_records],
                sample_value=group_records[0]['decision_content'][:200],
                government_numbers=[r['government_number'] for r in group_records],
                decision_numbers=[r['decision_number'] for r in group_records],
                dates=[r['decision_date'] for r in group_records]
            )
            duplicate_groups.append(group)
            total_duplicates += len(group_records) - 1
            affected_records += len(group_records)

    print(f"  Found {len(duplicate_groups)} groups with duplicate content")
    print(f"  Total duplicate records: {total_duplicates}")
    print(f"  Total affected records: {affected_records}")

    return duplicate_groups, total_duplicates, affected_records

def detect_duplicate_titles(records: List[Dict]) -> Tuple[List[DuplicateGroup], int, int]:
    """Detect duplicate titles (excluding 'ללא כותרת')"""
    print("🔍 Analyzing duplicate titles...")

    title_hashes = defaultdict(list)
    excluded_title = "ללא כותרת"

    for record in records:
        title = record.get('decision_title', '') or ''
        title = title.strip()
        if not title or title == "" or title == excluded_title:
            continue

        hash_val = hash_text(title)
        title_hashes[hash_val].append(record)

    # Find duplicates
    duplicate_groups = []
    total_duplicates = 0
    affected_records = 0

    for hash_val, group_records in title_hashes.items():
        if len(group_records) > 1:
            group = DuplicateGroup(
                hash_value=hash_val,
                field_type='title',
                decision_keys=[r['decision_key'] for r in group_records],
                sample_value=group_records[0]['decision_title'][:200],
                government_numbers=[r['government_number'] for r in group_records],
                decision_numbers=[r['decision_number'] for r in group_records],
                dates=[r['decision_date'] for r in group_records]
            )
            duplicate_groups.append(group)
            total_duplicates += len(group_records) - 1
            affected_records += len(group_records)

    print(f"  Found {len(duplicate_groups)} groups with duplicate titles")
    print(f"  Total duplicate records: {total_duplicates}")
    print(f"  Total affected records: {affected_records}")

    return duplicate_groups, total_duplicates, affected_records

def analyze_patterns(all_groups: List[DuplicateGroup]) -> Tuple[int, int, int]:
    """Analyze patterns in duplicate groups"""
    print("🔍 Analyzing duplicate patterns...")

    sequential_patterns = 0
    cross_government_duplicates = 0
    largest_group = 0

    for group in all_groups:
        if group.count > largest_group:
            largest_group = group.count

        if group.is_sequential:
            sequential_patterns += 1

        if not group.same_government:
            cross_government_duplicates += 1

    print(f"  Sequential patterns: {sequential_patterns}")
    print(f"  Cross-government duplicates: {cross_government_duplicates}")
    print(f"  Largest duplicate group: {largest_group}")

    return sequential_patterns, cross_government_duplicates, largest_group

def save_report(report: DuplicateAnalysisReport, output_file: str):
    """Save report to JSON file"""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"📊 Report saved to: {output_file}")

def print_summary(report: DuplicateAnalysisReport):
    """Print executive summary"""
    print("\n" + "="*60)
    print("PHASE 2 DUPLICATE ANALYSIS SUMMARY")
    print("="*60)
    print(f"Total records analyzed: {report.total_records_analyzed:,}")
    print(f"Analysis timestamp: {report.timestamp}")
    print()

    print("DUPLICATE SUMMARIES:")
    print(f"  Groups found: {len(report.duplicate_summary_groups)}")
    print(f"  Duplicate records: {report.total_summary_duplicates}")
    print(f"  Affected records: {report.summary_affected_records}")
    print()

    print("DUPLICATE CONTENT:")
    print(f"  Groups found: {len(report.duplicate_content_groups)}")
    print(f"  Duplicate records: {report.total_content_duplicates}")
    print(f"  Affected records: {report.content_affected_records}")
    print()

    print("DUPLICATE TITLES:")
    print(f"  Groups found: {len(report.duplicate_title_groups)}")
    print(f"  Duplicate records: {report.total_title_duplicates}")
    print(f"  Affected records: {report.title_affected_records}")
    print()

    print("PATTERN ANALYSIS:")
    print(f"  Sequential patterns: {report.sequential_patterns}")
    print(f"  Cross-government duplicates: {report.cross_government_duplicates}")
    print(f"  Largest duplicate group: {report.largest_duplicate_group}")
    print()

    total_affected = (report.summary_affected_records +
                     report.content_affected_records +
                     report.title_affected_records)

    print("KEY FINDINGS:")
    if len(report.duplicate_summary_groups) > 22:
        print(f"  ⚠️  Found MORE than the reported 22 duplicate summary pairs!")
        print(f"      Actual: {len(report.duplicate_summary_groups)} groups")
    else:
        print(f"  ✅ Found {len(report.duplicate_summary_groups)} duplicate summary groups (≤ 22 reported)")

    if report.content_affected_records > 0:
        print(f"  ⚠️  Found duplicates in CONTENT field: {report.content_affected_records} records")
    else:
        print("  ✅ No duplicate content found")

    if report.largest_duplicate_group > 2:
        print(f"  ⚠️  Found groups with 3+ duplicates: largest = {report.largest_duplicate_group}")
    else:
        print("  ✅ All duplicate groups are pairs (no 3+ groups)")

    if report.sequential_patterns > 0:
        print(f"  📈 {report.sequential_patterns} groups show sequential patterns")
    else:
        print("  📊 No sequential patterns detected (duplicates are random)")

    print(f"\nTOTAL AFFECTED RECORDS: {total_affected:,}")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description="Detect duplicates in Israeli government decisions")
    parser.add_argument("--sample", type=int, help="Analyze only N records for testing")
    args = parser.parse_args()

    print("Phase 2: Comprehensive Duplicate Detection")
    print("==========================================")

    # Fetch records
    records = fetch_all_records(limit=args.sample)
    if not records:
        return

    # Detect different types of duplicates
    summary_groups, summary_duplicates, summary_affected = detect_duplicate_summaries(records)
    content_groups, content_duplicates, content_affected = detect_duplicate_content(records)
    title_groups, title_duplicates, title_affected = detect_duplicate_titles(records)

    # Analyze patterns
    all_groups = summary_groups + content_groups + title_groups
    sequential_patterns, cross_gov_dups, largest_group = analyze_patterns(all_groups)

    # Create report
    report = DuplicateAnalysisReport(
        timestamp=datetime.now().isoformat(),
        total_records_analyzed=len(records),
        duplicate_summary_groups=summary_groups,
        total_summary_duplicates=summary_duplicates,
        summary_affected_records=summary_affected,
        duplicate_content_groups=content_groups,
        total_content_duplicates=content_duplicates,
        content_affected_records=content_affected,
        duplicate_title_groups=title_groups,
        total_title_duplicates=title_duplicates,
        title_affected_records=title_affected,
        sequential_patterns=sequential_patterns,
        cross_government_duplicates=cross_gov_dups,
        largest_duplicate_group=largest_group
    )

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"data/qa_reports/phase2_duplicates_{timestamp}.json"
    save_report(report, output_file)

    # Print summary
    print_summary(report)

if __name__ == "__main__":
    main()