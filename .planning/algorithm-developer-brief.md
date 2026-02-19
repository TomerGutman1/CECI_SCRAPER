# Brief for Algorithm Developer — GOV2DB Pipeline Rebuild

**Date:** February 19, 2026
**Project:** GOV2DB — Israeli Government Decisions Scraper & Database
**Context:** The production DB was restored from a pre-deployment backup. We need to rebuild the scraping pipeline so new decisions are validated locally before touching the DB.

---

## How to Work With This Brief

1. **Read the full brief first**, then explore the codebase yourself — read the files referenced, understand how data flows, and draw your own conclusions.
2. **Cross-reference everything** — don't trust this brief blindly. Open the actual code, check the authorized lists, look at the backup data.
3. **Ask me (Tomer) any question that isn't clear** — if something in the codebase doesn't match this brief, or if you're unsure about a design decision, stop and ask.
4. **Investigate as you go** — run the existing code, read the logs, test with small batches. Form your own understanding of edge cases.
5. **Document what you find** — if you discover issues not mentioned here, write them down and tell me.

---

## 1. Current DB State

The DB (`israeli_government_decisions` table on Supabase) is currently loaded from a **pre-deployment backup** dated Feb 18, 2026.

### Stats
| Metric | Value |
|--------|-------|
| Total records | 25,021 |
| Date range | 1993-01-03 to 2026-01-25 |
| Government numbers | 25–37 |
| Unique decision keys | 25,021 (unique constraint enforced) |
| Key format | `{gov_num}_{decision_num}` (e.g., `37_3811`) |

### Known Quality Issues in Current Data

| Issue | Scope | Details |
|-------|-------|---------|
| **Unauthorized policy tags** | **54.1%** (13,535 records) | 9 bad individual tags — partial names from old system |
| **Unauthorized gov bodies** | **0.5%** (126 records) | 3 bad names: `הגליל והחוסן הלאומי`, `משרד הנגב`, `שונות` |
| **`all_tags` field mismatch** | **99.9%** (25,001 records) | `all_tags` doesn't match expected concatenation of individual tag fields |
| **Missing operativity** | **0.7%** (174 records) | `operativity` is null or empty |
| **Short content** | **2.4%** (609 records) | `decision_content` < 100 characters |
| **Stub content** | 3 records | Content is literally `המשך התוכן...` |

### What's Fine
- **URLs**: All 25,018 follow valid `/he/pages/` pattern
- **Summaries**: Only 6 have generic prefix issue (~0%)
- **Operativity distribution**: 79.9% אופרטיבית, 19.4% דקלרטיבית (reasonable)
- **No duplicates** — unique constraint on `decision_key` is enforced

### Authorized Lists
- **Policy tags**: 46 tags defined in `new_tags.md`
- **Government bodies**: 45 bodies defined in `new_departments.md`
- Format: plain text, one item per line (no bullets, no markdown — just the name)
- Tags are **semicolon-separated** within a record (e.g., `חינוך; בריאות ורפואה`)

---

## 2. Real Data Examples

### Example A: Record with unauthorized tags (the most common issue — 54% of DB)

**From backup, record `34_3201`:**

```json
{
  "decision_key": "34_3201",
  "decision_date": "2017-11-30",
  "decision_title": "הצעת חוק התקשורת (בזק ושידורים) (תיקון - קליטה בטלפון נייד בכל חלקי הארץ), התשע\"",
  "tags_policy_area": "תקשורת ומדיה; חקיקה, משפט ורגולציה"
}
```

