# GOV2DB Monitoring Scripts

כלי עזר לניטור ובדיקת תקינות של GOV2DB.

## 📁 קבצים

### 1. monitor-health.sh
**מטרה**: בדיקת תקינות מקיפה של המערכת

**שימוש**:
```bash
# בדיקה בסיסית
./scripts/monitor-health.sh

# עם webhook (שליחת התראה על כשל)
./scripts/monitor-health.sh --webhook "https://hooks.slack.com/YOUR/WEBHOOK"
```

**בדיקות שמבצע**:
- ✓ Container running
- ✓ Health status
- ✓ Last sync time
- ✓ Cron daemon
- ✓ Timezone
- ✓ Environment variables
- ✓ Disk usage
- ✓ Network connectivity

**Exit codes**:
- `0` - הכל תקין
- `1` - נמצאו שגיאות

**אינטגרציה עם cron**:
```bash
# הרץ כל 15 דקות
*/15 * * * * /path/to/scripts/monitor-health.sh --webhook "YOUR_WEBHOOK_URL"
```

---

### 2. dashboard.sh
**מטרה**: תצוגת סטטוס מפורטת ויפה

**שימוש**:
```bash
./scripts/dashboard.sh
```

**מה זה מציג**:
- Container status & resource usage
- Health status
- Last sync time + next sync
- Cron schedule
- Recent logs
- Storage usage
- Configuration
- Quick action commands

**Tip**: הוסף alias:
```bash
echo "alias gov2db-status='cd /path/to/repo && ./GOV2DB/scripts/dashboard.sh'" >> ~/.bashrc
source ~/.bashrc

# עכשיו תוכל להריץ:
gov2db-status
```

---

### 3. webhook-example.sh
**מטרה**: דוגמאות לאינטגרציות webhook

**כולל דוגמאות ל**:
- Slack
- Discord
- Microsoft Teams
- Email (SendGrid)
- Telegram
- Generic webhooks (Zapier, n8n)

**שימוש**:
```bash
# טען את הפונקציות
source scripts/webhook-example.sh

# שלח התראה
send_slack_alert "🚨 Test alert"
```

**התאמה אישית**:
1. פתח את הקובץ
2. מצא את השירות שלך (Slack/Discord/etc.)
3. החלף את `YOUR_WEBHOOK_URL` עם ה-URL האמיתי
4. שמור וסגור

---

## 🚀 Quick Start

### הגדרת monitoring אוטומטי (מומלץ)

```bash
# 1. צור webhook (בחר שירות)
# לדוגמה Slack: https://api.slack.com/messaging/webhooks

# 2. בדוק שהכל עובד
./scripts/monitor-health.sh --webhook "YOUR_WEBHOOK_URL"

# 3. הוסף לcron (בשרת)
crontab -e

# 4. הוסף את השורה הזאת:
*/15 * * * * /path/to/GOV2DB/scripts/monitor-health.sh --webhook "YOUR_WEBHOOK_URL" >> /var/log/gov2db-monitor.log 2>&1
```

עכשיו תקבל התראה אוטומטית כל 15 דקות אם יש בעיה!

---

### הצגת dashboard

```bash
# צפייה חד-פעמית
./scripts/dashboard.sh

# צפייה רציפה (refresh כל 5 שניות)
watch -n 5 ./scripts/dashboard.sh
```

---

## 📊 Monitoring Strategy

### Recommended Setup

**Tier 1 - Critical (Real-time)**:
```bash
# Health check כל 15 דקות + webhook
*/15 * * * * /path/to/scripts/monitor-health.sh --webhook "YOUR_WEBHOOK"
```

**Tier 2 - Important (Hourly)**:
```bash
# Dashboard snapshot שמור ללוג
0 * * * * /path/to/scripts/dashboard.sh > /var/log/gov2db-dashboard-$(date +\%Y\%m\%d-\%H).log
```

**Tier 3 - Manual (On-demand)**:
```bash
# הרץ כשיש בעיה או לבדיקה שבועית
./scripts/dashboard.sh
```

---

## 🔧 Customization

### הוספת בדיקה חדשה ל-monitor-health.sh

```bash
# פתח את הקובץ
nano scripts/monitor-health.sh

# הוסף בדיקה חדשה אחרי Check 8:
# Check 9: Your custom check
echo -n "✓ Your check... "
if YOUR_CONDITION; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    ERRORS=$((ERRORS+1))
fi
```

### שינוי threshold ל-alerting

```bash
# בתוך monitor-health.sh, שנה:
ALERT_THRESHOLD=26  # hours

# ל:
ALERT_THRESHOLD=12  # שעות - יותר aggressive
```

---

## 💡 Tips & Tricks

### 1. Multiple webhooks
```bash
# במקום webhook אחד, שלח לכמה:
./scripts/monitor-health.sh --webhook "SLACK_URL"
if [ $? -ne 0 ]; then
    ./scripts/monitor-health.sh --webhook "DISCORD_URL"
fi
```

### 2. Silent hours
```bash
# אל תשלח alerts בין 00:00-06:00
HOUR=$(date +%H)
if [ $HOUR -ge 6 ] && [ $HOUR -lt 24 ]; then
    ./scripts/monitor-health.sh --webhook "YOUR_WEBHOOK"
else
    ./scripts/monitor-health.sh  # ללא webhook
fi
```

### 3. Dashboard in terminal multiplexer
```bash
# tmux split
tmux split-window -h 'watch -n 5 /path/to/scripts/dashboard.sh'

# או screen
screen -t "GOV2DB" watch -n 5 /path/to/scripts/dashboard.sh
```

### 4. Export metrics
```bash
# שמור metrics ל-JSON
./scripts/monitor-health.sh > /tmp/health.txt
# Parse ושלח ל-Prometheus/Grafana
```

---

## 🔍 Troubleshooting

### הסקריפטים לא רצים
```bash
# בדוק הרשאות
ls -la scripts/
# צריך להראות -rwxr-xr-x

# אם לא, הרץ:
chmod +x scripts/*.sh
```

### webhook לא עובד
```bash
# בדוק את ה-URL
curl -X POST YOUR_WEBHOOK_URL -d '{"text":"test"}'

# בדוק logs
tail -f /var/log/gov2db-monitor.log
```

### dashboard לא מציג מידע
```bash
# בדוק שהקונטיינר רץ
docker ps | grep gov2db-scraper

# בדוק permissions
docker exec gov2db-scraper ls -la /app/
```

---

## 📚 ראה גם

- [DEPLOYMENT-GUIDE.md](../DEPLOYMENT-GUIDE.md) - הוראות deployment
- [FAIL-SAFE-GUIDE.md](../FAIL-SAFE-GUIDE.md) - מנגנוני אל-כשל
- [README-DOCKER.md](../README-DOCKER.md) - מדריך Docker כללי
