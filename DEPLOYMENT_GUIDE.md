# GOV2DB Algorithm Improvement - Deployment Guide

## 🚨 **לפני שמתחילים - חשוב!**
- **גבה את ה-Database** לפני כל שינוי
- **עצור את כל תהליכי ה-sync** הרצים כרגע
- **בדוק שיש לך גישת admin** ל-Supabase

## 📊 **סטטוס נוכחי - בעיות קריטיות**
- 42% כפילויות (7,230+ רשומות כפולות)
- 50% דיוק בתגיות
- 813 החלטות ללא כותרת
- 472 משרדים מומצאים
- 5-6 קריאות AI לכל החלטה

## 🎯 **תוצאות צפויות אחרי הפריסה**
- <1% כפילויות
- 90%+ דיוק בתגיות
- <50 החלטות ללא כותרת
- 0 משרדים מומצאים
- 1-2 קריאות AI לכל החלטה
- 80% חיסכון בעלויות AI

## 📝 **רשימת קבצים שנוצרו**

### תצורת זיהוי
- `config/tag_detection_profiles.py` - פרופילי זיהוי ל-45 תגיות
- `config/ministry_detection_rules.py` - חוקי זיהוי ל-44 משרדים

### תיקוני Database
- `database/migrations/004_fix_duplicates_and_constraints.sql` - מחיקת כפילויות והוספת constraints
- `bin/verify_db_integrity.py` - כלי אימות תקינות

### עיבוד AI משופר
- `src/gov_scraper/processors/unified_ai.py` - מעבד AI מאוחד
- `src/gov_scraper/processors/ai_prompts.py` - פרומפטים מאוזנים
- `src/gov_scraper/processors/ai_validator.py` - תיקוף סמנטי

### ניטור ו-QA
- `src/gov_scraper/monitoring/quality_monitor.py` - ניטור real-time
- `config/monitoring_alerts.yaml` - הגדרות התראות
- `bin/generate_quality_report.py` - יצירת דוחות איכות

## 🚀 **שלבי הפריסה**

### שלב 1: גיבוי והכנה (30 דקות)
```bash
# 1. עצור את כל התהליכים
make stop-all

# 2. צור גיבוי של ה-Database
python -c "
from src.gov_scraper.db.connector import get_supabase_client
import json
from datetime import datetime

client = get_supabase_client()
backup_file = f'backups/db_backup_{datetime.now().strftime(\"%Y%m%d_%H%M%S\")}.json'

# גיבוי הנתונים
data = client.table('israeli_government_decisions').select('*').execute()
with open(backup_file, 'w', encoding='utf-8') as f:
    json.dump(data.data, f, ensure_ascii=False, indent=2)
print(f'Backup saved to {backup_file}')
"

# 3. בדוק תקינות נוכחית
python bin/verify_db_integrity.py --check-all
```

### שלב 2: תיקון Database (1 שעה)
```bash
# 1. הרץ את ה-migration
# חשוב: הרץ ב-Supabase SQL Editor או דרך CLI
psql $DATABASE_URL < database/migrations/004_fix_duplicates_and_constraints.sql

# 2. אמת את התיקון
python bin/verify_db_integrity.py --check-duplicates --check-constraints

# 3. בדוק שהכפילויות נמחקו
python -c "
from src.gov_scraper.db.dal import get_all_decisions
decisions = get_all_decisions()
keys = [d['decision_key'] for d in decisions]
print(f'Total: {len(keys)}, Unique: {len(set(keys))}, Duplicates: {len(keys) - len(set(keys))}')
"
```

### שלב 3: התקנת מודולי זיהוי (30 דקות)
```bash
# 1. בדוק שהקבצים במקום
ls -la config/tag_detection_profiles.py
ls -la config/ministry_detection_rules.py

# 2. טען והבדיקות
python -c "
from config.tag_detection_profiles import TAG_DETECTION_PROFILES
from config.ministry_detection_rules import MINISTRY_DETECTION_RULES
print(f'Loaded {len(TAG_DETECTION_PROFILES)} tag profiles')
print(f'Loaded {len(MINISTRY_DETECTION_RULES)} ministry rules')
"

# 3. עדכן את ה-imports ב-AI processor
# הוסף בתחילת src/gov_scraper/processors/ai.py:
# from config.tag_detection_profiles import TAG_DETECTION_PROFILES
# from config.ministry_detection_rules import MINISTRY_DETECTION_RULES
```

