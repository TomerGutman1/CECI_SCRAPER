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

(to be filled)
