# GOV2DB — Israeli Government Decisions Scraper

Automated scraper that extracts Israeli government decisions from [gov.il](https://www.gov.il),
processes them with Google Gemini (summaries, policy tags, government-body tags, operativity
classification), and stores results in Supabase.

**Production scale:** 25,500+ decisions, governments 25-37 (1993-2026). Runs nightly via
Docker cron on a dedicated server. Coverage 99.89% (2020-2026).

> **New here?** Read `ONBOARDING.md` first — it's a one-page getting-started guide that
> assumes zero prior context. This README is reference material.

---

## What This System Does

1. Discovers new decisions on gov.il via the official Content API (no Chrome needed)
2. Extracts Hebrew text + metadata (date, decision number, committee, title, content)
3. Runs each decision through Gemini for: summary, operativity classification, policy
   tags, government-body tags, location tags
4. Validates everything against authorized whitelists (46 policy tags, 45 government
   bodies — defined in `new_tags.md` / `new_departments.md`)
5. Inserts into Supabase (`israeli_government_decisions`) with idempotent unique key
   `{government_number}_{decision_number}`

---

## Quick Start (Docker — recommended)

### Prerequisites
- Docker Desktop installed and running
- Three credentials (request from the project owner):
  - `GEMINI_API_KEY` — Google AI Studio key with billing enabled on the GCP project
  - `SUPABASE_URL` — Supabase project URL (`https://xxxxx.supabase.co`)
  - `SUPABASE_SERVICE_ROLE_KEY` — Supabase service-role JWT

### Run locally in 5 minutes
```bash
git clone <repo-url>
cd GOV2DB

cp .env.example .env
# Open .env and fill in the three credentials

docker compose up -d --build      # Build & start (≈1 min)
docker logs gov2db-scraper        # Should show "container started, validation passed"
docker ps                         # Should show (healthy) after ~1 minute
```

### Verify the install works
```bash
# Simple test: env vars + DB read + DB write
docker exec gov2db-scraper python3 bin/test_cron.py

# Full integration suite (18 tests)
docker exec gov2db-scraper python3 bin/test_cron_full.py

# Manual single-decision sync (proves end-to-end works)
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --no-approval --verbose
```

### Stop
```bash
docker compose down
```

The container runs daily sync automatically at **02:00 IDT** with 0-30 min jitter (cron
inside the container). Logs persist in `./logs/`, health state in `./healthcheck/`.

---

## Make Targets (without Docker, runs against your local Python)

> Most operations should use Docker. These targets exist for development and one-off ops.

```bash
make sync              # Daily sync (auto-approve, no-headless)
make sync-test         # Test with 1 decision
make sync-dev          # Dev mode (5 decisions)
make test-conn         # Test Supabase connection

# QA
make simple-qa-run     # Fast incremental QA (2-10 min, samples recent records)
make simple-qa-status  # Check QA status
make qa-scan           # Full quality scan (all 25K records)

# 3-Phase pipeline (full re-scrape)
make discover          # Phase 1: discover all decision URLs → data/catalog_manifest.json
make full-scrape       # Phase 2: scrape all from manifest (local)
make push-local        # Phase 3: push local data to Supabase
make push-local-qa     # QA check before pushing
```

See `Makefile` for the full list (`make help`).

---

## Architecture

```
gov.il openapi-gc gateway  ──► catalog.py (list decisions, x-client-id header)
                              decision.py  (per-decision content via Content Page API)
                                       │
                                       ▼
            full content (Hebrew, JSON) │
                                       ▼
          unified_ai.py + ai.py  ◄──── prompt + dynamic summary length
                  │                    (1 Gemini call per decision)
                  ▼
        ai_post_processor.py  ── whitelist enforcement, dedup, normalization
                  │
                  ▼
                 dal.py  ────────► Supabase (israeli_government_decisions)
                  │
                  └── retry 5x, fail-loud on persistent error
```

### Key directories
```
bin/                   # CLI scripts (sync.py, qa.py, full_local_scraper.py, taste.sh, ...)
src/gov_scraper/
  scrapers/            # catalog.py, decision.py (gov.il integration)
  processors/          # ai.py, unified_ai.py, ai_post_processor.py, qa.py, incremental.py
  db/                  # connector.py, dal.py (Supabase data layer)
  monitoring/          # quality_monitor.py, alert_manager.py
  utils/               # selenium.py (Apple Silicon Chrome patches)
config/                # tag_detection_profiles, ministry_rules, committee_mappings
docker/                # docker-entrypoint.sh, randomized_sync.sh, healthcheck.sh, cron
new_tags.md            # 46 authorized policy tags (whitelist source of truth)
new_departments.md     # 45 authorized government bodies (whitelist source of truth)
```

---

## What Gets Extracted

### Direct from gov.il
- `decision_date` (תאריך פרסום)
- `decision_number` (מספר החלטה) — note: can include Hebrew prefixes like `מח/6`
- `committee` (ועדות שרים)
- `decision_title`
- `decision_content` (full Hebrew text)
- `decision_url`

### AI-generated (validated against whitelists)
- `summary` — dynamic length (1-7 sentences based on content size); never starts with
  "החלטת ממשלה מספר..." prefix
- `operativity` — `אופרטיבית` or `דקלרטיבית` (rule-based override layer corrects ~50%
  of AI misclassifications: appointments/committees/acknowledgments → declarative)
- `tags_policy_area` — validated against `new_tags.md` (46 categories)
- `tags_government_body` — validated against `new_departments.md` (45 entities)
- `tags_location` — geographic areas (filters generic terms like "ישראל")
- `all_tags` — deterministic union, rebuilt after validation

### System
- `government_number` (currently 37 for Netanyahu government)
- `prime_minister` (date-aware: handles Bennett→Lapid transition mid-government 36)
- `decision_key` — unique constraint, `{gov_num}_{decision_num}`

---

## Database

- **Provider:** Supabase
- **Table:** `israeli_government_decisions`
- **Unique key:** `decision_key` (UNIQUE constraint enforced; 0 duplicates)
- **DAL:** `src/gov_scraper/db/dal.py` — use these functions, never raw SQL
- **Insert retry:** 3x batch retry + 2x individual fallback before failing loudly
- **Hebrew-prefix keys:** Auto-normalized on insert (`37_מח/6` → `37_mh6`)

---

## Production Server (ceci, 178.62.39.248)

See `SERVER-OPERATIONS.md` for SSH setup, deployment, and troubleshooting. Quick refs:

```bash
ssh ceci "docker ps | grep gov2db"                                    # Container health
ssh ceci "/root/ceci-ai-production/ceci-ai/GOV2DB/taste.sh"           # 5 latest decisions + status + log tail
ssh ceci "tail -50 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log"   # Recent sync log
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git pull && docker compose up -d --build"   # Deploy
```

---

## Troubleshooting

### Database connection failed
- Run `docker exec gov2db-scraper python3 bin/test_cron.py` — first test catches missing/bad env vars
- Verify `.env` has `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (not `_ANON_KEY`)

### `limit: 0` in logs
- Gemini billing isn't enabled on the GCP project for your API key
- Fix: enable billing on the project at console.cloud.google.com → Billing
- Code fails fast (~30s) instead of hanging, so no resource burn — but no decisions get AI-processed

### Container reports unhealthy
```bash
docker exec gov2db-scraper /usr/local/bin/healthcheck.sh
# Check ./healthcheck/last_failure.txt for last failure reason
```

### `make sync` hangs on macOS
- Don't run sync locally on Apple Silicon — Chrome + Gemini conflict (httpx hangs). Use Docker.

### gov.il returns HTML instead of JSON
- gov.il may have rotated the `x-client-id`. The dynamic config fetch in `catalog.py:_fetch_govil_config()`
  should self-heal. Check logs for "config drift" warnings.

---

## Documentation

| File | Purpose |
|------|---------|
| `ONBOARDING.md` | **Start here** — day-1 guide for new developers |
| `CLAUDE.md` | Technical reference: setup, structure, known blockers, key files |
| `SERVER-OPERATIONS.md` | Production server: SSH, deploy, logs, troubleshooting |
| `ANTI-BLOCK-STRATEGY.md` | Why scraper design is careful (Cloudflare, headers, timing) |
| `PIPELINE-VULNERABILITIES.md` | 14 known vulnerabilities, mitigation status |
| `QA-LESSONS.md` | QA history: 14+ issues found, root causes, fixes |
| `.planning/state.md` | Current DB state + blocker history |
| `.planning/handoff.md` | Last session handoff snapshot |
| `.planning/docs/TRIBAL-KNOWLEDGE.md` | Non-obvious gotchas (Apple Silicon Chrome, etc.) |
| `.planning/docs/IMPLEMENTATION-DETAILS.md` | Algorithm deep-dive |
| `HANDOVER-CHECKLIST.md` | (For owner) out-of-band transfer items: credentials, SSH key, access |

---

## License

Internal project. Not currently licensed for redistribution.
