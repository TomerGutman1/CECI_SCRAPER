# מדריך מנגנוני אל-כשל (Fail-Safe) - GOV2DB

## 🛡️ סקירה כללית

המערכת כבר כוללת מספר מנגנוני אל-כשל built-in. מדריך זה מסביר מה קיים ומה אפשר להוסיף.

---

## ✅ מנגנונים קיימים (Built-in)

### 1. **Restart Policy**
📍 **מיקום**: docker-compose.yml
```yaml
restart: unless-stopped
```

**מה זה עושה**:
- אם הקונטיינר קורס → Docker מריץ אותו מחדש אוטומטית
- אם השרת מתאתחל → הקונטיינר עולה אוטומטית
- רק `docker-compose stop` ידני יעצור אותו

**בדיקה**:
```bash
# גרום לקונטיינר לקרוס
docker kill gov2db-scraper

# חכה 5 שניות
sleep 5

# בדוק שעלה מחדש
docker ps | grep gov2db-scraper
# צריך להראות: Up XX seconds (restarting)
```

---

### 2. **Health Checks**
📍 **מיקום**: Dockerfile (שורה 58), docker/healthcheck.sh

**מה זה עושה**:
- בודק כל שעה שהמערכת תקינה
- בדיקות:
  1. Timestamp של הרצה אחרונה (<48h)
  2. חיבור ל-Supabase DB
- אם נכשל 3 פעמים ברצף → מסומן כ-unhealthy

**בדיקה**:
```bash
# בדוק סטטוס
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# צפייה בהיסטוריית health checks
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' gov2db-scraper
```

**מה קורה אם unhealthy?**
- Docker **לא** עוצר אוטומטית (בשביל זה צריך orchestration כמו Kubernetes)
- אבל אפשר להוסיף monitoring שיתריע (ראה למטה)

---

### 3. **Log Rotation**
📍 **מיקום**: docker/logrotate.conf

**מה זה עושה**:
- מסובב logs כל יום ב-03:00
- שומר 30 יום
- דוחס ישנים (gzip)
- מונע disk-full

**בדיקה**:
```bash
# בדוק שlogrotate רץ
docker exec gov2db-scraper ls -lh /app/logs/*.gz

# אם יש .gz files → עובד
```

---

### 4. **Docker Logging Limits**
📍 **מיקום**: docker-compose.yml
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "50m"
    max-file: "5"
```

**מה זה עושה**:
- מגביל Docker logs ל-5 קבצים × 50MB = 250MB מקסימום
- מונע disk-full ברמת Docker

---

### 5. **Graceful Error Handling בקוד**
📍 **מיקום**: bin/sync.py, processors/*

**מה זה עושה**:
- `try/except` על כל decision
- אם decision אחד נכשל → ממשיך לבאים
- לוגים מפורטים
- Retry logic ב-OpenAI (5 נסיונות)

**בדיקה**:
```bash
# הרץ sync - תראה שגם אם decision אחד נכשל, זה ממשיך
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 5 --verbose
```

---

### 6. **Duplicate Prevention**
📍 **מיקום**: processors/incremental.py, db/dal.py

**מה זה עושה**:
- בודק `decision_key` לפני insertion
- מונע הכנסת אותה החלטה פעמיים
- גם אם הסקריפט רץ 2 פעמים בטעות

---

## 🚨 מנגנונים נוספים (מומלץ להוסיף)

### 1. **Monitoring + Alerting**

#### אפשרות A: Webhook על כשל
צור סקריפט שבודק health ושולח webhook:

```bash
# בשרת - צור /usr/local/bin/gov2db-monitor.sh
#!/bin/bash
WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)

if [ "$STATUS" != "healthy" ]; then
    MESSAGE="{\"text\":\"⚠️ GOV2DB Unhealthy: $STATUS\"}"
    curl -X POST -H 'Content-type: application/json' --data "$MESSAGE" "$WEBHOOK_URL"
fi
```

הוסף ל-cron:
```bash
crontab -e
# הוסף:
*/15 * * * * /usr/local/bin/gov2db-monitor.sh
```

#### אפשרות B: Email על כשל
```bash
#!/bin/bash
STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)

if [ "$STATUS" != "healthy" ]; then
    echo "GOV2DB is $STATUS" | mail -s "GOV2DB Alert" admin@example.com
fi
```

#### אפשרות C: Prometheus + Grafana
אם יש לך Prometheus:
```yaml
# הוסף ל-docker-compose.yml
labels:
  - "prometheus.scrape=true"
  - "prometheus.port=8080"
```

---

### 2. **Dead Letter Queue (DLQ)**

הוסף mechanism לשמירת decisions שנכשלו:

```bash
# צור תיקייה
mkdir -p GOV2DB/data/failed_decisions
```

ערוך את `bin/sync.py` (או צור wrapper):
```python
# בתוך loop של decisions
try:
    process_decision(decision)
