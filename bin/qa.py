#!/usr/bin/env python3
"""
QA Script - Quality Assurance checks and fixes for government decisions data.

Usage:
    python bin/qa.py scan                              # Full scan, all checks
    python bin/qa.py scan --check operativity          # Single check
    python bin/qa.py scan --check policy-relevance     # Policy tag vs content
    python bin/qa.py scan --check cross-field          # All cross-field checks
    python bin/qa.py scan --count 100                  # Limit records

    python bin/qa.py fix operativity preview            # Preview fix (10 records)
    python bin/qa.py fix operativity dry-run            # Full dry-run
    python bin/qa.py fix operativity execute            # Apply fixes
    python bin/qa.py fix operativity execute --yes      # Skip confirmation
    python bin/qa.py fix operativity-typos preview      # Preview typo fix ($0)
    python bin/qa.py fix government-bodies-ai preview   # Preview AI body re-tag
    python bin/qa.py fix policy-tags-defaults preview    # Preview default policy fix
    python bin/qa.py fix government-bodies-ai preview --from-report data/qa_reports/flagged_body_hallucination.json

Options:
    --count N              Limit to N records
    --start-date YYYY-MM-DD
    --end-date YYYY-MM-DD
    --prefix PREFIX        Filter by decision_key prefix
    --batch-size N         Batch size for updates (default: 10)
    --verbose              Enable verbose logging
    --yes                  Skip confirmation for execute
    --from-report PATH     Load decision_keys from JSON report to filter records
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.processors.qa import (
    fetch_records_for_qa,
    fetch_records_stratified,
    run_scan,
    format_report,
    export_report_json,
    ALL_CHECKS,
    ALL_FIXERS,
    CROSS_FIELD_CHECKS,
    SUSPICIOUS_BODY_COMBOS,
    SUSPICIOUS_POLICY_TAGS,
    POLICY_TAG_KEYWORDS,
    OPERATIVE_KEYWORDS,
    DECLARATIVE_KEYWORDS,
    _word_in_text,
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, 'qa.log'),
                encoding='utf-8'
            )
        ]
    )


def cmd_scan(args):
    """Run QA scan."""
    print("\n" + "=" * 60)
    print("  QA SCAN — בדיקת איכות נתונים")
    print("=" * 60)

    # Determine which checks to run
    checks = None
    if args.check:
        if args.check == "cross-field":
            checks = CROSS_FIELD_CHECKS
            print(f"\n  Running cross-field checks: {', '.join(checks)}")
        elif args.check in ALL_CHECKS:
            checks = [args.check]
            print(f"\n  Running check: {args.check}")
        else:
            print(f"\n  Unknown check: {args.check}")
            print(f"  Available checks: {', '.join(ALL_CHECKS.keys())}")
            print(f"  Or use 'cross-field' for all cross-field checks")
            return
    else:
        print(f"\n  Running all {len(ALL_CHECKS)} checks")

    # Fetch records
    print(f"\n  Fetching records...", end=" ", flush=True)
    if args.stratified:
        records = fetch_records_stratified(
            sample_percent_per_year=args.sample_percent,
            start_date=args.start_date,
            end_date=args.end_date,
            decision_key_prefix=args.prefix,
            seed=args.seed,
        )
        print(f"fetched {len(records)} records (stratified sampling, {args.sample_percent}% per year)")
    else:
        records = fetch_records_for_qa(
            start_date=args.start_date,
            end_date=args.end_date,
            max_records=args.count,
            decision_key_prefix=args.prefix,
        )
        print(f"fetched {len(records)} records")

    if not records:
        print("  No records found. Check your filters.")
        return

    # Run scan
    report = run_scan(records, checks=checks)

    # Display report
    print(format_report(report))

    # Export JSON report
    report_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"qa_scan_{timestamp}.json")
    export_report_json(report, report_path)
    print(f"\n  Report exported to: {report_path}")


def cmd_fix(args):
    """Run QA fix."""
    fix_name = args.fix_name
    mode = args.mode

    if fix_name not in ALL_FIXERS:
        print(f"\n  Unknown fixer: {fix_name}")
        print(f"  Available fixers: {', '.join(ALL_FIXERS.keys())}")
        return

    print("\n" + "=" * 60)
    print(f"  QA FIX — {fix_name} ({mode})")
    print("=" * 60)

    # Determine record count based on mode
    max_records = args.count
    if mode == "preview" and not max_records:
        max_records = 10

    # Load --from-report keys if provided
    report_keys = None
    if hasattr(args, 'from_report') and args.from_report:
        report_path = args.from_report
        if not os.path.isabs(report_path):
            report_path = os.path.join(PROJECT_ROOT, report_path)
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
            # Support both list-of-keys and dict-with-decision_keys
            if isinstance(report_data, list):
                report_keys = set(report_data)
            elif isinstance(report_data, dict) and "decision_keys" in report_data:
                report_keys = set(report_data["decision_keys"])
            else:
                print(f"  Error: Report file must be a JSON list of keys or dict with 'decision_keys'.")
                return
            print(f"  Loaded {len(report_keys)} keys from report: {args.from_report}")
        except Exception as e:
            print(f"  Error loading report: {e}")
            return

    # Fetch records
    print(f"\n  Fetching records...", end=" ", flush=True)
    records = fetch_records_for_qa(
        start_date=args.start_date,
        end_date=args.end_date,
        max_records=max_records,
        decision_key_prefix=args.prefix,
    )
    print(f"fetched {len(records)} records")

    if not records:
        print("  No records found. Check your filters.")
        return

    # Filter by report keys if provided
    if report_keys is not None:
        records = [r for r in records if r.get("decision_key", "") in report_keys]
        print(f"  Filtered to {len(records)} records matching report keys")
        if not records:
            print("  No matching records found.")
            return

    # Pre-filter for specific fixers
    if fix_name == "operativity":
        # Only fix records where keyword evidence conflicts with current classification
        filtered = []
        for r in records:
            content = (r.get("decision_content", "") or "")
            operativity = (r.get("operativity", "") or "").strip()
            if not content or not operativity:
                continue
            op_hits = sum(1 for kw in OPERATIVE_KEYWORDS if kw in content)
            decl_hits = sum(1 for kw in DECLARATIVE_KEYWORDS if kw in content)
            if op_hits == 0 and decl_hits == 0:
                continue  # No keyword evidence
            # Mismatch: classified operative but only declarative keywords, or vice versa
            if (operativity == "אופרטיבית" and decl_hits > 0 and op_hits == 0):
                filtered.append(r)
            elif (operativity == "דקלרטיבית" and op_hits > 0 and decl_hits == 0):
                filtered.append(r)
        records = filtered
        print(f"  Filtered to {len(records)} records with operativity-keyword mismatch")
        if not records:
            print("  No records need operativity re-classification.")
            return

    elif fix_name == "policy-tags":
        # Only fix records with שונות as sole tag
        records = [r for r in records if (r.get("tags_policy_area", "") or "").strip() == "שונות"]
        print(f"  Filtered to {len(records)} records with only 'שונות' tag")
        if not records:
            print("  No records need policy tag fixing.")
            return

    elif fix_name == "summaries":
        # Only fix records with problematic summaries
        filtered = []
        for r in records:
            summary = r.get("summary", "") or ""
            title = r.get("decision_title", "") or ""
            if len(summary) < 20 or len(summary) > 500 or (title and summary.strip() == title.strip()):
                filtered.append(r)
        records = filtered
        print(f"  Filtered to {len(records)} records with problematic summaries")
        if not records:
            print("  No records need summary fixing.")
            return

    elif fix_name == "government-bodies-ai":
        # Filter to records with suspicious body combos (unless --from-report already filtered)
        if report_keys is None:
            records = [r for r in records if (r.get("tags_government_body", "") or "").strip() in SUSPICIOUS_BODY_COMBOS]
            print(f"  Filtered to {len(records)} records with suspicious body combos")
            if not records:
                print("  No records need government body AI re-tagging.")
                return

    elif fix_name == "policy-tags-defaults":
        # Filter to records with suspicious sole policy tag + no keyword match
        if report_keys is None:
            filtered = []
            for r in records:
                policy_str = (r.get("tags_policy_area", "") or "").strip()
                tags = [t.strip() for t in policy_str.split(";") if t.strip()]
                if len(tags) != 1 or tags[0] not in SUSPICIOUS_POLICY_TAGS:
                    continue
                content = (r.get("decision_content", "") or "") + " " + (r.get("decision_title", "") or "")
                keywords = POLICY_TAG_KEYWORDS.get(tags[0], [])
                if not any(_word_in_text(kw, content) for kw in keywords):
                    filtered.append(r)
            records = filtered
            print(f"  Filtered to {len(records)} records with suspicious default policy tags")
            if not records:
                print("  No records need policy tag default fixing.")
                return

    elif fix_name == "cloudflare":
        # Filter to records with Cloudflare content
        cloudflare_patterns = ["Just a moment", "Cloudflare", "Verify you are human", "Ray ID:"]
        records = [r for r in records if any(p in (r.get("decision_content", "") or "") for p in cloudflare_patterns)]
        print(f"  Filtered to {len(records)} records with Cloudflare content")
        if not records:
            print("  No Cloudflare records found.")
            return

    # Determine dry_run mode
    dry_run = mode != "execute"

    if mode == "execute" and not args.yes:
        confirm = input(f"\n  About to update {len(records)} records. Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("  Cancelled.")
            return

    # Run fixer
    fixer_fn = ALL_FIXERS[fix_name]
    print(f"\n  Running {fix_name} fixer on {len(records)} records...")
    updates, scan_result = fixer_fn(records, dry_run=dry_run)

    # Display results
    print(f"\n  Results:")
    print(f"    Processed: {scan_result.total_scanned}")
    print(f"    Changes: {scan_result.issues_found}")
    if scan_result.summary:
        for key, val in scan_result.summary.items():
            print(f"    {key}: {val}")

    # Show sample changes
    if scan_result.issues[:10]:
        print(f"\n  Sample changes:")
        for issue in scan_result.issues[:10]:
            print(f"    {issue.decision_key}: {issue.description}")

    if mode == "execute":
        print(f"\n  Changes applied to database.")
    elif mode == "dry-run":
        print(f"\n  Dry-run complete. No changes made.")
    else:
        print(f"\n  Preview complete. Use 'dry-run' for full analysis or 'execute' to apply.")

    # Export report
    report_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"qa_fix_{fix_name}_{mode}_{timestamp}.json")

    import json
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(scan_result.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"  Report exported to: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="QA - Quality Assurance for government decisions data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bin/qa.py scan                              # Full scan
  python bin/qa.py scan --check operativity          # Single check
  python bin/qa.py scan --check cross-field          # Cross-field checks
  python bin/qa.py scan --count 100                  # Limit records

  python bin/qa.py fix operativity preview            # Preview
  python bin/qa.py fix operativity dry-run            # Dry-run
  python bin/qa.py fix operativity execute            # Execute
  python bin/qa.py fix operativity execute --yes      # Skip confirmation
  python bin/qa.py fix policy-tags preview            # Preview policy fix
  python bin/qa.py fix locations execute              # Fix locations
  python bin/qa.py fix operativity-typos preview      # Preview typo fix ($0)
  python bin/qa.py fix government-bodies-ai preview   # AI re-tag bodies
  python bin/qa.py fix policy-tags-defaults preview    # AI re-tag default policies
  python bin/qa.py fix government-bodies-ai preview --from-report data/qa_reports/flagged_body_hallucination.json
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    def add_common_args(p):
        p.add_argument("--count", type=int, default=None, help="Limit records")
        p.add_argument("--start-date", type=str, default=None, help="Filter from date (YYYY-MM-DD)")
        p.add_argument("--end-date", type=str, default=None, help="Filter until date (YYYY-MM-DD)")
        p.add_argument("--prefix", type=str, default=None, help="Decision key prefix")
        p.add_argument("--verbose", action="store_true", help="Verbose logging")

    # Scan subcommand
    scan_parser = subparsers.add_parser("scan", help="Run QA scan")
    add_common_args(scan_parser)
    scan_parser.add_argument(
        "--check", type=str, default=None,
        help=f"Specific check to run. Options: {', '.join(list(ALL_CHECKS.keys()) + ['cross-field'])}"
    )
    scan_parser.add_argument(
        "--stratified", action="store_true",
        help="Use stratified random sampling across years (ignores --count)"
    )
    scan_parser.add_argument(
        "--sample-percent", type=float, default=20.0,
        help="Percent to sample from each year with --stratified (default: 20.0)"
    )
    scan_parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible stratified sampling"
    )

    # Fix subcommand
    fix_parser = subparsers.add_parser("fix", help="Run QA fix")
    fix_parser.add_argument("fix_name", type=str, help=f"Fix to run: {', '.join(ALL_FIXERS.keys())}")
    fix_parser.add_argument("mode", type=str, choices=["preview", "dry-run", "execute"], help="Mode")
    add_common_args(fix_parser)
    fix_parser.add_argument("--batch-size", type=int, default=10, help="Batch size for updates")
    fix_parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    fix_parser.add_argument(
        "--from-report", type=str, default=None,
        help="Load decision_keys from a JSON report file to filter records"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(getattr(args, 'verbose', False))

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "fix":
        cmd_fix(args)


if __name__ == "__main__":
    main()
