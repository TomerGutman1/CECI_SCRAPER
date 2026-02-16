# Verify Step Command

You just completed a step. Now verify it worked correctly:

1. **For Code Changes:**
   - Run relevant tests if they exist
   - Check for Python syntax errors: `python -m py_compile <file>`
   - Run QA scan if it affects data quality

2. **For Database Changes:**
   - Query the DB to verify the change
   - Check for data integrity issues
   - Run `make test-conn` to ensure connectivity

3. **For Scraping Changes:**
   - Test with `python bin/sync.py --max-decisions 1 --verbose`
   - Verify Hebrew text is properly encoded
   - Check logs for errors

4. **For QA Fixes:**
   - Run the specific scanner: `make qa-scan-check check=<name>`
   - Compare before/after metrics
   - Verify no new issues introduced

5. **General Verification:**
   - Check logs in `logs/scraper.log`
   - Ensure no unintended side effects
   - Update `.planning/state.md` if needed

Report the verification results and ask if we should continue or fix issues.