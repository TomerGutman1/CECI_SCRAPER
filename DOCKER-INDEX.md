# GOV2DB Docker - מדריך מרכזי

## 🎯 התחלה מהירה

אתה רוצה להתחיל מהר? קרא את זה תחילה.

### המסלול המהיר ⚡

1. **בדיקה ראשונית** (5 דקות):
   ```bash
   cd GOV2DB
   ./docker-quick-start.sh
   ```

2. **אינטגרציה בשרת** (10 דקות):
   - קרא [INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md)
   - מצא את שם הרשת: `docker network ls`
   - העתק מ-`docker-compose.integration.yml` ל-docker-compose המרכזי
   - הרץ: `docker-compose up -d gov2db-scraper`

3. **בדיקה ש-אובד** (2 דקות):
   ```bash
   ./scripts/dashboard.sh
   ```

---

## 📚 מדריכים - מתי לקרוא מה?

### לפי תרחיש

| אני רוצה... | קרא את... | זמן קריאה |
|-------------|-----------|-----------|
| 🚀 **להתחיל מהר** | [INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md) | 5 דק' |
| 🏗️ **להעלות לשרת** | [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) | 15 דק' |
| 🛡️ **להבין fail-safety** | [FAIL-SAFE-GUIDE.md](FAIL-SAFE-GUIDE.md) | 10 דק' |
| 📖 **מידע מלא על Docker** | [README-DOCKER.md](README-DOCKER.md) | 20 דק' |
| 🔧 **לפתור בעיה** | [README-DOCKER.md](README-DOCKER.md) → Troubleshooting | 5 דק' |
| 📊 **להגדיר monitoring** | [scripts/README.md](scripts/README.md) | 10 דק' |

---

## 📁 מבנה הקבצים

```
GOV2DB/
├── 📘 DOCKER-INDEX.md                    ← אתה כאן!
├── 📗 INTEGRATION-GUIDE.md               ⭐ התחל כאן
├── 📙 DEPLOYMENT-GUIDE.md                🚀 מדריך לשרת
├── 📕 FAIL-SAFE-GUIDE.md                 🛡️ אל-כשל
├── 📖 README-DOCKER.md                   📚 מדריך מלא
│
├── 🐳 Dockerfile                         תמונת Docker
├── 🐳 .dockerignore                      אופטימיזציה
├── 🐳 docker-compose.yml                 לפיתוח מקומי
├── 🐳 docker-compose.integration.yml     📋 תבנית לעתק
│
├── 🛠️ docker-quick-start.sh              סקריפט התקנה
│
├── 📁 docker/                            תיקיית Docker
│   ├── docker-entrypoint.sh              Entry point
│   ├── healthcheck.sh                    Health monitoring
│   ├── crontab                           תזמון (02:00 יומי)
│   └── logrotate.conf                    Log rotation
│
└── 📁 scripts/                           כלי monitoring
    ├── README.md                         📚 מדריך scripts
    ├── monitor-health.sh                 ✅ בדיקת תקינות
    ├── dashboard.sh                      📊 תצוגת סטטוס
    └── webhook-example.sh                🔔 דוגמאות alerts
```

---

## 🎓 מסלולי למידה

### מסלול מתחיל (30 דקות)

1. קרא [INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md) - 5 דק'
2. הרץ `./docker-quick-start.sh` - 10 דק'
3. צפה ב-`./scripts/dashboard.sh` - 2 דק'
4. קרא [scripts/README.md](scripts/README.md) - 5 דק'
5. התנסה עם הפקודות - 8 דק'

**בסוף תדע**: איך להריץ GOV2DB ב-Docker ולבדוק שזה עובד

---

### מסלול מתקדם (1 שעה)

1. קרא [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) - 15 דק'
2. העלה לשרת - 20 דק'
3. קרא [FAIL-SAFE-GUIDE.md](FAIL-SAFE-GUIDE.md) - 10 דק'
4. הגדר monitoring (`scripts/monitor-health.sh`) - 10 דק'
5. בדיקות production - 5 דק'

**בסוף תדע**: איך להריץ production-ready עם monitoring מלא

---

### מסלול DevOps (2 שעות)

1. קרא [README-DOCKER.md](README-DOCKER.md) במלואו - 20 דק'
2. קרא [FAIL-SAFE-GUIDE.md](FAIL-SAFE-GUIDE.md) במלואו - 10 דק'
3. העלה לשרת production - 30 דק'
4. הגדר monitoring + alerting - 30 דק'
5. בדיקות stress וכשלים - 20 דק'
6. תעוד ההתקנה שלך - 10 דק'

**בסוף תדע**: איך לנהל את המערכת ברמה enterprise

---

## ⚡ פקודות חיוניות

### בדיקה מהירה (30 שניות)
```bash
docker ps | grep gov2db-scraper
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper
```

### סטטוס מלא (1 דקה)
```bash
./scripts/dashboard.sh
```

### Logs (real-time)
```bash
docker logs -f gov2db-scraper
# או:
tail -f logs/daily_sync.log
```

### בעיות? Troubleshooting
```bash
# בדוק health
./scripts/monitor-health.sh

# debug shell
docker exec -it gov2db-scraper bash

# restart
docker-compose restart gov2db-scraper
```

