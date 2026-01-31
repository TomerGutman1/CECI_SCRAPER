# CLAUDE.md - GOV2DB Israeli Government Decisions Scraper

## Project Overview

**Purpose:** Automated extraction, AI analysis, and storage of Israeli government decisions from gov.il
**Tech Stack:** Python 3.8+, Selenium, Supabase (PostgreSQL), Google Gemini 2.0 Flash, BeautifulSoup
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
│   │   ├── ai.py                 # Gemini integration (summaries, tags)
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
├── docker/                       # Docker infrastructure
│   ├── docker-entrypoint.sh      # Container entry point
│   ├── healthcheck.sh            # Health monitoring
│   ├── crontab                   # Daily sync schedule (02:00 AM)
│   └── logrotate.conf            # Log rotation config
│
├── tests/                        # Test suite
├── data/                         # CSV exports & migration reports
├── logs/                         # Log files (scraper.log, daily_sync.log)
├── Dockerfile                    # Container definition
├── SERVER-OPERATIONS.md          # Production server operations guide
├── new_tags.md                   # Authorized policy tags (40)
├── new_departments.md            # Authorized government bodies (44)
├── requirements.txt              # Dependencies
└── Makefile                      # Build commands
```

---

## Environment Variables (.env)

```bash
GEMINI_API_KEY=AIzaSy...                # Required - Google Gemini API key
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

**Model:** Gemini 2.0 Flash, Temperature: 0.3, Max retries: 5

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
- If steps 1-2 fail, ask Gemini to analyze decision summary
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
Step 0: Validate Gemini API Key
Step 1: Extract Decision URLs (100 for unlimited)
Step 2: Filter to new entries (key-based DB check)
Step 3: Process Decisions:
  3a: Scrape content with URL recovery
  3b: Validate scraped content (pre-AI blocking)
      - Cloudflare detection → retry with longer wait (max 2 retries)
      - Short content (<40 chars) → retry
      - No Hebrew content → skip
  3c: Process with AI (summaries, tags, operativity)
  3d: Apply algorithmic fixes ($0 cost)
      - Fix operativity typos (OPERATIVITY_TYPO_MAP)
      - Remove hallucinated locations not in content
      - Remove hallucinated government bodies not in text
  3e: Inline validation warnings (non-blocking)
Step 4: Prepare for Database
Step 5: Safety duplicate check
Step 6: User Approval (unless --no-approval)
Step 7: Database Insertion
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
GEMINI_MODEL = 'gemini-2.0-flash'
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
| Gemini API | 5 retries with exponential backoff (2s × attempt) |
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
Edit `GEMINI_MODEL` in [config.py](src/gov_scraper/config.py) or set env var

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
| AI Tag Match | 32,288 | 57.7% | AI semantic match by tag name |
| AI Summary | 2,073 | 3.7% | AI analysis of decision summary |
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
| 4 | AI Tag Match | AI semantic matching by tag name |
| 5 | AI Summary | AI analysis of decision summary (per-record) |
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

## QA System

Quality assurance system for detecting and fixing data quality issues across all ~25K records.
Full lessons-learned document: **[QA-LESSONS.md](QA-LESSONS.md)**

### Current Status (January 2026)

**Phase:** 20 scanners built (Phase 1-4). 8 fixers available. Algorithmic fixes completed. AI fixes in progress.

#### Completed Algorithmic Improvements (January 31, 2026)

**Algorithm enhancements (before fixing):**
- `_word_in_text()` rewritten with 6-tier matching: exact → prefix-stripped → suffix-stripped → stem → prefix-added → combined
- `_strip_hebrew_prefix()` improved: double prefix stripping (e.g., "שבביטחון" → "בביטחון" → "ביטחון")
- `_strip_hebrew_suffix()` added: handles ים, ות, ן, ית, יים, יות suffixes
- `_is_body_in_text()` updated: uses `_word_in_text()` for abbreviations + "המשרד ל..." pattern
- `_is_body_semantically_relevant()` added: infers body relevance from policy tags via TAG_BODY_MAP reverse lookup + keyword evidence
- `BODY_TO_TAGS_MAP` added: reverse mapping of TAG_BODY_MAP for semantic inference
- `POLICY_TAG_KEYWORDS` expanded: +42 keywords across 7 tags with low coverage
- `BODY_ABBREVIATIONS` expanded: +13 historical names for 7 bodies (e.g., "משרד המסחר והתעשייה" → "משרד הכלכלה והתעשייה")

**Improvement impact (482 stratified sample, seed=42):**

