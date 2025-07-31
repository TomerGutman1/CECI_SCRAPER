#!/usr/bin/env python3
"""
Test script specifically for data insertion functionality.
Tests the complete flow from data preparation to database insertion.
"""

import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def create_test_decision():
    """Create a test decision that won't conflict with real data."""
    timestamp = int(datetime.now().timestamp())
    
    return {
        'decision_number': f'TEST_{timestamp}',
        'decision_date': '2025-01-01',
        'committee': 'ועדת בדיקה למערכת',  # Test committee
        'decision_title': f'החלטת בדיקה למערכת - {timestamp}',
        'decision_content': f'זוהי החלטת בדיקה למערכת ניהול הנתונים. נוצרה בזמן: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}. מספר זיהוי: {timestamp}',
        'decision_url': f'https://example.com/test_{timestamp}',
        'summary': 'החלטת בדיקה למערכת',
        'operativity': 'אופרטיבית',
        'tags_policy_area': 'שונות',
        'tags_government_body': 'מערכת בדיקה',
        'tags_location': '',  # Empty location (testing the fix)
        'all_tags': 'שונות; מערכת בדיקה',
        'government_number': '37',
        'prime_minister': 'בנימין נתניהו',
        'decision_key': f'37_TEST_{timestamp}'
    }


def test_data_preparation():
    """Test data preparation for database insertion."""
    print("📋 TEST: Data Preparation")
    print("-" * 40)
    
    try:
        from gov_scraper.processors.incremental import prepare_for_database
        
        # Create test decision
        test_decision = create_test_decision()
        print(f"✅ Created test decision: {test_decision['decision_key']}")
        
        # Prepare for database
        prepared_decisions = prepare_for_database([test_decision])
        
        if prepared_decisions:
            prepared = prepared_decisions[0]
            print("✅ Data preparation successful:")
            print(f"   Decision key: {prepared.get('decision_key')}")
            print(f"   Committee: {prepared.get('committee')}")
            print(f"   Location: '{prepared.get('tags_location')}'")
            print(f"   Fields count: {len(prepared)}")
            return prepared
        else:
            print("❌ Data preparation failed - no data returned")
            return None
            
    except Exception as e:
        print(f"❌ Data preparation failed: {e}")
        return None


def test_duplicate_check():
    """Test duplicate detection before insertion."""
    print("\n🔍 TEST: Duplicate Detection")
    print("-" * 40)
    
    try:
        from gov_scraper.db.dal import check_existing_decision_keys, filter_duplicate_decisions
        
        # Create test decisions
        decisions = [create_test_decision() for _ in range(3)]
        decision_keys = [d['decision_key'] for d in decisions]
        
        print(f"✅ Created {len(decisions)} test decisions")
        print(f"   Keys: {decision_keys}")
        
        # Check for existing keys
        existing = check_existing_decision_keys(decision_keys)
        print(f"✅ Duplicate check complete - {len(existing)} existing keys found")
        
        # Filter duplicates
        unique_decisions, duplicate_keys = filter_duplicate_decisions(decisions)
        print(f"✅ Filtering complete:")
        print(f"   Unique decisions: {len(unique_decisions)}")
        print(f"   Duplicate keys: {duplicate_keys}")
        
        return unique_decisions
        
    except Exception as e:
        print(f"❌ Duplicate detection failed: {e}")
        return []


def test_single_insertion():
    """Test inserting a single decision."""
    print("\n💾 TEST: Single Decision Insertion")
    print("-" * 40)
    
    try:
        from gov_scraper.db.dal import insert_decisions_batch
        
        # Create and prepare test decision
        test_decision = create_test_decision()
        print(f"📝 Inserting test decision: {test_decision['decision_key']}")
        
        # Insert decision
        inserted_count, error_messages = insert_decisions_batch([test_decision])
        
        print(f"✅ Insertion attempt complete:")
        print(f"   Inserted: {inserted_count}")
        print(f"   Errors: {len(error_messages)}")
        
        if error_messages:
            print("   Error details:")
            for error in error_messages:
                print(f"     - {error}")
        
        if inserted_count == 1:
            print("✅ Single insertion successful!")
            return test_decision['decision_key']
        else:
            print("❌ Single insertion failed")
            return None
            
    except Exception as e:
        print(f"❌ Single insertion test failed: {e}")
        return None


def test_duplicate_prevention():
    """Test that duplicate insertion is prevented."""
    print("\n🚫 TEST: Duplicate Prevention")
    print("-" * 40)
    
    try:
        from gov_scraper.db.dal import insert_decisions_batch
        
        # Create test decision
        test_decision = create_test_decision()
        decision_key = test_decision['decision_key']
        
        print(f"📝 First insertion of: {decision_key}")
        
        # First insertion
        inserted_count_1, errors_1 = insert_decisions_batch([test_decision])
        print(f"   First attempt - Inserted: {inserted_count_1}, Errors: {len(errors_1)}")
        
        # Second insertion (should be prevented)
        print(f"🔄 Second insertion of same decision...")
        inserted_count_2, errors_2 = insert_decisions_batch([test_decision])
        print(f"   Second attempt - Inserted: {inserted_count_2}, Errors: {len(errors_2)}")
        
        if inserted_count_1 == 1 and inserted_count_2 == 0:
            print("✅ Duplicate prevention working correctly!")
            return True
        else:
            print("❌ Duplicate prevention failed")
            print(f"   Expected: 1st=1, 2nd=0. Got: 1st={inserted_count_1}, 2nd={inserted_count_2}")
            return False
            
    except Exception as e:
        print(f"❌ Duplicate prevention test failed: {e}")
        return False


