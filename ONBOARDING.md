# Onboarding — GOV2DB

Welcome. You're inheriting an Israeli government decisions scraper that runs in
production. This guide gets you operational in roughly 2 hours on a cold setup
(first Docker build pulls a ~2.5 GB base image).

**You can open this guide in Claude Code if it was shared with you as a link** — your
Claude will load the project context and you can ask follow-up questions inline.

---

## What you've inherited

A Python scraper that runs nightly in a Docker container on a Linux server, pulls new
Israeli government decisions from gov.il via their Content API, runs each through
Google Gemini for summarization + tagging, validates against authorized whitelists, and
inserts into Supabase. Production scale: **25,500+ decisions**, governments 25-37
(1993-2026), coverage 99.89% for recent years.

The system runs autonomously: cron at 02:00 IDT daily, 3x retry with backoff,
healthcheck reports unhealthy after 3 consecutive failures.

## Day 1 — Get operational (~1 hour)

### 1. What you'll need from the previous owner (out-of-band)

Ask for these — they aren't in the repo:

- [ ] `GEMINI_API_KEY` — Google AI Studio key. Verify the GCP project has billing enabled
      (otherwise you'll hit `limit: 0` immediately).
- [ ] `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` — from the Supabase project.
      Ask to be added as a collaborator on the project so you can manage it long-term.
- [ ] SSH private key for `ceci` server (178.62.39.248, root). Save to
      `~/.ssh/ceci-ai-key`, `chmod 600`. **Never commit this.**
- [ ] GitHub collaborator access on the repo (`TomerGutman1/CECI_SCRAPER`).
- [ ] (Optional) Docker Hub credentials for `tomerjoe/gov2db-scraper` if you want to
      push pre-built images. Default deploy path uses `git pull + docker compose build`
      on the server, so this is optional.

### 2. Local setup (15 min)

```bash
git clone <your-clone-url>
cd GOV2DB
cp .env.example .env
# Edit .env with the three credentials above
```

Add the ceci SSH config (one time):
```bash
cat >> ~/.ssh/config << 'EOF'

Host ceci
    HostName 178.62.39.248
    User root
    IdentityFile ~/.ssh/ceci-ai-key
    ServerAliveInterval 60
EOF
```

Test SSH:
```bash
ssh ceci "hostname && docker ps | grep gov2db"
```

### 3. Local Docker test (10 min)

```bash
docker compose up -d --build
docker logs gov2db-scraper       # Should show "container started, validation passed"
docker ps                        # After ~60s should show (healthy)

# Pipeline tests
docker exec gov2db-scraper python3 bin/test_cron.py       # 3 simple tests
docker exec gov2db-scraper python3 bin/test_cron_full.py  # 18 integration tests
```

If `test_cron.py` fails, the most common cause is `.env` issues — re-check the three vars.

### 4. End-to-end smoke test (5 min)

```bash
# Single-decision real sync against production DB.
# --use-api is REQUIRED on macOS/local — without it sync.py falls back to Selenium/Chrome
# which conflicts with Gemini (see TRIBAL-KNOWLEDGE #3). Cron path uses --use-api already.
docker exec gov2db-scraper python3 bin/sync.py \
    --max-decisions 1 --no-approval --use-api --verbose
```

You should see one decision scraped, AI-processed, and inserted. If it says "decision
already in DB" pick a different one or use `--ignore-baseline`. If you see `limit: 0` →
billing issue on GCP project; fix that first (see §6 below).

### 5. Verify the production server (5 min)

```bash
ssh ceci "/root/ceci-ai-production/ceci-ai/GOV2DB/taste.sh"
```

Output should include:
- 5 latest decisions from DB (date ascending around current date)
- `Status: running | Health: healthy`
- Last 5 lines of `daily_sync.log` showing a recent successful run

If you see `(unhealthy)`:
```bash
ssh ceci "docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"
# last_failure.txt only exists after a failure; when healthy you'll see last_success.txt
ssh ceci "ls /root/ceci-ai-production/ceci-ai/GOV2DB/healthcheck/ && cat /root/ceci-ai-production/ceci-ai/GOV2DB/healthcheck/last_failure.txt 2>/dev/null"
```

### 6. Read the canonical docs (20 min)

In order:

1. `.planning/state.md` — top section is current state + blocker history. **Always read this before touching anything.**
2. `CLAUDE.md` — project structure, env vars, key files. (This file is also auto-loaded by Claude Code in this repo.)
3. `SERVER-OPERATIONS.md` — production server commands (SSH, deploy, logs).
4. `.planning/docs/TRIBAL-KNOWLEDGE.md` — 16 non-obvious gotchas. Skim now, reference later.

### 7. Make one trivial change end-to-end (10 min)

To prove the deploy loop works end-to-end, change a file that IS in the Docker image.
**Don't edit README.md or top-level *.md files** — the Dockerfile only COPYs `bin/`,
`src/`, `setup.py`, `new_tags.md`, `new_departments.md`, and the docker/ scripts. README
changes produce an identical image hash and don't trigger a container restart, so the
"deploy" silently does nothing.

```bash
# Edit a file under src/ — even a comment counts (changes image layer hash)
git checkout -b proof-of-deploy
echo "# Reviewed by Hadar on $(date)" >> src/gov_scraper/__init__.py
git add src/gov_scraper/__init__.py
git commit -m "chore: confirm deploy loop"
git push origin proof-of-deploy

# Merge to master via GitHub PR (or push directly if you have permission). Then deploy:
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git pull && docker compose up -d --build --force-recreate"

# Verify the container actually restarted (don't trust 'healthy' alone — it's up to 60 min stale)
ssh ceci "docker inspect gov2db-scraper --format='Started: {{.State.StartedAt}}'"
ssh ceci "docker ps | grep gov2db"   # Wait for (healthy) — takes ~5 min after recreate
ssh ceci "/root/ceci-ai-production/ceci-ai/GOV2DB/taste.sh"
```

If `Started:` shows a fresh timestamp and `taste.sh` shows current data, you're operational.

---

## Day 2 — Watch the cron + understand the codebase

### 1. Cron observation

Cron runs at 02:00 IDT with 0-30 min jitter. Morning after:

```bash
ssh ceci "tail -50 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log"
ssh ceci "tail -20 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/cron.log"
ssh ceci "/root/ceci-ai-production/ceci-ai/GOV2DB/taste.sh"
```

Expected: sync completed in 30s-15min depending on backlog size; DB has new decisions
with today's or yesterday's date; healthcheck reports healthy.

### 2. Walk the pipeline

Daily cron path:
```
docker/randomized_sync.sh  (cron entrypoint, retries, exit-code propagation)
  → bin/sync.py            (orchestrator)
    → src/gov_scraper/processors/incremental.py  (baseline detection)
    → src/gov_scraper/scrapers/catalog.py        (list decisions via API)
    → src/gov_scraper/scrapers/decision.py       (per-decision content via API)
    → src/gov_scraper/processors/unified_ai.py   (Gemini, 1 call/decision)
    → src/gov_scraper/processors/ai_post_processor.py  (whitelist + dedup + normalize)
    → src/gov_scraper/db/dal.py                  (Supabase insert with retry)
```

Read these in order, then trace a single decision through:
```bash
docker exec gov2db-scraper python3 bin/sync.py \
    --max-decisions 1 --no-approval --verbose 2>&1 | less
```

### 3. QA tools

```bash
docker exec gov2db-scraper python3 bin/simple_incremental_qa.py run  # Fast (2-10 min)
docker exec gov2db-scraper python3 bin/qa.py scan --stratified --seed 42  # Full (samples 25K)
```

Read `QA-LESSONS.md` for the history of 14+ QA issues caught and fixed.

---

## Day 3 — Deploy your first real fix

Pick a real issue to work on. Suggestions:

1. **PDF extraction for the 6 missing decisions** — 0.1% gap (see `.planning/state.md`).
   Half-day project. Adds `pdfplumber` to pipeline.
2. **Pre-2020 backfill** — 71 truly missing decisions from earlier governments.
   Lower priority but visible improvement.
3. **Improve operativity classification** — currently ~93% accurate, target 95%+.
   Lessons are in `.planning/state.md` (search for "Operativity Classification") and
   `QA-LESSONS.md`.
4. **Anti-block resilience** — `ANTI-BLOCK-STRATEGY.md` documents 8 strategies; not all
   are implemented.

---

## Workflow conventions

### Planning files (`.planning/`)
- `state.md` — current DB status + blocker history. **Surgical edits only**, update
  "Last Updated" line on every change. **Never full-rewrite.**
- `handoff.md` — session snapshot. **Always overwrite entirely** at end of major session.
- `decisions.md` — append-only architectural decisions log. **Never remove past entries.**
- `todo.md` — current work plan with checkable items.

### Git workflow
- Solo developer — work on `master`, no PR ceremony required for solo changes
- Commit after each verified step
- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
- Push to GitHub regularly so server can deploy

### Deploying changes
```bash
git push origin master

# --force-recreate guarantees the container restarts even if Docker reuses cached layers.
# The server's GitHub auth is unauthenticated HTTPS (works because the repo is public —
# if you make it private, configure a GitHub PAT or deploy key on the server first).
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git pull && docker compose up -d --build --force-recreate"

# Verify restart actually happened (Started: timestamp should be fresh)
ssh ceci "docker inspect gov2db-scraper --format='Started: {{.State.StartedAt}}'"
ssh ceci "docker ps | grep gov2db"   # Wait for (healthy) — takes ~5 min after recreate
ssh ceci "/root/ceci-ai-production/ceci-ai/GOV2DB/taste.sh"   # Verify
```

> Avoid `docker compose down/restart` between 01:30-02:30 IDT — the daily cron fires at
> 02:00 IDT inside the container; if the container is down at that moment, that night's
> sync is skipped.

### Things not to do without thinking carefully
- Don't revert gov.il URLs to `www.gov.il/*WebApi/*` — those are dead (see TRIBAL-KNOWLEDGE #1)
- Don't add `set -e` to `docker/randomized_sync.sh` (see TRIBAL-KNOWLEDGE #5)
- Don't pipe `python3 sync.py | tee log` (swallows exit codes, see TRIBAL-KNOWLEDGE #5)
- Don't change `new_tags.md` or `new_departments.md` without reading TRIBAL-KNOWLEDGE #6
- Don't run `make sync` locally on macOS — Chrome + Gemini conflict (TRIBAL-KNOWLEDGE #3)
- Don't push 75MB+ files to git (they're in `data/scraped/` — already gitignored)

