# Database Integration Guide

This guide explains how to use the new integrated system that connects the Israeli Government decisions scraper with the Supabase database.

## Overview

The integration provides:
1. **Incremental scraping** - Only processes new decisions since the last database update
2. **Smart duplicate prevention** - Automatically skips decisions already in the database
3. **User approval workflow** - Review decisions before inserting into database
4. **Comprehensive logging** - Full audit trail of all operations
5. **Batch processing** - Efficient database operations with error handling

## Quick Start

### 1. Using the Master Orchestrator (Recommended)

```bash
# Run with default settings (10 decisions, with AI, requires approval)
python src/sync_with_db.py

# Process more decisions
python src/sync_with_db.py --max-decisions 25

# Skip AI processing
python src/sync_with_db.py --no-ai

# Auto-approve without user confirmation (use carefully!)
python src/sync_with_db.py --auto-approve

# Verbose logging
python src/sync_with_db.py --verbose
```

### 2. Using Enhanced Main Script

```bash
# Run in incremental mode (recommended)
python src/main.py --incremental

# Run in normal mode (processes all decisions)
python src/main.py

# Specify number of decisions
python src/main.py 15 --incremental
```

## How It Works

### Step-by-Step Process

1. **Database Query**: Fetches the latest decision from Supabase as baseline
2. **Smart Scraping**: Only scrapes decisions newer than the baseline
3. **AI Processing**: Generates summaries and tags (if enabled)
4. **Duplicate Filtering**: Removes decisions already in database
5. **User Approval**: Shows preview and asks for confirmation
6. **Batch Insertion**: Safely inserts new decisions with error handling

### Key Safety Features

- **No Overwrites**: Uses `decision_key` uniqueness to prevent duplicates
- **Transaction Safety**: Batch operations with individual fallback
- **User Control**: Manual approval required before database changes
- **Complete Logging**: All operations logged for audit trail
- **Rollback Capability**: Failed batches don't affect successful ones

## File Structure

```
src/
├── sync_with_db.py          # 🌟 Master orchestrator (USE THIS)
├── incremental_processor.py # Determines what's new vs existing
├── approval_manager.py      # User approval workflow
├── main.py                  # Enhanced original scraper
├── db/
│   ├── dal.py              # Enhanced database operations
│   ├── db_connector.py     # Supabase connection
│   └── utils.py           # Database utilities
└── [other existing files]
```

## Usage Examples

### Example 1: Daily Sync
```bash
# Check for new decisions daily
python src/sync_with_db.py --max-decisions 20
```

### Example 2: Bulk Import (First Time)
```bash
# Import many decisions without AI to save time
python src/sync_with_db.py --max-decisions 100 --no-ai
```

### Example 3: Automated Pipeline
```bash
# Fully automated (no user interaction)
python src/sync_with_db.py --max-decisions 10 --auto-approve
```

## Configuration

### Environment Variables (.env file)
```
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional, for AI processing
```

## Monitoring and Logs

- **Logs Location**: `logs/sync_with_db_YYYYMMDD_HHMMSS.log`
- **CSV Previews**: `data/new_decisions_for_approval_YYYYMMDD_HHMMSS.csv`
- **Status Updates**: Real-time console output with progress indicators

## Troubleshooting

### Common Issues

1. **No new decisions found**
   - Normal if database is up to date
   - Check baseline decision in logs

2. **Database connection errors**
   - Verify SUPABASE_URL and SUPABASE_SERVICE_KEY in .env
   - Check network connectivity

3. **AI processing fails**
   - Verify OPENAI_API_KEY in .env
   - Use `--no-ai` flag to skip AI processing

4. **Duplicate key errors**
   - Should be automatically handled
   - Check logs for specific decision causing issues

### Debug Commands

```bash
# Test database connection
python src/db/dal.py

# Test incremental processor
python src/incremental_processor.py

# Test approval manager
python src/approval_manager.py
```

## Best Practices

1. **Regular Syncing**: Run daily or weekly to keep database current
2. **Review Previews**: Always check the CSV preview before approving
3. **Monitor Logs**: Keep an eye on error messages and success rates
4. **Backup Database**: Regular backups before large imports
5. **Test Changes**: Use small `--max-decisions` values when testing

## Database Schema

The system works with the existing `israeli_government_decisions` table structure:

- `decision_key` (unique): Combination of government_number + decision_number
- `decision_date`: Date of the decision
- `decision_number`: Official decision number
- `decision_content`: Full text content
- Plus all other existing fields (summary, tags, etc.)

## Support

For issues or questions:
1. Check the logs in `logs/` directory
2. Review the CSV previews in `data/` directory
3. Run with `--verbose` flag for detailed debugging
4. Test individual components using their `__main__` methods

---

**🎯 Recommended Command for Regular Use:**
```bash
python src/sync_with_db.py --max-decisions 15 --verbose
```

This provides a good balance of coverage, user control, and detailed logging.