#!/bin/bash
# Daily Sync Wrapper (API mode)
# Runs once daily via cron with minimal jitter
#
# How it works:
# 1. Sources /app/.env for cron environment (GEMINI_API_KEY, SUPABASE, etc.)
# 2. Adds 0-30 minutes of random jitter
# 3. Runs sync via gov.il REST APIs (no Chrome/Selenium)
# 4. Retries up to 3 times on failure with escalating backoff

# Do NOT use set -e: we handle exit codes manually
set -o pipefail

LOG_FILE="/app/logs/daily_sync.log"
LAST_SUCCESS_FILE="/app/healthcheck/last_success.txt"
LAST_FAILURE_FILE="/app/healthcheck/last_failure.txt"
MAX_RETRIES=3
RETRY_BACKOFF_MINUTES=10  # 10min, 20min, 30min

log() {
    echo "$(date -Iseconds) [daily_sync] $1" >> "$LOG_FILE"
}

# Source environment variables for cron
# Docker entrypoint writes all env vars to /app/.env at startup
load_env() {
    if [ -f /app/.env ]; then
        set -a
        source /app/.env 2>/dev/null
        set +a
        log "Loaded $(wc -l < /app/.env) env vars from /app/.env"
    else
        log "WARNING: /app/.env not found — env vars may be missing"
    fi
}

# Run sync and return its actual exit code
run_sync() {
    cd /app

    python3 bin/sync.py \
        --unlimited \
        --no-approval \
        --use-api \
        --verbose \
        >> "$LOG_FILE" 2>&1

    return $?
}

# ---- Main logic ----

log "========================================="
log "Daily Sync Starting (API mode)"
log "========================================="

# Load env vars (required for cron — cron doesn't inherit Docker env)
load_env

# Validate critical env vars
if [ -z "$GEMINI_API_KEY" ] || [ -z "$SUPABASE_URL" ]; then
    log "FATAL: Missing GEMINI_API_KEY or SUPABASE_URL after loading /app/.env"
    echo "$(date -Iseconds) FAILED: missing env vars" > "$LAST_FAILURE_FILE"
    exit 1
fi

# Small random jitter (0-30 minutes) for API politeness
jitter_minutes=$((RANDOM % 30))
log "Random jitter: $jitter_minutes minutes"

if [ "$jitter_minutes" -gt 0 ]; then
    sleep "${jitter_minutes}m"
fi

# ---- Sync with retry ----

log "Starting sync..."

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