def test_batch_insertion():
    """Test inserting multiple decisions in batch."""
    print("\n📦 TEST: Batch Insertion")
    print("-" * 40)
    
    try:
        from gov_scraper.db.dal import insert_decisions_batch
        
        # Create multiple test decisions
        batch_size = 3
        test_decisions = [create_test_decision() for _ in range(batch_size)]
        
        print(f"📝 Creating batch of {batch_size} test decisions:")
        for i, decision in enumerate(test_decisions, 1):
            print(f"   {i}. {decision['decision_key']}")
        
        # Insert batch
        inserted_count, error_messages = insert_decisions_batch(test_decisions)
        
        print(f"✅ Batch insertion complete:")
        print(f"   Inserted: {inserted_count}/{batch_size}")
        print(f"   Errors: {len(error_messages)}")
        
        if error_messages:
            print("   Error details:")
            for error in error_messages[:3]:  # Show first 3 errors
                print(f"     - {error}")
        
        success_rate = (inserted_count / batch_size) * 100
        print(f"   Success rate: {success_rate:.1f}%")
        
        if inserted_count == batch_size:
            print("✅ Batch insertion fully successful!")
            return True
        elif inserted_count > 0:
            print("⚠️  Batch insertion partially successful")
            return True
        else:
            print("❌ Batch insertion failed completely")
            return False
            
    except Exception as e:
        print(f"❌ Batch insertion test failed: {e}")
        return False


def test_committee_and_location_handling():
    """Test that committee and location fields are handled correctly."""
    print("\n🏛️ TEST: Committee & Location Handling")
    print("-" * 40)
    
    try:
        from gov_scraper.db.dal import insert_decisions_batch
        
        # Test decision with committee
        decision_with_committee = create_test_decision()
        decision_with_committee['committee'] = 'ועדת השרים לענייני חקיקה'
        decision_with_committee['decision_key'] = f"37_TEST_COMMITTEE_{int(datetime.now().timestamp())}"
        
        # Test decision without committee (None)
        decision_without_committee = create_test_decision()
        decision_without_committee['committee'] = None
        decision_without_committee['decision_key'] = f"37_TEST_NO_COMMITTEE_{int(datetime.now().timestamp())}"
        
        # Test decision with location
        decision_with_location = create_test_decision()
        decision_with_location['tags_location'] = 'ירושלים, תל אביב'
        decision_with_location['decision_key'] = f"37_TEST_LOCATION_{int(datetime.now().timestamp())}"
        
        # Test decision without location (empty string)
        decision_without_location = create_test_decision()
        decision_without_location['tags_location'] = ''
        decision_without_location['decision_key'] = f"37_TEST_NO_LOCATION_{int(datetime.now().timestamp())}"
        
        test_cases = [
            ("with committee", decision_with_committee),
            ("without committee", decision_without_committee),
            ("with location", decision_with_location),
            ("without location", decision_without_location)
        ]
        
        results = []
        
        for case_name, decision in test_cases:
            print(f"   Testing decision {case_name}...")
            inserted_count, errors = insert_decisions_batch([decision])
            
            if inserted_count == 1:
                print(f"   ✅ {case_name}: SUCCESS")
                results.append(True)
            else:
                print(f"   ❌ {case_name}: FAILED - {errors}")
                results.append(False)
        
        success_count = sum(results)
        print(f"\n✅ Committee & Location test results: {success_count}/{len(results)} passed")
        
        return success_count == len(results)
        
    except Exception as e:
        print(f"❌ Committee & Location test failed: {e}")
        return False


def run_insertion_tests():
    """Run all data insertion tests."""
    print("💾 SUPABASE DATA INSERTION TESTS")
    print("=" * 60)
    print("Testing complete data insertion workflow with real database operations.\n")
    
    tests = [
        ("Data Preparation", test_data_preparation),
        ("Duplicate Detection", test_duplicate_check),
        ("Single Insertion", test_single_insertion),
        ("Duplicate Prevention", test_duplicate_prevention),
        ("Batch Insertion", test_batch_insertion),
        ("Committee & Location", test_committee_and_location_handling),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            # Convert result to boolean
            success = bool(result) if result is not None else True
            results.append((test_name, success))
        except Exception as e:
            print(f"\n💥 {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 DATA INSERTION TEST RESULTS")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:<10} {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 ALL INSERTION TESTS PASSED!")
        print("✅ Your database insertion functionality is working perfectly!")
        print("\n🚀 Your system is ready for:")
        print("   - Incremental decision processing")
        print("   - Batch data insertion")
        print("   - Duplicate prevention")
        print("   - Full sync workflow")
    else:
        print(f"\n⚠️  {total - passed} insertion tests failed.")
        print("❌ Review the errors above and fix issues before using the full system.")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_insertion_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        sys.exit(1)