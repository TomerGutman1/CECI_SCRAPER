#!/bin/bash

# GOV2DB Health Check Script
# Checks: 1) Last successful sync timestamp, 2) DB connectivity

set -e

HEALTH_FILE="/app/healthcheck/last_success.txt"
MAX_AGE_HOURS=48  # Alert if no sync in 48 hours

# Check 1: Last success timestamp
if [ ! -f "$HEALTH_FILE" ]; then
    echo "UNHEALTHY: No health check file found"
    exit 1
fi

# Read last success timestamp
LAST_SUCCESS=$(cat "$HEALTH_FILE")
LAST_SUCCESS_EPOCH=$(date -d "$LAST_SUCCESS" +%s 2>/dev/null || echo 0)
CURRENT_EPOCH=$(date +%s)
AGE_HOURS=$(( ($CURRENT_EPOCH - $LAST_SUCCESS_EPOCH) / 3600 ))

if [ $AGE_HOURS -gt $MAX_AGE_HOURS ]; then
    echo "UNHEALTHY: Last sync was $AGE_HOURS hours ago (threshold: $MAX_AGE_HOURS hours)"
    exit 1
fi

# Check 2: Database connectivity (quick test)
python3 -c "
import sys
import os
sys.path.insert(0, '/app/src')

try:
    from gov_scraper.db.connector import get_supabase_client
    client = get_supabase_client()
    # Quick ping to DB
    response = client.table('israeli_government_decisions').select('count', count='exact').limit(1).execute()
    print(f'HEALTHY: DB accessible, {response.count} records, last sync ${AGE_HOURS}h ago')
    sys.exit(0)
except Exception as e:
    print(f'UNHEALTHY: DB connection failed - {e}')
    sys.exit(1)
" || exit 1

exit 0
