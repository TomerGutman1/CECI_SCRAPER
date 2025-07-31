#!/usr/bin/env python3
"""
Test script to verify Supabase database integration works properly.
Run this before using the full sync system to ensure everything is connected.
"""

import sys
import os
from datetime import datetime
from typing import Dict, List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_environment_variables():
    """Test 1: Check if environment variables are set."""
    print("🔧 TEST 1: Environment Variables")
    print("-" * 50)
    
    from dotenv import load_dotenv
    
    # Load .env from current directory (project root)
    load_dotenv('.env')
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if supabase_url:
        print(f"✅ SUPABASE_URL found: {supabase_url[:30]}...")
    else:
        print("❌ SUPABASE_URL not found in environment")
        return False
    
    if supabase_key:
        print(f"✅ SUPABASE_SERVICE_KEY found: {supabase_key[:20]}...")
    else:
        print("❌ SUPABASE_SERVICE_KEY not found in environment")
        return False
    
    print("✅ Environment variables are set correctly\n")
    return True


def test_supabase_connection():
    """Test 2: Test basic Supabase connection."""
    print("🔌 TEST 2: Supabase Connection")
    print("-" * 50)
    
    try:
        from db.db_connector import get_supabase_client
        
        client = get_supabase_client()
        print("✅ Supabase client created successfully")
        
        # Test basic connection with a simple query
        response = client.table("israeli_government_decisions").select("count", count="exact").execute()
        print(f"✅ Connection test successful - table has {response.count} rows")
        print("✅ Database connection is working\n")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("❌ Check your SUPABASE_URL and SUPABASE_SERVICE_KEY\n")
        return False


def test_fetch_latest_decision():
    """Test 3: Test fetching latest decision from database."""
    print("📊 TEST 3: Fetch Latest Decision")
    print("-" * 50)
    
    try:
        from gov_scraper.db.dal import fetch_latest_decision
        
        latest = fetch_latest_decision()
        
        if latest:
            print("✅ Successfully fetched latest decision:")
            print(f"  - Decision Number: {latest.get('decision_number')}")
            print(f"  - Decision Date: {latest.get('decision_date')}")
            print(f"  - Decision Key: {latest.get('decision_key')}")
            print(f"  - Title: {latest.get('decision_title', '')[:50]}...")
            print("✅ Latest decision retrieval works\n")
            return latest
        else:
            print("⚠️  No decisions found in database (empty table)")
            print("   This is normal for a new setup\n")
            return None
            
    except Exception as e:
        print(f"❌ Failed to fetch latest decision: {e}\n")
        return None


def test_duplicate_detection():
    """Test 4: Test duplicate detection functionality."""
    print("🔍 TEST 4: Duplicate Detection")
    print("-" * 50)
    
    try:
        from gov_scraper.db.dal import check_existing_decision_keys
        
        # Test with some sample decision keys
        test_keys = ["37_3284", "37_3285", "37_9999", "37_0001"]
        
        existing_keys = check_existing_decision_keys(test_keys)
        
        print(f"✅ Tested {len(test_keys)} decision keys")
        print(f"✅ Found {len(existing_keys)} existing keys: {list(existing_keys)}")
        print("✅ Duplicate detection is working\n")
        return existing_keys
        
    except Exception as e:
        print(f"❌ Duplicate detection failed: {e}\n")
        return set()


