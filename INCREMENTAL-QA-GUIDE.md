# Incremental QA System Guide

## Overview

The Incremental QA system provides efficient quality assurance updates for GOV2DB by processing only changed records instead of running full scans. This dramatically reduces processing time for daily QA updates from hours to minutes.

## Key Features

### 🔄 Change Tracking
- **Database Triggers**: Automatic detection of all changes to decision records
- **Audit Log**: Complete history of modifications with field-level granularity
- **Priority System**: High-priority changes (tag/operativity updates) processed first

### 🎯 Smart Processing
- **Dependency Resolution**: Cascade updates for related QA checks
- **Resource-Aware Batching**: Automatic adjustment based on system load
- **Failure Recovery**: Retry logic with exponential backoff

### 💾 Checkpoint System
- **Progress Tracking**: Save state every 100 changes (configurable)
- **Resume Capability**: Continue from last checkpoint after failures
- **Rollback Support**: Undo bad updates if needed

### 📊 Differential Reporting
- **Change Analysis**: Show only new issues and improvements
- **Trend Tracking**: Monitor data quality over time
- **Automated Recommendations**: Suggest optimizations based on patterns

## Quick Start

### 1. Setup (One-time)
```bash
# Install change tracking infrastructure
make incremental-qa-setup

# Or manually:
python bin/incremental_qa.py setup
```

This creates:
- `qa_audit_log` table for tracking changes
- `qa_checkpoints` table for recovery points
- Database triggers on `israeli_government_decisions`
- Checkpoint storage directory

### 2. Daily QA Updates
```bash
# Run incremental QA (processes only changed records)
make incremental-qa-run

# Or manually:
python bin/incremental_qa.py run
```

### 3. Check Status
```bash
# View current processing status
make incremental-qa-status

# Generate differential report
make incremental-qa-report
```

## Command Reference

### Setup Commands
```bash
# Setup change tracking infrastructure
python bin/incremental_qa.py setup

# Setup with custom checkpoint directory
python bin/incremental_qa.py setup --checkpoint-dir /custom/path
```

### Processing Commands
```bash
# Run incremental processing
python bin/incremental_qa.py run

# Process changes since specific date
python bin/incremental_qa.py run --since 2025-01-01

# Limit number of changes processed
python bin/incremental_qa.py run --max-changes 100

# Dry run (show what would be processed)
python bin/incremental_qa.py run --dry-run

# Resume from checkpoint
python bin/incremental_qa.py resume CHECKPOINT_ID
```

### Monitoring Commands
```bash
# Show current status
python bin/incremental_qa.py status

# Generate differential report
python bin/incremental_qa.py report

# Generate report for specific period
python bin/incremental_qa.py report --since 2025-01-01

# Save report to file
python bin/incremental_qa.py report --output report.json
```

### Maintenance Commands
```bash
# Clean up old data (older than 7 days)
python bin/incremental_qa.py cleanup --days 7

# Custom batch size and checkpoint interval
python bin/incremental_qa.py run --batch-size 25 --checkpoint-interval 50
```

## Architecture

### Change Detection Flow
```
1. User/System modifies decision record
     ↓
2. Database trigger captures change
     ↓
3. Change logged to qa_audit_log with:
   - Field-level diff
   - Priority assignment
   - Change hash for deduplication
     ↓
4. Incremental processor fetches pending changes
     ↓
5. Changes ordered by priority + dependencies
     ↓
6. QA checks run on affected records only
```

### Priority System
- **Priority 1 (Low)**: Content updates, metadata changes
- **Priority 2 (Medium)**: Operativity changes, summary updates
- **Priority 3 (High)**: Tag changes (policy/government body)

### Dependency Resolution
- Tag changes trigger related content validation
- Operativity changes affect tag relevance checks
- Topological sort prevents circular dependencies

## Integration with Existing QA

### Backwards Compatibility
- Existing QA commands (`make qa-scan`) work unchanged
- Full scans still available when needed
- Incremental system is additive, not replacement

### When to Use Each Approach

**Use Incremental QA for:**
- Daily quality updates
- Processing recent changes
- Continuous monitoring
- Production maintenance

**Use Full QA for:**
- Initial system setup
- Major algorithm changes
- Comprehensive audits
- Problem investigation

## Performance Benefits

### Before (Full QA Scan)
- **Time**: 2-4 hours for 25K records
- **Resources**: High CPU/memory usage
- **Database Load**: Scans entire table
- **Frequency**: Weekly due to cost