### שלב 4: הפעלת AI מאוחד (20 דקות)
```bash
# 1. הפעל את ה-unified AI
echo "USE_UNIFIED_AI=true" >> .env

# 2. בדוק ביצועים
python bin/test_unified_ai.py --test-count 10

# 3. השווה תוצאות
python bin/ai_performance_monitor.py --compare-mode
```

### שלב 5: הפעלת ניטור (15 דקות)
```bash
# 1. הגדר התראות
cp config/monitoring_alerts.yaml.example config/monitoring_alerts.yaml
# ערוך את הקובץ עם הגדרות email/webhook שלך

# 2. הפעל את המוניטור
python src/gov_scraper/monitoring/quality_monitor.py --start

# 3. בדוק dashboard
make dashboard-start
# פתח browser ב-http://localhost:8050
```

### שלב 6: בדיקה סופית (30 דקות)
```bash
# 1. הרץ sync בדיקה
make sync-test  # רק החלטה אחת

# 2. בדוק QA מהיר
make simple-qa-run

# 3. צור דוח איכות
python bin/generate_quality_report.py --format html

# 4. אמת metrics
python -c "
from src.gov_scraper.monitoring.quality_monitor import QualityMonitor
monitor = QualityMonitor()
metrics = monitor.get_current_metrics()
print(f'Duplicate rate: {metrics[\"duplicate_rate\"]:.2%}')
print(f'Tag confidence: {metrics[\"avg_tag_confidence\"]:.2%}')
print(f'Missing fields: {metrics[\"missing_field_rate\"]:.2%}')
"
```

## ⚠️ **Rollback - במקרה של בעיה**

### חזרה מהירה
```bash
# 1. עצור את כל התהליכים
make stop-all

# 2. הסר את ה-constraint (אם נוסף)
psql $DATABASE_URL -c "ALTER TABLE israeli_government_decisions DROP CONSTRAINT IF EXISTS unique_decision_key;"

# 3. החזר unified AI
sed -i '' '/USE_UNIFIED_AI/d' .env

# 4. טען גיבוי אם צריך
python -c "
from src.gov_scraper.db.connector import get_supabase_client
import json

client = get_supabase_client()
with open('backups/db_backup_YYYYMMDD_HHMMSS.json', 'r') as f:
    data = json.load(f)
# WARNING: This will overwrite existing data!
# client.table('israeli_government_decisions').delete().neq('id', 0).execute()
# for record in data:
#     client.table('israeli_government_decisions').insert(record).execute()
"
```

## 📈 **ניטור אחרי הפריסה**

### יום ראשון
```bash
# כל שעה
make simple-qa-status
python bin/ai_performance_monitor.py --last-hour

# סוף היום
python bin/generate_quality_report.py --period today
```

### שבוע ראשון
```bash
# יומי
make qa-scan --stratified --sample-size 100
python bin/verify_db_integrity.py --quick-check

# שבועי
python bin/generate_quality_report.py --period week --format html
```

## 🎯 **Success Criteria**

### חייב להתקיים תוך 24 שעות:
- [ ] Duplicate rate < 1%
- [ ] No new hallucinated ministries
- [ ] AI calls reduced by >70%
- [ ] QA runtime < 15 minutes

### חייב להתקיים תוך שבוע:
- [ ] Tag accuracy > 85%
- [ ] Missing titles < 100
- [ ] Operativity balance 60-70%
- [ ] Summary-tag alignment > 70%

## 📞 **תמיכה**

אם יש בעיות:
1. בדוק את הלוגים ב-`logs/`
2. הרץ `python bin/verify_db_integrity.py --diagnose`
3. צור issue ב-GitHub עם output של הבדיקות

## ✅ **Checklist לאחר הפריסה**

- [ ] Database migration הושלם בהצלחה
- [ ] אין כפילויות חדשות נוצרות
- [ ] Unified AI עובד ומחזיר תוצאות
- [ ] Tag profiles נטענים ומזהים נכון
- [ ] Ministry rules מונעים hallucinations
- [ ] Monitoring dashboard מציג נתונים
- [ ] Alerts מגיעים כשיש בעיה
- [ ] QA רץ ב-<15 דקות
- [ ] Quality report נוצר אוטומטית

---

**הערה חשובה**: אל תריץ sync מלא עד שכל הבדיקות עברו בהצלחה!

תחילה בדוק עם `make sync-test` (החלטה אחת), אחר כך `make sync-dev` (5 החלטות), ורק אז `make sync` מלא.