---

## 🎯 Checklists

### ✅ Checklist: deployment ראשוני

- [ ] קוד מעודכן בשרת (git pull)
- [ ] `.env` קיים עם API keys
- [ ] `logs/` ו-`data/` directories קיימים
- [ ] שם הרשת מזוהה
- [ ] `docker-compose.integration.yml` ערוך עם שם הרשת
- [ ] קטע נוסף ל-docker-compose.yml המרכזי
- [ ] `docker-compose build gov2db-scraper`
- [ ] `docker-compose up -d gov2db-scraper`
- [ ] container רץ: `docker ps`
- [ ] health OK: `docker inspect --format='{{.State.Health.Status}}' gov2db-scraper`
- [ ] cron פעיל: `docker exec gov2db-scraper crontab -l`
- [ ] timezone נכון: `docker exec gov2db-scraper date`
- [ ] sync ידני עובד: `docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1`
- [ ] monitoring הוגדר (אופציונלי)

---

### ✅ Checklist: בדיקות שבועיות

- [ ] Container רץ ו-healthy
- [ ] Sync רץ ב-24h האחרונות
- [ ] אין errors משמעותיים בלוגים
- [ ] Logs לא מלאים (disk usage < 80%)
- [ ] Logrotate עובד (יש .gz files)
- [ ] Health checks עוברים
- [ ] Resources OK (CPU < 80%, Memory < 80%)

```bash
# הרץ את זה פעם בשבוע:
./scripts/monitor-health.sh
./scripts/dashboard.sh
```

---

## 🚨 מה לעשות כש...

### הקונטיינר לא עולה
1. `docker logs gov2db-scraper` - בדוק שגיאות
2. `docker run --rm -it --env-file .env gov2db-scraper bash` - נסה interactively
3. קרא [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) → Troubleshooting

### Sync לא רץ
1. `docker exec gov2db-scraper crontab -l` - בדוק cron
2. `docker exec gov2db-scraper date` - בדוק timezone
3. `docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose` - הרץ ידנית
4. קרא [README-DOCKER.md](README-DOCKER.md) → Troubleshooting

### Health check נכשל
1. `docker exec gov2db-scraper /usr/local/bin/healthcheck.sh` - הרץ ידנית
2. `docker exec gov2db-scraper cat /app/healthcheck/last_success.txt` - בדוק timestamp
3. קרא [FAIL-SAFE-GUIDE.md](FAIL-SAFE-GUIDE.md)

---

## 📊 Monitoring מומלץ

### Setup מינימלי (5 דקות)
```bash
# health check כל 15 דקות
crontab -e
# הוסף:
*/15 * * * * /path/to/GOV2DB/scripts/monitor-health.sh
```

### Setup מומלץ (15 דקות)
```bash
# 1. צור webhook (Slack/Discord/Teams)
# 2. בדוק:
./scripts/monitor-health.sh --webhook "YOUR_WEBHOOK_URL"
# 3. הוסף לcron:
*/15 * * * * /path/to/GOV2DB/scripts/monitor-health.sh --webhook "YOUR_WEBHOOK_URL" >> /var/log/gov2db-monitor.log 2>&1
```

קרא [scripts/README.md](scripts/README.md) לפרטים

---

## 🎓 מושגים

### מה זה...

**Cron**: תזמון משימות. GOV2DB רץ כל יום ב-02:00.

**Health check**: בדיקה אוטומטית כל שעה שהמערכת תקינה.

**Restart policy**: אם הקונטיינר קורס, Docker מריץ אותו מחדש.

**Volume**: תיקייה משותפת בין הקונטיינר והhost (logs/, data/).

**Network**: רשת שמחברת קונטיינרים זה לזה.

**Webhook**: URL שאליו נשלחות התראות (Slack, Discord, etc.).

---

## 🆘 עזרה

### מצאתי bug
1. בדוק [README-DOCKER.md](README-DOCKER.md) → Troubleshooting
2. הרץ `./scripts/monitor-health.sh` לאבחון
3. אסוף logs: `docker logs gov2db-scraper > debug.log`

### שאלות נפוצות
ראה [README-DOCKER.md](README-DOCKER.md) → FAQ section

### רוצה לשנות משהו
- **תזמון**: ערוך `docker/crontab` ובנה מחדש
- **Timezone**: ערוך `docker-compose.yml` → `TZ`
- **Safety mode**: ערוך `docker/crontab` → `--safety-mode`
- **Resources**: ערוך `docker-compose.yml` → `deploy.resources`

---

## 🎉 סיכום

אתה מוכן! יש לך:

✅ **תשתית Docker מלאה** - Dockerfile, compose, scripts
✅ **מדריכים מקיפים** - integration, deployment, fail-safe
✅ **כלי monitoring** - health checks, dashboard, webhooks
✅ **אוטומציה** - daily sync, log rotation, auto-restart

**הצעד הבא שלך**:
1. אם לא התחלת: קרא [INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md)
2. אם התחלת: קרא [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)
3. אם deployment עובד: הגדר monitoring מ-[scripts/README.md](scripts/README.md)

**בהצלחה!** 🚀