| Metric | Baseline | Post-Improvement | Change |
|--------|----------|-----------------|--------|
| Total issues | 1,489 | 1,369 | -8% |
| HIGH severity | 829 | 723 | -13% |
| policy-relevance | 257 (53.8%) | 175 (36.6%) | -32% |
| location-hallucination | 23 (21.9%) | 9 (8.6%) | -61% |

#### Completed Algorithmic Fixes ($0, no AI)

| Fix | Records Fixed | Errors | Date |
|-----|--------------|--------|------|
| `operativity-typos` | 17 | 0 | 2026-01-31 |
| `locations` | 390 | 0 | 2026-01-31 |
| `government-bodies` | 12,457 | 0 | 2026-01-31 |

**Post-fix scan results (482 stratified sample, seed=42):**

| Metric | Baseline | Post-Fix | Change |
|--------|----------|----------|--------|
| Total issues | 1,489 | 673 | **-55%** |
| HIGH severity | 829 | 217 | **-74%** |
| location-hallucination | 23 | 0 | **-100%** |
| gov-body-hallucination | 506 | 0 | **-100%** |
| operativity-validity | 5 | 0 | **-100%** |
| body-default | 93 | 3 | **-97%** |
| tag-body consistency | 164 | 109 | **-34%** |
| title-vs-content | 6 | 3 | **-50%** |

#### Completed AI Fixes (January 31, 2026)

| Fix | Records Fixed | Errors | Cost |
|-----|--------------|--------|------|
| `policy-tags` (שונות records) | 9 | 0 | ~$0.01 |
| `policy-tags-defaults` (תרבות וספורט) | 918 | 0 | ~$0.10 |
| `government-bodies-ai` (default combos) | 483 | 0 | ~$0.05 |
| `summaries` (too short/long) | 590 | 1 | ~$0.06 |
| `operativity` (keyword mismatches) | 1,322 | 0 | ~$0.15 |

**Final post-fix scan results (482 stratified sample, seed=42):**

| Metric | Baseline | After Algo Fixes | **After AI Fixes** | Total Change |
|--------|----------|-----------------|-------------------|-------------|
| Total issues | 1,489 | 673 | **585** | **-61%** |
| HIGH severity | 829 | 217 | **164** | **-80%** |
| location-hallucination | 23 | 0 | **0** | -100% |
| gov-body-hallucination | 506 | 0 | **2** | -99.6% |
| operativity-validity | 5 | 0 | **0** | -100% |
| operativity-vs-content | 41 | 26 | **1** | **-97.6%** |
| body-default | 93 | 3 | **0** | **-100%** |
| policy-default | 27 | 27 | **0** | **-100%** |
| summary-quality | 8 | 8 | **0** | **-100%** |
| policy-relevance | 257 | 183 | 164 | -36% |
| tag-body | 164 | 109 | 106 | -35% |

#### Remaining Issues (informational / require manual review)

| Issue | Count (sample) | Severity | Notes |
|-------|---------------|----------|-------|
| Policy tag ↔ content mismatch | 164 (34.3%) | HIGH | Residual — many are borderline/semantic matches |
| Tag-body consistency | 106 (34.1%) | LOW | Cross-ministry decisions are normal |
| Summary vs tags | 280 (58.2%) | LOW | Informational only — summaries too short for keywords |
| Content quality (short) | 4 (0.8%) | MEDIUM | Need re-scraping |
| Tag consistency | 5 (1.0%) | MEDIUM | "שונות" as unauthorized body tag |

### Architecture

- **Scanner**: Read-only analysis — detects issues and produces JSON reports
- **Fixer**: Batch update operations (preview → dry-run → execute) to correct issues
- **Inline validation**: Lightweight checks in the sync pipeline (warnings only, does not block)
- **Hebrew-aware matching**: `_word_in_text()` with 6-tier matching — prefix stripping (ב,ל,מ,ה,ו,כ,ש × 2), suffix stripping (ים,ות,ן,ית,יים,יות), stemming, and prefix-added variants
- **Semantic inference**: `_is_body_semantically_relevant()` — preserves government bodies linked to assigned policy tags via TAG_BODY_MAP or keyword evidence (≥2 keyword hits)

### Key Files

- [processors/qa.py](src/gov_scraper/processors/qa.py) - Core QA logic (scanners, fixers, keyword dictionaries)
- [bin/qa.py](bin/qa.py) - QA CLI script
- [QA-LESSONS.md](QA-LESSONS.md) - Lessons learned and known issues

### Quick Commands

