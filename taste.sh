#!/bin/bash
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
tail -5 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log 2>/dev/null || echo "  אין לוגים עדיין"
echo ""
