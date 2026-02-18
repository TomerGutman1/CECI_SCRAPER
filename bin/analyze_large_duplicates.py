#!/usr/bin/env python3
"""
Analyze the largest duplicate groups to understand their characteristics.
This script provides detailed analysis of the duplicate detection findings.
"""

import os
import sys
import json

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.gov_scraper.db.connector import get_supabase_client

def analyze_decision_keys(decision_keys):
    """Analyze characteristics of decision keys"""
    normal_keys = []
    unusual_keys = []

    for key in decision_keys:
        if "_רהמ/" in key or any(c.isalpha() and ord(c) > 127 for c in key):
            unusual_keys.append(key)
        else:
            normal_keys.append(key)

    return normal_keys, unusual_keys

def get_records_by_keys(decision_keys):
    """Fetch full records by decision keys"""
    client = get_supabase_client()

    # Split into chunks of 100 to avoid query limits
    chunks = [decision_keys[i:i+100] for i in range(0, len(decision_keys), 100)]
    all_records = []

    for chunk in chunks:
        response = client.table("israeli_government_decisions").select("*").in_("decision_key", chunk).execute()
        if response.data:
            all_records.extend(response.data)

    return all_records

def main():
    print("Analyzing Large Duplicate Groups")
    print("================================")

    # Load the latest duplicate report
    reports_dir = "data/qa_reports"
    report_files = [f for f in os.listdir(reports_dir) if f.startswith("phase2_duplicates_")]

    if not report_files:
        print("❌ No duplicate reports found")
        return

    latest_report = sorted(report_files)[-1]
    report_path = os.path.join(reports_dir, latest_report)

    print(f"📊 Loading report: {latest_report}")

    with open(report_path, 'r', encoding='utf-8') as f:
        report_data = json.load(f)

    print(f"Report timestamp: {report_data['timestamp']}")
    print(f"Total records analyzed: {report_data['total_records_analyzed']:,}")
    print()

    # Find the largest groups for each category
    print("LARGEST DUPLICATE GROUPS:")
    print("="*50)

    for category in ['duplicate_titles', 'duplicate_content', 'duplicate_summaries']:
        if category in report_data and report_data[category]['groups']:
            groups = report_data[category]['groups']
            largest_group = max(groups, key=lambda x: x['count'])

            print(f"\n{category.upper().replace('_', ' ')}:")
            print(f"  Largest group size: {largest_group['count']} records")
            print(f"  Sample value: {largest_group['sample_value'][:100]}...")

            if largest_group['count'] > 10:
                print(f"  First 10 decision keys: {largest_group['decision_keys'][:10]}")

                # Analyze decision key patterns
                normal_keys, unusual_keys = analyze_decision_keys(largest_group['decision_keys'])
                print(f"  Normal keys: {len(normal_keys)}")
                print(f"  Unusual keys (Hebrew chars): {len(unusual_keys)}")

                if unusual_keys:
                    print(f"  Sample unusual keys: {unusual_keys[:5]}")

                # Check if this is a data quality issue
                if len(unusual_keys) > len(normal_keys):
                    print("  ⚠️  ISSUE: More unusual keys than normal - likely data quality problem")

                if largest_group['count'] > 100:
                    print("  🔍 Investigating records for this large group...")

                    # Get sample records to understand the issue
                    sample_keys = largest_group['decision_keys'][:5]
                    records = get_records_by_keys(sample_keys)

                    if records:
                        print(f"  Sample record analysis (first {len(records)} records):")
                        for i, record in enumerate(records):
                            print(f"    Record {i+1}:")
                            print(f"      Decision key: {record['decision_key']}")
                            print(f"      Government: {record.get('government_number')}")
                            print(f"      Decision number: {record.get('decision_number')}")
                            print(f"      Date: {record.get('decision_date')}")

                            if category == 'duplicate_titles':
                                print(f"      Title: {record.get('decision_title', '')[:100]}...")
                            elif category == 'duplicate_content':
                                print(f"      Content: {record.get('decision_content', '')[:100]}...")
                            elif category == 'duplicate_summaries':
                                print(f"      Summary: {record.get('summary', '')[:100]}...")
                            print()

    # Overall findings
    print("\nKEY FINDINGS:")
    print("="*50)

    total_affected = report_data['summary']['total_affected_records']
    total_analyzed = report_data['total_records_analyzed']

    print(f"1. Total affected records: {total_affected:,} ({total_affected/total_analyzed*100:.2f}% of database)")
    print(f"2. Largest duplicate group: {report_data['summary']['largest_duplicate_group']} records")
    print(f"3. Cross-government duplicates: {report_data['summary']['cross_government_duplicates']} groups")
    print(f"4. Sequential patterns: {report_data['summary']['sequential_patterns']} groups")

    print("\nRECOMMENDations:")
    print("="*50)

    if report_data['duplicate_summaries']['total_groups'] > 22:
        print("❌ Found MORE duplicate summary groups than the 22 pairs reported")
    else:
        print("✅ Duplicate summary groups within expected range")

    if report_data['duplicate_content']['affected_records'] > 0:
        print(f"⚠️  Content duplicates found: investigate {report_data['duplicate_content']['affected_records']} records")

    if report_data['summary']['largest_duplicate_group'] > 100:
        print("🚨 Extremely large duplicate group detected - likely systematic data issue")
        print("   → Investigate decision keys with Hebrew characters ('רהמ/')")
        print("   → Check for data import/migration issues")
        print("   → May need manual cleanup of malformed records")

    if report_data['summary']['cross_government_duplicates'] > 100:
        print(f"⚠️  Many cross-government duplicates: {report_data['summary']['cross_government_duplicates']} groups")
        print("   → May indicate copy-paste of standard language across governments")

    print(f"\n📁 Detailed report available at: {report_path}")

if __name__ == "__main__":
    main()