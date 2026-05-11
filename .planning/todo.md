# Fix: gov.il API Migration + Silent Failures

**Date:** 2026-05-11
**Goal:** Make daily sync work reliably and silently never break again.

## Root Causes (all confirmed via live testing + log analysis)

### #1 — gov.il migrated APIs to centralized gateway
- Old base (now dead): `https://www.gov.il/CollectorsWebApi/api/` and `https://www.gov.il/ContentPageWebApi/api/`
- New base: `https://openapi-gc.digital.gov.il/pub/cio/govil/rest/collectors/v1/api/` and `.../contentpage/v1/api/`
- Required: `x-client-id: 9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc` header
- Verified from gov.il's own SPA config at `/CollectorsWebApi/client-config.js` and `/ContentpageWebApi/client-config.js`
- Old URLs were intermittently serving stale data until ~May 10, now consistently serve SPA HTML fallback

### #2 — Silent failure on `government_number=None`
- `_build_result_from_meta()` decision.py:582: `gov_num = decision_meta.get('government_number', GOVERNMENT_NUMBER)` returns None (not default) when key exists with None value
- Caused "FAILED" cron runs for months when only oddball decision was new (like #3947 missing `ממשלה` metadata)

### #3 — Old catalog data was frozen, then dead
- Old endpoint stopped getting new decisions ~April 27 while still responding with stale JSON
- Solved automatically by #1

### #4 — sync.py exit code misreports partial success
- Returns False if ANY decision fails, even if many succeeded
- Causes wrapper to log SYNC FAILED → healthcheck reports unhealthy
- Should return True if at least one decision inserted

### #5 — Sort key bug for non-matching URL formats
- `_extract_decision_sort_key()` regex doesn't match all URL formats
- Non-matching URLs get sort key (0,0,0,0), can position incorrectly
- Should push non-matches to END of list

## Implementation Plan

### Phase 1: Code fixes
- [ ] **catalog.py**:
  - Add `GOVIL_CLIENT_ID` constant near top
  - Update `CATALOG_API_URL` to new gateway URL
  - Optional resilience: `_fetch_govil_config()` that reads live `/CollectorsWebApi/client-config.js`, falls back to constants
  - Update `_create_api_session()` to set `x-client-id` and standard headers as defaults
  - Update both `extract_catalog_via_api()` and `paginate_full_catalog()` to pass header
  - Improve error: log first 200 chars of body when JSON parse fails
  - Fix `_extract_decision_sort_key()`: return `(1, 0, 0, 0)` for non-matches so they sort AFTER real entries
- [ ] **decision.py**:
  - Add `GOVIL_CLIENT_ID` constant (import from catalog or duplicate — duplicate to avoid circular)
  - Update `CONTENT_PAGE_API_BASE` to new gateway URL
  - Update `scrape_decision_via_api()` to pass `x-client-id` header
  - Fix `_build_result_from_meta()` line 582: use `decision_meta.get('government_number') or GOVERNMENT_NUMBER` (handles None, "", missing)
  - Also: try to derive gov_num from `decision_meta['url']` (pattern `/he/pages/dec{num}-{year}` → year → PM mapping)
- [ ] **sync.py**:
  - `_insert_to_database()`: return True if `inserted_count > 0`, regardless of error_messages
  - `_run_api_sync()` / `_run_selenium_sync()`: if `processed_decisions` is empty but `_filter_new_entries` returned new ones, return False (we tried and totally failed). If catalog was empty in first place, return True (nothing to do is success).
  - `main()`: keep returning script's exit code based on final return value
- [ ] **aux scripts**: `bin/process_missing_decisions.py` and `bin/diagnose_url_mismatches.py` — update hardcoded URLs

### Phase 2: Testing
- [ ] Standalone test script at `/tmp/test_govil_fix.py`:
  - Hit new catalog URL, verify returns JSON with >0 results
  - Hit new content-page URL for recent decision, verify shape
  - Test `_build_result_from_meta` with: gov=None, gov="", gov=37, gov="37"
  - Test sort key with: valid URL, old-format URL, garbage URL
- [ ] Local sync.py test: `--max-decisions 2 --use-api --no-approval --verbose`
- [ ] Verify 2 decisions inserted to DB

### Phase 3: Deploy
- [ ] Commit + push to master
- [ ] SSH ceci, git pull, docker compose up -d --build
- [ ] Wait for container HEALTHY
- [ ] In-container test: `docker exec gov2db-scraper python3 bin/sync.py --use-api --max-decisions 5 --no-approval --verbose`
- [ ] Verify healthcheck: `docker exec gov2db-scraper /usr/local/bin/healthcheck.sh`
- [ ] Tail logs for next cron cycle (won't run until 02:00 IST next day)

### Phase 4: Documentation
- [ ] Update `.planning/state.md` with: fix date, DB state pre/post, deployment status
- [ ] Update CLAUDE.md if needed (probably not — endpoint detail is in code)

## Edge cases to handle

1. **Network failure to gateway** → curl_cffi raises exception → existing retry loop handles
2. **Gateway returns 5xx** → `resp.raise_for_status()` raises → retry loop handles
3. **Gateway returns 200 with HTML** → `resp.json()` raises → retry loop handles + improved error log
4. **gov.il rotates clientId** → resilience via dynamic config fetch; warn in log
5. **catalog returns entry with `government_number=None`** → fixed fallback; falls back to default 37 (correct for current government)
6. **catalog returns entry with URL not matching regex** → sort key (1,0,0,0) puts at end, doesn't crash
7. **Partial sync (e.g., 9 of 10 decisions succeed)** → sync.py returns True, wrapper logs SUCCESS, healthcheck reports healthy
8. **Catalog returns 0 results** → sync.py returns True (nothing to do), wrapper logs SUCCESS
9. **Gemini 429 on all attempts** → existing retry+wait logic + skip decision; we report failure for that decision but continue with others

## Review section (filled after completion)

### Was completed
- ✅ All 5 root causes fixed (URL migration ×2, gov_num=None silent failure, exit code, sort key)
- ✅ +1 bonus: fail-fast Gemini hard-quota detection (saves ~15 min per decision when quota=0)
- ✅ Dynamic gov.il SPA config fetch as self-healing layer (if endpoint moves again, code adapts)
- ✅ HTML-fallback detection on both API call sites with body preview in error log
- ✅ Standalone test script with 23 assertions — all pass against live gov.il
- ✅ End-to-end verified from production container: catalog returns 25,871 entries, content-page scrapes work
- ✅ Bundled 4 uncommitted dependency changes that would have blocked deployment

### Caveats / known limitations
- ⚠️ **Gemini billing blocker** — current API key shows `limit: 0` for all free-tier metrics.
  Until user enables billing or rotates key, cron will scrape successfully but fail at AI step.
  Mitigation: fail-fast logic ensures runs complete in ~30s instead of 15-30 min.
- ⚠️ Selenium-based catalog path (`extract_decision_urls_from_catalog_selenium`) still uses
  the new URL but Selenium's `drv.get()` cannot inject x-client-id header. Marked with
  warning in code. Only invoked by full re-discovery (`bin/discover_all.py`) — not daily cron.
- ⚠️ The wrapper's exit-code reporting (`SYNC FAILED` vs `Sync completed successfully`)
  now correctly reflects whether ANY decision made it to DB, vs the prior all-or-nothing
  reporting.

### Cron behavior after this fix
- **If Gemini works:** cron scrapes new decisions, AI-processes, inserts to DB, logs SUCCESS,
  healthcheck reports HEALTHY. ~308 backlog catches up over multiple nights.
- **If Gemini fails (current state):** cron scrapes, hits hard quota at AI step, fails fast
  (~30s total run instead of 60+ min), wrapper retries 3x (all fail fast), logs SYNC FAILED,
  healthcheck reports unhealthy. No data corruption, no infinite hangs.

### Files changed (3 commits, master)
1. `f37e912` — fix: migrate to gov.il openapi-gc gateway + fix silent sync failures
   - .planning/state.md, .planning/todo.md, bin/sync.py, src/gov_scraper/scrapers/catalog.py,
     src/gov_scraper/scrapers/decision.py
2. `<sha2>` — fix: ship uncommitted Phase 1+2 improvements blocking import in catalog.py
   - src/gov_scraper/config.py (get_pm_for_decision function)
   - src/gov_scraper/processors/{ai_post_processor,qa,unified_ai}.py
3. `<sha3>` — fix(gemini): fail-fast on hard daily-quota exhaustion
   - src/gov_scraper/processors/{ai,unified_ai}.py

### What to verify after Gemini is unblocked
1. `make sync-test` — should insert 1 decision successfully
2. Wait for next 02:00 IDT cron — should report SUCCESS and insert backlog
3. `docker exec gov2db-scraper /usr/local/bin/healthcheck.sh` — should report HEALTHY
4. Supabase DB: latest decision_date should be near current date (decisions through May 7+)

