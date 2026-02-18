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
# Simple Incremental QA (Recommended - Working!)
make simple-qa-run                 # Fast daily QA updates (2-10 minutes)
make simple-qa-status              # Check incremental QA status
make simple-qa-reset               # Reset change tracking

# Full QA Scans (Use for Comprehensive Audits)
make qa-scan                       # Full quality scan (all 25K records)
make qa-scan-check check=operativity  # Specific check
make qa-fix-preview check=locations   # Preview fix
make qa-fix-execute check=locations   # Execute fix
```

### Direct CLI
```bash
# Scraping
python bin/sync.py --unlimited --no-approval --no-headless --verbose

# QA
python bin/qa.py scan --stratified --seed 42  # Reproducible sample
python bin/simple_incremental_qa.py run       # Fast incremental QA (working!)
```

## Project Structure
```
bin/               # CLI scripts (sync.py, qa.py, simple_incremental_qa.py)
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

## Simple Incremental QA System (Working!)
**Efficient daily QA updates processing only changed records:**
- **Performance**: 2-10 minutes vs 2-4 hours for full scans
- **Change Tracking**: File-based hash comparison (no DB changes needed)
- **Smart Processing**: Detects new and changed records automatically
- **Reporting**: Shows only new issues and improvements
- **Zero Setup**: Works immediately with existing database

**Usage**: Run `make simple-qa-run` daily for fast QA updates
**Status**: Check with `make simple-qa-status`

## Current Status (Feb 18, 2026)
- **Algorithm Improvements:** Ready for deployment (NOT YET DEPLOYED)
- **DB Quality:** 42% duplicates → <1% expected after migration
- **Tag Accuracy:** 50% → 90%+ expected with new detection profiles
- **API Efficiency:** 5-6 → 1-2 calls per decision (pending deployment)
- See `.planning/state.md` for deployment instructions and full details

## 🚀 Quick Deployment (New!)
```bash
# Deploy all algorithm improvements
make deploy-check        # Check prerequisites
make deploy-full         # Run full deployment (~40 min)
make verify-deployment   # Verify success

# Or auto-deploy (no prompts)
make deploy-auto
```

## New Components (Feb 2026 - Ready, Not Yet Deployed)
- **Smart Tag Detection:** 45 profiles in `config/tag_detection_profiles.py`
- **Ministry Validation:** 44 rules in `config/ministry_detection_rules.py`
- **Unified AI:** Single call processor in `src/gov_scraper/processors/unified_ai.py`
- **Real-time Monitoring:** Quality tracking in `src/gov_scraper/monitoring/`
- **DB Integrity:** Migration in `database/migrations/004_fix_duplicates_and_constraints.sql`
- **Deploy with:** `make deploy-check` then `make deploy-full`

## Things That Will Confuse You
1. **Hebrew RTL:** All content is Hebrew - decision titles, content, some tags
2. **Date Format:** Website uses DD.MM.YYYY, we store as YYYY-MM-DD
3. **Tag Validation:** Enhanced 3-tier system (AI + semantic + cross-validation)
4. **Safety Modes:** Use `--safety-mode extra-safe` after long breaks
5. **Incremental Logic:** Compares by date THEN number, not just number
6. **Unified AI:** Set `USE_UNIFIED_AI=true` in .env to enable new processor

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
- **Incremental QA:** `INCREMENTAL-QA-GUIDE.md` (New efficient QA system)
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