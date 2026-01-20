# CLAUDE.md - GOV2DB Israeli Government Decisions Scraper

## Project Overview

**Purpose:** Automated extraction, AI analysis, and storage of Israeli government decisions from gov.il
**Tech Stack:** Python 3.8+, Selenium, Supabase (PostgreSQL), OpenAI GPT-3.5-turbo, BeautifulSoup
**Language:** Hebrew (RTL) government content

---

## Quick Start Commands

```bash
make setup            # Initial setup (venv + dependencies)
make sync             # Daily sync - process all new decisions (regular mode)
make sync-test        # Quick test (1 decision, no approval)
make sync-dev         # Dev mode (5 decisions)
make test-conn        # Test database connection
make overnight        # Large batch (350+ decisions)

# Safety modes (see "Decision Discovery Logic" section below)
python bin/sync.py --unlimited --no-approval --safety-mode extra-safe  # Zero missed decisions
```

### Tag Migration Commands

```bash
make migrate-preview       # Preview on 10 records
make migrate-preview-n n=50  # Preview on N records
make migrate-dry           # Full dry-run (no DB changes)
make migrate-execute       # Execute migration (with confirmation)
```

---

## Project Structure

```
GOV2DB/
├── bin/                          # Executable scripts
│   ├── sync.py                   # Main orchestrator (8-step workflow)
│   ├── large_batch_sync.py       # Batch processor
│   ├── overnight_sync.sh         # Shell wrapper
│   └── migrate_tags.py           # Tag migration CLI
│
├── src/gov_scraper/              # Core package
│   ├── config.py                 # Configuration & env vars
│   ├── scrapers/
│   │   ├── catalog.py            # Extract decision URLs from catalog
│   │   └── decision.py           # Scrape individual decision pages
│   ├── processors/
│   │   ├── ai.py                 # OpenAI integration (summaries, tags)
│   │   ├── incremental.py        # Baseline & filtering logic
│   │   ├── approval.py           # User approval workflow
│   │   └── tag_migration.py      # Tag migration logic (one-time)
│   ├── db/
│   │   ├── connector.py          # Supabase client
│   │   ├── dal.py                # Data Access Layer
│   │   └── utils.py              # CSV utilities
│   └── utils/
│       ├── selenium.py           # WebDriver wrapper
│       └── data_manager.py       # Data handling
│
├── tests/                        # Test suite
├── docs/                         # Documentation
├── data/                         # CSV exports
├── logs/                         # Log files (scraper.log)
├── requirements.txt              # Dependencies
└── Makefile                      # Build commands
```

---

## Environment Variables (.env)

```bash
OPENAI_API_KEY=sk-proj-...              # Required - OpenAI API key
SUPABASE_URL=https://xxx.supabase.co    # Required - Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...   # Required - Service role JWT
```

---

## Core Algorithms

### 1. Web Scraping Pipeline

**Catalog Scraper** (`scrapers/catalog.py`):
- URL: `https://www.gov.il/he/collectors/policies`
- Waits 15s for JavaScript rendering
- Regex patterns for decision URLs:
  - `/he/pages/dec\d+[a-z]?-\d{4}[a-z]?`
  - Handles variations: `dec3284-2025`, `dec3173a-2025`, `dec3172-2025a`
- Returns URLs sorted by decision number (newest first)

**Decision Scraper** (`scrapers/decision.py`):
- Headless Chrome via Selenium
- Extracts: decision_number, date, title, committee, content, URL
- Hebrew date format: `DD.MM.YYYY` → `YYYY-MM-DD`
- Validates Hebrew content presence
- Cleans zero-width spaces and RTL marks

**URL Recovery** (3-tier fallback):
1. Try original URL
2. Search catalog for correct variant
3. Try URL variations (add 'a' suffix)

### 2. AI Processing Pipeline (`processors/ai.py`)

**Model:** GPT-3.5-turbo, Temperature: 0.3, Max retries: 5

#### Tag Sources (Updated):
- **Policy areas:** Loaded from `new_tags.md` (40 tags)
- **Government bodies:** Loaded from `new_departments.md` (44 departments)

#### Validation: 3-Step Algorithm

All tags go through strict 3-step validation to prevent hallucinations:

**Step 1: Exact Match**
- Tag exists verbatim in authorized list → Use it

**Step 2: Word-based Jaccard Similarity**
- Extract meaningful words (2+ chars, filter stop words: "ו", "ה", "של"...)
- Calculate Jaccard: `|intersection| / |union|`
- Threshold: >= 50%
- Handles word order variations: "חינוך ותרבות" = "תרבות וחינוך"

**Step 3: AI Summary Fallback**
- If steps 1-2 fail, ask GPT to analyze decision summary
- Prompt includes full authorized list
- Only accepts tags from authorized list
- Last resort before defaulting to "שונות" (policy) or empty (government)

