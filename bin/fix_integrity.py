#!/usr/bin/env python3
"""
Fix 19 data integrity issues in israeli_government_decisions.

Fixes:
- Group A (5): Clean NBSP from decision_number (keys already clean)
- Group B (11): Clean decision_number + decision_key (corrupted/parenthetical)
- Group C (3): Clean NBSP from decision_number + decision_key (Hebrew keys)

Usage:
    python bin/fix_integrity.py              # Dry run (default)
    python bin/fix_integrity.py --execute    # Apply fixes
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gov_scraper.db.connector import get_supabase_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# All 19 fixes, grouped by type
FIXES = {
    # Group A: decision_number only (keys already correct)
    63042: {"decision_number": "4706"},
    63501: {"decision_number": "1325"},
    64815: {"decision_number": "4"},
    64991: {"decision_number": "425"},
    66438: {"decision_number": "22"},

    # Group B: decision_number + decision_key
    80290: {"decision_number": "3926", "decision_key": "32_3926"},
    80291: {"decision_number": "5181", "decision_key": "32_5181"},
    80395: {"decision_number": "489", "decision_key": "33_489"},
    80396: {"decision_number": "547", "decision_key": "33_547"},
    80397: {"decision_number": "548", "decision_key": "33_548"},
    80398: {"decision_number": "549", "decision_key": "33_549"},
    80399: {"decision_number": "550", "decision_key": "33_550"},
    80400: {"decision_number": "551", "decision_key": "33_551"},
    80401: {"decision_number": "552", "decision_key": "33_552"},
    80402: {"decision_number": "553", "decision_key": "33_553"},
    80403: {"decision_number": "554", "decision_key": "33_554"},

    # Group C: NBSP in both fields (Hebrew decision numbers)
    80481: {"decision_number": "\u05d2\u05d1\u05dc/14", "decision_key": "35_gbl14"},
    80490: {"decision_number": "\u05d2\u05d1\u05dc/23", "decision_key": "35_gbl23"},
    80517: {"decision_number": "\u05e8\u05d4\u05de/7", "decision_key": "35_rhm7"},
}


def main():
    parser = argparse.ArgumentParser(description="Fix DB integrity issues")
    parser.add_argument("--execute", action="store_true",
                        help="Apply fixes (default: dry run)")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"  DB Integrity Fix — {mode}")
    print(f"{'=' * 60}")
    print(f"  Records to fix: {len(FIXES)}")
    print()

    client = get_supabase_client()

    # Fetch all records that need fixing
    ids = list(FIXES.keys())
    response = (
        client.table("israeli_government_decisions")
        .select("id, decision_key, decision_number, government_number, decision_title")
        .in_("id", ids)
        .execute()
    )

    current_records = {rec["id"]: rec for rec in response.data}

    if len(current_records) != len(FIXES):
        missing = set(FIXES.keys()) - set(current_records.keys())
        print(f"WARNING: {len(missing)} records not found in DB: {missing}")

    # Pre-flight collision check for new keys
    new_keys = [fix["decision_key"] for fix in FIXES.values() if "decision_key" in fix]
    collision_check = (
        client.table("israeli_government_decisions")
        .select("id, decision_key")
        .in_("decision_key", new_keys)
        .execute()
    )
    existing_target_keys = {rec["decision_key"]: rec["id"] for rec in collision_check.data}

    # Filter out records that ARE the ones we're fixing (same id)
    real_collisions = {}
    for key, existing_id in existing_target_keys.items():
        # Find which fix produces this key
        for fix_id, fix_data in FIXES.items():
            if fix_data.get("decision_key") == key and existing_id != fix_id:
                real_collisions[key] = existing_id

    if real_collisions:
        print("FATAL: Key collisions detected! Aborting.")
        for key, cid in real_collisions.items():
            print(f"  Key {key} already belongs to id={cid}")
        sys.exit(1)

    print("Pre-flight collision check: PASSED")
    print()

    # Apply fixes
    success = 0
    skipped = 0
    failed = 0

    for record_id, fix_data in sorted(FIXES.items()):
        current = current_records.get(record_id)
        if not current:
            print(f"  SKIP id={record_id}: not found in DB")
            skipped += 1
            continue

        cur_dn = current["decision_number"] or ""
        cur_key = current["decision_key"] or ""
        title = (current["decision_title"] or "")[:50]

        new_dn = fix_data.get("decision_number", cur_dn)
        new_key = fix_data.get("decision_key", cur_key)

        changes = []
        if new_dn != cur_dn:
            changes.append(f"dn: {cur_dn!r} -> {new_dn!r}")
        if new_key != cur_key:
            changes.append(f"key: {cur_key!r} -> {new_key!r}")

        if not changes:
            print(f"  SKIP id={record_id}: already correct")
            skipped += 1
            continue

        change_str = " | ".join(changes)
        print(f"  {'FIX' if args.execute else 'WOULD FIX'} id={record_id} gov={current['government_number']}: {change_str}")
        print(f"       title: {title}")

        if args.execute:
            try:
                update_data = {}
                if "decision_number" in fix_data:
                    update_data["decision_number"] = fix_data["decision_number"]
                if "decision_key" in fix_data:
                    update_data["decision_key"] = fix_data["decision_key"]

                client.table("israeli_government_decisions").update(update_data).eq("id", record_id).execute()
                success += 1
                print(f"       -> OK")
            except Exception as e:
                failed += 1
                print(f"       -> FAILED: {e}")
        else:
            success += 1

    print()
    print(f"{'=' * 60}")
    print(f"  Results: {success} {'fixed' if args.execute else 'would fix'}, {skipped} skipped, {failed} failed")
    print(f"{'=' * 60}")

    if not args.execute:
        print("\n  Run with --execute to apply these fixes.")


if __name__ == "__main__":
    main()