**The problem:** The tag `חקיקה, משפט ורגולציה` contains a comma. When split by semicolons, we get two tags: `תקשורת ומדיה` (valid) and `חקיקה, משפט ורגולציה` (valid — it's one tag name that contains a comma!). But some records have the tag split at the comma incorrectly, producing `חקיקה` and `משפט ורגולציה` as separate tags — neither is on the authorized list.

**The 9 bad partial tags and their correct mappings:**

| Bad Tag (partial) | Correct Authorized Tag |
|--------------------|------------------------|
| `דיור` | `דיור, נדלן ותכנון` |
| `נדלן ותכנון` | `דיור, נדלן ותכנון` |
| `חקיקה` | `חקיקה, משפט ורגולציה` |
| `משפט ורגולציה` | `חקיקה, משפט ורגולציה` |
| `מדע` | `מדע, טכנולוגיה וחדשנות` |
| `טכנולוגיה וחדשנות` | `מדע, טכנולוגיה וחדשנות` |
| `תקציב` | verify in `new_tags.md` |
| `פיננסים` | verify in `new_tags.md` |
| `ביטוח ומיסוי` | verify in `new_tags.md` |

> **Investigation task for you:** Open `new_tags.md` and check what the correct full tag names are for `תקציב`, `פיננסים`, and `ביטוח ומיסוי`. I'm not 100% sure of the mappings.

### Example B: `all_tags` field mismatch (99.9% of records)

**From backup, record `34_3058`:**

```json
{
  "decision_key": "34_3058",
  "tags_policy_area": "מינהל ציבורי ושירות המדינה; מינויים; התייעלות המנגנון הממשלתי",
  "tags_government_body": "משרד האוצר",
  "tags_location": "ישראל",
  "all_tags": "מינהל ציבורי ושירות המדינה; רשות המיסים, הממשלה; ישראל"
}
```

**The problem:** `all_tags` should be the deterministic concatenation of the three tag fields:
```
Expected: "מינהל ציבורי ושירות המדינה; מינויים; התייעלות המנגנון הממשלתי; משרד האוצר; ישראל"
Actual:   "מינהל ציבורי ושירות המדינה; רשות המיסים, הממשלה; ישראל"
```

The `all_tags` field has completely different content — it was generated independently by AI rather than built from the individual fields. **The fix:** always rebuild `all_tags` deterministically. See how it's done in the existing code at `ai_post_processor.py:525-543`.

### Example C: Record with unauthorized gov body

**From backup, record `31_1005`:**

```json
{
  "decision_key": "31_1005",
  "tags_government_body": "שונות"
}
```

`שונות` is not in `new_departments.md`. The body normalization map in `ai_post_processor.py:80-134` handles many variant names, but some still slip through.

### Example D: Missing operativity

**From backup, record `34_456`:**

```json
{
  "decision_key": "34_456",
  "decision_date": "2015-08-13",
  "operativity": null,
  "decision_title": "תקצוב רשויות הניקוז לשנת 2015"
}
```

Operativity must be either `אופרטיבית` or `דקלרטיבית`. The AI sometimes returns null or empty. The existing code has override patterns at `ai_post_processor.py:144-156` but doesn't handle the null case.

### Example E: Short content

**From backup, record `27_2709`:**

```json
{
  "decision_key": "27_2709",
  "decision_content": "החלטת ממשלה בנושא: ההחלטה עוסקת בארגון מחדש של יחידות ממשלתיות ומבוססת על דו\"ח מבקר המדינה."
}
```

Only 91 characters. This is a stub — the scraper didn't get the full content. These should be flagged, not pushed to DB.

### Example F: Full valid record (what the output should look like)

**From backup, record `34_2946`:**

```json
{
  "decision_date": "2017-08-03",
  "decision_number": "2946",
  "committee": "הממשלה ה- 34, בנימין נתניהו",
  "decision_title": "הצעת חוק איסור צריכת זנות ומתן סיוע לשורדות זנות, התשע\"ז-2017",
  "decision_content": "בהתאם לסעיף 66 בתקנון לעבודת הממשלה – לתמוך בקריאה הטרומית בלבד בהצעת חוק איסור צריכת זנות ומתן סיוע לשורדות זנות...",
  "decision_url": "https://www.gov.il/he/pages/2017_dec2946",
  "summary": "החלטת הממשלה היא לתמוך בקריאה הטרומית בלבד בהצעת החוק לאיסור צריכת זנות ומתן סיוע לשורדות זנות של ח\"כ עליזה לביא ואחרים...",
  "operativity": "דקלרטיבית",
  "tags_policy_area": "חקיקה, משפט ורגולציה; רווחה ושירותים חברתיים; שוויון חברתי וזכויות אדם; נשים ומגדר",
  "tags_government_body": "משרד הבריאות",
  "tags_location": "",
  "all_tags": "חקיקה, משפט ורגולציה; רווחה ושירותים חברתיים; שוויון חברתי וזכויות אדם; נשים ומגדר; משרד הבריאות",
  "government_number": "34",
  "prime_minister": "בנימין נתניהו",
  "decision_key": "34_2946",
  "created_at": "2025-05-23T15:07:40.009815+00:00",
  "updated_at": "2025-05-23T15:07:40.009815+00:00"
}
```

**Note:** This record's `all_tags` in the actual backup is `"משפט, חקיקה ורגולציה; הממשלה"` — completely wrong. After our fix, it should be rebuilt as shown above.

---

## 3. Architecture: Scrape → Local File → QA → Push to DB

**The new approach separates scraping from DB insertion.** Nothing goes into the DB until it passes local QA.

### Pipeline Flow

```
[1] SCRAPE            →  [2] SAVE LOCAL JSON    →  [3] LOCAL QA         →  [4] PUSH TO DB

Catalog + Selenium       backups/new_scraped/       Validate all fields      insert_decisions_batch()
  → decision pages       YYYY-MM-DD_HHMMSS.json    against authorized       only records that pass QA
  → AI processing                                   lists, format checks
  → post-processing                                 Fix what's fixable
                                                    Flag what's not
```

### Step 1: Scraping — Where It Happens in Code

The main orchestrator is `bin/sync.py`. Here's how data flows:

**`bin/sync.py:133-144`** — Catalog scraping:
```python
# Step 1: Extract decision entries using Selenium + catalog API
decision_entries = extract_decision_urls_from_catalog_selenium(max_decisions=large_batch_size, swd=swd)
```

**`bin/sync.py:155-170`** — Filter to new entries by checking DB:
```python
# Step 2: Check which entries already exist in database
candidate_keys = []
for entry in decision_entries:
    dec_num = entry.get('decision_number', '')
    if dec_num:
        key = f"{GOVERNMENT_NUMBER}_{dec_num}"
        candidate_keys.append(key)

existing_keys = check_existing_decision_keys(candidate_keys)
new_entries = [key_to_entry[k] for k in candidate_keys if k not in existing_keys]
```

**`bin/sync.py:202-253`** — Per-decision processing loop:
```python
# Scrape content
decision_data = scrape_decision_with_url_recovery(entry, wait_time=wait_time, swd=swd)

# Pre-AI validation
is_valid, error_msg = validate_scraped_content(decision_data)

# AI processing (Gemini)
decision_data = process_decision_with_ai(decision_data)

# Post-AI algorithmic fixes
decision_data = apply_inline_fixes(decision_data)
```

**`bin/sync.py:298-331`** — DB insertion (this is what we're replacing):
```python
# Step 4: Prepare data for database
db_ready_decisions = prepare_for_database(processed_decisions)

# Step 7: Insert into database  ← REPLACE THIS with save-to-file
inserted_count, error_messages = insert_decisions_batch(new_decisions)
```

> **Your change:** Add a `--local-only` flag. When set, replace Step 7 with saving `db_ready_decisions` to a local JSON file instead of calling `insert_decisions_batch()`.

### Step 2: Save to Local JSON (NEW)

Save processed records to `backups/new_scraped/{timestamp}.json`.

**Field reference — must match this schema exactly:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `decision_date` | `YYYY-MM-DD` | Yes | |
| `decision_number` | string | Yes | |
| `committee` | string | No | Can be null |
| `decision_title` | string | No | Can be null (612 nulls in current data) |
| `decision_content` | string | Yes | Full text, max ~32K chars |
| `decision_url` | string | Yes | Must start with `https://www.gov.il` |
| `summary` | string | Yes | 1-7 sentences, dynamic length based on content |
| `operativity` | string | Yes | Must be `אופרטיבית` or `דקלרטיבית` |
| `tags_policy_area` | string | Yes | Semicolon-separated, from authorized list only |
| `tags_government_body` | string | Yes | Semicolon-separated, from authorized list only |
| `tags_location` | string | No | Can be empty |
| `all_tags` | string | Yes | Deterministic: `policy; body; location` concatenation |
| `government_number` | string | Yes | Currently `37` |
| `prime_minister` | string | Yes | Currently `בנימין נתניהו` |
| `decision_key` | string | Yes | `{gov_num}_{decision_num}`, must be unique |
| `created_at` | ISO timestamp | Yes | |
| `updated_at` | ISO timestamp | Yes | |

**Do NOT include**: `id` (auto-generated by Supabase), `embedding` (all null, not used)

### Step 3: Local QA (NEW)

Before pushing to DB, run these checks on the local JSON:

1. **Tag whitelist enforcement** — Every tag in `tags_policy_area` must exist in `new_tags.md`. If not, try fuzzy match or drop.
2. **Body whitelist enforcement** — Every body in `tags_government_body` must exist in `new_departments.md`. If not, try fuzzy match or drop.
3. **`all_tags` rebuild** — Always rebuild deterministically: `tags_policy_area; tags_government_body; tags_location` (skip empty parts).
4. **Operativity validation** — Must be exactly `אופרטיבית` or `דקלרטיבית`.
5. **Summary quality** — Must not start with `החלטת ממשלה מספר` or `החלטה מספר`. Must not be empty.
6. **Decision key format** — Must match `^\d+_\d+[a-cא-ת]?$`.
7. **URL format** — Must start with `https://www.gov.il`.
8. **Content length** — Flag if < 100 chars.
9. **Date validation** — Must be valid date in range 1948–2027.

**Existing code you can reuse for QA checks:**

| Check | Existing function | File & Line |
|-------|-------------------|-------------|
| Policy whitelist | `enforce_policy_whitelist(tags_str)` | `ai_post_processor.py:191-219` |
| Body whitelist | `enforce_body_whitelist(tags_str)` | `ai_post_processor.py:222-247` |
| Body normalization map | `BODY_NORMALIZATION` dict | `ai_post_processor.py:80-134` |
| Fuzzy match | `_fuzzy_match(tag, authorized, threshold)` | `ai_post_processor.py:159-188` |
| Summary prefix strip | `strip_summary_prefix(summary)` | `ai_post_processor.py:250-269` |
| Operativity override | `validate_operativity(op, content)` | `ai_post_processor.py:308-330` |
| `all_tags` rebuild | inline in `post_process_ai_results()` | `ai_post_processor.py:525-543` |
| Content validation | `validate_scraped_content(data)` | `qa.py:2951-2984` |
| Full inline QA | `validate_decision_inline(data)` | `qa.py:3056-3139` |
| Inline fixes | `apply_inline_fixes(data)` | `qa.py:2987-3053` |

**Example: How `all_tags` rebuild works** (from `ai_post_processor.py:525-543`):
```python
all_individual_tags = []

if cleaned_data.get('tags_policy_area'):
    all_individual_tags.extend([t.strip() for t in cleaned_data['tags_policy_area'].split(';')])

if cleaned_data.get('tags_government_body'):
    all_individual_tags.extend([t.strip() for t in cleaned_data['tags_government_body'].split(';')])

if cleaned_data.get('tags_location'):
    all_individual_tags.extend([t.strip() for t in cleaned_data['tags_location'].split(',')])

# Remove duplicates while preserving order
unique_all_tags = list(dict.fromkeys(all_individual_tags))
cleaned_data['all_tags'] = '; '.join(unique_all_tags)
```

**Example: How whitelist enforcement works** (from `ai_post_processor.py:191-219`):
```python
def enforce_policy_whitelist(tags_str: str) -> str:
    tags = [t.strip() for t in tags_str.split(';') if t.strip()]
    validated = []

    for tag in tags:
        if tag in AUTHORIZED_POLICY_AREAS:
            validated.append(tag)
        else:
            match = _fuzzy_match(tag, AUTHORIZED_POLICY_AREAS)
            if match:
                validated.append(match)
            else:
                logger.warning(f"Dropping unauthorized policy tag: '{tag}'")

    validated = list(dict.fromkeys(validated))  # dedup
    if not validated:
        return "שונות"  # fallback
    return '; '.join(validated)
```

**Example: How body normalization works** (from `ai_post_processor.py:80-134`):
```python
BODY_NORMALIZATION = {
    # DROP: Generic / not a specific executive body
    "מזכירות הממשלה": None,
    "הכנסת": None,
    # MAP: Committee variations → authorized name
    "ועדת השרים לענייני חקיקה": "ועדת השרים",
    "ועדת שרים לענייני ביטחון לאומי": "ועדת השרים",
    # MAP: Common name variations → authorized names
    "משרד הכלכלה": "משרד הכלכלה והתעשייה",
    "משרד התחבורה": "משרד התחבורה והבטיחות בדרכים",
    # ... 50+ entries total
}
```

### Step 4: Push to DB

Only records that pass QA get inserted. Use existing `insert_decisions_batch()` from `src/gov_scraper/db/dal.py:128`.

**How it works** (from `dal.py:128-179`):
```python
def insert_decisions_batch(decisions: List[Dict], batch_size: int = 50) -> Tuple[int, List[str]]:
    # 1. Filter duplicates against DB
    unique_decisions, duplicate_keys = filter_duplicate_decisions(decisions)
    # 2. Validate decision key format
    # 3. Insert in batches of 50
    # 4. Retry logic: 3x per batch, then 2x per individual record on failure
    # Returns: (inserted_count, error_messages)
```

---

## 4. Key Files Reference

| File | Purpose | Lines to read |
|------|---------|---------------|
| `bin/sync.py` | Main sync orchestrator — **modify this** | Lines 298-331 (DB insertion to replace) |
| `src/gov_scraper/processors/ai.py` | AI processing (Gemini) | No changes needed |
| `src/gov_scraper/processors/ai_post_processor.py` | Post-processing — **reuse this** | Lines 80-134 (body map), 159-247 (whitelist), 435-545 (main function) |
| `src/gov_scraper/processors/qa.py` | QA checks — **reuse this** | Lines 2951-3139 (inline validation + fixes) |
| `src/gov_scraper/processors/incremental.py` | `prepare_for_database()` | Lines 241-311 |
| `src/gov_scraper/db/dal.py` | `insert_decisions_batch()` | Lines 128-179 |
| `src/gov_scraper/db/connector.py` | Supabase client setup | Lines 31-34 |
| `new_tags.md` | 46 authorized policy tags | Read the whole file |
| `new_departments.md` | 45 authorized government bodies | Read the whole file |
| `backups/pre_deployment_20260218_143933.json` | Backup format reference (76MB, 25,021 records) | Read first 2-3 records |

---

## 5. What Needs to be Built

### Minimal Changes

1. **In `bin/sync.py`**: Add a `--local-only` flag. When set, after Step 4 (`prepare_for_database`), save to JSON file instead of Steps 5-7 (DB insertion). **Touch only lines 298-363.**

2. **New script `bin/push_local.py`**: Reads a local JSON file, runs QA checks, and pushes passing records to DB. This script should:
   - Load JSON file
   - Run all QA checks (reuse existing functions)
   - Print a detailed report
   - In `--push` mode, call `insert_decisions_batch()` with passing records only
   - In `--qa-only` mode, just print the report

3. **QA validation function**: Can reuse logic from `ai_post_processor.py` (`enforce_policy_whitelist`, `enforce_body_whitelist`, `post_process_ai_results`) applied to the local file.

### Running It

```bash
# Step 1: Scrape and save locally
python bin/sync.py --unlimited --no-approval --no-headless --local-only --verbose
# Output: backups/new_scraped/2026-02-19_120000.json

# Step 2: Review the QA report
python bin/push_local.py --file backups/new_scraped/2026-02-19_120000.json --qa-only
# Output: QA report (no DB changes)

# Step 3: Push to DB (only passing records)
python bin/push_local.py --file backups/new_scraped/2026-02-19_120000.json --push
# Output: X records inserted, Y skipped
```

---

## 6. Important Gotchas

1. **Cloudflare**: Always use `--no-headless`. Headless Chrome is blocked. See `bin/sync.py:129-131`.
2. **Hebrew content**: All decision text is Hebrew RTL. Tag names are in Hebrew. Some tag names contain commas (e.g., `חקיקה, משפט ורגולציה` is ONE tag).
3. **Semicolons vs commas**: Policy tags and gov bodies are semicolon-separated (`;`). Locations are comma-separated (`,`). Don't mix them up.
4. **Unique constraint**: `decision_key` has a UNIQUE constraint in DB. Duplicate inserts will fail with a Postgres error (handled by `insert_decisions_batch` retry logic).
5. **Gemini API**: Uses Gemini 2.0 Flash. 1 unified API call per decision. Rate limits may apply. Key is in `.env` as `GEMINI_API_KEY`.
6. **`all_tags` field**: Must be rebuilt deterministically from individual fields. **Never** use the AI-generated value — it's wrong 99.9% of the time.
7. **Current government**: Government #37, PM בנימין נתניהו. Hardcoded in `prepare_for_database()` at `incremental.py:262-263`.
8. **Tag names with commas**: `חקיקה, משפט ורגולציה`, `דיור, נדלן ותכנון`, `מדע, טכנולוגיה וחדשנות` — these are single tag names that happen to contain commas. Don't split on commas for policy tags!
9. **Double-vav normalization**: Hebrew `וו` ↔ `ו` variants. See `ai_post_processor.py:295-303`.

---

## 7. Investigation Checklist

Before you start coding, investigate these things yourself and form your own conclusions:

- [ ] Open `new_tags.md` and `new_departments.md` — verify the exact authorized lists. What are the correct mappings for `תקציב`, `פיננסים`, `ביטוח ומיסוי`?
- [ ] Read the first 3 records of `backups/pre_deployment_20260218_143933.json` — understand the exact data format.
- [ ] Read `bin/sync.py` end to end — trace the full data flow from catalog to DB.
- [ ] Read `ai_post_processor.py` — understand what `post_process_ai_results()` does and whether it's called during the current pipeline (hint: check `bin/sync.py:242-245` and `ai.py`).
- [ ] Check: is `post_process_ai_results()` already called in the pipeline? If so, where? If the whitelist enforcement already runs during scraping, why do 54% of records still have bad tags? (Hint: the backup is from before the post-processor was deployed.)
- [ ] Run `python bin/sync.py --max-decisions 1 --no-headless --verbose` to see the full pipeline in action for one decision. Look at the output.
- [ ] Check what `prepare_for_database()` does to the data — does it add `created_at` / `updated_at`? Does it strip `id`?

**If anything doesn't make sense — stop and ask me. Don't guess.**
