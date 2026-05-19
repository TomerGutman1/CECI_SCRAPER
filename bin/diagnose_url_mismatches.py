#!/usr/bin/env python3
"""
Diagnose and fix URL mismatches in israeli_government_decisions.

For each of the 101 mismatched URLs:
1. Build candidate "correct" slugs based on government-era URL patterns
2. Test each candidate via Content Page API (fast, no Cloudflare)
3. Also test if current URL still works
4. Classify: easy_fix / keep_as_is / unfixable

Usage:
    python bin/diagnose_url_mismatches.py                    # Diagnose only
    python bin/diagnose_url_mismatches.py --fix              # Dry-run fixes
    python bin/diagnose_url_mismatches.py --fix --execute    # Apply fixes
"""

import sys
import os
import re
import csv
import time
import logging
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gov_scraper.db.connector import get_supabase_client

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Migrated 2026-05-11: gov.il moved ContentPageWebApi to openapi-gc gateway.
# Callers must set x-client-id header (see scrapers/catalog.py for canonical session factory).
CONTENT_PAGE_API_BASE = (
    "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/contentpage/v1/api/content-pages"
)
GOVIL_CLIENT_ID = "9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc"
BASE_URL = "https://www.gov.il/he/departments/policies/pages"


def fetch_all_records():
    client = get_supabase_client()
    all_records = []
    offset = 0
    while True:
        response = (
            client.table("israeli_government_decisions")
            .select("id, decision_url, government_number, decision_number, decision_date, decision_key")
            .order("id")
            .range(offset, offset + 999)
            .execute()
        )
        if not response.data:
            break
        all_records.extend(response.data)
        offset += 1000
        if len(response.data) < 1000:
            break
    return all_records


def extract_number_from_url(url):
    if not url:
        return None
    for pattern in [r'/pages/\d+_des(\d+)', r'/pages/dec(\d+)', r'/pages/\d+_dec(\d+)', r'/pages/des(\d+)']:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def clean_dn(dn):
    if not dn:
        return None
    cleaned = dn.strip().rstrip(".")
    cleaned = re.sub(r'\(.*\)$', '', cleaned).strip()
    return cleaned


def extract_slug(url):
    match = re.search(r'/pages/(.+?)(?:\?|$)', url)
    return match.group(1) if match else ""


def classify_slug(slug):
    """Classify URL slug pattern and extract components."""
    # {year}_des{num}{suffix} -- Gov 30-34
    m = re.match(r'^(\d{4})_des(\d+)(.*)$', slug)
    if m:
        return "year_des", {"year": m.group(1), "num": m.group(2), "suffix": m.group(3)}

    # {year}_dec{num}{suffix} -- Gov 30-34
    m = re.match(r'^(\d{4})_dec(\d+)(.*)$', slug)
    if m:
        return "year_dec", {"year": m.group(1), "num": m.group(2), "suffix": m.group(3)}

    # {year}_desr{num} -- special
    m = re.match(r'^(\d{4})_desr(\d+)(.*)$', slug)
    if m:
        return "year_desr", {"year": m.group(1), "num": m.group(2), "suffix": m.group(3)}

    # dec{num}-{year}{suffix} -- Gov 37
    m = re.match(r'^dec(\d+)-(\d{4})(.*)$', slug)
    if m:
        return "dec_num_hyp_year", {"num": m.group(1), "year": m.group(2), "suffix": m.group(3)}

    # dec-{num}-{year} -- Gov 37
    m = re.match(r'^dec-(\d+)-(\d{4})(.*)$', slug)
    if m:
        return "dec_hyp_num_hyp_year", {"num": m.group(1), "year": m.group(2), "suffix": m.group(3)}

    # dec{num}_{year}{suffix} -- Gov 34-36
    m = re.match(r'^dec(\d+)_(\d{4})(.*)$', slug)
    if m:
        return "dec_num_usc_year", {"num": m.group(1), "year": m.group(2), "suffix": m.group(3)}

    # des{num}_{year} -- Gov 29-30
    m = re.match(r'^des(\d+)_(\d{4})(.*)$', slug)
    if m:
        return "des_num_usc_year", {"year": m.group(2), "num": m.group(1), "suffix": ""}

    # dec{num}{year} (missing separator, e.g., dec3472023) -- broken Gov 37
    m = re.match(r'^dec(\d+?)(20\d{2})$', slug)
    if m:
        return "dec_num_nohyp_year", {"num": m.group(1), "year": m.group(2), "suffix": ""}

    # dec{num}-{extra}-{year} (extra segment, e.g., dec2686-7-2025)
    m = re.match(r'^dec(\d+)-\d+-(\d{4})(.*)$', slug)
    if m:
        return "dec_num_extra_year", {"num": m.group(1), "year": m.group(2), "suffix": m.group(3)}

    # {DDmmmYYYY}{num} -- Gov 25-29
    m = re.match(r'^(\d{2}\w{3}\d{4})(\d+)(.*)$', slug)
    if m:
        return "date_num", {"date_prefix": m.group(1), "num": m.group(2), "suffix": m.group(3)}

    # {year}-{mmm}{num} -- Gov 29-30
    m = re.match(r'^(\d{4})-(\w{3})(\d+)(.*)$', slug)
    if m:
        return "year_mmm_num", {"year": m.group(1), "month": m.group(2), "num": m.group(3), "suffix": m.group(4)}

    return "unknown", {"raw": slug}