---

## Emergency runbook

### Container reports unhealthy
```bash
ssh ceci "docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"
# last_failure.txt is written only after a sync failure; "No such file" means clean state
ssh ceci "cat /root/ceci-ai-production/ceci-ai/GOV2DB/healthcheck/last_failure.txt 2>/dev/null || echo 'no failure recorded'"
ssh ceci "docker logs --tail 100 gov2db-scraper"
```

Most common causes (in order of likelihood):
1. Gemini quota — check log for `limit: 0`
2. Supabase unreachable — check `SUPABASE_*` env vars in container
3. gov.il API changed again — check log for HTML-fallback warnings
4. Disk full — `ssh ceci "df -h"`

### Sync hung / runaway
```bash
ssh ceci "docker exec gov2db-scraper ps auxf"
ssh ceci "docker restart gov2db-scraper"
```

### Total rebuild
```bash
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && docker compose down && docker compose up -d --build"
```

### Rollback to last good commit
```bash
git log --oneline -10
ssh ceci "cd /root/ceci-ai-production/ceci-ai/GOV2DB && git reset --hard <good-sha> && docker compose up -d --build"
```

(Only use `--hard` if you understand what you're discarding.)

---

## Where to ask questions

- **Open Claude Code in this repo** — `CLAUDE.md` is auto-loaded; ask questions about
  files inline.
- **Memory transfer.** The previous owner used Claude Code memory heavily; the
  load-bearing facts have been migrated into `.planning/docs/TRIBAL-KNOWLEDGE.md`.
  Read it once and add new entries when you discover non-obvious behavior.
- **Tomer** (previous owner) for context-only questions that aren't in any doc.

---

## You're done with day 1 when

- [ ] Local Docker container runs and tests pass
- [ ] You can SSH to ceci and run `taste.sh`
- [ ] You've deployed one trivial change end-to-end
- [ ] You've read `state.md`, `CLAUDE.md`, `SERVER-OPERATIONS.md`,
      `.planning/docs/TRIBAL-KNOWLEDGE.md`

Welcome aboard.
