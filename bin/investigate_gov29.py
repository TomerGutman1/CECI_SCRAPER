#!/usr/bin/env python3
"""
Government 29 Specific Investigation Script - Focus on the reported 815 "ללא כותרת" issue.
"""

import sys
import os
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client


def investigate_gov29_titles():
    """Investigate titles specifically in Government 29."""
    client = get_supabase_client()

    print("Investigating Government 29 titles...")

    # Fetch all Government 29 records
    all_records = []
    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_key, decision_title, government_number, decision_date"
        ).eq("government_number", 29).range(offset, offset + chunk_size - 1)

        response = query.execute()

        if not response.data:
            break

        all_records.extend(response.data)
        offset += chunk_size

        if len(response.data) < chunk_size:
            break

    print(f"Found {len(all_records)} total records in Government 29")

    # Analyze titles
    title_analysis = {
        "null": 0,
        "empty": 0,
        "placeholder_exact": 0,  # Exact "ללא כותרת"
        "placeholder_variations": 0,  # Other variations
        "valid": 0
    }

    placeholder_variations = []
    sample_titles = []

    for record in all_records:
        title = record.get("decision_title")
        decision_key = record.get("decision_key", "")

        if title is None:
            title_analysis["null"] += 1
        elif title.strip() == "":
            title_analysis["empty"] += 1
        elif title.strip() == "ללא כותרת":
            title_analysis["placeholder_exact"] += 1
        elif "ללא כותרת" in title.strip():
            title_analysis["placeholder_variations"] += 1
            placeholder_variations.append(f"{decision_key}: '{title.strip()}'")
        else:
            title_analysis["valid"] += 1
            if len(sample_titles) < 5:
                sample_titles.append(f"{decision_key}: '{title.strip()[:100]}'")

    print(f"\nTitle Analysis for Government 29:")
    print(f"  NULL titles: {title_analysis['null']}")
    print(f"  Empty titles: {title_analysis['empty']}")
    print(f"  Exact 'ללא כותרת' titles: {title_analysis['placeholder_exact']}")
    print(f"  'ללא כותרת' variations: {title_analysis['placeholder_variations']}")
    print(f"  Valid titles: {title_analysis['valid']}")

    total_problematic = title_analysis["null"] + title_analysis["empty"] + title_analysis["placeholder_exact"] + title_analysis["placeholder_variations"]
    print(f"\nTotal problematic titles: {total_problematic}")

    if placeholder_variations:
        print(f"\nPlaceholder variations found:")
        for variation in placeholder_variations[:10]:
            print(f"  {variation}")

    if sample_titles:
        print(f"\nSample valid titles:")
        for sample in sample_titles:
            print(f"  {sample}")

    # Check if we can find the 815 figure
    if title_analysis["placeholder_exact"] == 815:
        print(f"\n✅ CONFIRMED: Found exactly 815 'ללא כותרת' titles in Government 29")
    else:
        print(f"\n❌ DISCREPANCY: Expected 815 'ללא כותרת' but found {title_analysis['placeholder_exact']}")
        print(f"   Total problematic: {total_problematic}")

    return title_analysis


def investigate_all_governments_placeholder():
    """Check all governments for 'ללא כותרת' pattern."""
    client = get_supabase_client()

    print("\nInvestigating 'ללא כותרת' pattern across all governments...")

    placeholder_by_gov = defaultdict(int)
    offset = 0
    chunk_size = 1000

    while True:
        query = client.table("israeli_government_decisions").select(
            "decision_title, government_number"
        ).range(offset, offset + chunk_size - 1)

        response = query.execute()

        if not response.data:
            break

        for record in response.data:
            title = record.get("decision_title", "")
            gov_num = record.get("government_number")

            if title and "ללא כותרת" in title:
                placeholder_by_gov[gov_num] += 1

        offset += chunk_size
        if len(response.data) < chunk_size:
            break

        if offset % 10000 == 0:
            print(f"  Processed {offset:,} records...")

    print(f"\nGovernments with 'ללא כותרת' titles:")
    for gov_num in sorted(placeholder_by_gov.keys()):
        count = placeholder_by_gov[gov_num]
        print(f"  Government {gov_num}: {count} records")

    return dict(placeholder_by_gov)


if __name__ == "__main__":
    gov29_analysis = investigate_gov29_titles()
    all_gov_placeholder = investigate_all_governments_placeholder()

    print(f"\n" + "=" * 50)
    print("SUMMARY:")
    print(f"Government 29 'ללא כותרת' titles: {gov29_analysis['placeholder_exact']}")
    total_across_govs = sum(all_gov_placeholder.values())
    print(f"Total 'ללא כותרת' across all governments: {total_across_govs}")

    if len(all_gov_placeholder) == 1 and 29 in all_gov_placeholder:
        print("✅ 'ללא כותרת' issue is isolated to Government 29 only")
    else:
        print(f"❌ 'ללא כותרת' issue affects {len(all_gov_placeholder)} governments")