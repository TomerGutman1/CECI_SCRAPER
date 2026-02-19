# GOV2DB - Israeli Government Decisions Scraper

## What This Is
Automated scraper that extracts Israeli government decisions from gov.il, analyzes them with AI (Gemini), and stores in Supabase. Currently in production with ~25K decisions indexed.

## Planning & State
**IMPORTANT:** Read `.planning/state.md` before starting any task to understand current DB issues and priorities.

## How To Run

### Docker (Production & Local)
```bash
# Start locally
docker compose up -d --build    # Build and start
docker logs gov2db-scraper      # Check startup (should show env vars exported)
docker ps                       # Should show (healthy) after ~1 minute

# Test inside container
docker exec gov2db-scraper python3 bin/test_cron.py        # Simple: env → DB read → DB write
docker exec gov2db-scraper python3 bin/test_cron_full.py   # Full: 18 integration tests

# Stop
docker compose down
```

**Requirements:** `.env` file with `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`

**What happens automatically:**
- Container validates env vars on startup (missing = FATAL, won't start)
- Cron runs sync daily (randomized 21-34h interval to avoid Cloudflare)
- Failed syncs retry 3x with backoff (30/60/90 min)
- Healthcheck runs hourly → 3 failures = `(unhealthy)` in `docker ps`
- Logs persist in `./logs/`, health state in `./healthcheck/`

### Daily Operations (Without Docker)
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
bin/               # CLI scripts (sync.py, qa.py, test_cron.py, test_cron_full.py)
src/gov_scraper/
  ├── scrapers/    # Web scraping (catalog.py, decision.py)
  ├── processors/  # AI & QA logic (ai.py, qa.py, incremental.py)
  └── db/          # Database (connector.py, dal.py)
docker/            # Docker infrastructure
  ├── docker-entrypoint.sh  # Startup: env validation, Xvfb, cron
  ├── randomized_sync.sh    # Sync wrapper: retry, backoff, health state
  ├── healthcheck.sh        # Hourly health check (DB + sync age + failures)
  ├── crontab               # Cron schedule (2AM + 2PM Israel time)
  └── logrotate.conf        # Log rotation (30 days, 100MB max)
healthcheck/       # Health state (persists across restarts via volume)
data/              # Reports, exports, backups
logs/              # Scraper and sync logs
new_tags.md        # 46 authorized policy tags
new_departments.md # 45 authorized government bodies
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

## Current Status (Feb 19, 2026)
- **Algorithm Improvements:** DEPLOYED ✅ + Post-deployment fixes applied
- **Docker Cron:** FIXED ✅ — env vars, retry logic, healthcheck, self-healing
- **DB Quality:** 0% duplicates (unique constraint enforced)
- **Tag Accuracy:** ~93% (up from 50%), known issues documented
- **API Efficiency:** 1 call per decision (down from 5-6)
- **Dynamic Summaries:** Implemented, scales with content length
- See `.planning/state.md` and `.planning/handoff.md` for details

## Docker Deployment
```bash
# Local
docker compose up -d --build
docker exec gov2db-scraper python3 bin/test_cron.py   # Verify pipeline

# Server (178.62.39.248, alias: ceci)
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git pull && docker compose up -d --build"
ssh ceci "docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"

# Server docker-compose.yml uses network: compose_ceci-internal
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
7. **Cloudflare:** Always use `--no-headless` for scraping (headless Chrome is blocked)
8. **Docker env vars:** Entrypoint exports ALL Docker env vars to `/app/.env` for cron — don't hardcode var names
9. **Apple Silicon:** Chrome/Selenium tests fail locally on macOS ARM (Rosetta limitation) — works on Linux server

## Key Files to Modify
- **Scraping:** `src/gov_scraper/scrapers/decision.py`
- **AI Prompts:** `src/gov_scraper/processors/ai.py`
- **QA Checks:** `src/gov_scraper/processors/qa.py`
- **Database:** `src/gov_scraper/db/dal.py`
- **Docker Cron:** `docker/randomized_sync.sh` (sync wrapper), `docker/docker-entrypoint.sh` (startup)
- **Health Check:** `docker/healthcheck.sh`

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
- **Session Handoff:** `.planning/handoff.md` (current status + next steps)

## When Making Changes
1. Run QA scan first to understand current issues
2. Test with `--max-decisions 5` before full runs
3. Always include `--no-headless` for scraping
4. Update this file only for workflow changes
5. Update `.planning/state.md` after completing tasks

answer in english unless i say otherwise