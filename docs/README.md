# Israeli Government Decisions Scraper with Database Integration 🏛️

A comprehensive web scraper that extracts and processes Israeli government decisions from the official government website (gov.il), with **Supabase database integration** for unlimited incremental processing and automated content analysis using AI.

## ✅ Current Status

**🚀 PRODUCTION READY** - Fully implemented system with database integration, unlimited sync capability, and quality data extraction fixes.

**🎯 Key Features**:
- ✅ **Unlimited Sync**: Process all decisions until database baseline with no timeout
- ✅ **Selenium Integration**: Handles JavaScript-heavy government website  
- ✅ **Smart Scraping**: Only processes new decisions since last database update  
- ✅ **Duplicate Prevention**: Automatic detection and skipping of existing decisions
- ✅ **Large Batch Processing**: Handle 350+ decision gaps overnight
- ✅ **Data Quality Fixes**: Proper committee extraction and location tag handling
- ✅ **AI-Powered Analysis**: GPT-3.5-turbo with 37 authorized Hebrew policy tags
- ✅ **Robust Error Recovery**: Continues processing even with individual failures

## 🚀 Quick Start

### Daily Sync (Recommended)
```bash
# Setup (one time)
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys

# Daily sync - unlimited processing until baseline
python sync_with_db_selenium.py --unlimited --no-approval
```

### Large Gap Processing (350+ decisions)
```bash
# Overnight sync for large decision gaps - NO TIMEOUT 
nohup python sync_with_db_selenium.py --unlimited --no-approval --no-ai > logs/overnight.log 2>&1 &

# Or use the specialized overnight script
./run_overnight_sync.sh
```

### Key Commands:
- **🌙 Overnight Sync**: `./run_overnight_sync.sh` - For large batches, no timeout
- **⚡ Daily Sync**: `python sync_with_db_selenium.py --unlimited --no-approval` 
- **🔧 With AI**: Add `--verbose` for full AI analysis (slower)
- **📊 Limited**: Use `--max-decisions 20` for testing small batches

## 📁 Project Structure

```
GOV2DB/
├── 🌟 sync_with_db_selenium.py     # MAIN UNLIMITED SYNC - Use this!
├── 🌙 run_overnight_sync.sh        # Overnight script for large batches
├── 📦 run_large_batch_sync.py      # Advanced large batch processor  
├── 📋 src/main_selenium.py         # Selenium-based scraper with AI
├── 🔍 src/catalog_scraper_selenium.py  # JavaScript-aware URL extraction
├── 📄 src/decision_scraper_selenium.py # Selenium decision scraping
├── 🤖 src/ai_processor.py          # OpenAI integration with validation  
├── ⚙️ src/incremental_processor.py # Database-aware processing logic
├── 👤 src/approval_manager.py      # User approval workflow
├── 💾 src/data_manager.py          # CSV generation and management
├── 🗄️ src/db/                      # DATABASE INTEGRATION
│   ├── db_connector.py             # Supabase connection with env fixes
│   ├── dal.py                      # Data access layer with batch operations
│   └── utils.py                    # Database utilities
├── 📊 data/                        # Output CSV files and scraped data
├── 📝 logs/                        # Comprehensive logging files  
├── 🧪 test_*.py                    # Database integration test scripts
├── 🔧 .env.example                 # Environment variables template
└── 📚 Various .md files            # Documentation and guides
```

## 🎯 What This System Does

### Complete Database-Integrated Pipeline:

1. **📊 Database Query**: Fetches latest decision from Supabase as baseline
2. **🔍 Smart Scraping**: Only processes decisions newer than baseline  
3. **📄 Content Extraction**: Extracts Hebrew text with proper committee/location handling
4. **🤖 AI Analysis**: Generates summaries and policy tags using GPT-3.5-turbo
5. **👤 User Approval**: Shows preview and requests confirmation
6. **💾 Database Insertion**: Safely inserts new decisions with duplicate prevention
7. **📈 Audit Trail**: Complete logging of all operations

## 📊 Data Schema (19 Fields)

| Field | Description | Example |
|-------|-------------|---------|
| `decision_date` | Date (YYYY-MM-DD) | 2025-07-24 |
| `decision_number` | Government decision number | 3284 |
| `committee` | **Fixed**: Text between "ועדות שרים:" and "ממשלה", NULL if not found | ועדת השרים לענייני חקיקה |
| `decision_title` | Full Hebrew title | תקנות שעת חירום... |
| `decision_content` | Complete Hebrew content | מזכירות הממשלה... |
| `decision_url` | Source URL | https://www.gov.il/he/pages/dec3284-2025 |
| `summary` | AI-generated Hebrew summary | ההחלטה מאפשרת... |
| `operativity` | Operational classification | אופרטיבית / דקלרטיבית |
| `tags_policy_area` | Policy area tags (37 authorized) | מדיניות ממשלתית |
| `tags_government_body` | Government body tags | הממשלה |
| `tags_location` | **Fixed**: Only explicit locations, empty if none | ירושלים, תל אביב |
| `all_tags` | Combined tags | מדיניות ממשלתית; הממשלה |
| `government_number` | Current government | 37 |
| `prime_minister` | Current PM | בנימין נתניהו |
| `decision_key` | Unique identifier | 37_3284 |

