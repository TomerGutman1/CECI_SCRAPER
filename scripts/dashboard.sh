#!/bin/bash

# GOV2DB Status Dashboard
# Shows comprehensive status overview

set -e

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

clear

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════╗"
echo "║        GOV2DB Status Dashboard                         ║"
echo "║        Israeli Government Decisions Scraper            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Container Info
echo -e "${BLUE}━━━ Container Status ━━━${NC}"
if docker ps | grep -q gov2db-scraper; then
    echo -e "${GREEN}● Running${NC}"
    UPTIME=$(docker inspect --format='{{.State.StartedAt}}' gov2db-scraper 2>/dev/null)
    echo "  Started: $UPTIME"

    # Resource usage
    STATS=$(docker stats gov2db-scraper --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | tail -1)
    echo "  Resources: $STATS"
else
    echo -e "${RED}● Not Running${NC}"
fi
echo ""

# Health Status
echo -e "${BLUE}━━━ Health Status ━━━${NC}"
STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null || echo "unknown")
case $STATUS in
    healthy)
        echo -e "${GREEN}● Healthy${NC}"
        ;;
    unhealthy)
        echo -e "${RED}● Unhealthy${NC}"
        ;;
    starting)
        echo -e "${YELLOW}● Starting${NC}"
        ;;
    *)
        echo -e "${YELLOW}● Unknown${NC}"
        ;;
esac

# Last health check output
HEALTH_OUTPUT=$(docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' gov2db-scraper 2>/dev/null | tail -1)
if [ -n "$HEALTH_OUTPUT" ]; then
    echo "  Last check: $HEALTH_OUTPUT"
fi
echo ""

# Last Sync
echo -e "${BLUE}━━━ Sync Status ━━━${NC}"
if docker exec gov2db-scraper test -f /app/healthcheck/last_success.txt 2>/dev/null; then
    LAST=$(docker exec gov2db-scraper cat /app/healthcheck/last_success.txt 2>/dev/null)
    echo "  Last successful sync: $LAST"

    # Calculate age
    CURRENT_EPOCH=$(date +%s)
    LAST_EPOCH=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
    AGE_SEC=$((CURRENT_EPOCH - LAST_EPOCH))
    AGE_HOURS=$((AGE_SEC / 3600))
    AGE_MIN=$(((AGE_SEC % 3600) / 60))

    if [ $AGE_HOURS -lt 24 ]; then
        echo -e "  Age: ${GREEN}${AGE_HOURS}h ${AGE_MIN}m ago${NC}"
    elif [ $AGE_HOURS -lt 48 ]; then
        echo -e "  Age: ${YELLOW}${AGE_HOURS}h ago${NC}"
    else
        echo -e "  Age: ${RED}${AGE_HOURS}h ago (STALE!)${NC}"
    fi
else
    echo -e "${YELLOW}  No sync record found${NC}"
fi

# Next scheduled sync
echo "  Next scheduled: 02:00 AM (Asia/Jerusalem)"
CURRENT_HOUR=$(docker exec gov2db-scraper date +%H 2>/dev/null || date +%H)
if [ $CURRENT_HOUR -lt 2 ]; then
    echo "  Time until next: $((2 - CURRENT_HOUR)) hours"
else
    echo "  Time until next: $((26 - CURRENT_HOUR)) hours"
fi
echo ""

# Cron Status
echo -e "${BLUE}━━━ Scheduler Status ━━━${NC}"
if docker exec gov2db-scraper ps aux 2>/dev/null | grep -q '[c]ron'; then
    echo -e "${GREEN}● Cron running${NC}"

    # Show cron schedule
    echo "  Schedule:"
    docker exec gov2db-scraper crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | sed 's/^/    /'
else
    echo -e "${RED}● Cron not running${NC}"
fi
echo ""

# Recent Activity
echo -e "${BLUE}━━━ Recent Activity ━━━${NC}"
if docker exec gov2db-scraper test -f /app/logs/daily_sync.log 2>/dev/null; then
    echo "  Last 5 log entries:"
    docker exec gov2db-scraper tail -5 /app/logs/daily_sync.log 2>/dev/null | sed 's/^/    /' || echo "    (no logs)"

    # Count recent errors
    ERROR_COUNT=$(docker exec gov2db-scraper grep -i "error" /app/logs/daily_sync.log 2>/dev/null | tail -10 | wc -l || echo 0)
    if [ $ERROR_COUNT -gt 0 ]; then
        echo -e "  ${RED}Recent errors: $ERROR_COUNT${NC}"
    fi
else
    echo "  No log file found"
fi
echo ""

# Storage
echo -e "${BLUE}━━━ Storage ━━━${NC}"
if docker exec gov2db-scraper test -d /app/logs 2>/dev/null; then
    LOGS_SIZE=$(docker exec gov2db-scraper du -sh /app/logs 2>/dev/null | awk '{print $1}')
    echo "  Logs: $LOGS_SIZE"
fi
if docker exec gov2db-scraper test -d /app/data 2>/dev/null; then
    DATA_SIZE=$(docker exec gov2db-scraper du -sh /app/data 2>/dev/null | awk '{print $1}')
    echo "  Data: $DATA_SIZE"
fi

# Container disk usage
DISK_USAGE=$(docker exec gov2db-scraper df -h /app 2>/dev/null | tail -1 | awk '{print $5}' || echo "N/A")
echo "  Container disk: $DISK_USAGE"
echo ""

# Configuration
echo -e "${BLUE}━━━ Configuration ━━━${NC}"
TZ=$(docker exec gov2db-scraper cat /etc/timezone 2>/dev/null || echo "unknown")
echo "  Timezone: $TZ"

CURRENT_TIME=$(docker exec gov2db-scraper date 2>/dev/null || echo "unknown")
echo "  Current time: $CURRENT_TIME"

# Environment check (don't show values!)
if docker exec gov2db-scraper env 2>/dev/null | grep -q OPENAI_API_KEY; then
    echo -e "  OpenAI API: ${GREEN}configured${NC}"
else
    echo -e "  OpenAI API: ${RED}missing${NC}"
fi

if docker exec gov2db-scraper env 2>/dev/null | grep -q SUPABASE_URL; then
    echo -e "  Supabase: ${GREEN}configured${NC}"
else
    echo -e "  Supabase: ${RED}missing${NC}"
fi
echo ""

# Quick Actions
echo -e "${BLUE}━━━ Quick Actions ━━━${NC}"
echo "  View logs:        docker logs -f gov2db-scraper"
echo "  Manual sync:      docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose"
echo "  Health check:     docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"
echo "  Debug shell:      docker exec -it gov2db-scraper bash"
echo "  Restart:          docker-compose restart gov2db-scraper"
echo ""

# Footer
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo "Last updated: $(date)"
echo ""
