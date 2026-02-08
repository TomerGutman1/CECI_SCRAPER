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

# Function to export Docker env vars to .env file for cron
export_env_for_cron() {
    echo "Exporting environment variables for cron..."
    # Write Docker env vars to .env file that Python's dotenv can read
    cat > /app/.env << EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
SUPABASE_URL=${SUPABASE_URL}
SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
OPENAI_MODEL=${OPENAI_MODEL:-gpt-3.5-turbo}
EOF
    chmod 600 /app/.env
    echo "Environment exported to /app/.env"
}

# Function to run sync once (for manual execution)
run_once() {
    echo "Running sync once (manual mode)..."
    cd /app
    python3 bin/sync.py \
        --unlimited \
        --no-approval \
        --no-headless \
        --verbose

    # Update health check file
    echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt
    echo "Sync completed successfully at $(date)"
}

# Function to setup and start cron
run_cron() {
    echo "Setting up cron for daily execution..."

    # Export Docker env vars to .env file for cron
    export_env_for_cron

    # Ensure cron log file exists
    touch /app/logs/cron.log

    # Start cron in foreground
    echo "Starting cron daemon..."
    echo "Daily sync scheduled for 02:00 AM ($TZ)"

    # Create initial health check file
    echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt

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
        # Execute custom command
        exec "$@"
        ;;
esac
