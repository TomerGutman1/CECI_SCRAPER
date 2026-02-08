#!/bin/bash
# Randomized Sync Wrapper
# Ensures 21-34 hours between runs to avoid Cloudflare rate limiting detection
#
# How it works:
# 1. Checks when the last successful sync was
# 2. If less than 21 hours ago, waits until 21 hours have passed
# 3. Adds random delay of 0-13 hours (0-780 minutes)
# 4. Runs sync with --no-headless to bypass Cloudflare
#
# This creates an effective interval of 21-34 hours between syncs

set -e

LOG_FILE="/app/logs/daily_sync.log"
LAST_SUCCESS_FILE="/app/healthcheck/last_success.txt"
MIN_HOURS=21
MAX_RANDOM_HOURS=13

log() {
    echo "$(date -Iseconds) [randomized_sync] $1" | tee -a "$LOG_FILE"
}

# Get hours since last successful sync
get_hours_since_last_sync() {
    if [ -f "$LAST_SUCCESS_FILE" ]; then
        last_sync=$(cat "$LAST_SUCCESS_FILE")
        last_epoch=$(date -d "$last_sync" +%s 2>/dev/null || echo 0)
        now_epoch=$(date +%s)
        hours=$(( (now_epoch - last_epoch) / 3600 ))
        echo $hours
    else
        echo 999  # No previous sync, run immediately
    fi
}

# Main logic
log "========================================="
log "Randomized Sync Starting"
log "========================================="

hours_since_last=$(get_hours_since_last_sync)
log "Hours since last sync: $hours_since_last"

# If less than MIN_HOURS, calculate wait time
if [ "$hours_since_last" -lt "$MIN_HOURS" ]; then
    wait_hours=$((MIN_HOURS - hours_since_last))
    wait_minutes=$((wait_hours * 60))
    log "Need to wait $wait_hours more hours to reach minimum interval"
else
    wait_minutes=0
fi

# Add random delay (0-13 hours = 0-780 minutes)
random_minutes=$((RANDOM % (MAX_RANDOM_HOURS * 60)))
total_delay_minutes=$((wait_minutes + random_minutes))

log "Random delay: $random_minutes minutes"
total_delay_hours=$((total_delay_minutes / 60))
log "Total delay: $total_delay_minutes minutes (~$total_delay_hours hours)"

if [ "$total_delay_minutes" -gt 0 ]; then
    log "Sleeping for $total_delay_minutes minutes..."
    sleep "${total_delay_minutes}m"
fi

log "Starting sync with --no-headless on virtual display..."
cd /app

# Use virtual display for non-headless Chrome (Cloudflare bypass)
export DISPLAY=:99

# Run sync with --no-headless to bypass Cloudflare
python3 bin/sync.py \
    --unlimited \
    --no-approval \
    --no-headless \
    --verbose \
    2>&1 | tee -a "$LOG_FILE"

# Update success timestamp
echo "$(date -Iseconds)" > "$LAST_SUCCESS_FILE"
log "Sync completed successfully"
log "========================================="
