# Full Pipeline Task Prompt
**Created:** 2026-02-22
**Purpose:** Hand this to whoever runs the full scrape+AI pipeline

---

## Task

Run the full 2-phase pipeline to scrape and AI-process all Israeli government decisions, then validate the output.

## Source File (CRITICAL — READ THIS)

**USE THIS FILE AND ONLY THIS FILE as input:**

```
data/catalog_manifest.json
```

- **25,421 entries**, each with a unique URL to scrape
- **0 duplicate `decision_key`s**, **0 duplicate URLs**
- Contains: `url`, `title`, `decision_number`, `decision_date`, `government_number`, `prime_minister`, `committee`, `description`, `decision_key`
- Created by Phase 1 (catalog discovery) on Feb 19, 2026

**DO NOT USE any of these files as source:**
- `backups/pre_deployment_20260218_143933.json` — old DB dump, contains 7,771 duplicate keys
- `data/scraped/ai_enhanced.json` — processed from the corrupt backup, inherits all duplicates
- `data/scraped/latest.json` — test file with 5 entries only
- Any file in `backups/` — all are old DB snapshots with known duplicate issues

**Why:** The manifest was built by crawling the gov.il catalog API from scratch. It is the only clean, deduplicated source of truth. All backup files were exported from the database which already had duplicates before the unique constraint was added.

---

## Environment

**Runs on local macOS (Apple Silicon).** No server available.

- **Machine:** Mac with Apple Silicon (ARM64)
- **Project path:** `/Users/tomergutman/Downloads/GOV2DB`
- **Python:** python3 (system)

**Apple Silicon Chrome Setup (IMPORTANT):**
- `undetected_chromedriver` is monkey-patched in `src/gov_scraper/utils/selenium.py` to use `mac-arm64` instead of `mac-x64`
- Pre-patched chromedriver at: `~/Library/Application Support/undetected_chromedriver/patched_chromedriver`
- If Chrome updates, you may need to re-download and re-patch: `codesign -s - -f <path_to_chromedriver>`
- Phase A was previously tested and **worked** locally — 5 decisions scraped in 1.6 min

**Required env vars** (in `.env` file at project root):
- `GEMINI_API_KEY` — Google Gemini API key
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` — Service role JWT
- `USE_UNIFIED_AI=true` — Enables 1-call AI (instead of 6 calls)

**macOS-specific constraints:**
- `--no-headless` opens real Chrome windows on screen — user must not close them
- Phase A and Phase B MUST run separately (Gemini httpx hangs while Chrome is open)
- If the pipeline runs both phases together, Chrome is closed between them automatically
- The process takes hours — keep Mac awake (use `caffeinate` or disable sleep)

---

## The Pipeline — 2 Phases

### Phase A: Scrape (Chrome → raw JSON)

Opens each URL from the manifest, extracts decision content with Chrome, saves to a raw intermediate file.

```bash
python3 bin/full_local_scraper.py \
  --manifest data/catalog_manifest.json \
  --output data/scraped/production_run.json \
  --no-headless \
  --verbose
```

**Parameters explained:**
| Parameter | Value | Why |
|-----------|-------|-----|
| `--manifest` | `data/catalog_manifest.json` | The ONLY clean source file. 25,421 unique entries. |
| `--output` | `data/scraped/production_run.json` | Final output path. Raw data saves to `production_run_raw.json` automatically. |
| `--no-headless` | (flag) | REQUIRED. Headless Chrome is blocked by Cloudflare. Server uses Xvfb virtual display. |
| `--verbose` | (flag) | Enables debug logging to `logs/full_scraper.log` |
| `--max-decisions N` | NOT SET | Do NOT set this — we want all 25,421. Only use for testing (e.g. `--max-decisions 5`). |
| `--resume` | NOT SET on first run | Use ONLY if Phase A crashes and you need to continue from where it stopped. |

**What happens:**
1. Loads manifest (25,421 entries)
2. Opens Chrome with undetected_chromedriver (anti-Cloudflare)
3. Visits each URL, waits for page load, extracts content
4. Saves raw scraped data to `production_run_raw.json` every 50 decisions
5. After all scraping: **closes Chrome completely**
6. Proceeds to Phase B automatically

**Estimated time:** 2-4 hours for scraping (rate-limited to avoid blocks)
**Keep Mac awake:** Run `caffeinate -dims` in a separate terminal, or disable sleep in System Settings.

**If it crashes mid-scrape:**
```bash
python3 bin/full_local_scraper.py \
  --manifest data/catalog_manifest.json \
  --output data/scraped/production_run.json \
  --no-headless \
  --resume \
  --verbose
