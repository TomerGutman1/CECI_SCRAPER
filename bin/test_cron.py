#!/usr/bin/env python3
"""
Simple end-to-end test for the cron pipeline.
Tests: env vars → Supabase connection → read → write to cron_test_log table.

Usage:
    python bin/test_cron.py          # Run test
    python bin/test_cron.py --check  # Check results in cron_test_log
"""

import os
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Load .env file (same mechanism as sync.py)
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")


def run_test():
    """Run the full pipeline test."""
    print(f"[{datetime.now().isoformat()}] Cron pipeline test starting...\n")

    # Test 1: Environment variables
    print("--- Test 1: Environment Variables ---")
    gemini_key = os.getenv('GEMINI_API_KEY')
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

    if not gemini_key:
        print("FAIL: GEMINI_API_KEY not set")
        return 1
    print(f"  GEMINI_API_KEY: set ({len(gemini_key)} chars)")

    if not supabase_url:
        print("FAIL: SUPABASE_URL not set")
        return 1
    print(f"  SUPABASE_URL: {supabase_url}")

    if not supabase_key:
        print("FAIL: SUPABASE_SERVICE_ROLE_KEY not set")
        return 1
    print(f"  SUPABASE_SERVICE_ROLE_KEY: set ({len(supabase_key)} chars)")
    print("  PASS\n")

    # Test 2: Supabase connection
    print("--- Test 2: Supabase Connection ---")
    from gov_scraper.db.connector import get_supabase_client
    client = get_supabase_client()
    print("  Client created successfully")
    print("  PASS\n")

    # Test 3: Read from production table
    print("--- Test 3: Read Production Table ---")
    response = client.table('israeli_government_decisions').select(
        'count', count='exact'
    ).limit(1).execute()
    record_count = response.count
    print(f"  Records in DB: {record_count}")
    print("  PASS\n")

    # Test 4: Write to test table
    print("--- Test 4: Write to cron_test_log ---")
    test_data = {
        "test_time": datetime.now().isoformat(),
        "source": "test_cron.py",
        "status": "success",
        "record_count": record_count
    }
    try:
        result = client.table('cron_test_log').insert(test_data).execute()
        print(f"  Inserted test record: {test_data['test_time']}")
        print("  PASS\n")
    except Exception as e:
        if '404' in str(e) or 'relation' in str(e).lower():
            print(f"  FAIL: Table 'cron_test_log' does not exist.")
            print("  Create it in Supabase SQL Editor:")
            print("  CREATE TABLE cron_test_log (")
            print("      id SERIAL PRIMARY KEY,")
            print("      test_time TIMESTAMPTZ NOT NULL,")
            print("      source TEXT,")
            print("      status TEXT,")
            print("      record_count INTEGER,")
            print("      created_at TIMESTAMPTZ DEFAULT NOW()")
            print("  );")
            return 1
        raise

    print(f"[{datetime.now().isoformat()}] ALL TESTS PASSED")
    return 0


def check_results():
    """Check what's in the cron_test_log table."""
    from gov_scraper.db.connector import get_supabase_client
    client = get_supabase_client()

    response = client.table('cron_test_log').select('*').order(
        'created_at', desc=True
    ).limit(10).execute()

    if not response.data:
        print("No records in cron_test_log")
        return

    print(f"Latest {len(response.data)} records in cron_test_log:\n")
    for row in response.data:
        print(f"  [{row.get('created_at', '?')}] "
              f"source={row.get('source', '?')} "
              f"status={row.get('status', '?')} "
              f"records={row.get('record_count', '?')}")


if __name__ == '__main__':
    try:
        if '--check' in sys.argv:
            check_results()
        else:
            sys.exit(run_test())
    except Exception as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)
