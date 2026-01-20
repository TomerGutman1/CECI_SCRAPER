#!/bin/bash

# Example Webhook Integration Scripts
# Copy and customize for your monitoring service

# ============================================
# Example 1: Slack Webhook
# ============================================
send_slack_alert() {
    local MESSAGE="$1"
    local WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

    curl -X POST -H 'Content-type: application/json' \
        --data "{
            \"text\": \"$MESSAGE\",
            \"username\": \"GOV2DB Monitor\",
            \"icon_emoji\": \":robot_face:\"
        }" \
        "$WEBHOOK_URL"
}

# Usage:
# send_slack_alert "⚠️ GOV2DB is unhealthy!"

# ============================================
# Example 2: Discord Webhook
# ============================================
send_discord_alert() {
    local MESSAGE="$1"
    local WEBHOOK_URL="https://discord.com/api/webhooks/YOUR/WEBHOOK"

    curl -X POST -H 'Content-type: application/json' \
        --data "{
            \"content\": \"$MESSAGE\",
            \"username\": \"GOV2DB Monitor\"
        }" \
        "$WEBHOOK_URL"
}

# ============================================
# Example 3: Microsoft Teams Webhook
# ============================================
send_teams_alert() {
    local MESSAGE="$1"
    local WEBHOOK_URL="https://outlook.office.com/webhook/YOUR/WEBHOOK"

    curl -X POST -H 'Content-type: application/json' \
        --data "{
            \"@type\": \"MessageCard\",
            \"@context\": \"http://schema.org/extensions\",
            \"summary\": \"GOV2DB Alert\",
            \"themeColor\": \"FF0000\",
            \"title\": \"GOV2DB Monitoring Alert\",
            \"text\": \"$MESSAGE\"
        }" \
        "$WEBHOOK_URL"
}

# ============================================
# Example 4: Email (using SendGrid API)
# ============================================
send_email_alert() {
    local MESSAGE="$1"
    local SENDGRID_API_KEY="YOUR_API_KEY"
    local TO_EMAIL="admin@example.com"

    curl -X POST "https://api.sendgrid.com/v3/mail/send" \
        -H "Authorization: Bearer $SENDGRID_API_KEY" \
        -H "Content-Type: application/json" \
        --data "{
            \"personalizations\": [{\"to\": [{\"email\": \"$TO_EMAIL\"}]}],
            \"from\": {\"email\": \"alerts@example.com\"},
            \"subject\": \"GOV2DB Alert\",
            \"content\": [{\"type\": \"text/plain\", \"value\": \"$MESSAGE\"}]
        }"
}

# ============================================
# Example 5: Telegram Bot
# ============================================
send_telegram_alert() {
    local MESSAGE="$1"
    local BOT_TOKEN="YOUR_BOT_TOKEN"
    local CHAT_ID="YOUR_CHAT_ID"

    curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${MESSAGE}"
}

# ============================================
# Example 6: Generic Webhook (Zapier, n8n, etc.)
# ============================================
send_generic_webhook() {
    local STATUS="$1"
    local MESSAGE="$2"
    local WEBHOOK_URL="YOUR_WEBHOOK_URL"

    curl -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        --data "{
            \"service\": \"GOV2DB\",
            \"status\": \"$STATUS\",
            \"message\": \"$MESSAGE\",
            \"timestamp\": \"$(date -Iseconds)\",
            \"hostname\": \"$(hostname)\"
        }"
}

# ============================================
# Integration with monitoring script
# ============================================

# Add to monitor-health.sh:
#
# if [ $ERRORS -gt 0 ]; then
#     source scripts/webhook-example.sh
#     send_slack_alert "🚨 GOV2DB: $ERRORS error(s) detected"
# fi

# ============================================
# Cron integration example
# ============================================

# Add to crontab:
# */15 * * * * /path/to/scripts/monitor-health.sh --webhook "https://hooks.slack.com/YOUR/WEBHOOK"

echo "Webhook examples loaded. Choose your integration method above."