#### Tag Generation Functions

| Function | Purpose | Validation | Output |
|----------|---------|------------|--------|
| `generate_summary()` | 1-2 sentence summary | N/A | Text |
| `generate_operativity()` | אופרטיבית/דקלרטיבית | N/A | Word |
| `generate_policy_area_tags_strict()` | Policy categories | **3-step** | 1-3 tags |
| `generate_government_body_tags_validated()` | Government entities | **3-step** | 1-3 tags |
| `generate_location_tags()` | Geographic locations | Filtered | Comma-sep |

**Key Improvement:** Both policy and government tags are now validated against authorized lists, preventing hallucinations.

### 3. Incremental Processing (`processors/incremental.py`)

```python
get_scraping_baseline()    # Get latest decision from DB
should_process_decision()  # Compare to baseline (date + number)
validate_decision_data()   # Check required fields
prepare_for_database()     # Format for insertion
```

**Logic:**
- No baseline → Process all
- Newer date → Process
- Same date, higher number → Process
- Older → Skip

### Decision Discovery Logic (Robust with Safety Modes)

**Problem:** Government website may publish decisions with lower numbers on later dates (e.g., same day publishing).

**Solution:** 3-layer defense against missing decisions, with configurable safety modes:

#### Safety Modes

**Regular Mode** (default) - Balanced efficiency:
- URL filtering by baseline year
- Efficient for daily syncs
- Minimal risk of missing decisions from same date

**Extra Safe Mode** (`--safety-mode extra-safe`) - Zero missed decisions:
- No URL filtering
- Processes all available URLs
- Guaranteed to catch all new decisions
- Use after long breaks or when suspicious of missed decisions

#### 3-Layer Defense (both modes)

1. **URL Extraction & Filtering**
   - Get 100 URLs in unlimited mode
   - Sort ascending by (date, number) for chronological processing
   - **Regular:** Filter by baseline year (e.g., keep 2026+ if baseline is 2026-01-01)
   - **Extra Safe:** No filtering - process all URLs

2. **Date-based Filtering** - `should_process_decision()` logic:
   ```
   IF decision_date > baseline_date:
       PROCESS (newer date)
   ELIF decision_date < baseline_date:
       SKIP (older date)
   ELSE (same date):
       IF decision_number > baseline_number:
           PROCESS (higher number, same date)
       ELSE:
           SKIP (lower or equal number, same date)
   ```

3. **Duplicate Prevention** - `check_existing_decision_keys()`
   - Query DB for decision_key (format: `{gov_num}_{decision_num}`)
   - Filter out existing decisions before insertion
   - Safety net against re-insertion

**Edge Cases Handled:**
- ✅ Same date, multiple decisions, published out of order
- ✅ Decision number lower than baseline but date is newer (both modes)
- ✅ Old decision updated recently (extra-safe mode)
- ✅ Decision already exists in DB (via decision_key check)

**Usage Examples:**
```bash
# Daily sync (regular mode - efficient)
python bin/sync.py --unlimited --no-approval

# After long break (extra safe mode)
python bin/sync.py --unlimited --no-approval --safety-mode extra-safe

# Testing with extra safety
python bin/sync.py --max-decisions 10 --safety-mode extra-safe
```

### 4. Database Operations (`db/dal.py`)

**Table:** `israeli_government_decisions`

| Field | Type | Description |
|-------|------|-------------|
| decision_key | STRING (UNIQUE) | `{gov_num}_{decision_num}` |
| decision_number | STRING | Official ID |
| decision_date | DATE | YYYY-MM-DD |
| decision_title | TEXT | Headline |
| decision_content | TEXT | Full Hebrew text |
| summary | TEXT | AI summary |
| operativity | STRING | Classification |
| tags_policy_area | TEXT | Policy tags |
| tags_government_body | TEXT | Government entities |
| tags_location | TEXT | Locations |
| government_number | INT | 37 (current) |
| prime_minister | STRING | בנימין נתניהו |

**Batch Insertion:**
- 50 decisions per transaction
- Falls back to individual insertion on batch failure
- Automatic duplicate detection via decision_key

---

## Main Workflow (bin/sync.py)

```
Step 0: Validate OpenAI API Key
Step 1: Get Database Baseline
Step 2: Extract Decision URLs (100 for unlimited)
Step 3: Filter & Sort URLs (ascending by date/number)
Step 4: Process Decisions (scrape + AI)
Step 5: Prepare for Database
Step 6: Check for Duplicates
Step 7: User Approval (unless --no-approval)
Step 8: Database Insertion
```

**CLI Arguments:**
```bash
--max-decisions N           # Limit decisions
--unlimited                 # Process all until baseline
--no-approval               # Skip confirmation
--verbose                   # Debug logging
--safety-mode MODE          # regular (default) or extra-safe
```

