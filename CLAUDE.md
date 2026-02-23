# GOV2DB - Israeli Government Decisions Scraper

## What This Is
Automated scraper that extracts Israeli government decisions from gov.il, analyzes them with AI (Gemini), and stores in Supabase. Production dataset: 25,401 decisions (governments 25-37, 1993-2026).

## Planning & State
**IMPORTANT:** Read `.planning/state.md` before starting any task to understand current DB status and priorities.

## How To Run

### Docker (Production & Local)
```bash
# Start locally
docker compose up -d --build
docker logs gov2db-scraper      # Check startup
docker ps                       # Should show (healthy) after ~1 minute

# Test inside container
docker exec gov2db-scraper python3 bin/test_cron.py        # Simple: env -> DB read -> DB write
docker exec gov2db-scraper python3 bin/test_cron_full.py   # Full: 18 integration tests

# Stop
docker compose down
```

**Requirements:** `.env` file with `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`

**What happens automatically:**
- Container validates env vars on startup (missing = FATAL, won't start)
- Cron runs sync daily (randomized 21-34h interval to avoid Cloudflare)
- Failed syncs retry 3x with backoff (30/60/90 min)
- Healthcheck runs hourly -> 3 failures = `(unhealthy)` in `docker ps`
- Logs persist in `./logs/`, health state in `./healthcheck/`

### Daily Operations (Without Docker)
```bash
make sync              # Daily sync (auto-approve, no-headless mode)
make sync-test         # Test with 1 decision
make sync-dev          # Dev mode (5 decisions)
make test-conn         # Test DB connection
```

### QA Commands
```bash
make simple-qa-run                 # Fast daily QA (2-10 minutes)
make simple-qa-status              # Check QA status
make qa-scan                       # Full quality scan (all 25K records)
make qa-scan-check check=operativity  # Specific check
```

### 3-Phase Pipeline (Full Re-scrape)
```bash
make discover          # Phase 1: Discover all decision URLs
make full-scrape       # Phase 2: Scrape all from manifest (local)
make push-local        # Phase 3: Push local data to Supabase
make push-local-qa     # QA check before pushing
```

### Direct CLI
```bash
python bin/sync.py --unlimited --no-approval --no-headless --verbose
python bin/qa.py scan --stratified --seed 42
python bin/simple_incremental_qa.py run
```

## Project Structure
```
bin/               # CLI scripts
  sync.py            - Daily sync pipeline
  qa.py              - QA scanning and fixing
  simple_incremental_qa.py - Fast daily QA
  full_local_scraper.py    - 2-phase scraper (API + AI)
  push_local.py      - QA validation + DB push
  parallel_phase_b.py - Parallel AI processing (4 workers)
  discover_all.py    - Phase 1 catalog discovery
  test_cron.py       - Docker pipeline test
  test_cron_full.py  - Docker integration tests (18 tests)
src/gov_scraper/
  scrapers/          - Web scraping (catalog.py, decision.py)
  processors/        - AI & QA logic (ai.py, unified_ai.py, qa.py, incremental.py)
  db/                - Database (connector.py, dal.py)
  monitoring/        - Quality monitoring (quality_monitor.py, alert_manager.py)
config/              - Tag detection profiles, ministry rules
docker/              - Docker infrastructure (entrypoint, sync, healthcheck, cron)
healthcheck/         - Health state (persists across restarts via volume)
data/                - Manifest, scraped output
logs/                - Scraper and sync logs
new_tags.md          - 46 authorized policy tags
new_departments.md   - 45 authorized government bodies
```

## Database Rules
- Table: `israeli_government_decisions`
- Unique key: `decision_key` = `{gov_num}_{decision_num}`
- All tags validated against authorized lists (46 policy, 45 bodies)
- No direct SQL - use DAL functions in `db/dal.py`

## Current Status (Feb 23, 2026)
- **DB Records:** 25,401 (full refresh completed Feb 23)
- **Quality Grade:** A+ (98.1%)
- **Duplicates:** 0% (unique constraint enforced)
- **Tag Accuracy:** ~93% (3-layer whitelist enforcement)
- **API Efficiency:** 1 Gemini call per decision
- **Content API:** Direct JSON API bypasses Cloudflare (~940 pages/min)
- See `.planning/state.md` for details

## Docker Deployment
```bash
# Local
docker compose up -d --build
docker exec gov2db-scraper python3 bin/test_cron.py

# Server (178.62.39.248, alias: ceci)
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git pull && docker compose up -d --build"
ssh ceci "docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"
```

## Things That Will Confuse You
1. **Hebrew RTL:** All content is Hebrew - decision titles, content, some tags
2. **Date Format:** Website uses DD.MM.YYYY, we store as YYYY-MM-DD
3. **Cloudflare:** Always use `--no-headless` for scraping (headless Chrome is blocked)
4. **Content API:** `scrape_decision_via_api()` in decision.py bypasses Cloudflare entirely
5. **Gemini + Chrome conflict:** Never call Gemini while Chrome is running on macOS
6. **Docker env vars:** Entrypoint exports ALL Docker env vars to `/app/.env` for cron
7. **Apple Silicon:** Chrome/Selenium tests fail locally on macOS ARM — works on Linux server
8. **Unified AI:** Set `USE_UNIFIED_AI=true` in .env (active in production)

## Key Files to Modify
- **Scraping:** `src/gov_scraper/scrapers/decision.py`
- **AI Prompts:** `src/gov_scraper/processors/ai.py`, `ai_prompts.py`
- **AI Processing:** `src/gov_scraper/processors/unified_ai.py`
- **Post-processing:** `src/gov_scraper/processors/ai_post_processor.py`
- **QA Checks:** `src/gov_scraper/processors/qa.py`
- **Database:** `src/gov_scraper/db/dal.py`
- **Docker:** `docker/randomized_sync.sh`, `docker/docker-entrypoint.sh`, `docker/healthcheck.sh`

## Environment Variables
```bash
GEMINI_API_KEY=...                # Google Gemini API
SUPABASE_URL=...                  # Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=...     # Service role JWT
USE_UNIFIED_AI=true               # Enable unified AI processor
```

## Documentation
- **Technical Details:** `.planning/docs/IMPLEMENTATION-DETAILS.md`
- **QA Process:** `QA-LESSONS.md`
- **Server Ops:** `SERVER-OPERATIONS.md`
- **Anti-Block:** `ANTI-BLOCK-STRATEGY.md`
- **Vulnerabilities:** `PIPELINE-VULNERABILITIES.md`
- **Session Handoff:** `.planning/handoff.md`

## When Making Changes
1. Run `make simple-qa-run` first to understand current issues
2. Test with `--max-decisions 5` before full runs
3. Always include `--no-headless` for scraping
4. Update `.planning/state.md` after completing tasks

answer in english unless i say otherwise
