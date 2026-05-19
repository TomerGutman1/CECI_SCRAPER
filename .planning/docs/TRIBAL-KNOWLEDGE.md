# Tribal Knowledge — Non-Obvious Gotchas

Things that aren't visible from reading the code but will bite you. Each entry includes
the *why* (so you can judge edge cases) and the *how to apply* (so you know when it
matters).

**Migrated from prior owner's Claude memory on 2026-05-19.** If you discover new
non-obvious behaviors, add them here so the next person doesn't relearn them.

---

## 1. gov.il API gateway migration (May 2026)

**The fact.** Both gov.il APIs we depend on moved to a centralized gateway in May 2026.
The old URLs are DEAD.

| Old (DEAD) | New |
|---|---|
| `https://www.gov.il/CollectorsWebApi/api/DataCollector/GetResults` | `https://openapi-gc.digital.gov.il/pub/cio/govil/rest/collectors/v1/api/DataCollector/GetResults` |
| `https://www.gov.il/ContentPageWebApi/api/content-pages/{slug}` | `https://openapi-gc.digital.gov.il/pub/cio/govil/rest/contentpage/v1/api/content-pages/{slug}` |

**Required header on BOTH endpoints:**
```
x-client-id: 9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc
```

The client ID is **public** — gov.il's own SPA loads it from
`https://www.gov.il/CollectorsWebApi/client-config.js`. Not a secret.

**Why.** gov.il transitioned away from per-app WebApi mounts to a centralized API gateway.
They had a transition window of ~2 months where the old endpoints served stale data; the
old URLs went fully dead around May 11.

**Self-healing layer.** `catalog.py:_fetch_govil_config()` reads gov.il's live SPA config
at startup. If gov.il rotates the clientId or moves the gateway again, the code adapts
automatically and logs a warning that the hardcoded constants drifted. The constants are
authoritative for offline use (tests, no-network); the live config wins at runtime.

**Selenium caveat.** `extract_decision_urls_from_catalog_selenium()` uses
`webdriver.get()` which cannot inject custom headers — so the Selenium path against the
new gateway will be rejected. Only impacts full re-discovery (`bin/discover_all.py`),
not the daily cron path. Marked with a warning in code.

**JSON shape preserved.** All field names (`מספר החלטה`, `תאריך פרסום`, `ממשלה`,
`ועדות שרים`, `contentMain.htmlContents`) are unchanged. Existing parsers work as-is.

**How to apply.** If you see "HTML SPA shell returned instead of JSON" in logs, the
gateway moved again. Check `_fetch_govil_config()` output and update `GOVIL_CLIENT_ID` /
`GOVIL_COLLECTORS_API_BASE` constants in `catalog.py` + `CONTENT_PAGE_API_BASE` in
`decision.py`. **Never revert to `www.gov.il/*WebApi/*` URLs.**

---

## 2. Gemini billing / quota: `limit: 0` means free tier expired

**The fact.** When Gemini API requests fail with 429 and the response body contains
`limit: 0` for free-tier metrics, the API key has *no* free-tier quota. This is independent
of any code change — the catalog scrape and content-page scrape work fine; only the AI
processing step fails.

**Why.** Either (a) the GCP project ran out free-tier trial and billing is not enabled, or
(b) free tier was disabled at the project level. As of 2026-05-13 the project is on paid
tier; if `limit: 0` returns, billing got disabled.

**Fail-fast logic.** `processors/ai.py` and `processors/unified_ai.py` detect the
`limit: 0` substring in 429 errors and **exit fast (~30s)** instead of running through
exponential backoff for 15+ min per decision. Cron run completes quickly when quota is
hard-blocked, so observability stays clean.

**How to apply.** If you see "no new decisions in DB despite cron firing":
```bash
ssh ceci "docker exec gov2db-scraper tail /app/logs/daily_sync.log | grep 'limit: 0'"
```
If matches → enable billing on the GCP project owning the `GEMINI_API_KEY`, or rotate to
a key from a billed project. No code change needed once Gemini works again.

Verify the fix:
```bash
ssh ceci 'docker exec gov2db-scraper python3 /app/bin/sync.py --use-api --max-decisions 1 --no-approval --verbose 2>&1 | grep -E "(Successfully|Failed|429)"'
```
Should show "Successfully processed decision #..." not "Gemini DAILY quota exhausted".

