#!/bin/bash

# GOV2DB Health Monitor Script
# Usage: ./scripts/monitor-health.sh [--webhook WEBHOOK_URL]

set -e

WEBHOOK_URL=""
ALERT_THRESHOLD=26  # hours

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --webhook)
            WEBHOOK_URL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

echo "=========================================="
echo "GOV2DB Health Monitor"
echo "Time: $(date)"
echo "=========================================="
echo ""

# Check 1: Container running
echo -n "✓ Container running... "
if docker ps | grep -q gov2db-scraper; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 2: Health status
echo -n "✓ Health status... "
STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null || echo "unknown")
if [ "$STATUS" = "healthy" ]; then
    echo -e "${GREEN}OK ($STATUS)${NC}"
elif [ "$STATUS" = "starting" ]; then
    echo -e "${YELLOW}STARTING${NC}"
    WARNINGS=$((WARNINGS+1))
else
    echo -e "${RED}FAILED ($STATUS)${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 3: Last sync time
echo -n "✓ Last sync... "
if docker exec gov2db-scraper test -f /app/healthcheck/last_success.txt 2>/dev/null; then
    LAST=$(docker exec gov2db-scraper cat /app/healthcheck/last_success.txt 2>/dev/null)
    CURRENT_EPOCH=$(date +%s)
    LAST_EPOCH=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
    AGE_SEC=$((CURRENT_EPOCH - LAST_EPOCH))
    AGE_HOURS=$((AGE_SEC / 3600))

    if [ $AGE_HOURS -lt $ALERT_THRESHOLD ]; then
        echo -e "${GREEN}OK (${AGE_HOURS}h ago)${NC}"
    else
        echo -e "${RED}STALE (${AGE_HOURS}h ago, threshold: ${ALERT_THRESHOLD}h)${NC}"
        ERRORS=$((ERRORS+1))
    fi
else
    echo -e "${YELLOW}No timestamp file${NC}"
    WARNINGS=$((WARNINGS+1))
fi

# Check 4: Cron running
echo -n "✓ Cron daemon... "
if docker exec gov2db-scraper ps aux 2>/dev/null | grep -q '[c]ron'; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}NOT RUNNING${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 5: Timezone
echo -n "✓ Timezone... "
TZ=$(docker exec gov2db-scraper cat /etc/timezone 2>/dev/null || echo "unknown")
if [ "$TZ" = "Asia/Jerusalem" ]; then
    echo -e "${GREEN}OK ($TZ)${NC}"
else
    echo -e "${YELLOW}Unexpected ($TZ)${NC}"
    WARNINGS=$((WARNINGS+1))
fi

# Check 6: Environment variables
echo -n "✓ Environment... "
if docker exec gov2db-scraper env 2>/dev/null | grep -q OPENAI_API_KEY && \
   docker exec gov2db-scraper env 2>/dev/null | grep -q SUPABASE_URL; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}Missing env vars${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 7: Disk usage
echo -n "✓ Disk usage... "
DISK_USAGE=$(docker exec gov2db-scraper df /app 2>/dev/null | tail -1 | awk '{print $5}' | sed 's/%//' || echo "0")
if [ $DISK_USAGE -lt 80 ]; then
    echo -e "${GREEN}OK (${DISK_USAGE}%)${NC}"
elif [ $DISK_USAGE -lt 90 ]; then
    echo -e "${YELLOW}WARNING (${DISK_USAGE}%)${NC}"
    WARNINGS=$((WARNINGS+1))
else
    echo -e "${RED}CRITICAL (${DISK_USAGE}%)${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 8: Network connectivity
echo -n "✓ Network... "
if docker exec gov2db-scraper timeout 5 curl -s -o /dev/null -w "%{http_code}" https://www.google.com 2>/dev/null | grep -q "200"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}Limited connectivity${NC}"
    WARNINGS=$((WARNINGS+1))
fi

echo ""
echo "=========================================="

# Summary
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed${NC}"
    STATUS_MESSAGE="GOV2DB: All systems operational"
    EXIT_CODE=0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ ${WARNINGS} warning(s)${NC}"
    STATUS_MESSAGE="GOV2DB: ${WARNINGS} warning(s) detected"
    EXIT_CODE=0
else
    echo -e "${RED}✗ ${ERRORS} error(s), ${WARNINGS} warning(s)${NC}"
    STATUS_MESSAGE="GOV2DB: ${ERRORS} error(s), ${WARNINGS} warning(s)"
    EXIT_CODE=1
fi

echo "=========================================="

# Send webhook if configured
if [ -n "$WEBHOOK_URL" ] && [ $ERRORS -gt 0 ]; then
    echo "Sending alert to webhook..."
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"🚨 $STATUS_MESSAGE\"}" \
        "$WEBHOOK_URL" 2>/dev/null || echo "Webhook failed"
fi

exit $EXIT_CODE
