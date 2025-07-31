# Database Integration Testing Guide

This guide explains how to test your Supabase database integration before using the full system.

## 🎯 Why Test First?

Before running the complete sync system, it's crucial to verify:
- ✅ Your Supabase credentials work
- ✅ Database connection is stable  
- ✅ Table schema matches expectations
- ✅ Insert/select permissions are correct
- ✅ Duplicate prevention works
- ✅ Data extraction fixes are working

## 🚀 Quick Start

### 1. Run All Tests (Recommended)
```bash
python run_all_tests.py
```
This runs all tests in the correct order and stops on first failure.

### 2. Quick Connection Check
```bash
python test_connection_simple.py
```
Fast test to verify basic connectivity and credentials.

## 📋 Individual Test Scripts

### `test_connection_simple.py` - Basic Connection
**Purpose**: Verify Supabase credentials and basic connectivity
**What it tests**:
- Environment variables are set
- Supabase client can be created
- Table exists and is accessible
- Can query latest decision

**Expected output**:
```
🔌 QUICK SUPABASE CONNECTION TEST
==================================================
1. Checking environment variables...
✅ Environment variables found
2. Testing Supabase connection...
✅ Client created successfully
3. Testing table access...
✅ Table access successful!
4. Testing latest decision query...
✅ Latest decision query successful
🎉 CONNECTION TEST SUCCESSFUL!
```

### `test_database_integration.py` - Full Integration
**Purpose**: Comprehensive test of all database operations
**What it tests**:
- Environment setup
- Connection stability
- Latest decision fetching
- Duplicate detection
- Sample data insertion
- Incremental processing logic

**Expected output**: 6 individual tests with pass/fail status

### `test_data_insertion.py` - Insertion Functionality  
**Purpose**: Test the complete data insertion workflow
**What it tests**:
- Data preparation for database format
- Duplicate detection before insertion
- Single decision insertion
- Duplicate prevention (insert same twice)
- Batch insertion of multiple decisions
- Committee and location field handling

### `test_fixes.py` - Data Extraction Fixes
**Purpose**: Verify committee and location extraction fixes work
**What it tests**:
- Committee text extraction between "ועדות שרים:" and "ממשלה"
- Handling missing committee sections (returns None)
- Location tags only for explicit mentions
- Empty location tags when no locations found

## 🔧 Environment Setup

Before running tests, ensure your `.env` file contains:

```bash
# Required for database integration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_key_here

# Optional for AI testing
OPENAI_API_KEY=your_openai_key_here
```

## 📊 Understanding Test Results

### ✅ All Tests Pass
```
🎉 ALL TESTS PASSED!
✅ Your Supabase integration is ready to use!
🚀 You can now run:
   python src/sync_with_db.py --max-decisions 5 --verbose
```

**What this means**: Your system is fully operational and ready for production use.

### ❌ Some Tests Fail

Common failure patterns and solutions:

#### Connection Failures
```
❌ SUPABASE_URL not found in .env file
❌ Failed to create client: Invalid API key
```
**Solution**: Check your `.env` file credentials

#### Permission Errors  
```
❌ Table access failed: insufficient_privilege
❌ Failed to insert rows: permission denied
```
**Solution**: Verify your service key has proper permissions (SELECT, INSERT, UPDATE)

#### Schema Mismatches
```
❌ Latest decision query failed: column does not exist
❌ Insert failed: null value in column violates not-null constraint
```
**Solution**: Check your table schema matches expected structure

## 🗄️ Expected Database Schema

Your `israeli_government_decisions` table should have these columns:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `decision_date` | date | Yes | Decision date |
| `decision_number` | text | Yes | Government decision number |
| `committee` | text | **Yes** | Committee name (can be NULL) |
| `decision_title` | text | Yes | Decision title |
| `decision_content` | text | Yes | Full content |
| `decision_url` | text | Yes | Source URL |
| `summary` | text | Yes | AI summary |
| `operativity` | text | Yes | Operational status |
| `tags_policy_area` | text | Yes | Policy tags |
| `tags_government_body` | text | Yes | Government body tags |
| `tags_location` | text | Yes | Location tags (can be empty) |
| `all_tags` | text | Yes | Combined tags |
| `government_number` | text | Yes | Government number |
| `prime_minister` | text | Yes | Prime minister name |
| `decision_key` | text | **No** | Unique key (PRIMARY/UNIQUE) |

## 🚨 Common Issues & Solutions

### Issue: "Table does not exist"
**Solution**: 
1. Check table name is exactly `israeli_government_decisions`
2. Verify table exists in your Supabase project
3. Ensure you're connecting to the correct project

### Issue: "Permission denied" 
**Solution**:
1. Use **service key**, not anon key
2. Check RLS (Row Level Security) policies
3. Verify key has INSERT, SELECT, UPDATE permissions

### Issue: "Duplicate key violation"
**Solution**: 
1. This is normal - duplicate prevention is working
2. Tests create unique keys to avoid conflicts
3. Check that `decision_key` column has UNIQUE constraint

### Issue: Tests pass but sync fails
**Solution**:
1. Run with minimal data first: `--max-decisions 2`
2. Check government website availability
3. Verify OpenAI API key if using AI processing

## 🎯 After Tests Pass

Once all tests pass, you can confidently use:

```bash
# Start with small batch
python src/sync_with_db.py --max-decisions 5 --verbose

# Daily sync  
python src/sync_with_db.py --max-decisions 20

# Bulk import (first time)
python src/sync_with_db.py --max-decisions 100 --no-ai
```

## 📞 Getting Help

If tests fail and you can't resolve the issues:

1. **Check logs**: Tests create detailed error messages
2. **Run individually**: Use single test scripts to isolate problems
3. **Verify setup**: Double-check Supabase project settings
4. **Test manually**: Try basic operations in Supabase dashboard

---

**🧪 Testing ensures reliability - always test before production use!**