---

## 3. Chrome + Gemini conflict on macOS

**The fact.** On macOS, Gemini API calls via `httpx` hang indefinitely while
`undetected_chromedriver` (UC) Chrome is running in the same process.

**Why.** UC's Chrome process conflicts with httpx's network stack on macOS. Doesn't
happen on Linux (the production server). Discovered the hard way.

**The fix.** `bin/full_local_scraper.py` is a 2-phase pipeline:
- **Phase A:** Scrape with Chrome → save to `data/scraped/*_raw.json` → close Chrome
- **Phase B:** AI-process with Gemini (no Chrome running) → save final output

Flags: `--ai-only` skips Phase A and runs Phase B on existing raw data; `--resume` lets
both phases pick up where they left off (dedup by `decision_key`).

**How to apply.** **Never call Gemini while Chrome is running on macOS.** If you're
debugging a flow that mixes scraping and AI, run it inside the Docker container (Linux)
or split into two scripts.

Daily cron is unaffected — it uses the API path (`bin/sync.py --use-api`), no Chrome.

---

## 4. Apple Silicon Chrome / undetected_chromedriver setup

**The fact.** Multiple workarounds needed to make UC Chrome work on Apple Silicon Macs.

**Issues + fixes (all in `src/gov_scraper/utils/selenium.py`):**

1. **UC hardcodes `mac-x64`.** UC's platform detection picks `mac-x64` on all Darwin
   regardless of CPU. We monkey-patch this to `mac-arm64` so the right chromedriver gets
   downloaded.

2. **ChromeDriver IPv6 download hangs.** UC tries to download chromedriver from a URL
   that resolves to an IPv6 address; on some Macs this hangs forever. We pre-download
   the driver manually and pass `driver_executable_path` to skip UC's download path.

3. **UC patches the binary in-place** to evade detection, which invalidates the macOS
   signature → Gatekeeper kills the process. Fix: re-codesign with an ad-hoc identity:
   ```
   codesign -s - -f <path-to-chromedriver>
   ```

**Pre-patched driver location:**
```
~/Library/Application Support/undetected_chromedriver/patched_chromedriver
```

