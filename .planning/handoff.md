# Session Handoff — Handover Prep
**Date:** 2026-05-19
**Focus:** Preparing the repo for transfer from Tomer to Hadar

## Snapshot of current system state

| Field | Value |
|---|---|
| DB records | 25,585+ (catalog at 25,871; ~0.1% PDF-only gap) |
| Latest decision | ~May 7, 2026 (cron catching up backlog) |
| Coverage 2020-2026 | 99.89% |
| Quality grade | A+ (98.1% pre-gap) |
| Container status | (healthy) on ceci server |
| Daily sync | 02:00 IDT with 0-30 min jitter, 3x retry |
| Active blockers | None — gov.il migration deployed, Gemini billing active |

## What was done this session (Tomer)
1. **Repo cleanup committed** (commit `41b4800`)
   - Staged 221 deletions from Feb 23 codebase cleanup that had been sitting unstaged for 3 months
   - Added 7 ops scripts to `bin/` (parallel_phase_b, audit_integrity, audit_manifest_vs_db, analyze/diagnose_url_mismatches, fix_integrity, process_missing_decisions)
   - Vendored `taste.sh` from ceci server into repo root (was referenced in SERVER-OPERATIONS.md but not tracked)
   - Extended `.gitignore`: `.claude/settings.local.json`, `.playwright-mcp/`, `data/**/*.json`, `src/gov_scraper/data/`

2. **Documentation refresh for handover** (commit `<TBD-after-this-session>`)
   - Rewrote `README.md` — Gemini-correct (was telling users to set OPENAI_API_KEY), Docker-first, dead command refs removed
   - Updated `CLAUDE.md` "Current Status" block to May 2026 + added "Known Blockers / Recent Migrations" section
   - Created `.planning/docs/TRIBAL-KNOWLEDGE.md` — 16 non-obvious gotchas migrated out of Tomer's personal Claude memory
   - Created `ONBOARDING.md` — self-contained day-1 guide for Hadar
   - Created `HANDOVER-CHECKLIST.md` — Tomer-facing out-of-band transfer list (SSH key, Supabase invite, Gemini key option, GitHub access)
   - Surgically updated `.planning/state.md` Last Updated + handover-prep note

3. **Pre-handover audit** — `.planning/todo.md` top section documents the plan and execution

## What's not done (and why)
- **Out-of-band credential transfer to Hadar** — Tomer needs to execute the steps in `HANDOVER-CHECKLIST.md`:
  - Share Supabase project (invite Hadar to org or create new project with same schema)
  - Decide on Gemini key sharing strategy (share existing billed key, or have Hadar use his own)
  - Transfer ceci SSH private key out-of-band (Signal/encrypted message, not git)
  - Add Hadar as GitHub collaborator on `TomerGutman1/CECI_SCRAPER`
  - (Optional) Decide on Docker Hub access for `tomerjoe/gov2db-scraper` — current deploy path is `git pull + docker compose build` on server, so this is only needed if Hadar wants to push pre-built images.

- **ShareOnboardingGuide link** — generated at end of session; URL captured in this handoff.

## Top things Hadar should know on day 1
1. **Read `ONBOARDING.md` first** — designed exactly for this purpose
2. **The gov.il APIs moved (May 11)** — old `www.gov.il/*WebApi/*` are DEAD. New gateway requires `x-client-id` header. Already fixed in code; just don't accidentally revert.
3. **Gemini needs paid tier** — free tier = instant `limit: 0`. Fix is billing-side, not code.
4. **Don't run sync locally on macOS** — Chrome + Gemini conflict (#3 in TRIBAL-KNOWLEDGE). Use Docker.
5. **Daily cron is at 02:00 IDT** — debug by reading server logs the morning after.
6. **Whitelists are sacred** — `new_tags.md` (46 policy) and `new_departments.md` (45 bodies) are source-of-truth for AI tagging. Don't add/remove without understanding the 3-layer enforcement.

## Read first (in order)
1. `ONBOARDING.md` (10 min) — day-1 setup + verify
2. `.planning/state.md` (5 min top section) — current blocker status, May 13 changes
3. `CLAUDE.md` (10 min) — project structure, env vars, key files
4. `SERVER-OPERATIONS.md` (15 min) — SSH, deploy, troubleshooting
5. `.planning/docs/TRIBAL-KNOWLEDGE.md` (20 min, full) — 16 non-obvious gotchas

Total: ~60 min to be operationally ready.

## Next session priorities (Hadar's first work session)
1. **Verify local Docker setup works** — `docker compose up -d --build` + `bin/test_cron.py` + manual `--max-decisions 1` sync
2. **Verify server health** — `ssh ceci "./GOV2DB/taste.sh"` shows healthy container + recent decisions
3. **Monitor next cron run** — read logs morning after 02:00 IDT, confirm backlog catching up
4. **One trivial PR end-to-end** — pick a tiny improvement (e.g., extra log line), commit, push, `ssh ceci git pull && docker compose up -d --build`, verify. This proves the deploy loop works.
