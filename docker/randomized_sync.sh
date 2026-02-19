#!/bin/bash
# Randomized Sync Wrapper
# Ensures 21-34 hours between runs to avoid Cloudflare rate limiting detection
#
# How it works:
# 1. Checks when the last successful sync was
# 2. If less than 21 hours ago, waits until 21 hours have passed
# 3. Adds random delay of 0-13 hours (0-780 minutes)
# 4. Runs sync with --no-headless to bypass Cloudflare
# 5. Retries up to 3 times on failure with escalating backoff
#
# This creates an effective interval of 21-34 hours between syncs

# Do NOT use set -e: we handle exit codes manually
set -o pipefail

LOG_FILE="/app/logs/daily_sync.log"
LAST_SUCCESS_FILE="/app/healthcheck/last_success.txt"
LAST_FAILURE_FILE="/app/healthcheck/last_failure.txt"
MIN_HOURS=21
MAX_RANDOM_HOURS=13
MAX_RETRIES=3
RETRY_BACKOFF_MINUTES=30  # 30min, 60min, 90min

log() {
    echo "$(date -Iseconds) [randomized_sync] $1" >> "$LOG_FILE"
}

# Get hours since last successful sync
get_hours_since_last_sync() {
    if [ -f "$LAST_SUCCESS_FILE" ]; then
        last_sync=$(cat "$LAST_SUCCESS_FILE")
        # Handle FRESH_START sentinel from entrypoint
        if echo "$last_sync" | grep -q "FRESH_START"; then
            echo 999
            return
        fi
        last_epoch=$(date -d "$last_sync" +%s 2>/dev/null || echo 0)
        now_epoch=$(date +%s)
        hours=$(( (now_epoch - last_epoch) / 3600 ))
        echo $hours
    else
        echo 999  # No previous sync, run immediately
    fi
}

# Run sync and return its actual exit code
run_sync() {
    cd /app
    export DISPLAY=:99

    python3 bin/sync.py \
        --unlimited \
        --no-approval \
        --no-headless \
        --verbose \
        >> "$LOG_FILE" 2>&1

    return $?
}

# ---- Main logic ----

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

# ---- Sync with retry ----

log "Starting sync with --no-headless on virtual display..."

sync_success=false
for attempt in $(seq 1 $MAX_RETRIES); do
    log "Sync attempt $attempt/$MAX_RETRIES..."

    if run_sync; then
        sync_success=true
        log "Sync attempt $attempt SUCCEEDED"
        break
    else
        exit_code=$?
        log "Sync attempt $attempt FAILED (exit code: $exit_code)"

        if [ "$attempt" -lt "$MAX_RETRIES" ]; then
            backoff=$((RETRY_BACKOFF_MINUTES * attempt))
            log "Retrying in $backoff minutes..."
            sleep "${backoff}m"
        fi
    fi
done

# ---- Update health state ----

if [ "$sync_success" = true ]; then
    echo "$(date -Iseconds)" > "$LAST_SUCCESS_FILE"
    rm -f "$LAST_FAILURE_FILE"
    log "Sync completed successfully"
else
    echo "$(date -Iseconds) FAILED after $MAX_RETRIES attempts" > "$LAST_FAILURE_FILE"
    log "SYNC FAILED after $MAX_RETRIES attempts"
fi

log "========================================="