```
The `--resume` flag reads existing `production_run_raw.json` and skips already-scraped decisions.

### Phase B: AI Processing (raw JSON → enhanced JSON)

Runs after Phase A automatically. Or run separately with `--ai-only`:

```bash
python3 bin/full_local_scraper.py \
  --manifest data/catalog_manifest.json \
  --output data/scraped/production_run.json \
  --ai-only \
  --verbose
```

**What happens:**
1. Loads `production_run_raw.json` (the Phase A output)
2. For each decision, calls Gemini API (unified processor, 1 call) to generate:
   - `summary` — Hebrew summary (dynamic length based on content)
   - `operativity` — "אופרטיבית" or "דקלרטיבית"
   - `tags_policy_area` — from 46 authorized tags
   - `tags_government_body` — from 45 authorized bodies
   - `tags_location` — location tags
   - `all_tags` — deterministic rebuild from individual fields
3. Applies post-processing: whitelist enforcement, body normalization, prefix stripping
4. Saves to `production_run.json` every 50 decisions

**Estimated time:** 3-6 hours (depends on Gemini rate limits)

**CRITICAL:** Do NOT run Gemini while Chrome is still open. The 2-phase design handles this — Phase B only starts after Chrome is fully closed.

---

## Phase C: Validation (MUST DO BEFORE ANYTHING ELSE)

After Phase B completes, validate the output:

```python
python3 -c "
import json
from collections import Counter

with open('data/scraped/production_run.json') as f:
    data = json.load(f)

# 1. Total count
print(f'Total records: {len(data)}')

# 2. Duplicate decision_keys (MUST BE 0)
keys = [r['decision_key'] for r in data]
dup_keys = {k:c for k,c in Counter(keys).items() if c>1}
print(f'Duplicate decision_keys: {len(dup_keys)}')
assert len(dup_keys) == 0, f'FAIL: {len(dup_keys)} duplicate keys!'

# 3. Duplicate URLs (MUST BE 0)
urls = [r['decision_url'] for r in data]
dup_urls = {u:c for u,c in Counter(urls).items() if c>1}
print(f'Duplicate URLs: {len(dup_urls)}')
assert len(dup_urls) == 0, f'FAIL: {len(dup_urls)} duplicate URLs!'

# 4. No empty summaries
empty_summaries = sum(1 for r in data if not r.get('summary'))
print(f'Empty summaries: {empty_summaries}')

# 5. Operativity balance (target: 50-65% operative)
ops = Counter(r.get('operativity') for r in data)
total = sum(ops.values())
for op, count in ops.most_common():
    print(f'  {op}: {count} ({count/total*100:.1f}%)')

# 6. No forbidden summary prefix
prefix_count = sum(1 for r in data if r.get('summary','').startswith('החלטת ממשלה'))
print(f'Forbidden summary prefix: {prefix_count}')

# 7. Records with content
has_content = sum(1 for r in data if len(r.get('decision_content','')) > 100)
print(f'Records with content >100 chars: {has_content} / {len(data)}')

print()
print('ALL CHECKS PASSED' if len(dup_keys)==0 and len(dup_urls)==0 else 'CHECKS FAILED')
"
```

**Expected output:**
- Total records: ~25,421
- Duplicate decision_keys: 0
- Duplicate URLs: 0
- Operativity: 50-65% אופרטיבית
- Forbidden prefix: 0

---

## Before You Start — Clean Slate

**Delete any leftover output files** from previous runs to prevent stale data from merging in:

```bash
rm -f data/scraped/production_run.json
rm -f data/scraped/production_run_raw.json
rm -f data/scraped/production_run_checkpoint.json
```

This is critical. The code previously had a bug where it silently loaded existing output files and merged new results into them, even without `--resume`. This bug has been fixed (only `--resume` loads old files now), but deleting stale files is still good hygiene.

---

## DO NOT

1. **DO NOT push to Supabase** without explicit user approval
2. **DO NOT use backup files** as source — they contain duplicates
3. **DO NOT close Chrome windows** during Phase A — the scraper controls them
4. **DO NOT run headless Chrome** — Cloudflare blocks it
5. **DO NOT call Gemini while Chrome is open** — httpx hangs due to UC conflict
6. **DO NOT skip validation** — always run Phase C before reporting success
7. **DO NOT use `--resume` on first run** — only use it after a crash to continue

---

## File Map

```
INPUTS:
  data/catalog_manifest.json          ← THE source (25,421 unique entries)