def build_candidates(slug, pat_type, pat_parts, correct_num, gov, decision_date):
    """Build candidate corrected slugs for a mismatch."""
    year = decision_date[:4] if decision_date else ""
    candidates = []

    # 1. In-place fix: same pattern, correct number
    if pat_type == "year_des":
        candidates.append(f"{pat_parts['year']}_des{correct_num}")
    elif pat_type == "year_dec":
        candidates.append(f"{pat_parts['year']}_dec{correct_num}")
    elif pat_type == "year_desr":
        candidates.append(f"{pat_parts['year']}_desr{correct_num}")
    elif pat_type == "dec_num_hyp_year":
        candidates.append(f"dec{correct_num}-{pat_parts['year']}")
    elif pat_type == "dec_hyp_num_hyp_year":
        candidates.append(f"dec-{correct_num}-{pat_parts['year']}")
        candidates.append(f"dec{correct_num}-{pat_parts['year']}")
    elif pat_type == "dec_num_usc_year":
        candidates.append(f"dec{correct_num}_{pat_parts['year']}")
    elif pat_type == "des_num_usc_year":
        # Reversed format — try the dominant pattern for this gov
        candidates.append(f"{pat_parts['year']}_des{correct_num}")
        candidates.append(f"des{correct_num}_{pat_parts['year']}")
    elif pat_type == "dec_num_nohyp_year":
        # Missing hyphen — add it
        candidates.append(f"dec{correct_num}-{pat_parts['year']}")
    elif pat_type == "dec_num_extra_year":
        # Extra segment — remove it
        candidates.append(f"dec{correct_num}-{pat_parts['year']}")
    elif pat_type == "date_num":
        candidates.append(f"{pat_parts['date_prefix']}{correct_num}")
    elif pat_type == "year_mmm_num":
        candidates.append(f"{pat_parts['year']}-{pat_parts['month']}{correct_num}")

    # 2. Government-dominant alternatives
    if year:
        if gov in [30, 31, 32]:
            _add_unique(candidates, f"{year}_des{correct_num}")
        elif gov == 33:
            _add_unique(candidates, f"{year}_dec{correct_num}")
            _add_unique(candidates, f"{year}_des{correct_num}")
        elif gov == 34:
            _add_unique(candidates, f"dec{correct_num}_{year}")
            _add_unique(candidates, f"{year}_dec{correct_num}")
            _add_unique(candidates, f"{year}_des{correct_num}")
        elif gov in [35, 36]:
            _add_unique(candidates, f"dec{correct_num}_{year}")
        elif gov == 37:
            _add_unique(candidates, f"dec{correct_num}-{year}")
            _add_unique(candidates, f"dec-{correct_num}-{year}")

    # 3. Universal fallbacks
    if year:
        _add_unique(candidates, f"dec{correct_num}-{year}")
        _add_unique(candidates, f"dec{correct_num}_{year}")
    _add_unique(candidates, f"dec{correct_num}")

    return candidates


def _add_unique(lst, item):
    if item not in lst:
        lst.append(item)


def test_slug(session, slug):
    """Test if a slug resolves via Content Page API. Returns status code."""
    api_url = f"{CONTENT_PAGE_API_BASE}/{slug}?culture=he"
    try:
        resp = session.get(api_url, timeout=15)
        return resp.status_code
    except Exception:
        return -1


def find_mismatches(records):
    mismatches = []
    for r in records:
        url = r.get("decision_url") or ""
        dn = r.get("decision_number") or ""
        if not url or not dn:
            continue
        url_num = extract_number_from_url(url)
        if url_num is None:
            continue
        cdn = clean_dn(dn)
        if not cdn:
            continue
        try:
            if int(url_num) != int(cdn):
                mismatches.append(r)
        except ValueError:
            pass
    return mismatches


