#!/bin/bash
set -e

# GOV2DB Docker Entrypoint Script
# Handles initialization, cron setup, and run modes

echo "========================================="
echo "GOV2DB Israeli Government Scraper"
echo "========================================="
echo "Timezone: $TZ"
echo "Mode: ${1:-cron}"
echo "========================================="

# Start Xvfb virtual display for non-headless Chrome (bypasses Cloudflare)
start_xvfb() {
    echo "Starting Xvfb virtual display on :99..."
    Xvfb :99 -screen 0 1920x1080x24 &>/dev/null &
    export DISPLAY=:99
    sleep 2
    echo "Xvfb started successfully"
}

# Export Docker env vars to .env file for cron
# Uses generic env dump — future-proof, no hardcoded variable list
export_env_for_cron() {
    echo "Exporting environment variables for cron..."

    # Validate required vars before anything else
    local missing=()
    [ -z "$GEMINI_API_KEY" ] && missing+=("GEMINI_API_KEY")
    [ -z "$SUPABASE_URL" ] && missing+=("SUPABASE_URL")
    [ -z "$SUPABASE_SERVICE_ROLE_KEY" ] && missing+=("SUPABASE_SERVICE_ROLE_KEY")

    if [ ${#missing[@]} -gt 0 ]; then
        echo "FATAL: Missing required environment variables: ${missing[*]}"
        echo "Container cannot start without these. Check your docker-compose.yml or .env file."
        exit 1
    fi

    # Export ALL env vars to .env (filter out shell internals only)
    env | grep -v '^_=' | grep -v '^SHLVL=' | grep -v '^PWD=' \
        | grep -v '^HOSTNAME=' | grep -v '^HOME=' \
        > /app/.env

    chmod 600 /app/.env
    echo "Environment exported to /app/.env ($(wc -l < /app/.env) variables)"
}

# Run sync once (for manual execution)
run_once() {
    echo "Running sync once (manual mode)..."
    start_xvfb
    export_env_for_cron
    cd /app

    python3 bin/sync.py \
        --unlimited \
        --no-approval \
        --no-headless \
        --verbose

    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt
        rm -f /app/healthcheck/last_failure.txt
        echo "Sync completed successfully at $(date)"
    else
        echo "Sync FAILED with exit code $exit_code at $(date)"
        exit $exit_code
    fi
}

# Setup and start cron
run_cron() {
    echo "Setting up cron for daily execution..."

    # Start Xvfb for non-headless Chrome (Cloudflare bypass)
    start_xvfb

    # Export Docker env vars to .env file for cron
    export_env_for_cron

    # Export DISPLAY for cron jobs
    echo "DISPLAY=:99" >> /etc/environment

    # Ensure log files exist
    touch /app/logs/cron.log /app/logs/daily_sync.log

    echo "Starting cron daemon..."
    echo "Randomized sync scheduled (every 12h, 21-34h intervals)"

    # Only create health file if none exists (volume preserves it across restarts)
    if [ ! -f /app/healthcheck/last_success.txt ]; then
        echo "No previous sync record found. First sync will establish health baseline."
        echo "FRESH_START $(date -Iseconds)" > /app/healthcheck/last_success.txt
    else
        echo "Restored health state from previous run: $(cat /app/healthcheck/last_success.txt)"
    fi

    # Start cron in foreground mode
    cron -f
}

# Main execution logic
case "${1:-cron}" in
    cron)
        run_cron
        ;;
    once)
        run_once
        ;;
    bash|sh)
        exec /bin/bash
        ;;
    *)
        exec "$@"
        ;;
esac
