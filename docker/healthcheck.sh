#!/bin/bash

# GOV2DB Health Check Script
# Checks: 1) Recent failure flag, 2) Last sync age, 3) DB connectivity

set -e

HEALTH_FILE="/app/healthcheck/last_success.txt"
FAILURE_FILE="/app/healthcheck/last_failure.txt"
MAX_AGE_HOURS=48  # Alert if no sync in 48 hours

# Check 0: Recent failure flag (written by randomized_sync.sh after all retries exhausted)
if [ -f "$FAILURE_FILE" ]; then
    failure_info=$(cat "$FAILURE_FILE")
    echo "UNHEALTHY: Recent sync failure: $failure_info"
    exit 1
fi

# Check 1: Last success timestamp
if [ ! -f "$HEALTH_FILE" ]; then
    echo "UNHEALTHY: No health check file found"
    exit 1
fi

LAST_SUCCESS=$(cat "$HEALTH_FILE")

# Handle FRESH_START sentinel (container started but never synced yet)
if echo "$LAST_SUCCESS" | grep -q "FRESH_START"; then
    start_time=$(echo "$LAST_SUCCESS" | awk '{print $2}')
    start_epoch=$(date -d "$start_time" +%s 2>/dev/null || echo 0)
    now_epoch=$(date +%s)
    hours_since_start=$(( (now_epoch - start_epoch) / 3600 ))

    if [ $hours_since_start -gt $MAX_AGE_HOURS ]; then
        echo "UNHEALTHY: Container started ${hours_since_start}h ago but no successful sync yet"
        exit 1
    else
        echo "HEALTHY: Awaiting first sync (container started ${hours_since_start}h ago)"
        exit 0
    fi
fi

LAST_SUCCESS_EPOCH=$(date -d "$LAST_SUCCESS" +%s 2>/dev/null || echo 0)
CURRENT_EPOCH=$(date +%s)
AGE_HOURS=$(( (CURRENT_EPOCH - LAST_SUCCESS_EPOCH) / 3600 ))

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
    response = client.table('israeli_government_decisions').select('count', count='exact').limit(1).execute()
    print(f'HEALTHY: DB accessible, {response.count} records, last sync ${AGE_HOURS}h ago')
    sys.exit(0)
except Exception as e:
    print(f'UNHEALTHY: DB connection failed - {e}')
    sys.exit(1)
" || exit 1

exit 0