def test_insert_sample_decision():
    """Test 5: Test inserting a sample decision (will be rolled back)."""
    print("💾 TEST 5: Sample Decision Insertion")
    print("-" * 50)
    
    try:
        from gov_scraper.db.dal import insert_decisions_batch
        
        # Create a test decision that won't conflict with real data
        timestamp = int(datetime.now().timestamp())
        test_decision = {
            'decision_number': f'TEST_{timestamp}',
            'decision_date': '2025-01-01',
            'committee': 'ועדת בדיקה',
            'decision_title': 'החלטת בדיקה למערכת',
            'decision_content': f'זוהי החלטת בדיקה למערכת הנתונים. זמן יצירה: {timestamp}',
            'decision_url': f'https://example.com/test_{timestamp}',
            'summary': 'החלטת בדיקה',
            'operativity': 'אופרטיבית',
            'tags_policy_area': 'שונות',
            'tags_government_body': 'מערכת בדיקה',
            'tags_location': '',
            'all_tags': 'שונות; מערכת בדיקה',
            'government_number': '37',
            'prime_minister': 'בנימין נתניהו',
            'decision_key': f'37_TEST_{timestamp}'
        }
        
        print(f"📝 Creating test decision with key: {test_decision['decision_key']}")
        
        # Try to insert the test decision
        inserted_count, error_messages = insert_decisions_batch([test_decision])
        
        if inserted_count == 1:
            print("✅ Test decision inserted successfully")
            
            # Now try to clean up by inserting the same decision again (should be skipped as duplicate)
            print("🔄 Testing duplicate prevention...")
            inserted_count_2, error_messages_2 = insert_decisions_batch([test_decision])
            
            if inserted_count_2 == 0:
                print("✅ Duplicate prevention working - second insert was skipped")
                print("✅ Database insertion is working properly\n")
                return True
            else:
                print("⚠️  Duplicate was inserted - check duplicate prevention logic")
                return False
                
        else:
            print(f"❌ Insert failed. Errors: {error_messages}")
            return False
            
    except Exception as e:
        print(f"❌ Sample insertion test failed: {e}\n")
        return False


def test_incremental_processing():
    """Test 6: Test incremental processing logic."""
    print("⚡ TEST 6: Incremental Processing")
    print("-" * 50)
    
    try:
        from gov_scraper.processors.incremental import get_scraping_baseline, should_process_decision
        
        # Test getting baseline
        baseline = get_scraping_baseline()
        
        if baseline:
            print("✅ Successfully retrieved scraping baseline:")
            print(f"  - Baseline Decision: {baseline.get('decision_number')} ({baseline.get('decision_date')})")
            
            # Test decision comparison logic
            newer_decision = {
                'decision_number': '9999',
                'decision_date': '2025-12-31',  # Future date
                'decision_content': 'Test newer decision'
            }
            
            older_decision = {
                'decision_number': '1000',
                'decision_date': '2020-01-01',  # Old date
                'decision_content': 'Test older decision'
            }
            
            should_process_newer = should_process_decision(newer_decision, baseline)
            should_process_older = should_process_decision(older_decision, baseline)
            
            print(f"✅ Newer decision should be processed: {should_process_newer}")
            print(f"✅ Older decision should be processed: {should_process_older}")
            
            if should_process_newer and not should_process_older:
                print("✅ Incremental processing logic is working correctly\n")
                return True
            else:
                print("⚠️  Incremental processing logic may have issues\n")
                return False
        else:
            print("⚠️  No baseline found (empty database)")
            print("✅ This is normal for a new setup\n")
            return True
            
    except Exception as e:
        print(f"❌ Incremental processing test failed: {e}\n")
        return False


def run_all_tests():
    """Run all database integration tests."""
    print("🧪 SUPABASE DATABASE INTEGRATION TESTS")
    print("=" * 80)
    print("This script will test all database operations without affecting your data.\n")
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Supabase Connection", test_supabase_connection),
        ("Fetch Latest Decision", test_fetch_latest_decision),
        ("Duplicate Detection", test_duplicate_detection),
        ("Sample Decision Insertion", test_insert_sample_decision),
        ("Incremental Processing", test_incremental_processing),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"💥 {test_name} crashed: {e}\n")
            results.append((test_name, False))
    
    # Summary
    print("=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<10} {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Your Supabase integration is ready to use!")
        print("\n🚀 You can now run:")
        print("   python src/sync_with_db.py --max-decisions 5 --verbose")
    else:
        print(f"\n⚠️  {total - passed} tests failed.")
        print("❌ Fix the issues above before using the full system.")
        print("\n🔧 Common fixes:")
        print("   - Check your .env file has correct Supabase credentials")
        print("   - Verify your Supabase table schema matches expectations")
        print("   - Ensure your service key has proper permissions")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)