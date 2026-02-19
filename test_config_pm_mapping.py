#!/usr/bin/env python3
"""Unit verification script for PM_BY_GOVERNMENT mapping in config.py."""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from gov_scraper.config import PM_BY_GOVERNMENT, GOVERNMENT_NUMBER, PRIME_MINISTER
    print("✅ Successfully imported PM_BY_GOVERNMENT from config")
except ImportError as e:
    print(f"❌ Failed to import PM_BY_GOVERNMENT: {e}")
    sys.exit(1)

def test_pm_mapping():
    """Test PM_BY_GOVERNMENT mapping for completeness and correctness."""
    print("\n🔍 Testing PM_BY_GOVERNMENT mapping...")

    # Test 1: Check all governments 25-37 are present
    expected_governments = list(range(25, 38))  # 25 to 37 inclusive
    actual_governments = list(PM_BY_GOVERNMENT.keys())

    print(f"Expected governments: {expected_governments}")
    print(f"Actual governments: {sorted(actual_governments)}")

    if sorted(actual_governments) != expected_governments:
        print("❌ FAIL: Not all governments 25-37 are present")
        missing = set(expected_governments) - set(actual_governments)
        extra = set(actual_governments) - set(expected_governments)
        if missing:
            print(f"  Missing: {sorted(missing)}")
        if extra:
            print(f"  Extra: {sorted(extra)}")
        return False
    else:
        print("✅ PASS: All governments 25-37 are present")

    # Test 2: Check no empty values
    empty_values = [gov for gov, pm in PM_BY_GOVERNMENT.items() if not pm or not pm.strip()]
    if empty_values:
        print(f"❌ FAIL: Empty PM names for governments: {empty_values}")
        return False
    else:
        print("✅ PASS: No empty PM names")

    # Test 3: Check Hebrew names format
    non_hebrew_count = 0
    for gov, pm in PM_BY_GOVERNMENT.items():
        # Check if contains Hebrew characters (basic test)
        if not any('\u0590' <= c <= '\u05FF' for c in pm):
            print(f"⚠️  WARNING: Government {gov} PM name '{pm}' doesn't contain Hebrew characters")
            non_hebrew_count += 1

    if non_hebrew_count == 0:
        print("✅ PASS: All PM names contain Hebrew characters")
    else:
        print(f"⚠️  WARNING: {non_hebrew_count} PM names don't contain Hebrew")

    # Test 4: Check current government consistency
    if GOVERNMENT_NUMBER in PM_BY_GOVERNMENT:
        mapped_pm = PM_BY_GOVERNMENT[GOVERNMENT_NUMBER]
        if mapped_pm == PRIME_MINISTER:
            print("✅ PASS: Current government PM mapping is consistent")
        else:
            print(f"❌ FAIL: Current PM mismatch - PRIME_MINISTER='{PRIME_MINISTER}' but PM_BY_GOVERNMENT[{GOVERNMENT_NUMBER}]='{mapped_pm}'")
            return False
    else:
        print(f"❌ FAIL: Current GOVERNMENT_NUMBER ({GOVERNMENT_NUMBER}) not in PM_BY_GOVERNMENT")
        return False

    # Test 5: Display all mappings for verification
    print("\n📊 All PM mappings:")
    for gov in sorted(PM_BY_GOVERNMENT.keys()):
        pm = PM_BY_GOVERNMENT[gov]
        current_marker = " (CURRENT)" if gov == GOVERNMENT_NUMBER else ""
        print(f"  Government {gov}: {pm}{current_marker}")

    return True

def main():
    """Run all tests."""
    print("🚀 PM_BY_GOVERNMENT Configuration Test")
    print("=" * 50)

    try:
        success = test_pm_mapping()

        print("\n" + "=" * 50)
        if success:
            print("🎉 ALL TESTS PASSED!")
            print("✅ PM_BY_GOVERNMENT mapping is ready for use")
            return True
        else:
            print("❌ SOME TESTS FAILED!")
            print("🔧 Please fix the issues above before proceeding")
            return False

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)