```bash
# Scanning (read-only, no AI cost, no DB changes)
make qa-scan                          # Full scan (all 20 checks)
make qa-scan-check check=operativity  # Single check
make qa-scan-check check=cross-field  # All cross-field checks
make qa-scan-check check=body-default # Detect body default patterns
make qa-scan-check check=policy-default # Detect policy default patterns
make qa-scan-check check=operativity-validity # Detect corrupted operativity

# Stratified sampling (representative sample across all years, no AI cost)
python bin/qa.py scan --stratified                           # ~5K records (20% per year)
python bin/qa.py scan --stratified --sample-percent 60       # ~15K records (60% per year)
python bin/qa.py scan --stratified --seed 42                 # Reproducible sampling
python bin/qa.py scan --stratified --check body-default      # Stratified + specific check

# Fixing (preview → dry-run → execute pattern)
make qa-fix-preview check=operativity      # Preview on 10 records (shows old vs new)
make qa-fix-dry check=operativity          # Full dry-run (no DB changes, generates report)
make qa-fix-execute check=operativity      # Execute fix (updates DB, with confirmation)

# New fixers
python bin/qa.py fix operativity-typos preview              # Preview typo fix ($0)
python bin/qa.py fix government-bodies-ai preview           # Preview AI body re-tag
python bin/qa.py fix policy-tags-defaults preview            # Preview default policy fix
python bin/qa.py fix government-bodies-ai preview --from-report data/qa_reports/flagged_body_hallucination.json

# Direct CLI with more options
python bin/qa.py scan --count 500 --verbose              # Limit to 500 records
python bin/qa.py scan --check policy-relevance --count 50 # Specific check
python bin/qa.py fix operativity preview                  # Preview fix
python bin/qa.py fix locations execute --yes               # Execute without confirmation
```

### Available Checks (20 total)

**Phase 1 — Core quality (high impact):**

| Check | What it does | Algorithm |
|-------|-------------|-----------|
| `operativity` | Distribution bias (too many operative?) | Count distribution |
| `policy-relevance` | Policy tags match content keywords | Hebrew keyword dict (40 tags × 10-25 keywords) |
| `policy-fallback` | Rate of "שונות" as sole tag | Count |

**Phase 2 — Cross-field consistency:**

| Check | What it does | Algorithm |
|-------|-------------|-----------|
| `operativity-vs-content` | Operative/declarative keywords match classification | Keyword evidence comparison |
| `tag-body` | Policy tag ↔ government body consistency | TAG_BODY_MAP lookup (single-tag records only) |
| `committee-tag` | Committee name ↔ policy tag consistency | COMMITTEE_TAG_MAP lookup |
| `location-hallucination` | Locations actually appear in content | Substring match in content |
| `government-body-hallucination` | Bodies mentioned in content | BODY_ABBREVIATIONS + minister title patterns |
| `summary-quality` | Summary length/quality checks | Length bounds (20-500 chars) |

**Phase 3 — Data integrity:**

| Check | What it does | Algorithm |
|-------|-------------|-----------|
| `summary-vs-tags` | Summary reflects assigned tags (informational) | Keyword match in summary |
| `location-vs-body` | Location ↔ government body consistency | LOCATION_BODY_MAP lookup |
| `date-vs-government` | Date matches government number | Gov 37 started 2022-12-29 |
| `title-vs-content` | Title keywords in content | Hebrew prefix-aware word matching |
| `date-validity` | Date in valid range (1948–today) | Range check |
| `content-quality` | Cloudflare pages, short content, nav text | Pattern matching |
| `tag-consistency` | Tags in authorized lists | Set membership check |
| `content-completeness` | Content not truncated | Sentence-ending heuristics |

**Phase 4 — Default/fallback pattern detection:**

| Check | What it does | Algorithm |
|-------|-------------|-----------|
| `body-default` | Detect AI-assigned default body combos (משרד הרווחה, trio combos) | SUSPICIOUS_BODY_COMBOS + keyword check |
| `policy-default` | Detect AI-assigned default policy tag (תרבות וספורט) | SUSPICIOUS_POLICY_TAGS + keyword check |
| `operativity-validity` | Detect corrupted/invalid operativity values (typos, encoding) | VALID_OPERATIVITY_VALUES + OPERATIVITY_TYPO_MAP |

### Available Fixers

| Fixer | What it does | AI Cost | Algorithm |
|-------|-------------|---------|-----------|
| `operativity` | Re-classify with improved prompt + keyword evidence | ~$2-5 for 25K | Gemini |
| `policy-tags` | Re-tag שונות-only and low-relevance records | ~$1-3 | Gemini |
| `locations` | Remove locations not found in text | **$0** | Text filter |
| `government-bodies` | Remove bodies not found in text | **$0** | Text filter + BODY_ABBREVIATIONS |
| `summaries` | Re-generate short/identical summaries | ~$1-3 | Gemini |
| `operativity-typos` | Fix corrupted operativity values via typo map | **$0** | OPERATIVITY_TYPO_MAP lookup |
| `government-bodies-ai` | AI re-tag bodies flagged as defaults/hallucinations | ~$3-8 | generate_government_body_tags_validated() |
| `policy-tags-defaults` | AI re-tag policy for "תרבות וספורט" defaults | ~$1-3 | generate_policy_area_tags_strict() |
| `cloudflare` | Re-scrape Cloudflare-blocked records + regenerate all AI fields | ~$0.50-$1 | Selenium re-scrape + process_decision_with_ai() |

