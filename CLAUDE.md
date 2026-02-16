# GOV2DB - Israeli Government Decisions Scraper

## What This Is
Automated scraper that extracts Israeli government decisions from gov.il, analyzes them with AI (Gemini), and stores in Supabase. Currently in production with ~25K decisions indexed.

## Planning & State
**IMPORTANT:** Read `.planning/state.md` before starting any task to understand current DB issues and priorities.

## How To Run

### Daily Operations
```bash
make sync              # Daily sync (auto-approve, no-headless mode)
make sync-test         # Test with 1 decision
make sync-dev          # Dev mode (5 decisions)
make test-conn         # Test DB connection
```

### QA Commands (Use These First!)
```bash
make qa-scan                       # Full quality scan
make qa-scan-check check=operativity  # Specific check
make qa-fix-preview check=locations   # Preview fix
make qa-fix-execute check=locations   # Execute fix
```

### Direct CLI
```bash
python bin/sync.py --unlimited --no-approval --no-headless --verbose
python bin/qa.py scan --stratified --seed 42  # Reproducible sample
```

## Project Structure
```
bin/               # CLI scripts (sync.py, qa.py, test_new_tags.py)
src/gov_scraper/
  ├── scrapers/    # Web scraping (catalog.py, decision.py)
  ├── processors/  # AI & QA logic (ai.py, qa.py, incremental.py)
  └── db/          # Database (connector.py, dal.py)
data/              # Reports, exports, backups
logs/              # Scraper and sync logs
new_tags.md        # 45 authorized policy tags
new_departments.md # 44 authorized government bodies
```

## Database Rules
- Table: `israeli_government_decisions`
- Unique key: `decision_key` = `{gov_num}_{decision_num}`
- All tags validated against authorized lists
- No direct SQL - use DAL functions in `db/dal.py`

## Current Issues (Feb 2026)
- **DB Quality:** Running QA fixes on 25K records
- **Cloudflare:** Must use `--no-headless` flag
- **Tag Accuracy:** ~80% accuracy after fixes
- See `.planning/state.md` for detailed status

## Things That Will Confuse You
1. **Hebrew RTL:** All content is Hebrew - decision titles, content, some tags
2. **Date Format:** Website uses DD.MM.YYYY, we store as YYYY-MM-DD
3. **Tag Validation:** 3-step algorithm prevents hallucinations (see `.planning/docs/IMPLEMENTATION-DETAILS.md`)
4. **Safety Modes:** Use `--safety-mode extra-safe` after long breaks
5. **Incremental Logic:** Compares by date THEN number, not just number

## Key Files to Modify
- **Scraping:** `src/gov_scraper/scrapers/decision.py`
- **AI Prompts:** `src/gov_scraper/processors/ai.py`
- **QA Checks:** `src/gov_scraper/processors/qa.py`
- **Database:** `src/gov_scraper/db/dal.py`

## Environment Variables
```bash
GEMINI_API_KEY=...                # Google Gemini API
SUPABASE_URL=...                  # Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=...     # Service role JWT
```

## Documentation
- **Technical Details:** `.planning/docs/IMPLEMENTATION-DETAILS.md`
- **QA Process:** `QA-LESSONS.md`
- **Server Ops:** `SERVER-OPERATIONS.md`
- **Anti-Block:** `ANTI-BLOCK-STRATEGY.md`

## When Making Changes
1. Run QA scan first to understand current issues
2. Test with `--max-decisions 5` before full runs
3. Always include `--no-headless` for scraping
4. Update this file only for workflow changes
5. Update `.planning/state.md` after completing tasks

answer in english unless i say otherwise