def main():
    parser = argparse.ArgumentParser(description="Diagnose URL mismatches")
    parser.add_argument("--fix", action="store_true", help="Show fix plan")
    parser.add_argument("--execute", action="store_true", help="Apply fixes (requires --fix)")
    args = parser.parse_args()

    print("=" * 70)
    print("  URL Mismatch Diagnosis")
    print("=" * 70)

    # Fetch and find mismatches
    print("Fetching records...")
    records = fetch_all_records()
    print(f"Total records: {len(records)}")

    mismatches = find_mismatches(records)
    print(f"URL mismatches: {len(mismatches)}")
    print()

    # Set up API session with x-client-id (required by openapi-gc gateway)
    from curl_cffi import requests as curl_requests
    session = curl_requests.Session(impersonate="safari")
    session.headers.update({
        "x-client-id": GOVIL_CLIENT_ID,
        "Origin": "https://www.gov.il",
    })

    # Diagnose each mismatch
    results = []
    easy_fix = []
    keep_as_is = []
    unfixable = []

    for i, r in enumerate(mismatches):
        url = r["decision_url"]
        dn = r["decision_number"]
        cdn = clean_dn(dn)
        gov = r["government_number"]
        date = r.get("decision_date") or ""
        slug = extract_slug(url)
        pat_type, pat_parts = classify_slug(slug)

        candidates = build_candidates(slug, pat_type, pat_parts, cdn, gov, date)

        # Test current URL
        time.sleep(0.1)
        current_status = test_slug(session, slug)

        # Test candidates
        best_candidate = None
        best_status = None
        for cand in candidates:
            time.sleep(0.1)
            status = test_slug(session, cand)
            if status == 200:
                best_candidate = cand
                best_status = 200
                break

        # Classify
        if best_candidate and best_status == 200:
            category = "easy_fix"
            new_url = f"https://www.gov.il/he/departments/policies/pages/{best_candidate}"
            easy_fix.append({
                "id": r["id"], "gov": gov, "dn": cdn,
                "old_url": url, "old_slug": slug,
                "new_slug": best_candidate, "new_url": new_url,
                "current_status": current_status,
                "pat_type": pat_type,
            })
        elif current_status == 200:
            category = "keep_as_is"
            keep_as_is.append({
                "id": r["id"], "gov": gov, "dn": cdn,
                "slug": slug, "current_status": current_status,
                "candidates_tried": len(candidates),
                "pat_type": pat_type,
            })
        else:
            category = "unfixable"
            unfixable.append({
                "id": r["id"], "gov": gov, "dn": cdn,
                "slug": slug, "current_status": current_status,
                "candidates_tried": len(candidates),
                "pat_type": pat_type,
            })

        status_icon = {"easy_fix": "+", "keep_as_is": "~", "unfixable": "X"}[category]
        print(f"  [{status_icon}] {i+1:>3}/{len(mismatches)} id={r['id']} gov={gov} dn={cdn:<6} "
              f"cur={current_status} | {category}"
              f"{f' -> {best_candidate}' if best_candidate else ''}")

    # Summary
    print()
    print("=" * 70)
    print(f"  Summary")
    print("=" * 70)
    print(f"  Easy fix (candidate URL works):    {len(easy_fix):>4}")
    print(f"  Keep as-is (current URL works):    {len(keep_as_is):>4}")
    print(f"  Unfixable (nothing works):         {len(unfixable):>4}")
    print(f"  Total:                             {len(mismatches):>4}")

    # Export CSV
    csv_path = "data/url_diagnosis.csv"
    os.makedirs("data", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "id", "gov", "dn", "pat_type", "old_slug", "new_slug",
                          "current_status", "old_url", "new_url"])
        for item in easy_fix:
            writer.writerow(["easy_fix", item["id"], item["gov"], item["dn"], item["pat_type"],
                              item["old_slug"], item["new_slug"], item["current_status"],
                              item["old_url"], item["new_url"]])
        for item in keep_as_is:
            writer.writerow(["keep_as_is", item["id"], item["gov"], item["dn"], item["pat_type"],
                              item["slug"], "", item["current_status"], "", ""])
        for item in unfixable:
            writer.writerow(["unfixable", item["id"], item["gov"], item["dn"], item["pat_type"],
                              item["slug"], "", item["current_status"], "", ""])
    print(f"\n  CSV exported to: {csv_path}")

    # Fix mode
    if args.fix and easy_fix:
        print()
        print("=" * 70)
        print(f"  {'APPLYING' if args.execute else 'DRY RUN'}: {len(easy_fix)} URL fixes")
        print("=" * 70)

        client = get_supabase_client()
        success = 0
        failed = 0

        for item in easy_fix:
            print(f"  {'FIX' if args.execute else 'WOULD FIX'} id={item['id']} gov={item['gov']} dn={item['dn']}")
            print(f"    old: {item['old_slug']}")
            print(f"    new: {item['new_slug']}")

            if args.execute:
                try:
                    client.table("israeli_government_decisions").update(
                        {"decision_url": item["new_url"]}
                    ).eq("id", item["id"]).execute()
                    success += 1
                    print(f"    -> OK")
                except Exception as e:
                    failed += 1
                    print(f"    -> FAILED: {e}")

        if args.execute:
            print(f"\n  Results: {success} fixed, {failed} failed")
        else:
            print(f"\n  Run with --fix --execute to apply {len(easy_fix)} fixes.")


if __name__ == "__main__":
    main()
