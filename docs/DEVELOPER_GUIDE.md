# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Israeli government decisions scraper project designed to extract, process, and analyze government decisions from the official Israeli government website (`https://www.gov.il/he/collectors/policies`). The project combines **Selenium-based web scraping**, Hebrew text processing, AI-powered content analysis, and **Supabase database integration** with **unlimited incremental processing** capability.
## Objective

Create a Python script to scrape and process government decisions from the official Israeli government database:

* Base URL:

  ```
  https://www.gov.il/he/collectors/policies?Type=30280ed5-306f-4f0b-a11d-cacf05d36648
  ```
* Pagination format:

  ```
  https://www.gov.il/he/collectors/policies?Type=30280ed5-306f-4f0b-a11d-cacf05d36648&skip=10&limit=1000
  ```

## Required Data Extraction

Each decision URL should yield these parameters:

### Directly from the text

* `decision_date`: Specified after "תאריך פרסום:"
* `decision_number`: Specified clearly as "מספר החלטה:"
* `committee`: **Special extraction** - Text between "ועדות שרים:" and "ממשלה" (with optional space). Returns NULL if "ועדות שרים:" not found.
* `decision_title`: From the page content
* `decision_content`: Full textual content
* `decision_url`: The direct URL of the decision page
* `government_number`: Currently fixed as `37`
* `prime_minister`: Currently fixed as `בנימין נתניהו`
* `decision_key`: Concatenation of `government_number` and `decision_number` (e.g., `37_3719`)

### Generated via OpenAI GPT

* `summary`: Concise summary of the decision content
* `operativity`: Operational status or implications
* `tags_policy_area`: Policy areas related
* `tags_government_body`: Relevant government bodies
* `tags_location`: **Special handling** - Only actual geographic locations mentioned in text. Returns empty string if no locations found.
* `all_tags`: Aggregation of all decision tags

## Project Structure

**✅ FULLY IMPLEMENTED** - The project now includes a complete working implementation with unlimited sync capability:

```
GOV2DB/
├── sync_with_db_selenium.py       # 🌟 MAIN UNLIMITED SYNC - Use this!
├── run_overnight_sync.sh          # 🌙 Overnight script for large batches  
├── run_large_batch_sync.py        # 📦 Advanced large batch processor
├── data/                          # Output CSV files and scraped data
├── logs/                          # Comprehensive logging files
├── src/
│   ├── main_selenium.py           # Selenium-based scraper with AI
│   ├── catalog_scraper_selenium.py # JavaScript-aware URL extraction
│   ├── decision_scraper_selenium.py # Selenium decision page scraping
│   ├── ai_processor.py           # OpenAI integration with policy area validation
│   ├── incremental_processor.py   # Database-aware processing logic
│   ├── approval_manager.py        # User approval workflow  
│   ├── data_manager.py           # CSV generation and management
│   ├── config.py                 # Configuration and constants
│   ├── selenium_utils.py         # Selenium WebDriver utilities
│   └── db/                       # 🗄️ DATABASE INTEGRATION
│       ├── db_connector.py       # Supabase connection with env fixes
│       ├── dal.py               # Data access layer with batch operations
│       └── utils.py             # Database utilities
├── test_*.py                     # 🧪 Database integration test scripts
├── requirements.txt              # Updated with Selenium + Supabase dependencies
├── .env.example                 # Environment variables template
├── INTEGRATION_GUIDE.md         # Complete usage documentation
└── DATA_EXTRACTION_FIXES.md     # Details on committee/location fixes
```

## Current State

**🚀 PRODUCTION READY** - Fully implemented system with unlimited sync capability:

### Core Features ✅
- ✅ **Unlimited Sync**: Process all decisions until database baseline with no timeout
- ✅ **Selenium Integration**: Handles JavaScript-heavy government website  
- ✅ **Large Batch Processing**: Handle 350+ decision gaps overnight
- ✅ **Smart Scraping**: Only processes new decisions since last database update
- ✅ **Duplicate Prevention**: Automatic detection and skipping of existing decisions
- ✅ **Robust Error Recovery**: Continues processing even with individual failures
- ✅ **Data Quality Fixes**: Proper committee extraction and location tag handling
- ✅ **Environment Variable Fixes**: Proper .env loading from src/ directory

### Key Files
- `sync_with_db_selenium.py` - **MAIN ENTRY POINT** for unlimited database synchronization
- `run_overnight_sync.sh` - **OVERNIGHT SCRIPT** for large batch processing (no timeout)
- `test_connection_simple.py` - Quick database connection validation
- `INTEGRATION_GUIDE.md` - Complete usage instructions
- `DATA_EXTRACTION_FIXES.md` - Committee and location extraction fixes