---

## Key Files to Modify

### For Scraping Changes:
- [scrapers/catalog.py](src/gov_scraper/scrapers/catalog.py) - URL extraction patterns
- [scrapers/decision.py](src/gov_scraper/scrapers/decision.py) - Page parsing logic

### For AI Algorithm Changes:
- [processors/ai.py](src/gov_scraper/processors/ai.py) - Prompts, tag validation, retry logic

### For Database Schema:
- [db/dal.py](src/gov_scraper/db/dal.py) - CRUD operations
- [db/connector.py](src/gov_scraper/db/connector.py) - Connection setup

### For Configuration:
- [config.py](src/gov_scraper/config.py) - URLs, headers, fixed values

---

## Fixed Values (config.py)

```python
GOVERNMENT_NUMBER = 37
PRIME_MINISTER = "בנימין נתניהו"
BASE_CATALOG_URL = 'https://www.gov.il/he/collectors/policies'
OPENAI_MODEL = 'gpt-3.5-turbo'
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds
```

---

## Authorized Tags

Policy area tags and government bodies are defined in external files:

- **Policy Areas:** See [new_tags.md](new_tags.md) (40 tags)
- **Government Bodies:** See [new_departments.md](new_departments.md) (44 departments)

These files are the source of truth for tag validation and migration.

---

## Hebrew Text Handling

**Cleaning Operations:**
```python
# Remove zero-width spaces
text.replace('\u200b', '')
# Remove RTL/LTR marks
text.replace('\u200e', '').replace('\u200f', '')
# Normalize whitespace
' '.join(text.split())
```

**Date Format Conversion:**
```python
# Input: "24.07.2025"
datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
# Output: "2025-07-24"
```

---

## Error Handling

| Layer | Strategy |
|-------|----------|
| URL Scraping | 3-tier recovery (original → catalog search → variations) |
| OpenAI API | 5 retries with exponential backoff (2s × attempt) |
| Database | Batch fails → individual insertion fallback |
| Validation | Skip decision if critical fields missing |

---

## Performance

- **Speed:** 5-10 decisions/minute (with AI)
- **AI Processing:** ~20-30 seconds/decision
- **Batch Size:** 50 decisions per DB transaction
- **Capacity:** 350+ decisions in overnight batch

---

## Testing

```bash
make test           # All tests
make test-conn      # Database connection
pytest tests/       # Run with pytest
```

---

## Logging

- **File:** `logs/scraper.log` (UTF-8)
- **Format:** Timestamp + level + message
- **Console:** Also outputs to terminal

---

## Common Modifications

### Add New Policy Area Tag
Edit `POLICY_AREAS` list in [processors/ai.py](src/gov_scraper/processors/ai.py:30-70)

### Change AI Model
Edit `OPENAI_MODEL` in [config.py](src/gov_scraper/config.py) or set env var

### Modify Scraping Patterns
Edit regex in `extract_decision_urls_from_catalog_selenium()` in [catalog.py](src/gov_scraper/scrapers/catalog.py)

### Add Database Field
1. Add to Supabase table
2. Update `prepare_for_database()` in [incremental.py](src/gov_scraper/processors/incremental.py)
3. Update `insert_decisions_batch()` in [dal.py](src/gov_scraper/db/dal.py)

### Change Summary Prompt
Edit `generate_summary()` prompt in [processors/ai.py](src/gov_scraper/processors/ai.py)

---

## Data Flow

```
gov.il → Selenium → Catalog Scraper → Decision Scraper
                                           ↓
                                    URL Recovery
                                           ↓
                                    Validation
                                           ↓
                                    AI Processing
                                           ↓
                                    Incremental Filter
                                           ↓
                                    User Approval
                                           ↓
                                    Supabase DB
```

---

## Tag Migration System (Completed December 2024)

One-time migration tool to update `tags_policy_area` and `tags_government_body` fields to new standardized values.

### Migration Status: ✅ COMPLETED

| Metric | Value |
|--------|-------|
| Total Records | 24,919 (1993-2025) |
| Records Updated | 24,853 (99.7%) |
| Total Mappings | 55,922 |
| Runtime | 3h 30m |
| Fallback Rate | 0.3% (180 records) |

### Mapping Results by Method

| Method | Count | % | Description |
|--------|-------|---|-------------|
| Exact Match | 10,363 | 18.5% | Tag exists verbatim in new list |
| Substring Match | 6,449 | 11.5% | "משרד ה" prefix matching |
| Word Overlap | 4,569 | 8.2% | Jaccard similarity >= 50% |
| AI Tag Match | 32,288 | 57.7% | GPT-3.5 semantic match by tag name |
| AI Summary | 2,073 | 3.7% | GPT-3.5 analysis of decision summary |
| Fallback | 180 | 0.3% | Defaulted to "שונות" |