**Detection.** `_detect_chrome_version()` uses
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --version` on macOS, falls
back to Linux commands elsewhere.

**How to apply.** If Chrome updates and Selenium breaks on Mac:
1. Delete `~/Library/Application Support/undetected_chromedriver/`
2. Re-run `make discover` or any Selenium command — UC will re-download
3. Re-codesign the new patched binary

If you're not doing local discovery / re-scraping, this never matters. The daily cron
runs in Docker on Linux and bypasses all of this.

---

## 5. Docker / cron pitfalls (entrypoint + sync wrapper)

These are subtle and have all caused outages at least once. Don't change them without
understanding why.

### Never use `set -e` in `docker/randomized_sync.sh`
**Why.** Pipes (`cmd | tee logfile`) propagate the LAST stage's exit code, not the
sync.py exit code. `set -e` combined with pipes masks real failures. We need to capture
the actual sync exit code via `${PIPESTATUS[0]}` or by redirecting (`>> file 2>&1`)
instead of piping.

### Never use `tee` to capture sync output
**Why.** `python3 sync.py | tee log` exits with `tee`'s exit code, which is always 0
unless the disk is full. Real sync failures get reported as success. Use
`python3 sync.py >> log 2>&1` and capture `$?` directly.

### Never hardcode env-var names in `docker/docker-entrypoint.sh`
**Why.** The entrypoint must export *all* Docker env vars to `/app/.env` so cron (which
doesn't inherit container env) can read them. Older versions hardcoded `OPENAI_*` and
broke when we migrated to Gemini. Use `env | grep ...` generic export. The current
entrypoint validates `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` are
all present and fails hard (exit 1) if any are missing.

### `./healthcheck/` volume mount preserves state
**Why.** `healthcheck.sh` writes `last_failure.txt` and `FRESH_START` sentinel files.
These must persist across container restarts for the "3 failures → unhealthy" logic
to work. Volume mount in `docker-compose.yml` handles this. Don't remove it.

### Chrome / Selenium tests fail on Apple Silicon via Docker
**Why.** Rosetta limitation — UC Chrome can't run in arm64 containers properly. Test
suite that uses Chrome will fail locally on M1/M2/M3 Macs. Run on the Linux server
instead, or skip Chrome tests (`pytest -m 'not selenium'`).

---

## 6. 3-Layer Whitelist Enforcement

**The fact.** Only authorized policy tags and government-body tags are allowed in the DB.
Enforced at three layers.

| Layer | What | File |
|---|---|---|
| 1. Prompt | AI is told the full authorized list | `processors/ai_prompts.py` |
| 2. Normalization | `BODY_NORMALIZATION` map (50+ entries): unauthorized → authorized, or → None (drop) | `processors/ai_post_processor.py` |
| 3. Whitelist enforcement | `enforce_policy_whitelist()` / `enforce_body_whitelist()` post-process | `processors/ai_post_processor.py` |

**Sources of truth:**
- `new_tags.md` — 46 authorized policy tags
- `new_departments.md` — 45 authorized government bodies

Loaded at module level when `ai_post_processor` imports.

**Fuzzy match details.** Jaccard word overlap ≥ 0.5 threshold for close matches.
Hebrew double-vav normalization (`וו → ו`) handles spelling variants.

**Fallbacks.**
- If no policy tags survive → falls back to `"שונות"` (Other)
- If no bodies survive → returns empty string (legitimate for committee/admin decisions)

**How to apply.** Don't modify `new_tags.md` or `new_departments.md` casually. The
whole pipeline assumes those lists are authoritative. If a new tag/body is needed,
update the file AND review the normalization map in `ai_post_processor.py`.

---

## 7. AI Post-Processor Pipeline

**The fact.** Every AI result passes through a deterministic post-processor before
hitting the DB. This catches AI drift and enforces invariants.

**Called from both unified and legacy paths:**
```python
post_process_ai_results(decision_data, decision_content)
```
in `ai.py`.

**What it does:**
1. Strip `"החלטת ממשלה מספר..."` summary prefix (regex)
2. Deduplicate tag lists
3. Normalize committee variants → canonical "ועדת השרים..."
4. Filter generic locations (`"ישראל"` etc.)
5. Apply `BODY_NORMALIZATION` map
6. Enforce whitelists (policy + bodies)
7. Pattern-based operativity override (appointments/committees → declarative)
8. Rebuild `all_tags` deterministically from individual fields
9. Validate operativity classification

**Dynamic summary length.** `calculate_dynamic_summary_params()` in `ai.py` picks
instructions + max_tokens based on content length:
- `<2K chars` → 1-2 sentences (200 tokens)
- `2-5K` → 2-3 sentences (300)
- `5-10K` → 3-4 sentences (400)
- `10-20K` → 4-5 sentences (500)
- `>20K` → 5-7 sentences (700)

---

## 8. Content truncation: there is none

**Status:** **NO truncation** — all AI functions receive full decision content.

Gemini 2.0 Flash supports 1M tokens. Max decision content is ~32K chars (~15K tokens).
Cost is negligible.

**Functions confirmed receiving full content:** `generate_summary`,
`generate_operativity`, `generate_policy_area_tags_strict`,
`generate_government_body_tags_validated`, `generate_government_body_tags` (legacy),
`generate_location_tags`, `generate_special_category_tags`.

Only `_ai_summary_fallback` uses 1,500 chars (summary fallback only, not full pipeline).

**Stats.** 11 decisions are exactly 32,768 chars (DB / scraper limit). Not a Gemini limit.

---

## 9. Pipeline Vulnerability Fixes (Feb 2026, all live)

5 critical/high fixes that should not be reverted:

1. **`generate_decision_key()`** (`processors/incremental.py`) — explicit None check
   prevents "37_None" keys
2. **`check_existing_decision_keys()`** (`db/dal.py`) — 5 retries + `RuntimeError`
   on failure (no silent empty set, which used to cause spurious re-insertions)
3. **`try_url_variations()`** (`scrapers/catalog.py`) — handles `a/b/c` suffixes +
   hyphen patterns
4. **`extract_and_format_date()`** (`scrapers/decision.py`) — returns None on parse
   failure + validates date range (1948–2027)
5. **`insert_decisions_batch()`** (`db/dal.py`) — 3× batch retry + 2× individual
   retry before failing loud

Status doc: `PIPELINE-VULNERABILITIES.md`.

---

## 10. Hebrew-prefix decision keys

**The fact.** Some decisions have Hebrew prefixes in their decision_number, e.g.
`37_מח/6` (privatization committee), `37_רהמ/95` (PM directive), `37_גבל/...`.

**Why.** Israeli government uses prefixes for special-category decisions (committee
delegations, classified matters, etc.). Stored historically with Hebrew characters.

**Fix (Feb 2026 + May 2026).** `normalize_decision_key()` in `db/dal.py` auto-converts
Hebrew prefixes to Latin form at insert time:
- `מח` → `mh`
- `רהמ` → `rhm`
- `גבל` → `gbl`
- etc.

The validator `_is_valid_decision_key_format` accepts both `\d+_\d+[a-z]?` (regular)
and `\d+_[a-z]+\d+` (transliterated-Hebrew).

**How to apply.** Don't write new code that assumes decision_number is purely numeric.
Use the DAL's `normalize_decision_key()` if constructing keys manually.

---

## 11. Cloudflare bypass: headless Chrome is BLOCKED

**The fact.** Headless Chrome is blocked by Cloudflare on gov.il. Always use `--no-headless`.

**Docker workaround.** The container uses Xvfb virtual display (`:99`) to run non-headless
Chrome without an X server. Set up in `docker/Dockerfile`.

**Daily cron path doesn't use Chrome at all** — it uses the gov.il REST API (Content
Page API) via `curl_cffi` with browser TLS impersonation. ~940 pages/min, zero Cloudflare
blocks observed.

**How to apply.** If you write a new scraper path, prefer the API. Only fall back to
Selenium for cases where API doesn't expose the data.

---

## 12. Date format conventions

- **gov.il website:** `DD.MM.YYYY`
- **Our database:** `YYYY-MM-DD` (ISO)
- **Date range validation:** `extract_and_format_date()` returns None outside `1948–2027`

---

## 13. Prime Minister date-awareness

**The fact.** Government 36 (Bennett-Lapid) had a mid-term PM transition on 2022-07-01.
Decisions before that date have PM=Bennett; after, PM=Lapid.

**Fix.** `get_pm_for_decision()` in `src/gov_scraper/config.py` is date-aware. Pass
the decision date, not just the government number.

---

## 14. Don't run `make sync` on macOS

Use Docker. The Chrome + Gemini conflict (#3) plus Apple Silicon UC issues (#4) make
local sync flaky. Docker container runs Linux, no issues.

`make sync-test` is fine for testing the pipeline logic if no AI step is involved
(which is rare).

---

## 15. Sort key bug for non-matching URLs

**The fact.** `_extract_decision_sort_key()` in `catalog.py` returns a sort tuple
based on regex matching the URL. Legacy URL formats (old governments) don't match
and previously returned `(0,0,0,0)`, which sorted them BEFORE real entries —
corrupting downstream baseline logic.

**Fix.** Non-matching URLs now return `(1, 0, 0, 0)` so they sort AFTER real entries,
or are explicitly handled as "out of recognized format".

---

## 16. The 6 PDF-only decisions (0.1% gap)

**The fact.** 6 decisions in 2020-2026 exist as PDF attachments on gov.il with no
HTML content. Our scraper extracts HTML, so it has nothing to scrape on these.

**Decision (May 13, 2026):** Skip them. 0.1% gap, no user-facing impact. Adding
`pdfplumber` integration is a separate half-day project, parked for now.

**Don't.** Treat these as bugs to fix urgently. They're known and intentional gaps.

---

## What to do when you discover something new

If you spent more than 30 minutes figuring out a non-obvious behavior, add an entry
here. Format:

```markdown
## N. Short title

**The fact.** One-line statement of the surprising behavior.
**Why.** Root cause / the constraint that caused this design.
**How to apply.** When this matters / what to do when you see symptoms.
```

The point is to prevent the next person from relearning what you just learned.