## Data Schema

The system processes 19 fields per decision:
- **Direct extraction** (from Hebrew labels): `decision_date` (תאריך פרסום), `decision_number` (מספר החלטה), `committee` (ועדות שרים)
- **Fixed values**: `government_number` (37), `prime_minister` (בנימין נתניהו)
- **AI-generated**: `summary`, `operativity`, `tags_policy_area`, `tags_government_body`, `tags_location`, `all_tags`

## Quick Start Commands

**🎯 Daily Sync (3-15 decisions):**
```bash
# Setup environment (one time)
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys

# Daily unlimited sync (MAIN COMMAND)  
python sync_with_db_selenium.py --unlimited --no-approval

# With AI analysis (slower but complete)
python sync_with_db_selenium.py --unlimited --no-approval --verbose
```

**🌙 Large Batch Processing (350+ decisions):**
```bash
# Overnight sync - NO TIMEOUT, handles any size gap
nohup python sync_with_db_selenium.py --unlimited --no-approval --no-ai > logs/overnight.log 2>&1 &

# Use specialized overnight script
./run_overnight_sync.sh

# Monitor progress  
tail -f logs/overnight.log
```

**🧪 Testing & Validation:**
```bash
# Quick connection test
python test_connection_simple.py

# Test data extraction fixes
python test_fixes.py

# Limited test sync
python sync_with_db_selenium.py --max-decisions 5 --verbose
```

## Data Extraction Specifications

### Committee Field (`committee`)
**Critical Requirements:**
- Extract text between "ועדות שרים:" and "ממשלה" (handling both "ממשלה:" and " ממשלה:")
- Return `NULL` if "ועדות שרים:" label is not found in the decision
- Clean whitespace and remove trailing punctuation
- Example: "ועדת השרים לענייני חקיקה" → `"ועדת השרים לענייני חקיקה"`

### Location Tags (`tags_location`)
**Critical Requirements:**
- Only extract geographic locations explicitly mentioned in the decision text
- Return empty string (`""`) if no actual locations are found
- Filter out AI responses like "אין מקומות", "לא מוזכר", etc.
- Example: Decision mentioning "ירושלים ותל אביב" → `"ירושלים, תל אביב"`
- Example: General policy decision → `""` (empty)

## Implementation Details

**✅ All Critical Requirements Implemented:**

- **Unlimited Processing**: No timeout, processes until database baseline reached
- **Selenium Integration**: Handles JavaScript-heavy government website
- **Large Batch Capability**: Overnight processing of 350+ decisions  
- **Error Handling**: 5-retry logic with exponential backoff + robust recovery
- **Hebrew Text Processing**: Specialized committee extraction + Hebrew label parsing
- **Database Integration**: Supabase with duplicate prevention using `decision_key`
- **Incremental Processing**: Only scrape decisions newer than latest DB entry
- **Environment Variable Fixes**: Proper .env loading from src/ directory
- **Batch Operations**: Efficient database insertion with individual fallback
- **User Approval**: Interactive workflow with CSV preview
- **CSV Output**: UTF-8-BOM encoding for Hebrew compatibility
- **AI Integration**: GPT-3.5-Turbo with validated policy area tags
- **Comprehensive Logging**: All operations logged with timestamps

## Environment Variables (.env)

```bash
# Required for AI processing
OPENAI_API_KEY=your_openai_api_key_here

# Required for database integration  
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here
```

## Dependencies

**Core libraries:** `requests`, `beautifulsoup4`, `pandas`, `openai`, `python-dotenv`, `supabase`, `selenium`, `webdriver-manager`, `logging`

**See `requirements.txt` for complete list with versions.**

## Performance Specifications

### Processing Times
- **Daily Sync (3-15 decisions)**: 2-10 minutes with AI, 1-3 minutes without
- **Large Batch (350+ decisions)**: 30-90 minutes without AI, 3-5 hours with AI
- **Per Decision**: ~5-15 seconds (including AI processing)

### Capabilities  
- **No Timeout**: System runs until completion regardless of size
- **Baseline Detection**: Automatically stops when reaching latest DB decision
- **Overnight Processing**: Designed for unattended large batch operations
- **Memory Efficient**: Processes in batches to handle any volume
- **Network Resilient**: Robust retry logic for unreliable connections

## Development Notes

* To make sure, there is no use for the whole thing in "no-ai" mode, since its an important part of the scraping. dont even suggest it if not to test minor stuff