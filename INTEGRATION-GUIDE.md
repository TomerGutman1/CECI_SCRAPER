# מדריך אינטגרציה מהיר - GOV2DB ב-Docker Compose מרכזי

## 🎯 סיכום

יש לך ריפו גדול עם docker-compose מרכזי. הנה איך להוסיף את GOV2DB.

---

## שלב 1: מצא את שם הרשת הקיימת

```bash
# הרץ מה-root של הריפו
cd /path/to/your-repo

# צפה ב-docker-compose.yml המרכזי
cat docker-compose.yml | grep -A 5 "networks:"

# או אם הקונטיינרים כבר רצים:
docker network ls
```

תקבל משהו כמו:
```
NETWORK ID     NAME                    DRIVER
abc123def456   myproject_default       bridge
abc123def456   backend-network         bridge
```

שם הרשת הוא בדרך כלל: `<project-name>_default` או שם מותאם אישית.

---

## שלב 2: העתק את הקטע ל-docker-compose המרכזי

פתח את `docker-compose.integration.yml` שנוצר, והעתק את **כל** הקטע של `gov2db-scraper` service.

**לפני ההעתקה - החלף**:
1. `YOUR_NETWORK_NAME` → שם הרשת שמצאת בשלב 1
2. ודא שה-paths נכונים (אם GOV2DB לא בתיקייה ישירה ב-root)

---

## שלב 3: הדבק ב-docker-compose.yml המרכזי

```yaml
version: '3.8'

services:
  # ... השירותים הקיימים שלך ...

  gov2db-scraper:      # ← הדבק את כל הקטע מ-docker-compose.integration.yml
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
      - backend-network    # ← שם הרשת שמצאת
    # ... שאר ההגדרות

networks:
  backend-network:         # ← צריך להתאים לרשת הקיימת
    external: true         # אם הרשת כבר קיימת
```

---

## שלב 4: ודא ש-.env קיים

```bash
cd GOV2DB

# אם אין .env - צור אותו
cp .env.example .env

# ערוך עם המפתחות האמיתיים
vim .env
```

הקובץ חייב להכיל:
```env
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

---

## שלב 5: בנה והרץ

```bash
# מה-root של הריפו
cd /path/to/your-repo

# בנה את GOV2DB (פעם ראשונה)
docker-compose build gov2db-scraper

# הרץ רק את GOV2DB
docker-compose up -d gov2db-scraper

# או הרץ את כל המערכת
docker-compose up -d
```

---

## שלב 6: בדוק שהכל עובד ✅

```bash
# סטטוס
docker ps | grep gov2db-scraper

# בריאות
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# לוגים
docker logs -f gov2db-scraper

# בדיקת cron
docker exec gov2db-scraper crontab -l

# timezone
docker exec gov2db-scraper date
# צריך להראות: Asia/Jerusalem

# בדיקת רשת
docker inspect gov2db-scraper | grep -A 10 "Networks"
# צריך להראות את הרשת הנכונה
```

---

## שלב 7: בדיקת sync ידנית (אופציונלי)

```bash
# הרץ sync אחד לבדיקה
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose

# צפה בלוגים
tail -f GOV2DB/logs/daily_sync.log
```

---

## 🎉 סיימת!

הקונטיינר:
- ✅ רץ באופן תמידי
- ✅ מריץ סנכרון ב-02:00 כל לילה
- ✅ מבצע health checks כל שעה
- ✅ שומר logs ב-`GOV2DB/logs/`
- ✅ מחובר לרשת המשותפת שלך

---

## Troubleshooting מהיר

### הקונטיינר לא עולה
```bash
docker logs gov2db-scraper
# בדוק errors
```

### בעיית רשת
```bash
# בדוק שהרשת קיימת
docker network ls

# בדוק שהקונטיינר מחובר
docker network inspect YOUR_NETWORK_NAME
```

### בעיית API keys
```bash
docker exec gov2db-scraper env | grep -E 'OPENAI|SUPABASE'
# וודא שהמפתחות מוגדרים
```

### Timezone לא נכון
```bash
docker exec gov2db-scraper date
# אם לא מראה Asia/Jerusalem:
# בדוק ש-TZ מוגדר ב-docker-compose.yml
```

---

## עזרה נוספת

📖 מדריך מלא: [README-DOCKER.md](README-DOCKER.md)
🔧 Troubleshooting: ראה README-DOCKER.md סעיף Troubleshooting
📝 תבנית Compose: [docker-compose.integration.yml](docker-compose.integration.yml)

---

## פקודות שימושיות

```bash
# הרץ sync ידני
docker exec gov2db-scraper python3 bin/sync.py --unlimited --no-approval --verbose

# כניסה לקונטיינר
docker exec -it gov2db-scraper bash

# health check
docker exec gov2db-scraper /usr/local/bin/healthcheck.sh

# צפייה בלוגים
docker logs -f gov2db-scraper
tail -f GOV2DB/logs/daily_sync.log

# עצירה והסרה
docker-compose stop gov2db-scraper
docker-compose rm -f gov2db-scraper

# rebuild אחרי שינויים
docker-compose build gov2db-scraper
docker-compose up -d gov2db-scraper
```
