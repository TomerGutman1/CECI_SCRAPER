# Database Change Command

You're about to make a database change. Follow this safety protocol:

## Pre-Change Checklist

1. **Backup First:**
   ```python
   python -c "from src.gov_scraper.db.utils import export_to_csv; export_to_csv()"
   ```

2. **Document the Change:**
   - What field/table/index are you changing?
   - Why is this change needed?
   - What's the rollback plan?
   - Save to `.planning/db/migrations/YYYYMMDD_description.md`

3. **Test Query First:**
   - Write a SELECT to verify current state
   - Write the ALTER/UPDATE in a transaction
   - Test on a few records first

## For GOV2DB Schema Changes

Common operations:

```python
# Add a new field
from src.gov_scraper.db.connector import get_supabase_client
supabase = get_supabase_client()

# Query current schema
result = supabase.table('israeli_government_decisions').select('*').limit(1).execute()

# For updates, always use decision_key
supabase.table('israeli_government_decisions').update({
    'field': 'value'
}).eq('decision_key', '37_1234').execute()
```

## Post-Change Verification

1. Run `make test-conn` to verify connectivity
2. Query a sample of records to verify the change
3. Run relevant QA scanner if it affects data quality
4. Update `.planning/db/schema-design.md`
5. Commit the migration document

## Rollback Plan

Always have a rollback ready:
- Keep the backup CSV
- Document the reverse operation
- Test the rollback command before proceeding

Ask for approval before executing any destructive operations.