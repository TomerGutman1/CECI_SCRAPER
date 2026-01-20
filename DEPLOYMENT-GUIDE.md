# מדריך Deployment לשרת - GOV2DB

## 📋 תוכן עניינים
1. [הכנה לפני Deployment](#הכנה-לפני-deployment)
2. [העלאה לשרת](#העלאה-לשרת)
3. [בנייה והרצה](#בנייה-והרצה)
4. [בדיקות ואימותים](#בדיקות-ואימותים)
5. [ניטור שוטף](#ניטור-שוטף)
6. [Troubleshooting בשרת](#troubleshooting-בשרת)

---

## הכנה לפני Deployment

### ✅ Checklist לפני העלאה

- [ ] **קוד מוכן**: כל הקבצים התחייבו ל-git
- [ ] **.env מוכן**: יש לך את כל ה-API keys
- [ ] **רשת מזוהה**: אתה יודע את שם הרשת ב-docker-compose המרכזי
- [ ] **גישה לשרת**: SSH access + Docker permissions
- [ ] **backup**: יש backup של docker-compose.yml המרכזי הקיים

### 📦 מה להעלות לשרת

```bash
# מהמחשב המקומי
cd GOV2DB

# ודא שהכל committed (אופציונלי אם משתמש ב-git)
git status
git add .
git commit -m "Add Docker infrastructure for automated daily sync"
git push
```

או אם לא משתמש ב-git:
```bash
# העתק את כל התיקייה לשרת
rsync -avz --exclude 'venv' --exclude 'logs' --exclude 'data' \
  GOV2DB/ user@server:/path/to/repo/GOV2DB/
```

---

## העלאה לשרת

### שלב 1: התחבר לשרת

```bash
ssh user@your-server.com
cd /path/to/your-repo
```

### שלב 2: ודא שהקוד עודכן

אם משתמש ב-git:
```bash
git pull origin main
```

אם העתקת ידנית - ודא שכל הקבצים הגיעו:
```bash
ls -la GOV2DB/docker/
# צריך להראות: docker-entrypoint.sh, healthcheck.sh, crontab, logrotate.conf

ls -la GOV2DB/
# צריך להראות: Dockerfile, .dockerignore, docker-compose*.yml
```

### שלב 3: הגדר .env בשרת

```bash
cd GOV2DB

# צור .env מהתבנית
cp .env.example .env

# ערוך עם המפתחות האמיתיים (השתמש ב-vim/nano)
nano .env
```

הקובץ צריך להכיל:
```env
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

**🔒 אבטחה**: ודא שה-.env לא committed ל-git!
```bash
git status  # .env לא צריך להופיע
```

### שלב 4: צור תיקיות logs ו-data

```bash
mkdir -p logs data
chmod 755 logs data
```

---

## בנייה והרצה

### אופציה A: Standalone (לבדיקה ראשונית)

```bash
cd GOV2DB

# בנה את ה-image
docker build -t gov2db-scraper:latest .

# הרץ בדיקה חד-פעמית
docker run --rm \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  gov2db-scraper:latest \
  once

# בדוק שעבד
ls -lh logs/
cat logs/scraper.log
```

### אופציה B: אינטגרציה עם docker-compose המרכזי (Production)

#### שלב 1: מצא את שם הרשת

```bash
# מה-root של הריפו
cd /path/to/your-repo

# צפה ברשתות קיימות
docker network ls

# או בדוק בdocker-compose הקיים
grep -A 5 "networks:" docker-compose.yml
```

תקבל משהו כמו:
```
NETWORK ID     NAME                    DRIVER
abc123         myproject_default       bridge
def456         backend-network         bridge
```

שמור את שם הרשת (למשל: `backend-network`).

#### שלב 2: ערוך את docker-compose.integration.yml

```bash
cd GOV2DB

# ערוך את הקובץ
nano docker-compose.integration.yml

# החלף את 'YOUR_NETWORK_NAME' עם השם האמיתי
# לדוגמה: backend-network
```

או באופן אוטומטי:
```bash
# החלף YOUR_NETWORK_NAME ב-backend-network (דוגמה)
sed -i 's/YOUR_NETWORK_NAME/backend-network/g' docker-compose.integration.yml
```

#### שלב 3: העתק את הקטע ל-docker-compose המרכזי

```bash
# חזור ל-root של הריפו
cd /path/to/your-repo

# גבה את הקובץ הקיים!
cp docker-compose.yml docker-compose.yml.backup

# פתח את docker-compose.yml לעריכה
nano docker-compose.yml
```

העתק את **כל הקטע** של `gov2db-scraper` מ-`GOV2DB/docker-compose.integration.yml` והדבק אותו תחת `services:`.

הקובץ צריך להיראות כך:
```yaml
version: '3.8'

services:
  # ... השירותים הקיימים שלך ...

  gov2db-scraper:              # ← הקטע החדש
    build:
      context: ./GOV2DB
      dockerfile: Dockerfile
    container_name: gov2db-scraper
    restart: unless-stopped
    env_file:
      - ./GOV2DB/.env
    volumes:
      - ./GOV2DB/logs:/app/logs
      - ./GOV2DB/data:/app/data
    networks:
      - backend-network        # ← השם שמצאת
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

networks:
  backend-network:             # ← השם שמצאת
    external: true
```

#### שלב 4: בנה והרץ

```bash
# מה-root של הריפו
cd /path/to/your-repo

# בנה את GOV2DB (פעם ראשונה)
docker-compose build gov2db-scraper

# הרץ רק את GOV2DB
docker-compose up -d gov2db-scraper

# בדוק שעלה
docker ps | grep gov2db-scraper
```

---

## בדיקות ואימותים

### ✅ Checklist אימותים

#### 1. הקונטיינר רץ
```bash
docker ps | grep gov2db-scraper

# צפוי:
# gov2db-scraper   Up X minutes (healthy)
```

#### 2. Logs נראים תקינים
```bash
docker logs gov2db-scraper

# צפוי:
# =========================================
# GOV2DB Israeli Government Scraper
# =========================================
# Timezone: Asia/Jerusalem
# Mode: cron
# Starting cron daemon...
```

#### 3. Cron מוגדר נכון
```bash
docker exec gov2db-scraper crontab -l

# צפוי:
# 0 2 * * * cd /app && python3 bin/sync.py ...
```

#### 4. Timezone נכון
```bash
docker exec gov2db-scraper date

# צפוי להראות שעון ישראלי:
# Tue Jan  7 21:30:00 IST 2026
```

#### 5. Environment variables מוגדרים
```bash
docker exec gov2db-scraper env | grep -E 'OPENAI|SUPABASE'

# צפוי:
# OPENAI_API_KEY=sk-proj-...
# SUPABASE_URL=https://xxx.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

#### 6. Health check עובד
```bash
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# צפוי:
# healthy
```

#### 7. חיבור לרשת
```bash
docker inspect gov2db-scraper | grep -A 10 "Networks"

# צפוי להראות את הרשת הנכונה
```

#### 8. חיבור ל-DB
```bash
docker exec gov2db-scraper python3 tests/test_connection.py

# צפוי:
# ✅ Connection successful
```

#### 9. הרצת sync ידנית (בדיקה אמיתית)
```bash
# הרץ sync של decision אחד
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose

# צפה בלוגים
docker exec gov2db-scraper tail -f /app/logs/daily_sync.log
```

#### 10. Volume mounts עובדים
```bash
# מה-host - בדוק שהלוגים מתעדכנים
ls -lh GOV2DB/logs/
tail -f GOV2DB/logs/daily_sync.log
```

---

## ניטור שוטף

### בדיקות יומיות/שבועיות

#### בדיקה יומית (2 דקות)
```bash
# מהשרת
cd /path/to/your-repo

# בדוק שהקונטיינר רץ
docker ps | grep gov2db-scraper

# בדוק health
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# בדוק שהיה sync אתמול
ls -lt GOV2DB/logs/daily_sync.log
tail -20 GOV2DB/logs/daily_sync.log | grep "successfully"
```

#### בדיקה שבועית (5 דקות)
```bash
# גודל לוגים
du -sh GOV2DB/logs/

# מספר decisions בDB (צריך לגדול)
docker exec gov2db-scraper python3 -c "
from gov_scraper.db.dal import get_latest_decision
latest = get_latest_decision()
print(f'Latest decision: {latest}')
"

# בדיקת logrotate
docker exec gov2db-scraper ls -lh /app/logs/*.gz 2>/dev/null | wc -l
# אם יש קבצים .gz - logrotate עובד
```

### Monitoring אוטומטי (אופציונלי)

#### יצירת health check script בשרת
```bash
# בשרת - צור סקריפט monitoring
cat > /usr/local/bin/gov2db-health.sh << 'EOF'
#!/bin/bash
STATUS=$(docker inspect --format='{{.State.Health.Status}}' gov2db-scraper 2>/dev/null)
if [ "$STATUS" != "healthy" ]; then
    echo "GOV2DB UNHEALTHY: $STATUS"
    # שלח התראה (webhook/email)
    # curl -X POST https://your-monitoring-service.com/alert ...
    exit 1
fi
echo "GOV2DB OK"
EOF

chmod +x /usr/local/bin/gov2db-health.sh

# הרץ כל שעה דרך cron
crontab -e
# הוסף:
# 0 * * * * /usr/local/bin/gov2db-health.sh >> /var/log/gov2db-health.log 2>&1
```

---

## Troubleshooting בשרת

### בעיה: הקונטיינר לא עולה

```bash
# בדוק לוגים
docker logs gov2db-scraper

# בדוק אם יש port conflicts
docker ps -a | grep 8080

# נסה להריץ interactively
docker run --rm -it --env-file GOV2DB/.env gov2db-scraper:latest bash
```

### בעיה: Sync לא רץ בזמן

```bash
# בדוק שcron רץ
docker exec gov2db-scraper ps aux | grep cron

# בדוק timezone
docker exec gov2db-scraper date
docker exec gov2db-scraper cat /etc/timezone

# בדוק cron logs
docker exec gov2db-scraper cat /app/logs/cron.log
```

### בעיה: Health check נכשל

```bash
# הרץ health check ידנית
docker exec gov2db-scraper /usr/local/bin/healthcheck.sh

# בדוק timestamp
docker exec gov2db-scraper cat /app/healthcheck/last_success.txt

# אפס timestamp אם צריך
docker exec gov2db-scraper sh -c 'echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt'
```

### בעיה: חיבור ל-DB נכשל

```bash
# בדוק env vars
docker exec gov2db-scraper env | grep SUPABASE

# בדוק connectivity
docker exec gov2db-scraper curl -I https://your-project.supabase.co

# בדוק רשת
docker network inspect backend-network
```

### בעיה: Logs ממלאים דיסק

```bash
# בדוק גודל
du -sh GOV2DB/logs/

# הרץ logrotate ידנית
docker exec gov2db-scraper /usr/sbin/logrotate /etc/logrotate.d/gov2db -f

# נקה ישן (זהירות!)
find GOV2DB/logs -name "*.log.*" -mtime +30 -delete
```

---

## Roll Back (במקרה של בעיה)

אם משהו השתבש:

```bash
# עצור והסר את GOV2DB
docker-compose stop gov2db-scraper
docker-compose rm -f gov2db-scraper

# שחזר docker-compose ישן
cp docker-compose.yml.backup docker-compose.yml

# הרץ מחדש
docker-compose up -d
```

---

## Update/Rebuild

כשצריך לעדכן את הקוד:

```bash
# עדכן קוד
cd /path/to/your-repo
git pull

# rebuild image
docker-compose build gov2db-scraper

# restart
docker-compose up -d gov2db-scraper

# בדוק
docker logs -f gov2db-scraper
```

---

## סיכום - Quick Reference

```bash
# סטטוס
docker ps | grep gov2db
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# לוגים
docker logs -f gov2db-scraper
tail -f GOV2DB/logs/daily_sync.log

# הרצה ידנית
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose

# debug
docker exec -it gov2db-scraper bash

# restart
docker-compose restart gov2db-scraper

# rebuild
docker-compose build gov2db-scraper && docker-compose up -d gov2db-scraper
```

---

## צור קשר לעזרה

- 📖 [README-DOCKER.md](README-DOCKER.md) - מדריך מלא
- 🔧 [INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md) - אינטגרציה מהירה
- 💡 [FAIL-SAFE-GUIDE.md](FAIL-SAFE-GUIDE.md) - מנגנוני אל-כשל