except Exception as e:
    # שמור את ה-decision הכושל
    with open(f'data/failed_decisions/{decision_key}.json', 'w') as f:
        json.dump({
            'decision': decision,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, f)
```

ואז אפשר לעבד אותם מאוחר יותר:
```bash
# הרץ retry על failed decisions
docker exec gov2db-scraper python3 bin/retry_failed.py
```

---

### 3. **Backup לפני Sync**

הוסף backup אוטומטי לפני כל sync:

```bash
# ב-docker/crontab - עדכן את השורה:
0 2 * * * pg_dump $SUPABASE_URL > /app/data/backup_$(date +\%Y\%m\%d).sql && cd /app && python3 bin/sync.py ...
```

או backup לוקלי:
```bash
# ב-docker/crontab - הוסף שורה לפני הsync:
55 1 * * * docker exec gov2db-scraper python3 -c "from gov_scraper.db.utils import backup_to_csv; backup_to_csv('data/backup_$(date +\%Y\%m\%d).csv')"
```

---

### 4. **Notification על הצלחה**

לפעמים כדאי לדעת שהכל **עבד**:

```bash
# בדוק אם sync הצליח והתריע
# ב-docker/crontab:
0 2 * * * cd /app && python3 bin/sync.py --unlimited --no-approval --verbose --safety-mode regular >> /app/logs/daily_sync.log 2>&1 && echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt && curl -X POST -d "status=success&time=$(date)" https://your-monitor.com/gov2db || (echo "Sync failed at $(date)" >> /app/logs/daily_sync.log && curl -X POST -d "status=failed&time=$(date)" https://your-monitor.com/gov2db)
```

---

### 5. **Watchdog Process**

אם רוצה ממש להבטיח שה-sync רץ:

```python
# צור bin/watchdog.py
"""
Watchdog: בודק שהsync היומי אכן רץ
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

HEALTH_FILE = Path('/app/healthcheck/last_success.txt')
MAX_AGE_HOURS = 26  # אם לא רץ 26 שעות - תריעה

def check_last_run():
    if not HEALTH_FILE.exists():
        return False, "No health file"

    last_run = datetime.fromisoformat(HEALTH_FILE.read_text().strip())
    age = datetime.now() - last_run

    if age > timedelta(hours=MAX_AGE_HOURS):
        return False, f"Last run was {age.total_seconds()/3600:.1f} hours ago"

    return True, f"Last run {age.total_seconds()/3600:.1f} hours ago"

if __name__ == '__main__':
    ok, msg = check_last_run()
    if not ok:
        # שלח alert
        print(f"ALERT: {msg}")
        # webhook/email here
        exit(1)
    else:
        print(f"OK: {msg}")
```

הרץ כל 6 שעות:
```bash
# ב-cron של השרת
0 */6 * * * docker exec gov2db-scraper python3 bin/watchdog.py || echo "GOV2DB WATCHDOG ALERT" | mail -s "Alert" admin@example.com
```

---

## 📊 Best Practices

### 1. **Monitoring Dashboard**

צור dashboard פשוט:
```bash
# bin/dashboard.sh
#!/bin/bash
echo "=========================================="
echo "GOV2DB Status Dashboard"
echo "=========================================="
echo ""
echo "Container Status:"
docker ps | grep gov2db-scraper || echo "NOT RUNNING"
echo ""
echo "Health:"
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null
echo ""
echo "Last Sync:"
docker exec gov2db-scraper cat /app/healthcheck/last_success.txt 2>/dev/null
echo ""
echo "Recent Errors:"
docker exec gov2db-scraper tail -20 /app/logs/daily_sync.log | grep -i error
echo ""
echo "Disk Usage:"
docker exec gov2db-scraper du -sh /app/logs /app/data
echo "=========================================="
```

הרץ:
```bash
./bin/dashboard.sh
```

---

### 2. **Scheduled Health Checks**

```bash
# צור /usr/local/bin/gov2db-full-check.sh
#!/bin/bash
ERRORS=0

# 1. Container running?
docker ps | grep -q gov2db-scraper || ERRORS=$((ERRORS+1))

# 2. Health OK?
STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)
[ "$STATUS" = "healthy" ] || ERRORS=$((ERRORS+1))

# 3. Last sync < 26h?
LAST=$(docker exec gov2db-scraper cat /app/healthcheck/last_success.txt 2>/dev/null)
AGE_SEC=$(( $(date +%s) - $(date -d "$LAST" +%s 2>/dev/null || echo 0) ))
AGE_HOURS=$((AGE_SEC / 3600))
[ $AGE_HOURS -lt 26 ] || ERRORS=$((ERRORS+1))

# 4. Disk not full?
DISK_USAGE=$(docker exec gov2db-scraper df /app | tail -1 | awk '{print $5}' | sed 's/%//')
[ $DISK_USAGE -lt 90 ] || ERRORS=$((ERRORS+1))

if [ $ERRORS -gt 0 ]; then
    echo "GOV2DB: $ERRORS issues found"
    # שלח התראה
    exit 1
fi

echo "GOV2DB: All checks passed"
```

הוסף ל-cron:
```bash
0 */4 * * * /usr/local/bin/gov2db-full-check.sh
```

---

### 3. **Automated Recovery**

סקריפט שמנסה לתקן בעיות:

```bash
# /usr/local/bin/gov2db-auto-recover.sh
#!/bin/bash

STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)

if [ "$STATUS" != "healthy" ]; then
    echo "$(date): Unhealthy detected, attempting recovery..."

    # נסיון 1: Restart
    docker-compose restart gov2db-scraper
    sleep 30

    STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)
    if [ "$STATUS" = "healthy" ]; then
        echo "$(date): Recovered with restart"
        exit 0
    fi

    # נסיון 2: Rebuild
    cd /path/to/repo
    docker-compose build gov2db-scraper
    docker-compose up -d gov2db-scraper
    sleep 60

    STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)
    if [ "$STATUS" = "healthy" ]; then
        echo "$(date): Recovered with rebuild"
        exit 0
    fi

    # כשל - התראה
    echo "$(date): Recovery failed - manual intervention needed"
    # שלח email/webhook
    exit 1
fi
```

---

## 🔍 Monitoring Checklist

### בדיקות אוטומטיות (cron)
- [ ] Health check כל 15 דקות
- [ ] Full check כל 4 שעות
- [ ] Watchdog כל 6 שעות
- [ ] Log rotation פעם ביום
- [ ] Backup שבועי

### בדיקות ידניות (שבועי/חודשי)
- [ ] צפייה בלוגים (`tail -100 logs/daily_sync.log`)
- [ ] בדיקת גודל DB (צומח?)
- [ ] בדיקת failed decisions (`ls data/failed_decisions/`)
- [ ] בדיקת disk space (`df -h`)
- [ ] בדיקת resource usage (`docker stats gov2db-scraper`)

---

## 🚨 Incident Response Plan

### תרחיש 1: הקונטיינר לא עולה
```bash
# 1. בדוק logs
docker logs gov2db-scraper

# 2. בדוק resource limits
docker stats gov2db-scraper

# 3. נסה interactive
docker run --rm -it --env-file GOV2DB/.env gov2db-scraper:latest bash

# 4. rebuild
docker-compose build gov2db-scraper
docker-compose up -d gov2db-scraper
```

### תרחיש 2: Sync לא רץ
```bash
# 1. בדוק cron
docker exec gov2db-scraper ps aux | grep cron

# 2. בדוק timezone
docker exec gov2db-scraper date

# 3. הרץ ידנית לבדיקה
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose

# 4. בדוק cron logs
docker exec gov2db-scraper cat /app/logs/cron.log
```

### תרחיש 3: DB connection נכשל
```bash
# 1. בדוק credentials
docker exec gov2db-scraper env | grep SUPABASE

# 2. בדוק network
docker exec gov2db-scraper curl -I https://your-project.supabase.co

# 3. בדוק firewall/security groups בשרת

# 4. בדוק Supabase status
curl -I https://status.supabase.com
```

### תרחיש 4: Disk מלא
```bash
# 1. בדוק גודל
du -sh GOV2DB/logs/ GOV2DB/data/

# 2. נקה logs ישנים
find GOV2DB/logs -name "*.log.*" -mtime +30 -delete

# 3. הרץ logrotate
docker exec gov2db-scraper /usr/sbin/logrotate /etc/logrotate.d/gov2db -f

# 4. בדוק data/
ls -lh GOV2DB/data/
```

---

## 📈 Metrics to Track

מדדים חשובים למעקב:

1. **Uptime**: % זמן שהקונטיינר healthy
2. **Success Rate**: % syncs שהצליחו
3. **Processing Time**: כמה זמן לוקח sync
4. **Decisions/Day**: כמה החלטות מעובדות
5. **Error Rate**: כמה שגיאות ליום
6. **Disk Growth**: קצב גידול ה-logs/data

---

## 🎯 SLA Recommendations

הגדרת SLA מציאותי:

- **Availability**: 99% (3.6 שעות downtime/חודש מותר)
- **Success Rate**: 95% (5% failures מותר)
- **Recovery Time**: < 1 שעה
- **Data Loss**: אפס (כל decision נשמר)

---

## סיכום

### מה כבר קיים ✅
1. Restart policy
2. Health checks
3. Log rotation
4. Error handling בקוד
5. Duplicate prevention

### מה כדאי להוסיף 🔧
1. **Monitoring + Alerting** (webhook/email על כשל)
2. **Watchdog** (בודק שהsync רץ)
3. **Automated recovery** (restart אוטומטי על כשל)
4. **Dead letter queue** (שמירת failures)
5. **Dashboard** (סטטוס מרוכז)

### Priority
1. 🔴 **High**: Monitoring + Alerting
2. 🟡 **Medium**: Watchdog, Automated recovery
3. 🟢 **Low**: DLQ, Dashboard

---

ראה גם:
- [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) - הוראות deployment
- [README-DOCKER.md](README-DOCKER.md) - מדריך כללי
