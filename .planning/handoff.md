# Session Handoff
**Date:** 2026-02-18
**Focus:** Implemented whitelist enforcement, QA fixes, and planned server deployment

## Done
- **Summary prefix fix** — anti-prefix instructions added to all 3 prompts (legacy, unified, fallback) + post-processor regex safety net in `ai_post_processor.py`
- **Gov body normalization** — expanded `BODY_NORMALIZATION` map with Knesset committees, single-yod variants, וו→ו handling
- **Whitelist enforcement** — `enforce_policy_whitelist()` and `enforce_body_whitelist()` in `ai_post_processor.py` — loads authorized lists from `new_tags.md` / `new_departments.md` at module level, fuzzy match (Jaccard >=0.5), unauthorized tags dropped
- **Operativity rules** — pattern-based override for bill opposition (→declarative) and principle approval patterns
- **all_tags desync fix** — deterministic rebuild added at end of `apply_inline_fixes()` in `qa.py`
- **Authorized list expansion** — added "השכלה גבוהה" to `new_tags.md` (46 tags), "המוסד לביטוח לאומי" to `new_departments.md` (45 bodies)
- **Test sync** — 15 decisions synced and QA'd, all fixes confirmed working
- **All 7 tests pass**
- **Deployment plan written** — full plan at `.claude/plans/nifty-squishing-valiant.md`

## Not Done
- **Commit & push** — 8 modified files uncommitted, 5 commits unpushed to origin
- **Docker build & push** — image not yet rebuilt with new code
- **Server deployment** — new image not deployed to `ceci` (178.62.39.248)
- **Full re-sync** — all ~25K decisions need re-processing with improved AI pipeline

## Warnings
- **Do NOT commit** `recent_decisions_qa.json` or `recent_sync_qa.json` — temporary QA exports
- **5 commits already unpushed** — push all together with the new commit
- `new_tags.md` and `new_departments.md` are copied into Docker image by Dockerfile — must rebuild image after changes
- Full re-sync will take hours — run detached on server (tmux or `docker exec -d`)

## Next Session Priorities
1. **Commit, push, build, deploy** — follow the plan in `.claude/plans/nifty-squishing-valiant.md` steps 1-3
2. **Test sync from server** — 1 decision to verify Docker image works (step 4)
3. **Full re-sync from server** — unlimited sync, run detached (step 5)
4. **Verify results** — QA after full sync completes (step 6)

## Read First
- `.planning/state.md`
- `.claude/plans/nifty-squishing-valiant.md` — the deployment plan (follow it step by step)
- `SERVER-OPERATIONS.md` — server SSH/Docker commands reference
- `Dockerfile` — confirms `new_tags.md` / `new_departments.md` are copied into image