### Pipeline Integration

QA checks are integrated into the sync pipeline at 3 stages:

**Stage 1: Pre-AI Content Validation (BLOCKING)** — `validate_scraped_content()`
- Cloudflare challenge page detection → retry with longer wait (25s, 35s)
- Short content (<40 chars) → retry
- No Hebrew content → skip
- Navigation text captured → retry
- Up to 2 retries before skipping. Prevents wasting AI credits on garbage content.

**Stage 2: Post-AI Algorithmic Fixes ($0)** — `apply_inline_fixes()`
- Fix operativity typos via OPERATIVITY_TYPO_MAP
- Remove locations not found in content (substring match)
- Remove government bodies not in text and not semantically relevant

**Stage 3: Inline Validation Warnings (non-blocking)** — `validate_decision_inline()`
- Policy tag keyword presence in content
- Operative/declarative keyword match vs classification
- Location tags appear in text
- Government body tags appear in text
- Summary length bounds (20-500 chars)
- Summary not identical to title
- Operativity classification clarity
- Suspicious body default patterns (SUSPICIOUS_BODY_COMBOS)
- Suspicious policy default patterns (SUSPICIOUS_POLICY_TAGS)

### Output

Reports are exported to `data/qa_reports/`:
- `qa_scan_YYYYMMDD_HHMMSS.json` - Scan results with issue counts, severity, and sample issues
- `qa_fix_{check}_{mode}_YYYYMMDD_HHMMSS.json` - Fix results

---

## Dependencies

**Core:**
- selenium 4.34.2
- beautifulsoup4 4.12.2
- supabase 2.17.0
- google-genai 1.0.0+
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

## Production Deployment (CECI Server)

The system is deployed as a Docker container on the CECI production server with automated daily syncing.

### Server Details

| Field | Value |
|-------|-------|
| **IP** | 178.62.39.248 |
| **User** | root |
| **SSH Alias** | ceci |
| **Project Path** | /root/ceci-ai-production/ceci-ai/GOV2DB |
| **Container** | gov2db-scraper |
| **Image** | tomerjoe/gov2db-scraper:latest |
| **Network** | compose_ceci-internal |
| **Daily Sync** | 02:00 AM (Asia/Jerusalem) |

### Quick Commands

```bash
# SSH to server
ssh ceci

# Container status
docker ps | grep gov2db-scraper

# Health check
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# View sync logs
tail -f /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log

# Manual sync
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 5 --verbose

# Full operations guide
cat GOV2DB/SERVER-OPERATIONS.md
```

### Key Files

- **[SERVER-OPERATIONS.md](SERVER-OPERATIONS.md)** - Complete server operations guide with SSH setup, verification checklist, troubleshooting, and update procedures
- **[Dockerfile](Dockerfile)** - Container definition (selenium/standalone-chrome base)
- **[docker/crontab](docker/crontab)** - Cron schedule (02:00 AM daily)
- **[docker/healthcheck.sh](docker/healthcheck.sh)** - Health monitoring script

### Updating Production

```bash
# Build and push new image (from local machine)
docker buildx build --platform linux/amd64 -t tomerjoe/gov2db-scraper:latest --push .

# Pull and restart on server
ssh ceci "docker pull tomerjoe/gov2db-scraper:latest && docker restart gov2db-scraper"
```

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

---

## Documentation Update Policy

**IMPORTANT:** Every improvement or change to the project must be briefly documented in this file (CLAUDE.md).

When making changes, update the relevant section:
- **New scanner/fixer?** → Update the "Available Checks" or "Available Fixers" tables in the QA System section
- **Pipeline change?** → Update "Main Workflow" steps
- **New script/file?** → Update "Project Structure"
- **Config change?** → Update "Fixed Values" or "Environment Variables"
- **QA finding?** → Update "Current Status" table + add detail to [QA-LESSONS.md](QA-LESSONS.md)
- **Scraping improvement?** → Update "Web Scraping Pipeline"
- **AI prompt change?** → Update "AI Processing Pipeline"
- **New Makefile target?** → Update "Quick Start Commands"

Related documentation files:
- **[QA-LESSONS.md](QA-LESSONS.md)** — QA process lessons learned, known issues, recommendations
- **[SERVER-OPERATIONS.md](SERVER-OPERATIONS.md)** — Production server operations guide