### Source Files

- **New policy tags:** `new_tags.md` (40 tags)
- **New departments:** `new_departments.md` (44 departments)

### 6-Step Mapping Algorithm

| Step | Method | Description |
|------|--------|-------------|
| 1 | Exact Match | Tag exists in new list |
| 2 | Substring Match | "משרד ה" prefix matching with high confidence |
| 3 | Word Overlap | Jaccard similarity >= 50% (same words, different order) |
| 4 | AI Tag Match | GPT-3.5 semantic matching by tag name |
| 5 | AI Summary | GPT-3.5 analysis of decision summary (per-record) |
| 6 | Fallback | Default to "שונות" |

### Usage

```bash
# Step 1: Preview on 10 records (mandatory first step)
make migrate-preview

# Step 2: Full dry-run (no DB changes, generates report)
make migrate-dry

# Step 3: Execute migration
make migrate-execute
```

### CLI Options

```bash
python bin/migrate_tags.py preview --count 50           # Custom count
python bin/migrate_tags.py dry-run --start-date 2024-01-01  # Filter by date
python bin/migrate_tags.py execute --count 100 --batch-size 20  # Limit + batch
python bin/migrate_tags.py execute --yes               # Skip confirmation
```

### Filter Options

| Option | Description | Example |
|--------|-------------|---------|
| `--count N` | Limit records | `--count 100` |
| `--start-date` | From date (YYYY-MM-DD) | `--start-date 2024-01-01` |
| `--end-date` | Until date | `--end-date 2024-12-31` |
| `--prefix` | Decision key prefix | `--prefix 37_` |
| `--batch-size` | Update batch size | `--batch-size 20` |

### Output Files

Generated in `data/` directory:
- `backup_YYYYMMDD_HHMMSS.csv` - Full backup before changes
- `migration_report_YYYYMMDD.json` - Detailed statistics
- `dry_run_report_YYYYMMDD.json` - Dry-run results

### Key Files

- [bin/migrate_tags.py](bin/migrate_tags.py) - CLI script for single runs
- [bin/migrate_all_years.py](bin/migrate_all_years.py) - Year-by-year migration runner
- [processors/tag_migration.py](src/gov_scraper/processors/tag_migration.py) - Core logic (6-step algorithm)
- [new_tags.md](new_tags.md) - Policy area tags list (40 tags)
- [new_departments.md](new_departments.md) - Department names list (44 departments)

### Year-by-Year Migration

For large-scale migrations, use the year-by-year runner:

```bash
# Run all years (2024→1993)
python bin/migrate_all_years.py --yes

# Run specific year range
python bin/migrate_all_years.py --start-year 2020 --end-year 2015

# Dry-run (no DB changes, generates reports)
python bin/migrate_all_years.py --dry-run

# Background execution
nohup python bin/migrate_all_years.py --yes > logs/migration_output.log 2>&1 &
```

### Multi-Tag Support

The migration system supports returning multiple tags (up to 3) when AI determines multiple are clearly relevant:

- **Exact/Substring/Word Overlap:** Always returns single tag
- **AI Tag Match:** May return 1-3 tags if semantically appropriate
- **AI Summary Match:** May return 1-3 tags based on decision content
- **Deduplication:** Automatic removal of duplicate tags in final output

---

## Dependencies

**Core:**
- selenium 4.34.2
- beautifulsoup4 4.12.2
- supabase 2.17.0
- openai 1.97.1
- pandas 2.2.0+

**Utilities:**
- webdriver-manager 4.0.2
- python-dotenv 1.0.0
- requests 2.31.0
- lxml 5.0.0+

---

## Security Notes

- Never commit `.env` file
- Use service role key for Supabase (not user key)
- Rotate API keys regularly
- All credentials via environment variables

---

## Upgrading the Algorithm

### To Improve AI Quality:
1. Edit prompts in [ai.py](src/gov_scraper/processors/ai.py)
2. Adjust temperature (lower = more consistent)
3. Increase max_tokens for longer outputs
4. Add few-shot examples in prompts

### To Add New Tags:
1. Create new `generate_X_tags()` function in [ai.py](src/gov_scraper/processors/ai.py)
2. Add field to database schema
3. Update `process_decision_with_ai()` to call new function
4. Update `prepare_for_database()` in [incremental.py](src/gov_scraper/processors/incremental.py)

### To Improve Scraping:
1. Update regex patterns in [catalog.py](src/gov_scraper/scrapers/catalog.py)
2. Add new CSS selectors in [decision.py](src/gov_scraper/scrapers/decision.py)
3. Increase wait times if pages fail to load

### To Change Database:
1. Modify Supabase table structure
2. Update [dal.py](src/gov_scraper/db/dal.py) queries
3. Update field mappings in [incremental.py](src/gov_scraper/processors/incremental.py)
