#!/bin/bash
# Resolve log path relative to this script — works on any host with the
# standard repo layout (logs/ sibling to taste.sh). Designed for the ceci
# server; will produce empty log output if run from a host that doesn't
# also run the gov2db-scraper container.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/daily_sync.log"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           GOV2DB - טעימת החלטות אחרונות                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 5 ההחלטות האחרונות ב-DB:"
echo "─────────────────────────────────────────────────────────────────"
docker exec gov2db-scraper python3 -c "
import sys
sys.path.insert(0, '/app/src')
from gov_scraper.db.connector import get_supabase_client
client = get_supabase_client()
response = client.table('israeli_government_decisions') \
    .select('decision_number, decision_date, decision_title') \
    .order('decision_date', desc=True) \
    .order('decision_number', desc=True) \
    .limit(5) \
    .execute()
for d in response.data:
    title = d['decision_title'][:45] + '...' if len(d['decision_title']) > 45 else d['decision_title']
    print(f\"  {d['decision_number']:>5} | {d['decision_date']} | {title}\")
"
echo ""
echo "📊 סטטוס קונטיינר:"
echo "─────────────────────────────────────────────────────────────────"
STATUS=$(docker inspect --format='{{.State.Status}}' gov2db-scraper 2>/dev/null)
HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)
echo "  Status: $STATUS | Health: $HEALTH"
echo ""
echo "📝 Sync אחרון (5 שורות אחרונות):"
echo "─────────────────────────────────────────────────────────────────"
if [ -f "$LOG_FILE" ]; then
    tail -5 "$LOG_FILE"
else
    echo "  אין לוגים עדיין (log file not found at $LOG_FILE)"
fi
echo ""
