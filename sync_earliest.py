#!/usr/bin/env python3
"""
Sync earliest decisions from the catalog.
This script fetches decisions from the END of the catalog (oldest first).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.gov_scraper.scrapers.catalog import extract_decision_urls_from_catalog_selenium
from src.gov_scraper.db.dal import check_existing_decision_keys
from src.gov_scraper.utils.selenium import SeleniumWebDriver

def main():
    print("=" * 60)
    print("SYNCING EARLIEST 100 DECISIONS")
    print("=" * 60)

    # Initialize driver
    print("🌐 Opening Chrome session...")
    driver = SeleniumWebDriver(headless=False)

    try:
        # Total decisions in catalog: ~25,712
        # To get the earliest, we need to skip most of them
        skip_values = [25600, 25500, 25400, 25300, 25200]  # Try different skip values
        all_entries = []

        for skip in skip_values:
            print(f"\n📊 Fetching decisions with skip={skip}...")

            # Manually construct the API URL with skip parameter
            api_url = f"https://www.gov.il/CollectorsWebApi/api/DataCollector/GetResults?CollectorType=policy&CollectorType=pmopolicy&Type=30280ed5-306f-4f0b-a11d-cacf05d36648&culture=he&skip={skip}&limit=20"

            # Navigate to the API endpoint
            driver.driver.get(api_url)

            # Wait for JSON to load
            import time
            time.sleep(3)

            # Get the JSON response
            import json
            page_source = driver.driver.find_element("tag name", "pre").text
            response = json.loads(page_source)

            if 'Results' in response:
                entries = response['Results']
                print(f"  Found {len(entries)} entries")

                for entry in entries:
                    # Parse entry
                    decision_data = {
                        'url': entry.get('Url', ''),
                        'decision_number': entry.get('Title', '').split('#')[-1].strip() if '#' in entry.get('Title', '') else '',
                        'decision_date': entry.get('LastUpdateDate', '').split('T')[0] if 'T' in entry.get('LastUpdateDate', '') else entry.get('LastUpdateDate', '')
                    }

                    if decision_data['decision_number']:
                        all_entries.append(decision_data)

                if len(all_entries) >= 100:
                    break

        # Take first 100 unique decisions
        seen = set()
        unique_entries = []
        for entry in all_entries:
            key = f"37_{entry['decision_number']}"
            if key not in seen:
                seen.add(key)
                unique_entries.append(entry)
                if len(unique_entries) >= 100:
                    break

        print(f"\n✅ Found {len(unique_entries)} unique earliest decisions")

        # Check which ones are already in database
        decision_keys = [f"37_{e['decision_number']}" for e in unique_entries]
        existing_keys = check_existing_decision_keys(decision_keys)

        new_decisions = [e for e in unique_entries if f"37_{e['decision_number']}" not in existing_keys]

        print(f"📊 {len(new_decisions)} are NEW (not in database)")
        print(f"📊 {len(existing_keys)} already exist in database")

        if new_decisions:
            print("\n🎯 First 10 new decisions to process:")
            for i, entry in enumerate(new_decisions[:10]):
                print(f"  {i+1}. Decision #{entry['decision_number']} from {entry['decision_date']}")

            print(f"\n💡 To sync these {len(new_decisions)} decisions, run:")
            print(f"   python bin/sync.py --max-decisions {len(new_decisions)} --no-approval --no-headless")

            # Save decision numbers to file for reference
            with open('earliest_decisions.txt', 'w') as f:
                for entry in new_decisions:
                    f.write(f"{entry['decision_number']}\n")
            print(f"\n📝 Decision numbers saved to earliest_decisions.txt")
        else:
            print("\n✅ All earliest decisions are already in the database!")

    finally:
        driver.quit()
        print("\n🏁 Done!")

if __name__ == "__main__":
    main()