OUTPUTS (generated by pipeline):
  data/scraped/production_run_raw.json  ← Phase A output (raw scraped HTML content)
  data/scraped/production_run.json      ← Phase B output (AI-enhanced, final)
  logs/full_scraper.log                 ← Full debug log

DO NOT TOUCH:
  backups/*.json                        ← Old DB dumps with duplicates
  data/scraped/ai_enhanced.json         ← Built from corrupt backup
  data/scraped/latest*.json             ← Test files
```

---

## Quick Test (Before Full Run)

To verify everything works, run with 5 decisions first:

```bash
python3 bin/full_local_scraper.py \
  --manifest data/catalog_manifest.json \
  --output data/scraped/test_5.json \
  --no-headless \
  --max-decisions 5 \
  --verbose
```

Check: `test_5.json` should have 5 records, each with summary, tags, operativity. `test_5_raw.json` should have raw scraped content.

---

## Known Bugs Fixed (Feb 22, 2026)

These bugs were found during deep audit and **already fixed** in the codebase. Listed here so you understand what was wrong and don't reintroduce them.

### Fixed: Stale file merge (full_local_scraper.py)
**Was:** Both Phase A and B always loaded existing output files and merged new data into them, even without `--resume`. A leftover corrupt file would silently contaminate a fresh run.
**Fix:** Only loads existing files when `--resume` is explicitly passed.

### Fixed: Empty strings in tag deduplication (ai_post_processor.py:472)
**Was:** `"tag1;;tag3".split(';')` → `['tag1', '', 'tag3']` — empty strings leaked into `all_tags`.
**Fix:** Added `if t.strip()` filter to all `.split()` calls in `deduplicate_tags()` and `all_tags` rebuild (6 locations total across ai_post_processor.py and ai.py).

### Fixed: Invalid decision_key generation (decision.py:564-584)
**Was:** If `decision_number` was missing/None, created malformed keys like `"37_"` or `"37_None"`. Also crashed with `KeyError` if `url` was missing from decision_meta.
**Fix:** `_build_result_from_meta()` now validates `url`, `decision_number`, `government_number` before building. Returns `None` (not partial data) on missing fields.

### Fixed: Unified AI corrupts data before fallback (ai.py:~1018)
**Was:** If unified AI failed mid-processing after `.update()` modified `decision_data`, the legacy fallback ran on partially corrupted data.
**Fix:** Creates `decision_data.copy()` before unified processing. Restores the clean copy if unified fails.

### Fixed: Silent whitelist bypass (ai_post_processor.py:26-50)
**Was:** If `new_tags.md` or `new_departments.md` was missing, returned empty set → whitelist enforcement short-circuited → all tags passed unchecked.
**Fix:** `_load_authorized_list()` now raises `RuntimeError` if file is missing or list is empty.

### Fixed: Double post-processing (push_local.py:173)
**Was:** `push_local.py` re-applied `post_process_ai_results()` on data already post-processed in the pipeline. Could mutate tags differently on second pass.
**Fix:** Replaced with validation-only checks (verify tags are on whitelist, flag if not — but don't re-mutate).

---

## Known Risks NOT Fixed (Accept or Monitor)

These are lower-priority issues found during audit. They're unlikely to cause data loss in a normal run but worth knowing about.

1. **Cloudflare detection is weak** — `scrape_decision_content_only()` returns `""` for both Cloudflare blocks and real empty pages. The pipeline treats both as "scrape failed" and logs a warning, but can't distinguish them. **Mitigated by:** `--no-headless` flag + rate limiting + retry logic.

2. **`prepare_for_database()` strips None values** — `{k: v for k, v in db_decision.items() if v is not None}` removes nullable fields instead of preserving NULL. **Impact:** Minor — DB uses defaults for missing columns.

3. **Policy tags always default to "שונות"** — If AI returns nothing valid, record gets `"שונות"` instead of empty. Government bodies default to `""`. Asymmetric but intentional.

4. **Committee name truncated to 4 words** — `extract_committee_name()` takes max 4 words. Some real committee names are 5+ words. **Impact:** ~5% of committee names slightly truncated.

5. **Content extraction can grab page furniture** — The fallback extraction strategy takes the "largest text block" on the page, which could be a table of contents or sidebar. **Mitigated by:** Hebrew text check + 50-char minimum + content validation in Phase A.
