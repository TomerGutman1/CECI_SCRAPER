# Implementation Details

This document contains technical implementation details moved from CLAUDE.md for reference.

## Core Algorithms

### 1. Web Scraping Pipeline

**Catalog Scraper** (`scrapers/catalog.py`):
- URL: `https://www.gov.il/he/collectors/policies`
- Waits 15s for JavaScript rendering
- Regex patterns for decision URLs: `/he/pages/dec\d+[a-z]?-\d{4}[a-z]?`
- Returns URLs sorted by decision number (newest first)

**Decision Scraper** (`scrapers/decision.py`):
- Uses `undetected-chromedriver` (auto-detects Chrome version)
- Extracts: decision_number, date, title, committee, content, URL
- Hebrew date format: `DD.MM.YYYY` → `YYYY-MM-DD`
- Validates Hebrew content presence

**URL Recovery** (3-tier fallback):
1. Try original URL
2. Search catalog for correct variant
3. Try URL variations (add 'a' suffix)

### 2. AI Processing Pipeline

**Model:** Gemini 2.0 Flash, Temperature: 0.3, Max retries: 5

#### Tag Validation: 3-Step Algorithm

**Step 1: Exact Match** - Tag exists verbatim in authorized list
**Step 2: Word-based Jaccard Similarity** - 50% threshold for word overlap
**Step 3: AI Summary Fallback** - Last resort before defaulting

#### Tag Generation Functions

| Function | Purpose | Output |
|----------|---------|--------|
| `generate_summary()` | 1-2 sentence summary | Text |
| `generate_operativity()` | אופרטיבית/דקלרטיבית | Word |
| `generate_policy_area_tags_strict()` | Policy categories | 1-3 tags |
| `generate_government_body_tags_validated()` | Government entities | 1-3 tags |
| `generate_location_tags()` | Geographic locations | Comma-sep |

### 3. Incremental Processing

- Get baseline from DB (latest decision)
- Compare new decisions by date + number
- Skip older decisions
- Prevent duplicates via decision_key

### 4. Safety Modes

**Regular Mode** (default):
- URL filtering by baseline year
- Efficient for daily syncs

**Extra Safe Mode** (`--safety-mode extra-safe`):
- No URL filtering
- Processes all available URLs
- Use after long breaks

## Database Schema

**Table:** `israeli_government_decisions`

| Field | Type | Description |
|-------|------|-------------|
| decision_key | STRING (UNIQUE) | `{gov_num}_{decision_num}` |
| decision_number | STRING | Official ID |
| decision_date | DATE | YYYY-MM-DD |
| decision_title | TEXT | Headline |
| decision_content | TEXT | Full Hebrew text |
| summary | TEXT | AI summary |
| operativity | STRING | Classification |
| tags_policy_area | TEXT | Policy tags |
| tags_government_body | TEXT | Government entities |
| tags_location | TEXT | Locations |
| government_number | INT | 37 (current) |
| prime_minister | STRING | בנימין נתניהו |

## Special Category Tags

5 cross-cutting policy tags with weighted keyword detection:

| Tag | Description |
|-----|-------------|
| החברה הערבית | Arab society decisions |
| החברה החרדית | Haredi society decisions |
| נשים ומגדר | Women & gender equality |
| שיקום הצפון | Northern rehabilitation |
| שיקום הדרום | Southern rehabilitation |

**Scoring Thresholds:**
- >= 60 points: Auto-tag
- 30-59 points: AI verify
- 15-29 points: Manual review
- < 15 points: Skip

## QA System Architecture

- **20 Scanners:** Read-only analysis
- **8 Fixers:** Batch update operations
- **3-Stage Pipeline Integration:**
  1. Pre-AI Content Validation (blocking)
  2. Post-AI Algorithmic Fixes ($0 cost)
  3. Inline Validation Warnings (non-blocking)

## Production Infrastructure

- **Server:** 178.62.39.248 (CECI)
- **Container:** gov2db-scraper
- **Schedule:** Randomized 21-34 hour intervals
- **Cloudflare Bypass:** Requires `--no-headless` flag

## Hebrew Text Processing

```python
# Remove zero-width spaces and RTL marks
text.replace('\u200b', '').replace('\u200e', '').replace('\u200f', '')
# Normalize whitespace
' '.join(text.split())
# Date conversion
datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
```