## 🔧 Environment Setup

Create `.env` file with:
```bash
# Required for AI processing
OPENAI_API_KEY=your_openai_api_key_here

# Required for database integration
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here
```

## 📋 Usage Examples

### ⚡ Daily Sync (3-15 decisions)
```bash
# Quick daily sync
python sync_with_db_selenium.py --unlimited --no-approval

# With full AI analysis (slower)
python sync_with_db_selenium.py --unlimited --no-approval --verbose
```

### 🌙 Large Gap Processing (350+ decisions)
```bash
# Overnight processing - NO TIMEOUT
nohup python sync_with_db_selenium.py --unlimited --no-approval --no-ai > logs/overnight.log 2>&1 &

# Monitor progress
tail -f logs/overnight.log

# Specialized overnight script
./run_overnight_sync.sh
```

### 🧪 Testing & Validation
```bash
# Test database connection
python test_connection_simple.py

# Test data extraction fixes  
python test_fixes.py

# Limited sync for testing
python sync_with_db_selenium.py --max-decisions 5 --verbose
```

### 📊 Performance Options
```bash
# Fast mode (no AI) - ~30-60 minutes for 350 decisions
python sync_with_db_selenium.py --unlimited --no-approval --no-ai

# Complete mode (with AI) - ~3-5 hours for 350 decisions  
python sync_with_db_selenium.py --unlimited --no-approval --verbose
```

## 🛡️ Data Quality Fixes

### Committee Extraction ✅
- **Fixed**: Extracts text between "ועדות שרים:" and "ממשלה" (with optional space)
- **Fixed**: Returns NULL if committee section doesn't exist
- **Example**: "ועדת השרים לענייני חקיקה" extracted correctly

### Location Tags ✅  
- **Fixed**: Only extracts actual geographic locations mentioned in text
- **Fixed**: Returns empty string when no locations found
- **Example**: Generic policy decisions now correctly return "" instead of irrelevant text

## 🗄️ Database Integration Features

- **✅ Incremental Processing**: Only scrape decisions newer than latest in DB
- **✅ Duplicate Prevention**: Uses `decision_key` uniqueness to prevent overwrites
- **✅ Batch Operations**: Efficient insertion with individual fallback on errors
- **✅ Transaction Safety**: Failed batches don't affect successful ones
- **✅ User Control**: Manual approval required before any database changes
- **✅ Audit Trail**: Complete logging of all database operations

## 🏷️ AI-Powered Analysis

### Policy Area Tags (37 Authorized Categories)
The system uses strict classification with authorized Hebrew policy areas:

- **ביטחון לאומי וצבא** - National Security & Military
- **כלכלה מאקרו ותקציב** - Macroeconomics & Budget  
- **חינוך** - Education
- **בריאות ורפואה** - Health & Medicine
- **טכנולוגיה, חדשנות ודיגיטל** - Technology, Innovation & Digital
- **מדיניות ממשלתית** - Government Policy
- **שונות** - Miscellaneous
- ... and 30 more categories

### Smart AI Processing
- **Summarization**: Concise Hebrew summaries
- **Operativity Analysis**: אופרטיבית vs. דקלרטיבית classification
- **Tag Validation**: Maps AI responses to authorized policy areas
- **Error Recovery**: Falls back gracefully on AI failures

## 📈 Performance & Monitoring

- **Processing Speed**: ~5-10 decisions per minute
- **Log Files**: Comprehensive logging in `logs/` directory  
- **CSV Previews**: Generated in `data/` for user review
- **Success Tracking**: Real-time statistics and progress indicators
- **Error Handling**: Robust retry logic and fallback mechanisms

## 🐛 Troubleshooting

### Common Issues

**Database Connection Error:**
```bash
# Check your .env file has correct Supabase credentials
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_key
```

**No New Decisions Found:**
```bash
# Normal behavior - database is up to date
# Check logs for baseline decision info
```

**Committee Extraction Issues:**
```bash
# Run test script to verify fixes
python3 test_fixes.py
```

## 📚 Documentation

- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - Complete usage instructions
- **[DATA_EXTRACTION_FIXES.md](DATA_EXTRACTION_FIXES.md)** - Committee and location fixes
- **[CLAUDE.md](CLAUDE.md)** - Developer guidance and specifications

## 🎯 Best practices

1. **Regular Syncing**: Run daily/weekly to keep database current
2. **Review Previews**: Always check CSV preview before approving  
3. **Monitor Logs**: Keep eye on error messages and success rates
4. **Backup Database**: Regular backups before large imports
5. **Test Changes**: Use small `--max-decisions` values when testing

---

**🚀 Ready for Production Use** - The system is fully implemented and tested with real government data, providing reliable incremental processing with comprehensive safety features.

🇮🇱 **Built for Israeli Government Decision Analysis & Transparency**