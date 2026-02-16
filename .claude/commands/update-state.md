# Update State Command

You've completed a significant piece of work. Update the project state:

1. **Update `.planning/state.md`:**
   - Update "Last Updated" date
   - Update "Current Focus" if it changed
   - Add to "Recent Changes" section
   - Update "Known Issues" if any were fixed or found
   - Update "Next Steps" based on what was completed
   - List "Files Recently Modified"

2. **If a phase was completed:**
   - Create `.planning/phase-{N}/summary.md` with:
     - What was accomplished
     - Metrics/improvements achieved
     - Any issues encountered
     - Lessons learned

3. **Update other docs if needed:**
   - `.planning/decisions.md` for architectural decisions
   - `.planning/db/schema-design.md` for DB changes
   - `CLAUDE.md` ONLY for workflow changes

4. **For GOV2DB specifically, track:**
   - QA scan results (issues before/after)
   - Number of decisions processed
   - AI cost if significant work was done
   - Any new Cloudflare blocks encountered

5. **Git commit the updates:**
   ```bash
   git add .planning/
   git commit -m "docs: update planning state - <brief description>"
   ```

Show me the updated state and confirm it's accurate.