#!/usr/bin/env python3
"""
DB Integrity Audit — Verify data integrity issues in israeli_government_decisions.

Checks 6 issue types:
1. URL mismatches (decision_number vs number in URL)
2. Duplicate decision_number + government_number pairs
3. Corrupted decision_number (text in number field)
4. Parenthetical suffixes in decision_number
5. Extra spaces in decision_number
6. Trailing dots in decision_number

Usage:
    python bin/audit_integrity.py
    python bin/audit_integrity.py --csv data/integrity_audit.csv
"""

import sys
import os
import re
import csv
import logging
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gov_scraper.db.connector import get_supabase_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FIELDS = "id, decision_key, decision_number, decision_url, decision_title, government_number, decision_date"


def fetch_all_records():
    """Fetch all records with pagination (1000/chunk)."""
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

    logger.info(f"Fetched {len(all_records)} records total")
    return all_records


def extract_number_from_url(url):
    """Extract the decision number from a gov.il decision URL."""
    if not url:
        return None

    # Pattern: /pages/{gov}_des{num} or /pages/dec{num}-{year} etc.
    # Common patterns:
    #   https://www.gov.il/he/pages/34_des1234
    #   https://www.gov.il/he/pages/dec1234-2023
    #   https://www.gov.il/he/pages/34_des01234
    patterns = [
        r'/pages/\d+_des(\d+)',           # {gov}_des{num}
        r'/pages/dec(\d+)',                # dec{num} or dec{num}-{year}
        r'/pages/\d+_dec(\d+)',            # {gov}_dec{num}
        r'/pages/des(\d+)',                # des{num}
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def clean_decision_number(dn):
    """Strip a decision_number to its core numeric value for comparison."""
    if not dn:
        return None
    # Remove spaces, dots, parenthetical suffixes
    cleaned = dn.strip().rstrip(".")
    # Remove parenthetical suffix
    cleaned = re.sub(r'\(.*\)$', '', cleaned).strip()
    return cleaned


def check_url_mismatches(records):
    """Check 1: URL number doesn't match decision_number."""
    issues = []
    for r in records:
        url = r.get("decision_url") or ""
        dn = r.get("decision_number") or ""
        if not url or not dn:
            continue

        url_num = extract_number_from_url(url)
        if url_num is None:
            continue

        # Clean decision_number for comparison
        clean_dn = clean_decision_number(dn)
        if not clean_dn:
            continue

        # Compare: strip leading zeros for numeric comparison
        try:
            url_int = int(url_num)
            dn_int = int(clean_dn)
            if url_int != dn_int:
                issues.append({
                    "issue_type": "אי-התאמת URL",
                    "original_id": r["id"],
                    "government_number": r["government_number"],
                    "decision_number": dn,
                    "field_with_error": "decision_url",
                    "current_value": url_num,
                    "proposed_value": clean_dn,
                    "title": (r.get("decision_title") or "")[:80],
                })
        except ValueError:
            # Non-numeric decision_number (e.g., "גבל/14") — skip URL check
            pass

    return issues


def check_duplicates(records):
    """Check 2: Same decision_number + government_number appearing multiple times."""
    groups = defaultdict(list)
    for r in records:
        dn = r.get("decision_number") or ""
        gov = r.get("government_number")
        if dn and gov:
            groups[(gov, dn)].append(r)

    issues = []
    for (gov, dn), recs in groups.items():
        if len(recs) > 1:
            ids = [str(rec["id"]) for rec in recs]
            titles = [((rec.get("decision_title") or "")[:60]) for rec in recs]
            for rec in recs:
                issues.append({
                    "issue_type": "כפילות",
                    "original_id": rec["id"],
                    "government_number": gov,
                    "decision_number": dn,
                    "field_with_error": "decision_number+government_number",
                    "current_value": f"dup_ids={','.join(ids)}",
                    "proposed_value": "לבדוק ולמחוק כפילות",
                    "title": (rec.get("decision_title") or "")[:80],
                })

    return issues


def check_corrupted_number(records):
    """Check 3: decision_number contains long text (>20 chars)."""
    issues = []
    for r in records:
        dn = r.get("decision_number") or ""
        if len(dn) > 20:
            # Try to extract the real number
            match = re.match(r'^(\d+)', dn)
            proposed = match.group(1) if match else "?"
            issues.append({
                "issue_type": "שדה מושחת",
                "original_id": r["id"],
                "government_number": r["government_number"],
                "decision_number": dn[:50] + "..." if len(dn) > 50 else dn,
                "field_with_error": "decision_number",
                "current_value": f"len={len(dn)}",
                "proposed_value": proposed,
                "title": (r.get("decision_title") or "")[:80],
            })
    return issues


def check_parenthetical_suffix(records):
    """Check 4: decision_number contains parenthetical suffix like '5181(קבר/24)'."""
    issues = []
    for r in records:
        dn = r.get("decision_number") or ""
        if "(" in dn:
            match = re.match(r'^(\d+)', dn)
            proposed = match.group(1) if match else dn.split("(")[0].strip()
            issues.append({
                "issue_type": "סיומת בסוגריים",
                "original_id": r["id"],
                "government_number": r["government_number"],
                "decision_number": dn,
                "field_with_error": "decision_number",
                "current_value": dn,
                "proposed_value": proposed,
                "title": (r.get("decision_title") or "")[:80],
            })
    return issues


def check_extra_spaces(records):
    """Check 5: decision_number has leading or trailing spaces."""
    issues = []
    for r in records:
        dn = r.get("decision_number") or ""
        if dn and (dn != dn.strip()):
            issues.append({
                "issue_type": "רווחים מיותרים",
                "original_id": r["id"],
                "government_number": r["government_number"],
                "decision_number": repr(dn),
                "field_with_error": "decision_number",
                "current_value": repr(dn),
                "proposed_value": dn.strip(),
                "title": (r.get("decision_title") or "")[:80],
            })
    return issues


def check_trailing_dots(records):
    """Check 6: decision_number ends with a dot."""
    issues = []
    for r in records:
        dn = r.get("decision_number") or ""
        dn_stripped = dn.strip()
        if dn_stripped and dn_stripped.endswith("."):
            issues.append({
                "issue_type": "נקודה מיותרת",
                "original_id": r["id"],
                "government_number": r["government_number"],
                "decision_number": dn,
                "field_with_error": "decision_number",
                "current_value": dn,
                "proposed_value": dn_stripped.rstrip("."),
                "title": (r.get("decision_title") or "")[:80],
            })
    return issues


def export_csv(all_issues, path):
    """Export issues to CSV."""
    fieldnames = [
        "issue_type", "original_id", "government_number", "decision_number",
        "field_with_error", "current_value", "proposed_value", "title"
    ]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for issue in all_issues:
            writer.writerow(issue)
    logger.info(f"Exported {len(all_issues)} issues to {path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DB Integrity Audit")
    parser.add_argument("--csv", default="data/integrity_audit_results.csv",
                        help="Output CSV path")
    args = parser.parse_args()

    print("=" * 60)
    print("  DB Integrity Audit — israeli_government_decisions")
    print("=" * 60)
    print()

    # Fetch all records
    print("Fetching all records...")
    records = fetch_all_records()
    print(f"Total records: {len(records)}")
    print()

    # Run all checks
    checks = [
        ("1. URL mismatches", check_url_mismatches),
        ("2. Duplicates (dn+gov)", check_duplicates),
        ("3. Corrupted decision_number", check_corrupted_number),
        ("4. Parenthetical suffix", check_parenthetical_suffix),
        ("5. Extra spaces", check_extra_spaces),
        ("6. Trailing dots", check_trailing_dots),
    ]

    all_issues = []
    print(f"{'Check':<35} {'Found':>8} {'Reported':>10}")
    print("-" * 55)

    reported_counts = {
        "1. URL mismatches": 33,
        "2. Duplicates (dn+gov)": "32 pairs",
        "3. Corrupted decision_number": 1,
        "4. Parenthetical suffix": 10,
        "5. Extra spaces": 8,
        "6. Trailing dots": 3,
    }

    for name, check_fn in checks:
        issues = check_fn(records)
        all_issues.extend(issues)
        reported = reported_counts.get(name, "?")
        print(f"  {name:<33} {len(issues):>6}   (reported: {reported})")

    print("-" * 55)
    print(f"  {'TOTAL':<33} {len(all_issues):>6}   (reported: 87)")
    print()

    # Print details for each category
    for name, check_fn in checks:
        category_issues = [i for i in all_issues if True]  # we'll filter below
        pass

    # Show sample issues per category
    categories = defaultdict(list)
    for issue in all_issues:
        categories[issue["issue_type"]].append(issue)

    for cat, cat_issues in categories.items():
        print(f"\n--- {cat} ({len(cat_issues)} issues) ---")
        for issue in cat_issues[:5]:
            print(f"  id={issue['original_id']} gov={issue['government_number']} "
                  f"dn={issue['decision_number']} "
                  f"| {issue['current_value']} -> {issue['proposed_value']}")
        if len(cat_issues) > 5:
            print(f"  ... and {len(cat_issues) - 5} more")

    # Export CSV
    export_csv(all_issues, args.csv)
    print(f"\nCSV exported to: {args.csv}")


if __name__ == "__main__":
    main()
