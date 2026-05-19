#!/usr/bin/env python3
"""Analyze and categorize URL mismatches from integrity audit."""

import sys
import os
import re
import csv
from collections import defaultdict, Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gov_scraper.db.connector import get_supabase_client

FIELDS = "id, decision_key, decision_number, decision_url, decision_title, government_number, decision_date"


def fetch_all_records():
    client = get_supabase_client()
    all_records = []
    offset = 0
    chunk_size = 1000
    while True:
        response = (
            client.table("israeli_government_decisions")
            .select(FIELDS)
            .order("id")
            .range(offset, offset + chunk_size - 1)
            .execute()
        )
        if not response.data:
            break
        all_records.extend(response.data)
        offset += chunk_size
        if len(response.data) < chunk_size:
            break
    return all_records


def extract_number_from_url(url):
    if not url:
        return None
    patterns = [
        r'/pages/\d+_des(\d+)',
        r'/pages/dec(\d+)',
        r'/pages/\d+_dec(\d+)',
        r'/pages/des(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def clean_decision_number(dn):
    if not dn:
        return None
    cleaned = dn.strip().rstrip(".")
    cleaned = re.sub(r'\(.*\)$', '', cleaned).strip()
    return cleaned


def categorize_mismatch(dn, url_num):
    """Categorize the type of URL mismatch."""
    try:
        dn_int = int(clean_decision_number(dn))
        url_int = int(url_num)
    except (ValueError, TypeError):
        return "non-numeric"

    diff = abs(url_int - dn_int)

    # Date suffix appended to URL number (e.g., 3571120608 = 3571 + date 12/06/08)
    url_str = str(url_int)
    dn_str = str(dn_int)
    if url_str.startswith(dn_str) and len(url_str) > len(dn_str) + 3:
        return "date-suffix-appended"

    # Year suffix (e.g., 4162023 = 416 + 2023)
    if url_str.endswith("2023") or url_str.endswith("2024") or url_str.endswith("2025"):
        stripped = url_str[:-4]
        if stripped == dn_str:
            return "year-suffix-appended"

    # Off by one
    if diff == 1:
        return "off-by-one"

    # Small transposition / typo (diff < 100)
    if diff < 100:
        return "small-digit-error"

    # Large offset (timestamp-like suffix)
    if diff > 1000000:
        return "timestamp-suffix"

    # Digit swap or transposition
    if sorted(dn_str) == sorted(url_str):
        return "digit-transposition"

    # Completely different number
    return f"large-mismatch (diff={diff})"


def main():
    print("Fetching records...")
    records = fetch_all_records()
    print(f"Total records: {len(records)}\n")

    mismatches = []
    for r in records:
        url = r.get("decision_url") or ""
        dn = r.get("decision_number") or ""
        if not url or not dn:
            continue
        url_num = extract_number_from_url(url)
        if url_num is None:
            continue
        clean_dn = clean_decision_number(dn)
        if not clean_dn:
            continue
        try:
            if int(url_num) != int(clean_dn):
                category = categorize_mismatch(dn, url_num)
                mismatches.append({
                    "id": r["id"],
                    "gov": r["government_number"],
                    "dn": dn,
                    "url_num": url_num,
                    "category": category,
                    "title": (r.get("decision_title") or "")[:70],
                    "url": url,
                })
        except ValueError:
            pass

    # Summary by category
    cat_counts = Counter(m["category"] for m in mismatches)
    print("=" * 70)
    print("URL Mismatch Categories")
    print("=" * 70)
    for cat, count in cat_counts.most_common():
        print(f"  {cat:<30} {count:>4}")
    print(f"  {'TOTAL':<30} {len(mismatches):>4}")

    # Summary by government
    gov_counts = Counter(m["gov"] for m in mismatches)
    print(f"\nBy Government:")
    for gov in sorted(gov_counts.keys()):
        print(f"  Gov {gov}: {gov_counts[gov]} mismatches")

    # Detail by category
    for cat, count in cat_counts.most_common():
        print(f"\n--- {cat} ({count}) ---")
        cat_items = [m for m in mismatches if m["category"] == cat]
        for m in cat_items[:10]:
            print(f"  id={m['id']} gov={m['gov']} dn={m['dn']} url_num={m['url_num']} | {m['title']}")
        if len(cat_items) > 10:
            print(f"  ... and {len(cat_items) - 10} more")

    # Which ones were in the report vs new
    report_ids = {
        62154, 65453, 70782, 69870, 70406, 71163, 71200, 71269, 71681,
        71933, 72605, 74106, 74962, 75487, 76653, 75713, 75857, 76364,
        # Gov 37 additions from extended report
        77480, 78114, 78145, 78180, 78534, 78628, 78732, 79161, 79438,
        79599, 79633, 79650, 79684, 79770, 79778, 79980, 80182,
    }

    new_findings = [m for m in mismatches if m["id"] not in report_ids]
    confirmed = [m for m in mismatches if m["id"] in report_ids]

    print(f"\n{'=' * 70}")
    print(f"Report Comparison")
    print(f"{'=' * 70}")
    print(f"  Confirmed from report:  {len(confirmed)}")
    print(f"  NEW findings:           {len(new_findings)}")

    # New findings by category
    new_cats = Counter(m["category"] for m in new_findings)
    print(f"\nNew findings by category:")
    for cat, count in new_cats.most_common():
        print(f"  {cat:<30} {count:>4}")

    print(f"\nNew findings detail:")
    for m in new_findings:
        print(f"  id={m['id']} gov={m['gov']} dn={m['dn']} url={m['url_num']} cat={m['category']} | {m['title']}")


if __name__ == "__main__":
    main()
