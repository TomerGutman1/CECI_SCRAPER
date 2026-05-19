#!/usr/bin/env python3
"""
Audit: Compare manifest decision_keys against DB decision_keys.

Finds decisions that were "dropped" — present in the manifest but missing from DB.
Classifies each dropped key by likely reason (invalid format, number mismatch, etc.).

Usage:
    python bin/audit_manifest_vs_db.py
"""

import json
import os
import re
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.db.connector import get_supabase_client


def load_manifest(path="data/catalog_manifest.json"):
    """Load manifest and return list of entries."""
    manifest_path = os.path.join(os.path.dirname(__file__), '..', path)
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fetch_all_db_keys():
    """Fetch all decision_keys from DB, paginated."""
    client = get_supabase_client()
    db_keys = set()
    offset = 0
    page_size = 1000

    while True:
        response = (
            client.table("israeli_government_decisions")
            .select("decision_key")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not response.data:
            break
        db_keys.update(r["decision_key"] for r in response.data)
        if len(response.data) < page_size:
            break
        offset += page_size

    return db_keys


def is_valid_key_format(key):
    """Check if key matches the DB-accepted format."""
    if re.match(r'^\d+_\d+$', key):
        return True
    if re.match(r'^\d+_(COMMITTEE|SECURITY|ECON|SPECIAL)_\d+$', key):
        return True
    return False


def extract_number_from_description(desc):
    """Extract decision number from description text like 'החלטה מספר 1021 של'."""
    m = re.search(r'החלטה מספר\s+(\d+)\s+של', desc or '')
    return m.group(1) if m else None


def extract_number_from_url(url):
    """Extract decision number from URL like dec1021_2022."""
    m = re.search(r'dec(\d+)', url or '')
    return m.group(1) if m else None


def classify_dropped_key(entry):
    """Classify why a manifest entry was likely dropped."""
    key = entry.get('decision_key', '')
    dec_num = entry.get('decision_number', '')
    desc = entry.get('description', '')
    url = entry.get('url', '')

    reasons = []

    # 1. Invalid key format (Hebrew, dates, special chars)
    if not is_valid_key_format(key):
        reasons.append('invalid_format')

    # 2. Description says different number
    desc_num = extract_number_from_description(desc)
    if desc_num and desc_num != dec_num:
        reasons.append('description_mismatch')

    # 3. URL says different number
    url_num = extract_number_from_url(url)
    if url_num and url_num != dec_num:
        reasons.append('url_mismatch')

    return reasons if reasons else ['unknown']


def main():
    print("=" * 70)
    print("MANIFEST vs DB — Decision Key Audit")
    print("=" * 70)

    # Step 1: Load manifest
    print("\n[1/4] Loading manifest...")
    manifest = load_manifest()
    manifest_keys = {e["decision_key"] for e in manifest}
    manifest_by_key = {e["decision_key"]: e for e in manifest}
    print(f"  Manifest entries: {len(manifest)}")
    print(f"  Unique keys:     {len(manifest_keys)}")

    # Step 2: Fetch DB keys
    print("\n[2/4] Fetching all decision_keys from DB...")
    db_keys = fetch_all_db_keys()
    print(f"  DB records: {len(db_keys)}")

    # Step 3: Compute diffs
    print("\n[3/4] Computing diffs...")
    manifest_only = manifest_keys - db_keys
    db_only = db_keys - manifest_keys
    in_both = manifest_keys & db_keys

    print(f"  In both:         {len(in_both)}")
    print(f"  Manifest only:   {len(manifest_only)} (dropped)")
    print(f"  DB only:         {len(db_only)} (not in manifest)")

    # Step 4: Classify dropped keys
    print("\n[4/4] Classifying dropped keys...")
    dropped_details = []
    reason_counts = {}

    for key in sorted(manifest_only):
        entry = manifest_by_key.get(key, {})
        reasons = classify_dropped_key(entry)

        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1

        desc_num = extract_number_from_description(entry.get('description', ''))
        url_num = extract_number_from_url(entry.get('url', ''))

        dropped_details.append({
            'decision_key': key,
            'reasons': reasons,
            'government_number': entry.get('government_number'),
            'decision_number': entry.get('decision_number'),
            'description_number': desc_num,
            'url_number': url_num,
            'url': entry.get('url'),
            'title': entry.get('title'),
            'description': entry.get('description'),
        })

    # Report
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print(f"\nDropped keys (manifest only): {len(manifest_only)}")
    print(f"DB-only keys (not in manifest): {len(db_only)}")

    if reason_counts:
        print("\nDrop reason breakdown:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count}")

    if dropped_details:
        print(f"\n--- Dropped keys detail ({len(dropped_details)}) ---\n")
        for d in dropped_details:
            reasons_str = ', '.join(d['reasons'])
            print(f"  {d['decision_key']}")
            print(f"    Reasons: {reasons_str}")
            if d.get('description_number'):
                print(f"    Description says: {d['description_number']} (catalog says: {d['decision_number']})")
            if d.get('url_number') and d['url_number'] != d.get('decision_number'):
                print(f"    URL says: {d['url_number']}")
            print(f"    Title: {(d.get('title') or '')[:80]}")
            print(f"    URL: {d.get('url')}")
            print()

    if db_only:
        print(f"\n--- DB-only keys ({len(db_only)}) ---")
        print("  These exist in DB but NOT in manifest:")
        for key in sorted(db_only):
            print(f"  {key}")

    # Save JSON report
    report = {
        'timestamp': datetime.now().isoformat(),
        'manifest_count': len(manifest),
        'db_count': len(db_keys),
        'in_both': len(in_both),
        'manifest_only_count': len(manifest_only),
        'db_only_count': len(db_only),
        'reason_breakdown': reason_counts,
        'dropped_details': dropped_details,
        'db_only_keys': sorted(db_only),
    }

    report_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'qa_reports')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f'manifest_vs_db_audit_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nFull report saved to: {report_path}")


if __name__ == '__main__':
    main()