### After (Incremental QA)
- **Time**: 2-10 minutes for typical daily changes
- **Resources**: Minimal CPU/memory usage
- **Database Load**: Processes only changed records
- **Frequency**: Can run multiple times daily

### Typical Change Volumes
- **Daily changes**: 10-50 records (new decisions + updates)
- **Weekly changes**: 50-200 records
- **Monthly changes**: 200-500 records

## Configuration

### Environment Variables
```bash
# Standard GOV2DB environment variables apply
GEMINI_API_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

### Processor Settings
```python
processor = IncrementalQAProcessor(
    checkpoint_dir="data/qa_checkpoints",  # Checkpoint storage
    batch_size=50,                        # Records per batch
    checkpoint_interval=100,               # Save every N changes
    max_retries=3,                        # Retry failed changes
    resource_threshold=0.8                # Pause if resources high
)
```

## Monitoring and Alerts

### Key Metrics to Monitor
- **Pending changes**: Should stay low (< 100)
- **Failed changes**: Should be minimal (< 5%)
- **Processing rate**: Target 10+ changes/second
- **Checkpoint frequency**: Every 100 changes

### Status Dashboard
```bash
# Quick status check
make incremental-qa-status

# Output shows:
# - Pending changes: 23
# - Changes in last 24h: 45
# - Recent checkpoints: 3
```

### Differential Reports
```bash
# Generate report for last 24 hours
make incremental-qa-report

# Shows:
# - Processing progress
# - Most changed fields
# - Quality trends
# - Automated recommendations
```

## Troubleshooting

### Common Issues

#### 1. High Number of Pending Changes
```bash
# Check what's pending
make incremental-qa-status

# Process in smaller batches
python bin/incremental_qa.py run --max-changes 50
```

#### 2. Processing Failures
```bash
# Check recent failures
python bin/incremental_qa.py status

# Resume from last checkpoint
python bin/incremental_qa.py resume CHECKPOINT_ID

# Skip failed changes if necessary
python bin/incremental_qa.py cleanup --days 1
```

#### 3. Performance Issues
```bash
# Reduce batch size
python bin/incremental_qa.py run --batch-size 25

# Check resource usage
python bin/incremental_qa.py run --verbose

# Clean up old data
make incremental-qa-cleanup
```

### Database Issues

#### Missing Tables
```sql
-- Check if audit table exists
SELECT * FROM qa_audit_log LIMIT 1;

-- Recreate if missing
python bin/incremental_qa.py setup
```

#### Trigger Issues
```sql
-- Check trigger exists
SELECT * FROM information_schema.triggers
WHERE trigger_name = 'qa_change_trigger';

-- Recreate if missing
python bin/incremental_qa.py setup
```

## Best Practices

### 1. Regular Maintenance
```bash
# Run incremental QA daily
0 2 * * * cd /path/to/GOV2DB && make incremental-qa-run

# Weekly cleanup
0 3 * * 0 cd /path/to/GOV2DB && make incremental-qa-cleanup

# Monthly full scan (belt and suspenders)
0 4 1 * * cd /path/to/GOV2DB && make qa-scan
```

### 2. Monitoring
- Check status before major operations
- Review differential reports weekly
- Monitor checkpoint creation frequency

### 3. Disaster Recovery
- Checkpoints stored in both files and database
- Can resume from any checkpoint
- Full QA scan as ultimate fallback

### 4. Performance Optimization
- Adjust batch size based on system resources
- Use higher checkpoint frequency for critical periods
- Clean up old data regularly

## Future Enhancements

### Planned Features
- **Real-time Processing**: Process changes as they occur
- **Machine Learning**: Predict which changes need QA
- **API Integration**: REST API for external monitoring
- **Advanced Reporting**: Grafana dashboards

### Extension Points
- Custom change priority rules
- Pluggable QA check selection
- External notification systems
- Advanced dependency tracking

## Getting Help

### Documentation
- This guide: `INCREMENTAL-QA-GUIDE.md`
- Implementation details: `.planning/docs/IMPLEMENTATION-DETAILS.md`
- QA system guide: `QA-LESSONS.md`

### Debugging
- Logs: `logs/incremental_qa.log`
- Verbose mode: `--verbose` flag
- Dry run: `--dry-run` flag

### Support
- Check existing issues and patterns
- Use differential reports for insights
- Monitor system metrics regularly

---

*Last updated: February 2026*