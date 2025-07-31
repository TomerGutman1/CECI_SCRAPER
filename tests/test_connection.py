#!/usr/bin/env python3
"""
Simple connection test for Supabase database.
Quick test to verify credentials and basic connection work.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def main():
    print("🔌 QUICK SUPABASE CONNECTION TEST")
    print("=" * 50)
    
    # Step 1: Check environment variables
    print("1. Checking environment variables...")
    
    from dotenv import load_dotenv
    
    # Load .env from current directory (project root)
    env_path = '.env'
    print(f"   Looking for .env at: {os.path.abspath(env_path)}")
    print(f"   .env file exists: {os.path.exists(env_path)}")
    
    load_dotenv(env_path)
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if not supabase_url:
        print("❌ SUPABASE_URL not found in .env file")
        print("   Create .env file with: SUPABASE_URL=your_url_here")
        return False
        
    if not supabase_key:
        print("❌ SUPABASE_SERVICE_KEY not found in .env file")
        print("   Add to .env file: SUPABASE_SERVICE_KEY=your_key_here")
        return False
    
    print(f"✅ Environment variables found")
    print(f"   URL: {supabase_url}")
    print(f"   Key: {supabase_key[:20]}...")
    
    # Step 2: Test connection
    print("\n2. Testing Supabase connection...")
    
    try:
        from gov_scraper.db.connector import get_supabase_client
        client = get_supabase_client()
        print("✅ Client created successfully")
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return False
    
    # Step 3: Test table access
    print("\n3. Testing table access...")
    
    try:
        # Try to query the table
        response = client.table("israeli_government_decisions").select("count", count="exact").limit(1).execute()
        print(f"✅ Table access successful!")
        print(f"   Table has {response.count} total rows")
        
        # Try to get one sample row
        sample_response = client.table("israeli_government_decisions").select("decision_number,decision_date,decision_key").limit(1).execute()
        
        if sample_response.data:
            sample = sample_response.data[0]
            print(f"✅ Sample data retrieved:")
            print(f"   Decision: {sample.get('decision_number')} ({sample.get('decision_date')})")
            print(f"   Key: {sample.get('decision_key')}")
        else:
            print("ℹ️  Table is empty (no sample data)")
            
    except Exception as e:
        print(f"❌ Table access failed: {e}")
        print("   Check your service key permissions")
        print("   Verify table name 'israeli_government_decisions' exists")
        return False
    
    # Step 4: Test latest decision query
    print("\n4. Testing latest decision query...")
    
    try:
        from gov_scraper.db.dal import fetch_latest_decision
        latest = fetch_latest_decision()
        
        if latest:
            print("✅ Latest decision query successful:")
            print(f"   Latest: {latest.get('decision_number')} from {latest.get('decision_date')}")
            print(f"   Title: {latest.get('decision_title', '')[:50]}...")
        else:
            print("ℹ️  No latest decision found (empty table or no recent decisions)")
            
    except Exception as e:
        print(f"❌ Latest decision query failed: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 CONNECTION TEST SUCCESSFUL!")
    print("✅ Your Supabase database is ready to use")
    print("\n🚀 Next steps:")
    print("   python test_database_integration.py  # Full test suite")
    print("   python src/sync_with_db.py --max-decisions 5  # Try sync")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)