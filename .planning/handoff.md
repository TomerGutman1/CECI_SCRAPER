# Session Handoff
**Date:** February 18, 2026
**Focus:** Implemented post-deployment improvements (dedup, dynamic summaries, committee mapping, post-processor), then deep QA on 20 decisions found 8 systematic issues — top 4 still need fixing.

## Done
- **Tag deduplication** — `deduplicate_tags()` in `ai.py` + full dedup in unified result conversion
- **Dynamic summary length** — `calculate_dynamic_summary_params()` scales 200-700 tokens based on content length (5 tiers)
- **Summary truncation fix** — detects mid-word cutoffs, removes incomplete words, adds "..."
- **Committee mapping** — `config/committee_mappings.py` with 30+ variations → canonical forms
- **Post-processor pipeline** — `src/gov_scraper/processors/ai_post_processor.py` — dedup, committee normalization, generic location filter ("ישראל"), ministry context validation (military≠police)
- **Unified prompt updated** — `ai_prompts.py` now accepts `{summary_instructions}` for dynamic summary
- **Deep QA on 20 decisions** — graded each on 4 axes, found 8 systematic issues with impact percentages
- **CLAUDE.md** — fixed stale "NOT YET DEPLOYED" status section
- **Tests** — `test_improvements.py` (6 tests all passing), `test_dynamic_summary.py`

## Not Done
**8 issues identified in QA, top 4 NOT yet fixed:**

1. **Summary prefix waste (40%)** — 8/20 summaries start with "החלטת ממשלה מספר XXXX". Need to add explicit instruction to AI prompt: "אל תתחיל עם מספר ההחלטה"
2. **Gov body normalization (50%)** — AI returns names not on authorized list: "מזכירות הממשלה" (drop), "ועדת השרים לענייני חקיקה" (→"ועדת השרים"), "ממשלה" (drop), "הכנסת" (drop). Expand map in `ai_post_processor.py`
3. **all_tags mismatch (25%)** — Field has tags not in individual fields and missing ones that are. Fix: compute deterministically from `tags_policy_area + tags_government_body + tags_location`
4. **Operativity inconsistency (20%)** — "oppose bill" = declarative in #3871 but operative in #3873. Add rules: "להתנגד להצעת חוק"=declarative, "לאשר עקרונית+להסמיך"=operative

**Lower priority (not started):**
5. Empty gov bodies — infer from policy tags when empty (15%)
6. "תיירות" on diplomatic visits (15%)

**No new decisions processed** — DB was up to date. Fixes will apply to next sync.

## Warnings
- Gemini API rate limits hit 429 frequently. Backoff logic handles it but processing is slow.
- Post-processor integrated but not yet tested on live sync — only unit tests.
- `recent_decisions_sample.json` has the 20 decisions used for QA — use as test reference.

## Next Session Priorities
1. **Fix summary prefix** — add "אל תתחיל את התקציר עם 'החלטת ממשלה מספר...'" to prompts in `ai.py:340` and `ai_prompts.py:119`
2. **Fix gov body normalization** — expand `BODY_NORMALIZATION` map in `ai_post_processor.py` to drop/remap unauthorized names
3. **Fix all_tags** — compute from individual fields deterministically (replace AI-generated all_tags)
4. **Fix operativity rules** — add pattern-based rules to prompt or post-processor

## Read First
- `.planning/state.md` — full issue table with impact percentages
- `src/gov_scraper/processors/ai_post_processor.py` — post-processor to expand
- `src/gov_scraper/processors/ai.py` — main AI processing (lines 340-356 for summary prompt)
- `src/gov_scraper/processors/ai_prompts.py` — unified prompt (line 119 for summary instructions)
- `recent_decisions_sample.json` — 20 QA decisions for testing
