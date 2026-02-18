"""
QA Module - Quality Assurance checks and fixes for government decisions data.

Architecture:
- Scanners: Read-only analysis that detect issues and produce reports
- Fixers: Batch update operations (preview/dry-run/execute) to correct issues
- Inline validation: Lightweight checks for the sync pipeline

Usage:
    python bin/qa.py scan                          # Full scan
    python bin/qa.py scan --check operativity      # Single check
    python bin/qa.py fix operativity preview        # Preview fix
    python bin/qa.py fix operativity execute        # Apply fix
"""

import os
import logging
import json
import random
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

from ..db.connector import get_supabase_client
from ..config import GEMINI_API_KEY, GEMINI_MODEL
from .ai import make_openai_request_with_retry, POLICY_AREAS, GOVERNMENT_BODIES

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QAIssue:
    """Single QA issue found in a record."""
    decision_key: str
    check_name: str
    severity: str  # "high", "medium", "low"
    field: str
    current_value: str
    description: str
    expected_value: str = ""


@dataclass
class QAScanResult:
    """Result of a single QA check."""
    check_name: str
    total_scanned: int
    issues_found: int
    issues: List[QAIssue] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "check_name": self.check_name,
            "total_scanned": self.total_scanned,
            "issues_found": self.issues_found,
            "issue_rate": f"{(self.issues_found / self.total_scanned * 100):.1f}%" if self.total_scanned > 0 else "0%",
            "summary": self.summary,
            "sample_issues": [
                {
                    "decision_key": i.decision_key,
                    "severity": i.severity,
                    "field": i.field,
                    "current_value": i.current_value[:200] if i.current_value else "",
                    "description": i.description
                }
                for i in self.issues[:10]
            ]
        }


@dataclass
class QAReport:
    """Complete QA report across all checks."""
    timestamp: str
    total_records: int
    scan_results: List[QAScanResult] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return sum(r.issues_found for r in self.scan_results)

    @property
    def issues_by_severity(self) -> Dict[str, int]:
        counts = defaultdict(int)
        for result in self.scan_results:
            for issue in result.issues:
                counts[issue.severity] += 1
        return dict(counts)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "total_records": self.total_records,
            "total_issues": self.total_issues,
            "issues_by_severity": self.issues_by_severity,
            "checks": [r.to_dict() for r in self.scan_results]
        }


# =============================================================================
# Keyword Dictionaries
# =============================================================================

# Policy tag → keywords that should appear in decision content.
# IMPORTANT: Keywords must be specific enough to avoid false positives.
# Avoid generic words that appear in many decisions (e.g., "פעולה", "החלטה", "ממשלה").
# Each keyword list should contain terms that are strongly indicative of that domain.
POLICY_TAG_KEYWORDS: Dict[str, List[str]] = {
    "אזרחים ותיקים": [
        "קשיש", "אזרח ותיק", "אזרחים ותיקים", "גמלאי", "פנסיה", "זקנה",
        "סיעוד", "סיעודי", "גיל הפרישה", "גיל הזהב", "בית אבות", "דיור מוגן",
        "קצבת זקנה", "ביטוח לאומי", "תוחלת חיים",
    ],
    "אנרגיה מים ותשתיות": [
        "אנרגיה", "חשמל", "מים", "תשתיות", "גז טבעי", "נפט", "סולארי",
        "מקורות", "חברת חשמל", "מתקן אנרגיה", "התפלה", "ביוב", "תחנת כוח",
        "רשת החשמל", "אנרגיה מתחדשת", "מאגר גז", "צנרת", "לוויתן", "תמר",
        "קידוח", "דלק",
    ],
    "ביטחון פנים": [
        "ביטחון פנים", "כבאות", "שב\"כ", "טרור", "פשיעה", "אכיפה",
        "משמר הגבול", "מג\"ב", "סדר ציבורי", "עבריינות", "פיגוע",
        "חירום אזרחי", "הגנה אזרחית", "פיקוד העורף", "מקלט",
        "ביטחון המדינה", "איום ביטחוני", "שידורים", "מחבל",
        "שירות הביטחון", "גורמי ביטחון", "ביטחון הציבור",
    ],
    "בינוי ושיכון": [
        "בינוי", "שיכון", "בנייה", "דירות", "מגורים", "קבלן", "היתר בנייה",
        "תוכנית בניין עיר", "התחדשות עירונית", "פינוי בינוי", "תמ\"א 38",
        "יחידות דיור", "שכונה", "מבנה", "יישוב", "יישובים", "הקמת",
        "הקמה", "קהילתי", "מתחם",
    ],
    "בריאות ורפואה": [
        "בריאות", "רפואה", "חולה", "בית חולים", "רופא", "תרופ", "קופת חולים",
        "רפואי", "מטופל", "אשפוז", "מרפאה", "בריאות הנפש", "ביטוח בריאות",
        "סל בריאות", "מחלה", "טיפול רפואי", "חיסון", "שירותי בריאות",
        "רוקח", "אחות", "רפואה דחופה",
    ],
    "דיור, נדלן ותכנון": [
        "דיור", "נדל\"ן", "תכנון", "קרקע", "מקרקעין", "דירה",
        "תמ\"א", "ועדת תכנון", "תוכנית מתאר", "רשות מקרקעי ישראל",
        "שוק הדיור", "מחיר למשתכן", "שכר דירה", "רמ\"י", "מינהל מקרקעין",
        "תב\"ע",
    ],
    "דת ומוסדות דת": [
        "דת", "רבנות", "כשרות", "בית כנסת", "דתי", "הלכ",
        "מועצה דתית", "רב ראשי", "בתי דין רבניים", "שבת",
        "מקומות קדושים", "כותל", "נישואין", "גיור", "קבורה",
    ],
    "הגנת הסביבה ואקלים": [
        "סביבה", "אקלים", "זיהום", "מחזור", "פסולת", "אקולוגי",
        "שמורת טבע", "מזהמים", "פליטות", "גזי חממה", "קיימות",
        "ביולוגי", "ים תיכון", "חוף", "נחל", "מיחזור", "ירוק",
        "טבע", "בעלי חיים", "צמחייה",
    ],
    "התייעלות המנגנון הממשלתי": [
        "התייעלות", "מנגנון ממשלתי", "רפורמ", "ייעול", "ממשל דיגיטלי",
        "שיפור שירות", "ביורוקרט", "מנגנון", "ממשל זמין", "שקיפות",
        "מדד שירות", "הפחתת רגולציה", "מיזוג משרדים", "ארגון מחדש",
        "צמצום ממשלה", "ממשל תקין", "חיסכון",
    ],
    "חוץ הסברה ותפוצות": [
        "דיפלומט", "שגרירות", "הסברה", "תפוצות", "יחסי חוץ",
        "קונסוליה", "אמנה בינלאומית", "מדינת חוץ", "ממשלת חוץ",
        "קשרי חוץ", "יהדות התפוצות", "משרד החוץ",
        "בינלאומי", "זירה בינלאומית", "חוצ לארץ", "שגריר",
        "מדינות זרות", "ציר", "נציגות",
    ],
    "חינוך": [
        "חינוך", "תלמיד", "בית ספר", "מורה", "לימוד", "אוניברסיטה",
        "סטודנט", "הוראה", "מכללה", "גן ילדים", "גננת",
        "תוכנית לימודים", "משרד החינוך", "מל\"ג", "בגרות", "מכינה",
        "חינוך מיוחד", "השכלה גבוהה", "אקדמי", "ישיבה",
    ],
    "חקיקה, משפט ורגולציה": [
        "חקיקה", "חוק", "תקנות", "פקודה", "יועץ משפטי", "הצעת חוק",
        "תיקון חוק", "רגולציה", "צו", "דבר חקיקה", "חוק יסוד",
        "פרשנות משפטית", "סעיף", "תקנות שעת חירום",
        "טיוטת חוק", "ועדת חקיקה", "הסמכה", "להסמיך",
        "חוקי", "נוסח משולב", "רשומות",
    ],
    "חקלאות ופיתוח הכפר": [
        "חקלאות", "חקלאי", "חווה", "גידול", "יבול", "משק חקלאי",
        "מושב", "קיבוץ", "גידולים", "בעלי חיים", "וטרינר",
        "מועצה אזורית", "פיתוח הכפר", "אגודה שיתופית", "תוצרת חקלאית",
    ],
    "יוקר המחייה": [
        "יוקר המחייה", "מחירים", "צרכן", "יקר", "מדד המחירים",
        "הגנת הצרכן", "עלויות מחיה", "סל מוצרים", "ייקור",
        "זולות", "פיקוח מחירים", "הוזלה",
    ],
    "מדיני ביטחוני": [
        "צבא", "צה\"ל", "מלחמה", "גבול", "איום", "צבאי", "מודיעין",
        "לוחם", "מערכת ביטחון", "מבצע צבאי", "כוחות הביטחון",
        "שירות צבאי", "מילואים", "אויב", "הגנה", "נשק",
        "חיילים", "קצין", "סייבר", "ריגול",
        # NOT using "ביטחון" alone — could be ביטחון פנים/ביטחון לאומי
    ],
    "מדע, טכנולוגיה וחדשנות": [
        "מדע", "טכנולוגיה", "חדשנות", "מחקר", "סטארטאפ", "הייטק",
        "מעבדה", "מדען", "פטנט", "בינה מלאכותית", "נתונים",
        "רשות החדשנות", "מו\"פ", "אקדמיה",
        # NOT using "פיתוח" alone — too generic
    ],
    "מורשת": [
        "מורשת", "שואה", "זיכרון", "הנצחה", "מוזיאון", "היסטורי",
        "ניצול שואה", "יד ושם", "אתר הנצחה", "מורשת ישראל",
        "ימי זיכרון", "גבורה",
    ],
    "מינהל ציבורי ושירות המדינה": [
        "שירות המדינה", "עובד מדינה", "נציבות שירות המדינה",
        "מינהל ציבורי", "עובדי ציבור", "שירות ציבורי",
        "משרות ממשלתיות", "דרגות שכר", "תנאי שירות",
        "מכרז", "מכרזים", "כוח אדם", "תקן", "תקנים",
        "משרד ממשלתי", "סגן שר", "מנכ\"ל משרד",
        # NOT using "מינהל" alone — appears in many contexts
    ],
    "מינויים": [
        "מינוי", "מונה", "למנות", "מועמד", "מתמנה",
        "כהונה", "תפקיד", "יו\"ר", "מנכ\"ל",
        # Careful: these are inherently generic. The scanner uses these
        # only when the SOLE tag is "מינויים"
    ],
    "מיעוטים": [
        "מיעוט", "ערבי", "דרוזי", "בדואי", "מגזר ערבי",
        "חרדי", "אתיופי", "מגזר", "חברה ערבית",
        "שילוב מיעוטים", "חברה בדואית", "יישוב ערבי",
    ],
    "מנהלת תקומה": [
        "תקומה", "שיקום", "עוטף עזה", "מפונים", "אוכלוסיות מפונות",
        "מנהלת תקומה", "עוטף", "7 באוקטובר", "שבעה באוקטובר",
        "יישובי עוטף", "שיקום הדרום", "שיקום הצפון",
    ],
    "מנהלתי": [
        "מנהלתי", "נוהל", "סדר יום", "פרוטוקול", "הסדר מנהלי",
        "הנחיה מנהלית", "נוהל עבודה",
    ],
    "משבר הקורונה": [
        "קורונה", "covid", "מגפה", "חיסון", "סגר", "תו ירוק",
        "בידוד", "מתווה קורונה", "נגיף", "תחלואה", "מנת דחף",
    ],
    "משטרת ישראל": [
        "משטרה", "משטרת ישראל", "שוטר", "ניידת", "תחנת משטרה",
        "מפכ\"ל", "מפקד משטרה", "שיטור", "ניידות",
    ],
    "משפטים": [
        "בית משפט", "שופט", "עורך דין", "פרקליט", "תביעה",
        "פסק דין", "ערעור", "נאשם", "עתירה", "סנגור",
        "בית המשפט העליון", "פרקליטות", "משפטי", "בית דין",
        "סמכות שיפוט", "הליך משפטי", "חקירה",
    ],
    "תרבות וספורט": [
        "תרבות", "ספורט", "אמנות", "מוזיקה", "תיאטרון", "ספורטאי",
        "אולימפי", "סרט", "קולנוע", "פסטיבל", "הצגה",
        "אולם תרבות", "ספרייה", "מוזיקאי", "אולם ספורט", "ליגה",
        "אצטדיון",
    ],
    "פיתוח הנגב והגליל": [
        "נגב", "גליל", "באר שבע", "פריפריה צפונית", "פריפריה דרומית",
        "ישובי נגב", "ישובי גליל", "פיתוח הנגב", "פיתוח הגליל",
        "עפולה", "צפת", "קריית שמונה", "דימונה", "ערד",
        # NOT using "צפון" or "דרום" alone — too generic geographically
    ],
    "פיתוח הפריפריה ואוכלוסיות": [
        "פריפריה", "אוכלוסיות", "פערים", "שוליים", "יישובים מוחלשים",
        "פיתוח אזורי", "רשויות חלשות", "מצוקה", "שכונות",
        "עדה", "עדות", "חלשה", "מוחלש", "פיזור אוכלוסין",
        "עוצבה", "עוצבת", "אשכול", "רשות בדירוג",
    ],
    "פיתוח כלכלי ותחרות": [
        "פיתוח כלכלי", "תחרות", "שוק", "צמיחה כלכלית", "תוצר",
        "ייצוא", "יבוא", "סחר", "כלכלה", "מונופול", "רשות התחרות",
        "תחרותיות", "משק",
    ],
    "קליטת עלייה": [
        "עלייה", "קליטה", "עולה", "עולים", "קליטת עלייה",
        "סל קליטה", "מרכז קליטה", "עלייה מ", "עולים חדשים",
        "הגירה", "מהגר", "אזרחות", "תושבות", "תעודת עולה",
    ],
    "רגולציה": [
        "רגולציה", "פיקוח", "אסדרה", "רישוי", "רגולטור",
        "רשות רגולטורית", "רישיון", "אסדרה חכמה", "נטל רגולטורי",
    ],
    "רווחה ושירותים חברתיים": [
        "רווחה", "שירותים חברתיים", "סיוע", "סעד", "נזקק", "עוני",
        "עובד סוציאלי", "ילדים בסיכון", "נוער בסיכון", "מעון",
        "אומנה", "שיקום", "קצבה", "נכה", "נכות", "פעוטון",
        "משפחה", "הורה יחיד", "חסר בית", "דיור ציבורי",
        # NOT using "חברתי" alone — appears in many policy contexts
    ],
    "תחבורה ובטיחות בדרכים": [
        "תחבורה", "כביש", "רכבת", "בטיחות בדרכים", "תאונה",
        "נהיגה", "נתיבי ישראל", "רכב", "אוטובוס", "מטרו",
        "רכבת קלה", "כביש מהיר", "צומת", "מסילת ברזל", "נתב\"ג",
        "תחבורה ציבורית", "נתיב", "נתיבים מהירים", "תעופה",
        "שדה תעופה", "שדות תעופה", "תעבורה", "רישיון נהיגה",
    ],
    "תיירות": [
        "תיירות", "תייר", "מלון", "אטרקציה", "תיירותי",
        "תיירות נכנסת", "אכסון", "צימר", "מלונאות", "אתר תיירות",
    ],
    "תעסוקה ועבודה": [
        "תעסוקה", "עבודה", "עובד", "מעסיק", "שכר", "אבטלה",
        "פיטור", "יחסי עבודה", "שוק העבודה", "דמי אבטלה",
        "שכר מינימום", "הסכם קיבוצי", "הסתדרות", "מעסיקים",
        # NOT using "עבודה" in scanner for generic matching — it's too common
        # The scanner requires at least 1 hit from this list
    ],
    "תעשייה מסחר ומשק": [
        "תעשייה", "מסחר", "ייצור", "מפעל", "תעשייתי",
        "אזור תעשייה", "מסחרי", "עסקים קטנים", "יצרן",
        "ייצוא", "תעשיין", "חברות", "תאגיד", "יזמות",
    ],
    "תקציב, פיננסים, ביטוח ומיסוי": [
        "תקציב המדינה", "מיסוי", "ביטוח", "פיננס", "מס הכנסה",
        "מע\"מ", "אגרת", "מס רכישה", "ארנונה", "רשות המיסים",
        "אג\"ח", "בנק ישראל", "ריבית", "אינפלציה", "גירעון",
        "תקציבי", "הכנסות המדינה", "חוק ההסדרים", "חשב כללי",
        "תוספת תקציב", "הקצאת תקציב", "אגף תקציבים", "גמלאות",
        "שכר", "גמלה", "קצבה", "פנסי", "ביטוח לאומי",
        # NOT using "תקציב", "מיליון", "ש\"ח" alone — they appear in almost every decision
    ],
    "תקשורת ומדיה": [
        "תקשורת", "מדיה", "שידור", "עיתונות", "טלוויזיה", "רדיו",
        "רשות השידור", "כאן", "ערוץ", "עיתון", "אמצעי תקשורת",
        "רשת חברתית", "שידורים", "גוף שידור", "תקשורתי",
        "כלי תקשורת", "אלג'זירה",
    ],
    "שוויון חברתי וזכויות אדם": [
        "שוויון", "זכויות אדם", "אפליה", "הפליה", "נגישות",
        "שוויון הזדמנויות", "נשים", "מגדר", "זכויות", "להט\"ב",
        "שוויון מגדרי", "קידום נשים", "אלימות במשפחה", "הטרדה מינית",
        "אנשים עם מוגבלות", "מוגבלות", "שילוב חברתי",
        # NOT using "שוויוני" — too generic
    ],
    "שלטון מקומי": [
        "שלטון מקומי", "עירייה", "רשות מקומית", "מועצה מקומית",
        "מועצה אזורית", "ראש עיר", "ראש רשות", "רשויות מקומיות",
        "ארנונה", "חינוך מוניציפלי",
    ],
    # === תגיות חדשות (פברואר 2026) ===
    "החברה הערבית": [
        "תכנית 922", "תכנית 550", "החלטה 922", "החלטה 550",
        "הרשות לפיתוח כלכלי של המגזר הערבי", "ועדת השרים לענייני האזרחים הערבים",
        "המגזר הערבי", "האוכלוסייה הערבית", "החברה הערבית", "הציבור הערבי",
        "יישובים ערביים", "רשויות ערביות", "הנגב הבדואי", "יישובי הבדואים",
        "שילוב ערבים", "בדואי", "בדואים", "יישובים בדואיים", "כפרים ערביים",
        "אזרחים ערבים", "פיתוח המגזר הערבי", "חינוך ערבי",
        "השתלבות ערבים", "תעסוקת ערבים", "בתי ספר ערביים", "רשות ערבית",
    ],
    "החברה החרדית": [
        "גיוס חרדים", "שירות לאומי חרדי", "לימודי ליבה", "תורתו אומנותו",
        "רשת החינוך החרדי", "מועצת גדולי התורה",
        "המגזר החרדי", "האוכלוסייה החרדית", "החברה החרדית", "הציבור החרדי",
        "שילוב חרדים בשוק העבודה", "תעסוקת חרדים", "השתלבות חרדים", "פטור מגיוס",
        "יישובים חרדיים", "עיר חרדית", "חינוך חרדי", "בית יעקב", "תלמוד תורה",
        "מודיעין עילית", "ביתר עילית",
        "ישיבות גדולות", "כוללים", "אברכים", "לומדי תורה", "בני ישיבות", "אלעד",
        # NOT using: "ישיבה" (=meeting), "שבת", "כשרות", "בני ברק"
    ],
    "נשים ומגדר": [
        "רשות לקידום מעמד האישה", "הטרדה מינית", "אלימות מינית", "תקיפה מינית",
        "אלימות נגד נשים", "שכר שווה לעבודה שווה", "נציבות שוויון הזדמנויות בעבודה",
        "שוויון מגדרי", "שוויון בין המינים", "מעמד האישה", "קידום מעמד האישה",
        "קידום נשים", "ייצוג נשים", "העצמת נשים", "מנהיגות נשית",
        "פערי שכר מגדריים", "זכויות נשים",
        "אפליה מגדרית", "תקרת זכוכית", "אלימות במשפחה", "נשים מוכות",
        "יועצת למעמד האישה",
        "אמהות עובדות", "חופשת לידה", "הארכת חופשת לידה",
        "משפחות חד-הוריות", "הורות יחידנית", "מעונות יום לעובדים", "בריאות האישה",
        # NOT using: "נשים" alone, "הריון" alone, "יולדות"
    ],
    "שיקום הצפון": [
        "מנהלת שיקום הצפון", "תכנית שיקום הצפון", "שיקום הצפון", "תקומת הצפון",
        "קרן לב\"ב", "מפוני הצפון", "מפונים מהצפון", "פינוי הצפון",
        "פינוי יישובי הצפון", "חזרה לצפון", "שיבה לצפון",
        "קו העימות הצפוני", "יישובי קו העימות",
        "פינוי תושבי הצפון", "חזרת תושבי הצפון", "פיצויים למפוני הצפון",
        "דיור למפוני הצפון", "שיקום יישובי הצפון", "בנייה מחדש בצפון",
        "מנגנון שיקום הצפון",
        "גבול לבנון", "איום מלבנון", "רקטות מלבנון", "ירי מלבנון", "חיזבאללה",
        "חזרה ליישובי הצפון",
        # NOT using: individual town names alone
    ],
    "שיקום הדרום": [
        "מנהלת תקומה", "תכנית תקומה", "שיקום הדרום", "תקומת הדרום",
        "7 באוקטובר", "שבעה באוקטובר", "מלחמת חרבות ברזל",
        "עוטף עזה", "מפוני הדרום", "מפונים מהדרום", "פינוי הדרום",
        "חטופים", "בני ערובה", "שחרור חטופים", "משפחות החטופים",
        "יישובי העוטף", "קיבוצי העוטף",
        "נפגעי 7 באוקטובר", "שיקום יישובי העוטף", "בנייה מחדש בעוטף",
        "פיצויים לנפגעי 7 באוקטובר", "מועצה אזורית שער הנגב",
        "מועצה אזורית אשכול", "מנגנון תקומה", "השביעי באוקטובר",
        "קרן האחים", "רשות שיקום", "שיקום קהילתי", "שיקום נפשי לניצולים",
        "אירועי 7 באוקטובר", "מתקפת 7 באוקטובר",
        # NOT using: individual town names alone, "ניצולים" alone, "טראומה" alone
    ],
}

# Operative vs declarative keyword indicators.
# These are used for cross-validation of the operativity field.
# OPERATIVE: action-requiring language (budgets, appointments, directives)
# DECLARATIVE: principled statements, acknowledgements, calls to action without binding
OPERATIVE_KEYWORDS = [
    # Budget/financial actions
    "להקצות", "יוקצ", "מקצה", "הקצאת", "תקציב של", "תוקצב",
    # Directives
    "יפעל", "יבצע", "ימנה", "יפנה", "יורה", "יועבר", "ינקוט",
    "יפעלו", "יבצעו", "ימנו", "ידווח", "ידווחו",
    "מטיל על", "מטילה על", "מחייב", "מחייבת",
    "מופקד", "אחראי", "יישום", "ליישם", "לבצע",
    # Approvals with concrete action
    "מאשרת את", "מאשרת ל", "לאשר",
    # Timeline/deadlines
    "עד ליום", "לוח זמנים", "בתוך", "עד תום", "תוך 30", "תוך 60", "תוך 90",
    # Appointments
    "למנות את", "ימונה", "תמנה",
    # Establishment
    "להקים", "יוקם", "תוקם", "הקמת",
]

DECLARATIVE_KEYWORDS = [
    # Acknowledgements
    "מכירה ב", "רושמת בפניה", "רושמת לפניה",
    "נוטלת לידיעה", "נרשם לפני",
    # Expressions
    "מברכת", "מביעה", "מביעה הערכה", "מביעה שביעות רצון",
    "מביעה תודה", "מביעה דאגה",
    # Declarations
    "עקרונית", "מצהירה", "מודיעה", "מציינת", "לציין",
    # Calls (non-binding)
    "קוראת ל", "קוראת לציבור", "קוראת לממשלה",
    # Principled statements
    "עמדת הממשלה", "עמדה עקרונית", "הצהרת כוונות",
    "מכריזה", "מכירה בחשיבות", "מכירה בצורך",
]

# Policy tag → expected government bodies
TAG_BODY_MAP: Dict[str, List[str]] = {
    "חינוך": ["משרד החינוך"],
    "בריאות ורפואה": ["משרד הבריאות"],
    "מדיני ביטחוני": ["משרד הביטחון", "המשרד לביטחון לאומי"],
    "ביטחון פנים": ["המשרד לביטחון פנים", "המשרד לביטחון לאומי"],
    "תחבורה ובטיחות בדרכים": ["משרד התחבורה והבטיחות בדרכים"],
    "חוץ הסברה ותפוצות": ["משרד החוץ"],
    "תיירות": ["משרד התיירות"],
    "קליטת עלייה": ["משרד העלייה והקליטה"],
    "חקלאות ופיתוח הכפר": ["משרד החקלאות ופיתוח הכפר"],
    "תרבות וספורט": ["משרד התרבות והספורט"],
    "דת ומוסדות דת": ["המשרד לשירותי דת", "משרד הדתות"],
    "הגנת הסביבה ואקלים": ["המשרד להגנת הסביבה"],
    "רווחה ושירותים חברתיים": ["משרד הרווחה"],
    "תעסוקה ועבודה": ["משרד העבודה"],
    "משפטים": ["משרד המשפטים"],
    "חקיקה, משפט ורגולציה": ["משרד המשפטים", "היועץ המשפטי לממשלה"],
    "בינוי ושיכון": ["משרד השיכון והבינוי"],
    "דיור, נדלן ותכנון": ["משרד השיכון והבינוי", "מנהל התכנון"],
    "אנרגיה מים ותשתיות": ["משרד האנרגיה והתשתיות"],
    "תקשורת ומדיה": ["משרד התקשורת"],
    "פיתוח הנגב והגליל": ["המשרד לפיתוח הנגב והגליל", "משרד הנגב, הגליל והחוסן הלאומי"],
    "שוויון חברתי וזכויות אדם": ["המשרד לשוויון חברתי"],
    "מדע, טכנולוגיה וחדשנות": ["משרד החדשנות המדע והטכנולוגיה"],
    "פיתוח כלכלי ותחרות": ["משרד הכלכלה והתעשייה"],
    "תעשייה מסחר ומשק": ["משרד הכלכלה והתעשייה"],
    "תקציב, פיננסים, ביטוח ומיסוי": ["משרד האוצר", "אגף תקציבים"],
    "מינהל ציבורי ושירות המדינה": ["נציבות שירות המדינה"],
    "משטרת ישראל": ["משטרת ישראל"],
    "מורשת": ["משרד ירושלים ומורשת"],
    "רגולציה": ["רשות הרגולציה"],
    # === תגיות חדשות (פברואר 2026) ===
    "החברה הערבית": ["המשרד לשוויון חברתי", "משרד הרווחה", "משרד החינוך"],
    "החברה החרדית": ["המשרד לשירותי דת", "משרד הרווחה", "משרד החינוך"],
    "נשים ומגדר": ["המשרד לשוויון חברתי", "משרד הרווחה", "משרד העבודה"],
    "שיקום הצפון": ["משרד הנגב, הגליל והחוסן הלאומי", "המשרד לפיתוח הנגב והגליל", "משרד הביטחון", "משרד הפנים"],
    "שיקום הדרום": ["משרד הנגב, הגליל והחוסן הלאומי", "המשרד לפיתוח הנגב והגליל", "משרד הביטחון", "רשות החירום הלאומית (רח\"ל)"],
}

# Committee name → expected policy areas
COMMITTEE_TAG_MAP: Dict[str, List[str]] = {
    "ועדת שרים לענייני ביטחון לאומי": ["מדיני ביטחוני", "ביטחון פנים"],
    "ועדת השרים לענייני ביטחון לאומי": ["מדיני ביטחוני", "ביטחון פנים"],
    "ועדת שרים לענייני חקיקה": ["חקיקה, משפט ורגולציה"],
    "ועדת שרים לענייני כלכלה": ["פיתוח כלכלי ותחרות", "תעשייה מסחר ומשק"],
    "ועדת שרים לענייני חברה": ["רווחה ושירותים חברתיים", "שוויון חברתי וזכויות אדם"],
}

# =========================================================================
# NEW TAG WEIGHTED KEYWORDS (February 2026)
# Scoring system for the 5 new tags with weighted keywords
# Score = (matched_weight / total_weight) * 100
# =========================================================================

# Thresholds (absolute score, not percentage)
# Based on weight system: CRITICAL=30, STRONG=15, MODERATE=8, SUPPORTING=3
# Example: 1 CRITICAL + 1 STRONG = 45 points
NEW_TAG_AUTO_THRESHOLD = 60       # >= 60 points → auto-tag (e.g., 2 CRITICAL or 1 CRITICAL + 2 STRONG)
NEW_TAG_AI_THRESHOLD = 35         # 35-59 points → AI verification (raised from 30 to reduce false positives)
NEW_TAG_MANUAL_THRESHOLD = 15     # 15-29 points → manual review (e.g., 1 STRONG or 2 MODERATE)
NEW_TAG_MIN_KEYWORDS = 2          # Minimum keyword matches required

NEW_TAG_KEYWORDS: Dict[str, Dict[str, int]] = {
    "החברה הערבית": {
        # CRITICAL (30) - מזהים חד-משמעיים
        "תכנית 922": 30,
        "תכנית 550": 30,
        "החלטה 922": 30,
        "החלטה 550": 30,
        "הרשות לפיתוח כלכלי של המגזר הערבי": 30,
        "ועדת השרים לענייני האזרחים הערבים": 30,
        # STRONG (15) - ביטויים ספציפיים חזקים
        "המגזר הערבי": 15,
        "האוכלוסייה הערבית": 15,
        "החברה הערבית": 15,
        "הציבור הערבי": 15,
        "יישובים ערביים": 15,
        "רשויות ערביות": 15,
        "הנגב הבדואי": 15,
        "יישובי הבדואים": 15,
        "שילוב ערבים": 15,
        # MODERATE (8) - ביטויים רלוונטיים
        "בדואי": 8,
        "בדואים": 8,
        "יישובים בדואיים": 8,
        "כפרים ערביים": 8,
        "אזרחים ערבים": 8,
        "פיתוח המגזר הערבי": 8,
        "חינוך ערבי": 8,
        # SUPPORTING (3) - מילות תמיכה
        "השתלבות ערבים": 3,
        "תעסוקת ערבים": 3,
        "בתי ספר ערביים": 3,
        "רשות ערבית": 3,
    },
    "החברה החרדית": {
        # CRITICAL (30)
        "גיוס חרדים": 30,
        "שירות לאומי חרדי": 30,
        "לימודי ליבה": 30,
        "תורתו אומנותו": 30,
        "רשת החינוך החרדי": 30,
        "מועצת גדולי התורה": 30,
        # STRONG (15)
        "המגזר החרדי": 15,
        "האוכלוסייה החרדית": 15,
        "החברה החרדית": 15,
        "הציבור החרדי": 15,
        "שילוב חרדים בשוק העבודה": 15,
        "תעסוקת חרדים": 15,
        "השתלבות חרדים": 15,
        "פטור מגיוס": 15,
        # MODERATE (8)
        "יישובים חרדיים": 8,
        "עיר חרדית": 8,
        "חינוך חרדי": 8,
        "בית יעקב": 8,
        "תלמוד תורה": 8,
        "מודיעין עילית": 8,
        "ביתר עילית": 8,
        # SUPPORTING (3)
        "ישיבות גדולות": 3,
        "כוללים": 3,
        "אברכים": 3,
        "לומדי תורה": 3,
        "בני ישיבות": 3,
        "אלעד": 3,
    },
    "נשים ומגדר": {
        # CRITICAL (30)
        "רשות לקידום מעמד האישה": 30,
        "הטרדה מינית": 30,
        "אלימות מינית": 30,
        "תקיפה מינית": 30,
        "אלימות נגד נשים": 30,
        "שכר שווה לעבודה שווה": 30,
        "נציבות שוויון הזדמנויות בעבודה": 30,
        # STRONG (15)
        "שוויון מגדרי": 15,
        "שוויון בין המינים": 15,
        "מעמד האישה": 5,  # Lowered from 15 - appears in ministry names (false positives)
        "קידום מעמד האישה": 5,  # Lowered from 15 - appears in ministry names (false positives)
        "קידום נשים": 15,
        "ייצוג נשים": 15,
        "העצמת נשים": 15,
        "מנהיגות נשית": 15,
        "פערי שכר מגדריים": 15,
        "זכויות נשים": 15,
        # MODERATE (8)
        "אפליה מגדרית": 8,
        "תקרת זכוכית": 8,
        "אלימות במשפחה": 8,
        "נשים מוכות": 8,
        "יועצת למעמד האישה": 8,
        # SUPPORTING (3)
        "אמהות עובדות": 3,
        "חופשת לידה": 3,
        "הארכת חופשת לידה": 3,
        "משפחות חד-הוריות": 3,
        "הורות יחידנית": 3,
        "מעונות יום לעובדים": 3,
        "בריאות האישה": 3,
    },
    "שיקום הצפון": {
        # CRITICAL (30)
        "מנהלת שיקום הצפון": 30,
        "תכנית שיקום הצפון": 30,
        "שיקום הצפון": 30,
        "תקומת הצפון": 30,
        "קרן לב\"ב": 30,
        # STRONG (15)
        "מפוני הצפון": 15,
        "מפונים מהצפון": 15,
        "פינוי הצפון": 15,
        "פינוי יישובי הצפון": 15,
        "חזרה לצפון": 15,
        "שיבה לצפון": 15,
        "קו העימות הצפוני": 15,
        "יישובי קו העימות": 15,
        # MODERATE (8)
        "פינוי תושבי הצפון": 8,
        "חזרת תושבי הצפון": 8,
        "פיצויים למפוני הצפון": 8,
        "דיור למפוני הצפון": 8,
        "שיקום יישובי הצפון": 8,
        "בנייה מחדש בצפון": 8,
        "מנגנון שיקום הצפון": 8,
        # SUPPORTING (3)
        "גבול לבנון": 3,
        "איום מלבנון": 3,
        "רקטות מלבנון": 3,
        "ירי מלבנון": 3,
        "חיזבאללה": 3,
        "חזרה ליישובי הצפון": 3,
    },
    "שיקום הדרום": {
        # CRITICAL (30)
        "מנהלת תקומה": 30,
        "תכנית תקומה": 30,
        "שיקום הדרום": 30,
        "תקומת הדרום": 30,
        "7 באוקטובר": 30,
        "שבעה באוקטובר": 30,
        "מלחמת חרבות ברזל": 30,
        # STRONG (15)
        "עוטף עזה": 15,
        "מפוני הדרום": 15,
        "מפונים מהדרום": 15,
        "פינוי הדרום": 15,
        "חטופים": 15,
        "בני ערובה": 15,
        "שחרור חטופים": 15,
        "משפחות החטופים": 15,
        "יישובי העוטף": 15,
        "קיבוצי העוטף": 15,
        # MODERATE (8)
        "נפגעי 7 באוקטובר": 8,
        "שיקום יישובי העוטף": 8,
        "בנייה מחדש בעוטף": 8,
        "פיצויים לנפגעי 7 באוקטובר": 8,
        "מועצה אזורית שער הנגב": 8,
        "מועצה אזורית אשכול": 8,
        "מנגנון תקומה": 8,
        "השביעי באוקטובר": 8,
        # SUPPORTING (3)
        "קרן האחים": 3,
        "רשות שיקום": 3,
        "שיקום קהילתי": 3,
        "שיקום נפשי לניצולים": 3,
        "אירועי 7 באוקטובר": 3,
        "מתקפת 7 באוקטובר": 3,
    },
}

# Government body abbreviations for text matching.
# Includes minister title patterns ("שר ה...", "שרת ה...") since government
# decisions frequently reference ministers by title rather than ministry name.
BODY_ABBREVIATIONS: Dict[str, List[str]] = {
    "משרד האוצר": ["האוצר", "משרד האוצר", "שר האוצר", "שרת האוצר"],
    "משרד הביטחון": ["הביטחון", "משרד הביטחון", "מש\"הב", "שר הביטחון", "שרת הביטחון"],
    "משרד החינוך": ["החינוך", "משרד החינוך", "שר החינוך", "שרת החינוך"],
    "משרד הבריאות": ["הבריאות", "משרד הבריאות", "שר הבריאות", "שרת הבריאות"],
    "משרד המשפטים": ["המשפטים", "משרד המשפטים", "שר המשפטים", "שרת המשפטים"],
    "משרד החוץ": ["החוץ", "משרד החוץ", "שר החוץ", "שרת החוץ"],
    "משרד הפנים": ["הפנים", "משרד הפנים", "שר הפנים", "שרת הפנים"],
    "משרד התחבורה והבטיחות בדרכים": ["התחבורה", "משרד התחבורה", "שר התחבורה", "שרת התחבורה"],
    "משרד הרווחה": ["הרווחה", "משרד הרווחה", "שר הרווחה", "שרת הרווחה",
        "הרווחה והביטחון החברתי", "משרד הרווחה והשירותים החברתיים", "השירותים החברתיים"],
    "משרד העבודה": ["העבודה", "משרד העבודה", "שר העבודה", "שרת העבודה",
        "משרד העבודה והרווחה", "משרד התעשייה המסחר והתעסוקה"],
    "משרד התיירות": ["התיירות", "משרד התיירות", "שר התיירות", "שרת התיירות"],
    "משרד החקלאות ופיתוח הכפר": ["החקלאות", "משרד החקלאות", "שר החקלאות", "שרת החקלאות"],
    "משרד הכלכלה והתעשייה": ["הכלכלה", "משרד הכלכלה", "שר הכלכלה", "שרת הכלכלה",
        "משרד המסחר והתעשייה", "שר המסחר", "משרד התמ\"ת", "התעשייה"],
    "משרד השיכון והבינוי": ["השיכון", "משרד השיכון", "שר השיכון", "שרת השיכון",
        "הבינוי והשיכון", "שר הבינוי", "משרד הבינוי"],
    "משרד התקשורת": ["התקשורת", "משרד התקשורת", "שר התקשורת", "שרת התקשורת"],
    "משרד התרבות והספורט": ["התרבות", "משרד התרבות", "שר התרבות", "שרת התרבות", "הספורט"],
    "משרד העלייה והקליטה": ["העלייה", "משרד העלייה", "הקליטה", "שר העלייה", "שרת העלייה"],
    "משרד רה\"מ": ["רה\"מ", "ראש הממשלה", "משרד רה\"מ", "ראש-הממשלה"],
    "משרד האנרגיה והתשתיות": ["האנרגיה", "משרד האנרגיה", "שר האנרגיה", "שרת האנרגיה", "התשתיות"],
    "משרד החדשנות המדע והטכנולוגיה": ["החדשנות", "המדע", "משרד המדע", "שר המדע", "שרת המדע", "שר החדשנות"],
    "משרד ירושלים ומורשת": ["ירושלים ומורשת", "שר ירושלים"],
    "המשרד לביטחון לאומי": ["ביטחון לאומי", "השר לביטחון לאומי"],
    "המשרד לביטחון פנים": ["ביטחון פנים", "השר לביטחון פנים"],
    "המשרד להגנת הסביבה": ["הגנת הסביבה", "המשרד להגנת הסביבה", "איכות הסביבה", "השר להגנת הסביבה", "השרה להגנת הסביבה"],
    "המשרד לפיתוח הנגב והגליל": ["הנגב והגליל", "פיתוח הנגב", "השר לפיתוח הנגב"],
    "המשרד לשוויון חברתי": ["שוויון חברתי", "השר לשוויון חברתי", "השרה לשוויון חברתי"],
    "המשרד לשירותי דת": ["שירותי דת", "השר לשירותי דת"],
    "משרד הנגב, הגליל והחוסן הלאומי": ["הנגב", "הגליל", "חוסן לאומי", "שר הנגב"],
    "נציבות שירות המדינה": ["נציבות שירות המדינה", "הנציבות", "נציב שירות המדינה"],
    "רשות הרגולציה": ["רשות הרגולציה", "רגולציה ממשלתית"],
    "אגף תקציבים": ["אגף תקציבים", "אגף התקציבים", "החשב הכללי"],
    "רשות החדשנות": ["רשות החדשנות", "המדען הראשי"],
    "רשות החברות הממשלתיות": ["רשות החברות", "החברות הממשלתיות", "חברה ממשלתית"],
    "רשות החירום הלאומית (רח\"ל)": ["רח\"ל", "רשות החירום", "חירום לאומית"],
    "ועדת השרים": ["ועדת השרים", "ועדת שרים"],
    "ועדת הכספים": ["ועדת הכספים"],
    "היועץ המשפטי לממשלה": ["היועץ המשפטי", "היועמ\"ש", "ייעוץ משפטי"],
    "משטרת ישראל": ["משטרת ישראל", "המשטרה", "משטרה", "המפכ\"ל"],
    "כבאות והצלה": ["כבאות", "כבאי", "כבאות והצלה"],
    "מל\"ג/ות\"ת": ["מל\"ג", "ות\"ת", "מועצה להשכלה גבוהה"],
    "מנהל התכנון": ["מנהל התכנון", "התכנון והבנייה"],
    "מערך הדיגיטל": ["מערך הדיגיטל", "דיגיטל לאומי"],
    "משרד הדיגיטל": ["משרד הדיגיטל", "שר הדיגיטל"],
    "משרד הדתות": ["הדתות", "משרד הדתות", "שר הדתות"],
}

# Location → expected government body
LOCATION_BODY_MAP: Dict[str, List[str]] = {
    "הנגב": ["המשרד לפיתוח הנגב והגליל", "משרד הנגב, הגליל והחוסן הלאומי"],
    "הגליל": ["המשרד לפיתוח הנגב והגליל", "משרד הנגב, הגליל והחוסן הלאומי"],
    "ירושלים": ["משרד ירושלים ומורשת"],
}


# =============================================================================
# Database Fetch (for QA - fetches more fields than tag_migration)
# =============================================================================

def fetch_records_for_qa(
    fields: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    max_records: int = None,
    decision_key_prefix: str = None
) -> List[Dict]:
    """
    Fetch records from database for QA analysis.

    Args:
        fields: List of fields to fetch. None = all QA-relevant fields.
        start_date: Filter by decision_date >= start_date
        end_date: Filter by decision_date <= end_date
        max_records: Maximum records to fetch
        decision_key_prefix: Filter by decision_key prefix

    Returns:
        List of record dictionaries
    """
    if fields is None:
        fields = [
            "decision_key", "decision_date", "decision_number",
            "decision_title", "decision_content", "decision_url", "summary",
            "operativity", "tags_policy_area", "tags_government_body",
            "tags_location", "government_number", "committee"
        ]

    client = get_supabase_client()
    all_records = []
    offset = 0
    chunk_size = 1000
    select_str = ", ".join(fields)

    while True:
        query = client.table("israeli_government_decisions").select(select_str)

        if start_date:
            query = query.gte("decision_date", start_date)
        if end_date:
            query = query.lte("decision_date", end_date)
        if decision_key_prefix:
            query = query.like("decision_key", f"{decision_key_prefix}%")

        query = query.order("decision_date", desc=True)

        if max_records and (offset + chunk_size) > max_records:
            remaining = max_records - offset
            if remaining <= 0:
                break
            query = query.range(offset, offset + remaining - 1)
        else:
            query = query.range(offset, offset + chunk_size - 1)

        response = query.execute()

        if not response.data:
            break

        all_records.extend(response.data)
        offset += chunk_size

        if max_records and len(all_records) >= max_records:
            all_records = all_records[:max_records]
            break

        if len(response.data) < chunk_size:
            break

    logger.info(f"Fetched {len(all_records)} records for QA analysis")
    return all_records


def fetch_records_stratified(
    fields: List[str] = None,
    sample_percent_per_year: float = 20.0,
    start_date: str = None,
    end_date: str = None,
    decision_key_prefix: str = None,
    seed: int = None
) -> List[Dict]:
    """
    Fetch a stratified random sample of records, sampling N% from each year.

    Args:
        fields: List of fields to fetch. None = all QA-relevant fields.
        sample_percent_per_year: Percent of records to sample from each year (default 20%).
        start_date: Filter by decision_date >= start_date
        end_date: Filter by decision_date <= end_date
        decision_key_prefix: Filter by decision_key prefix
        seed: Random seed for reproducible sampling

    Returns:
        List of record dictionaries, sampled proportionally from each year.
    """
    # Fetch all records using existing function (no max_records limit)
    all_records = fetch_records_for_qa(
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        decision_key_prefix=decision_key_prefix,
    )

    if not all_records:
        return []

    # Group by year
    by_year = defaultdict(list)
    for record in all_records:
        year = record.get('decision_date', '')[:4] if record.get('decision_date') else 'unknown'
        by_year[year].append(record)

    # Sample from each year
    rng = random.Random(seed)
    sampled = []
    logger.info(f"Stratified sampling ({sample_percent_per_year}% per year) from {len(all_records)} records across {len(by_year)} years:")
    for year in sorted(by_year.keys()):
        year_records = by_year[year]
        sample_size = max(1, int(len(year_records) * sample_percent_per_year / 100))
        sample_size = min(sample_size, len(year_records))
        year_sample = rng.sample(year_records, sample_size)
        sampled.extend(year_sample)
        logger.info(f"  {year}: {sample_size}/{len(year_records)} records")

    logger.info(f"Total stratified sample: {len(sampled)} records")
    return sampled


# =============================================================================
# Scanners (Read-Only)
# =============================================================================

def check_operativity(records: List[Dict]) -> QAScanResult:
    """Check operativity distribution for bias."""
    result = QAScanResult(check_name="operativity_distribution", total_scanned=0, issues_found=0)

    counts = defaultdict(int)
    for r in records:
        op = r.get("operativity", "")
        if op:
            result.total_scanned += 1
            counts[op] += 1

    total = result.total_scanned
    if total == 0:
        return result

    operative_pct = counts.get("אופרטיבית", 0) / total * 100
    declarative_pct = counts.get("דקלרטיבית", 0) / total * 100

    result.summary = {
        "distribution": dict(counts),
        "operative_pct": f"{operative_pct:.1f}%",
        "declarative_pct": f"{declarative_pct:.1f}%",
        "bias_detected": operative_pct > 80 or declarative_pct > 80
    }

    # Flag if distribution is suspiciously skewed
    if operative_pct > 80:
        result.issues_found = int(counts.get("אופרטיבית", 0) * 0.3)  # Estimate ~30% may be wrong
        result.issues.append(QAIssue(
            decision_key="AGGREGATE",
            check_name="operativity_distribution",
            severity="high",
            field="operativity",
            current_value=f"אופרטיבית: {operative_pct:.1f}%",
            description=f"Operativity heavily skewed: {operative_pct:.1f}% operative. Expected ~50-65%."
        ))

    return result


def check_operativity_vs_content(records: List[Dict]) -> QAScanResult:
    """Cross-check operativity classification against content keywords."""
    result = QAScanResult(check_name="operativity_vs_content", total_scanned=0, issues_found=0)

    for r in records:
        content = r.get("decision_content", "") or ""
        operativity = r.get("operativity", "")
        if not content or not operativity:
            continue

        result.total_scanned += 1

        # Count keyword hits
        op_hits = sum(1 for kw in OPERATIVE_KEYWORDS if kw in content)
        decl_hits = sum(1 for kw in DECLARATIVE_KEYWORDS if kw in content)

        # Determine expected classification based on keywords
        if op_hits == 0 and decl_hits == 0:
            continue  # Not enough signal

        if decl_hits > 0 and op_hits == 0 and operativity == "אופרטיבית":
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="operativity_vs_content",
                severity="high",
                field="operativity",
                current_value=operativity,
                description=f"Classified operative but content has {decl_hits} declarative keywords, 0 operative keywords"
            ))
        elif op_hits > 0 and decl_hits == 0 and operativity == "דקלרטיבית":
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="operativity_vs_content",
                severity="medium",
                field="operativity",
                current_value=operativity,
                description=f"Classified declarative but content has {op_hits} operative keywords, 0 declarative keywords"
            ))

    result.summary = {"mismatches_found": result.issues_found}
    return result


def check_policy_tag_relevance(records: List[Dict]) -> QAScanResult:
    """Check if policy area tags are relevant to decision content using keyword matching.

    Uses Hebrew prefix-aware matching to handle morphological variations
    (e.g., "בביטחון" should match keyword "ביטחון").

    Multi-source matching: checks content, title, and tag name in content
    to reduce false positives from keyword-only matching.
    """
    result = QAScanResult(check_name="policy_tag_relevance", total_scanned=0, issues_found=0)

    low_relevance_count = 0
    no_keywords_count = 0

    for r in records:
        content = r.get("decision_content", "") or ""
        tags_str = r.get("tags_policy_area", "") or ""
        title = r.get("decision_title", "") or ""
        if not content or not tags_str:
            continue

        # Skip bad content (scraping failures, Cloudflare)
        if len(content) < 100 or "Cloudflare" in content or "Just a moment" in content:
            continue

        result.total_scanned += 1
        tags = [t.strip() for t in tags_str.split(";") if t.strip()]

        # Combine content + title for broader matching
        search_text = content + " " + title

        for tag in tags:
            if tag == "שונות" or tag == "מנהלתי" or tag == "מינויים":
                continue  # Skip generic tags

            keywords = POLICY_TAG_KEYWORDS.get(tag, [])
            if not keywords:
                continue

            # First check: does the tag name itself appear in content/title?
            tag_words = [w for w in tag.split() if len(w) > 2 and w not in ("ו", "ה")]
            tag_in_text = any(_word_in_text(tw, search_text) for tw in tag_words)
            if tag_in_text:
                continue  # Tag name found — likely relevant, skip

            # Use prefix-aware matching for Hebrew morphology
            hits = sum(1 for kw in keywords if _word_in_text(kw, search_text))
            score = hits / len(keywords) if keywords else 0

            if hits == 0:
                no_keywords_count += 1
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="policy_tag_relevance",
                    severity="high",
                    field="tags_policy_area",
                    current_value=tag,
                    description=f"Tag '{tag}' has 0 keyword matches in content+title ({len(keywords)} keywords checked)"
                ))
            elif score < 0.15:
                low_relevance_count += 1

    result.summary = {
        "no_keyword_matches": no_keywords_count,
        "low_relevance": low_relevance_count
    }
    return result


def check_policy_fallback_rate(records: List[Dict]) -> QAScanResult:
    """Check rate of 'שונות' (Other) as sole policy tag."""
    result = QAScanResult(check_name="policy_fallback_rate", total_scanned=0, issues_found=0)

    by_year = defaultdict(lambda: {"total": 0, "fallback": 0})

    for r in records:
        tags = r.get("tags_policy_area", "") or ""
        date_str = r.get("decision_date", "") or ""
        if not tags:
            continue

        result.total_scanned += 1
        year = date_str[:4] if len(date_str) >= 4 else "unknown"
        by_year[year]["total"] += 1

        if tags.strip() == "שונות":
            result.issues_found += 1
            by_year[year]["fallback"] += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="policy_fallback_rate",
                severity="medium",
                field="tags_policy_area",
                current_value="שונות",
                description="Only policy tag is 'שונות' (fallback)"
            ))

    result.summary = {
        "fallback_rate": f"{(result.issues_found / result.total_scanned * 100):.1f}%" if result.total_scanned > 0 else "0%",
        "by_year": {
            year: {
                "total": data["total"],
                "fallback": data["fallback"],
                "rate": f"{(data['fallback'] / data['total'] * 100):.1f}%" if data["total"] > 0 else "0%"
            }
            for year, data in sorted(by_year.items(), reverse=True)
        }
    }
    return result


def check_location_hallucination(records: List[Dict]) -> QAScanResult:
    """Check if location tags actually appear in decision content, title, or summary.

    Uses prefix-aware matching and multi-word location handling.
    """
    result = QAScanResult(check_name="location_hallucination", total_scanned=0, issues_found=0)

    for r in records:
        locations_str = r.get("tags_location", "") or ""
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        if not locations_str or not content:
            continue

        result.total_scanned += 1
        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        full_text = content + " " + title + " " + summary

        for loc in locations:
            # For multi-word locations, check if ANY significant word appears
            loc_words = [w for w in loc.split() if len(w) > 2]
            found = _word_in_text(loc, full_text)
            if not found and loc_words:
                # Check individual words of the location
                found = any(_word_in_text(w, full_text) for w in loc_words)
            if not found:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="location_hallucination",
                    severity="medium",
                    field="tags_location",
                    current_value=loc,
                    description=f"Location '{loc}' not found in content/title/summary"
                ))

    result.summary = {"hallucinated_locations": result.issues_found}
    return result


def _is_body_in_text(body: str, full_text: str) -> bool:
    """Check if a government body is mentioned in text using abbreviations, minister titles, and prefix matching."""
    abbreviations = BODY_ABBREVIATIONS.get(body, [body])
    # Use prefix-aware matching for each abbreviation
    if any(_word_in_text(abbr, full_text) for abbr in abbreviations):
        return True

    # Dynamic minister pattern for "משרד ה..." bodies
    if body.startswith("משרד "):
        domain = body[5:]  # "משרד הביטחון" → "הביטחון"
        if _word_in_text(f"שר {domain}", full_text) or _word_in_text(f"שרת {domain}", full_text):
            return True

    # Dynamic pattern for "המשרד ל..." bodies
    if body.startswith("המשרד ל"):
        domain = body[7:]  # "המשרד לביטחון פנים" → "ביטחון פנים"
        if _word_in_text(f"השר ל{domain}", full_text) or _word_in_text(f"השרה ל{domain}", full_text):
            return True

    return False


# Reverse map: body → list of policy tags that imply this body
BODY_TO_TAGS_MAP: Dict[str, List[str]] = {}
for _tag, _bodies in TAG_BODY_MAP.items():
    for _body in _bodies:
        if _body not in BODY_TO_TAGS_MAP:
            BODY_TO_TAGS_MAP[_body] = []
        BODY_TO_TAGS_MAP[_body].append(_tag)


def _is_body_semantically_relevant(body: str, policy_tags: List[str], content: str) -> bool:
    """Check if a government body is semantically relevant based on policy tags and content keywords.

    Returns True if:
    1. The body is expected for one of the record's policy tags (via TAG_BODY_MAP), OR
    2. The content contains keywords from a policy area that implies this body
    """
    # Check 1: body is expected for one of the assigned policy tags
    expected_tags = BODY_TO_TAGS_MAP.get(body, [])
    if expected_tags:
        for tag in policy_tags:
            if tag in expected_tags:
                return True

    # Check 2: content has strong keyword evidence for a policy area that implies this body
    for tag in expected_tags:
        keywords = POLICY_TAG_KEYWORDS.get(tag, [])
        if keywords:
            hits = sum(1 for kw in keywords if _word_in_text(kw, content))
            if hits >= 2:  # At least 2 keyword hits = strong semantic signal
                return True

    return False


def check_government_body_hallucination(records: List[Dict]) -> QAScanResult:
    """Check if government body tags are mentioned in decision content.

    Focuses on records where ALL tagged bodies are missing from text
    (high severity — likely hallucination or bad content). Records where
    only some bodies are missing are flagged as low severity since
    government decisions often reference bodies implicitly.
    """
    result = QAScanResult(check_name="government_body_hallucination", total_scanned=0, issues_found=0)

    all_missing_count = 0
    some_missing_count = 0

    for r in records:
        bodies_str = r.get("tags_government_body", "") or ""
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        if not bodies_str or not content:
            continue

        # Skip garbage content (Cloudflare challenge pages, very short)
        if len(content) < 100 or "Cloudflare" in content or "Just a moment" in content:
            continue

        result.total_scanned += 1
        bodies = [b.strip() for b in bodies_str.split(";") if b.strip()]
        policy_tags_str = r.get("tags_policy_area", "") or ""
        policy_tags = [t.strip() for t in policy_tags_str.split(";") if t.strip()]
        committee = r.get("committee", "") or ""
        full_text = content + " " + title + " " + summary + " " + committee

        missing_bodies = [
            body for body in bodies
            if not _is_body_in_text(body, full_text)
            and not _is_body_semantically_relevant(body, policy_tags, content)
        ]

        if len(missing_bodies) == len(bodies) and len(bodies) > 0:
            # ALL bodies missing — high severity
            all_missing_count += 1
            for body in missing_bodies:
                abbreviations = BODY_ABBREVIATIONS.get(body, [body])
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="government_body_hallucination",
                    severity="high",
                    field="tags_government_body",
                    current_value=body,
                    description=f"ALL bodies missing: '{body}' not in content (checked: {abbreviations})"
                ))
        elif missing_bodies:
            # Some bodies missing — low severity (implicit reference is common)
            some_missing_count += 1
            for body in missing_bodies:
                abbreviations = BODY_ABBREVIATIONS.get(body, [body])
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="government_body_hallucination",
                    severity="low",
                    field="tags_government_body",
                    current_value=body,
                    description=f"Government body '{body}' not in content (checked: {abbreviations})"
                ))

    result.summary = {
        "hallucinated_bodies": result.issues_found,
        "records_all_missing": all_missing_count,
        "records_some_missing": some_missing_count,
    }
    return result


def check_summary_quality(records: List[Dict]) -> QAScanResult:
    """Check summary length and quality."""
    result = QAScanResult(check_name="summary_quality", total_scanned=0, issues_found=0)

    too_short = 0
    too_long = 0
    same_as_title = 0

    for r in records:
        summary = r.get("summary", "") or ""
        title = r.get("decision_title", "") or ""
        if not summary:
            continue

        result.total_scanned += 1

        if len(summary) < 20:
            too_short += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="summary_quality",
                severity="medium",
                field="summary",
                current_value=summary,
                description=f"Summary too short ({len(summary)} chars)"
            ))
        elif len(summary) > 500:
            too_long += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="summary_quality",
                severity="low",
                field="summary",
                current_value=summary[:200] + "...",
                description=f"Summary too long ({len(summary)} chars)"
            ))

        if title and summary.strip() == title.strip():
            same_as_title += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="summary_quality",
                severity="medium",
                field="summary",
                current_value=summary[:200],
                description="Summary identical to title"
            ))

    result.summary = {
        "too_short": too_short,
        "too_long": too_long,
        "same_as_title": same_as_title
    }
    return result


def check_tag_body_consistency(records: List[Dict]) -> QAScanResult:
    """Check consistency between policy area tags and government body tags.

    Only flags records where:
    - The record has a SINGLE policy tag (suggesting a clear domain)
    - The expected government body has no overlap with tagged bodies
    Multi-tag records are inherently cross-ministerial and are expected
    to have bodies from different domains.
    """
    result = QAScanResult(check_name="tag_body_consistency", total_scanned=0, issues_found=0)

    for r in records:
        policy_str = r.get("tags_policy_area", "") or ""
        body_str = r.get("tags_government_body", "") or ""
        if not policy_str or not body_str:
            continue

        result.total_scanned += 1
        policies = [t.strip() for t in policy_str.split(";") if t.strip()]
        bodies = [b.strip() for b in body_str.split(";") if b.strip()]

        # Skip multi-tag records — cross-ministerial decisions are expected
        if len(policies) > 1:
            continue

        for policy in policies:
            expected_bodies = TAG_BODY_MAP.get(policy, [])
            if not expected_bodies:
                continue

            # Check if any expected body is in the tagged bodies (substring match)
            has_match = any(
                eb in bodies or any(eb in b or b in eb for b in bodies)
                for eb in expected_bodies
            )

            # Also check via minister title pattern ("שר ה..." → "משרד ה...")
            if not has_match:
                for eb in expected_bodies:
                    # Extract domain word: "משרד הביטחון" → "הביטחון"
                    if eb.startswith("משרד "):
                        domain = eb[5:]  # remove "משרד "
                        minister_pattern = f"שר {domain}"
                        has_match = any(minister_pattern in b for b in bodies)
                        if has_match:
                            break

            if not has_match and len(bodies) > 0:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="tag_body_consistency",
                    severity="low",
                    field="tags_policy_area + tags_government_body",
                    current_value=f"policy='{policy}', bodies='{body_str}'",
                    description=f"Policy '{policy}' expects bodies {expected_bodies} but got '{body_str}'"
                ))

    result.summary = {"inconsistencies": result.issues_found}
    return result


def check_committee_tag_consistency(records: List[Dict]) -> QAScanResult:
    """Check consistency between committee name and policy area tags."""
    result = QAScanResult(check_name="committee_tag_consistency", total_scanned=0, issues_found=0)

    for r in records:
        committee = r.get("committee", "") or ""
        policy_str = r.get("tags_policy_area", "") or ""
        if not committee or not policy_str:
            continue

        result.total_scanned += 1
        policies = [t.strip() for t in policy_str.split(";") if t.strip()]

        # Find matching committee mapping
        for committee_name, expected_policies in COMMITTEE_TAG_MAP.items():
            if committee_name in committee:
                has_match = any(ep in policies for ep in expected_policies)
                if not has_match:
                    result.issues_found += 1
                    result.issues.append(QAIssue(
                        decision_key=r.get("decision_key", ""),
                        check_name="committee_tag_consistency",
                        severity="low",
                        field="committee + tags_policy_area",
                        current_value=f"committee='{committee}', tags='{policy_str}'",
                        description=f"Committee '{committee_name}' expects policy areas {expected_policies}"
                    ))
                break

    result.summary = {"inconsistencies": result.issues_found}
    return result


def check_summary_vs_tags(records: List[Dict]) -> QAScanResult:
    """Check that summary content reflects assigned policy tags.

    Only flags when the summary is long enough (>60 chars) AND neither
    the tag name nor any domain keyword appears in it. Short summaries
    are inherently too brief to contain domain keywords reliably.
    """
    result = QAScanResult(check_name="summary_vs_tags", total_scanned=0, issues_found=0)

    for r in records:
        summary = (r.get("summary", "") or "")
        tags_str = r.get("tags_policy_area", "") or ""
        if not summary or not tags_str or len(summary) < 60:
            continue

        result.total_scanned += 1
        summary_lower = summary.lower()
        tags = [t.strip() for t in tags_str.split(";") if t.strip()]

        for tag in tags:
            if tag in ("שונות", "מנהלתי", "מינויים"):
                continue

            # First check: does the tag name (or its main word) appear in summary?
            tag_words = [w for w in tag.split() if len(w) > 2 and w not in ("ו", "של", "את")]
            tag_name_found = any(tw in summary for tw in tag_words)
            if tag_name_found:
                continue

            # Second check: do any domain keywords appear?
            keywords = POLICY_TAG_KEYWORDS.get(tag, [])
            if not keywords:
                continue

            hits = sum(1 for kw in keywords if kw in summary_lower)
            if hits == 0:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="summary_vs_tags",
                    severity="low",
                    field="summary + tags_policy_area",
                    current_value=f"tag='{tag}', summary='{summary[:100]}'",
                    description=f"Tag '{tag}' keywords not found in summary"
                ))

    result.summary = {"mismatches": result.issues_found}
    return result


def check_location_vs_body(records: List[Dict]) -> QAScanResult:
    """Check consistency between location tags and government body tags."""
    result = QAScanResult(check_name="location_vs_body", total_scanned=0, issues_found=0)

    for r in records:
        locations_str = r.get("tags_location", "") or ""
        body_str = r.get("tags_government_body", "") or ""
        if not locations_str or not body_str:
            continue

        result.total_scanned += 1
        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        bodies = [b.strip() for b in body_str.split(";") if b.strip()]

        for loc in locations:
            for loc_key, expected_bodies in LOCATION_BODY_MAP.items():
                if loc_key in loc:
                    has_match = any(eb in bodies for eb in expected_bodies)
                    if not has_match:
                        result.issues_found += 1
                        result.issues.append(QAIssue(
                            decision_key=r.get("decision_key", ""),
                            check_name="location_vs_body",
                            severity="low",
                            field="tags_location + tags_government_body",
                            current_value=f"location='{loc}', bodies='{body_str}'",
                            description=f"Location '{loc}' suggests bodies {expected_bodies}"
                        ))

    result.summary = {"inconsistencies": result.issues_found}
    return result


def check_date_vs_government(records: List[Dict]) -> QAScanResult:
    """Check that government number matches the decision date."""
    result = QAScanResult(check_name="date_vs_government", total_scanned=0, issues_found=0)

    # Government 37 started 2022-12-29
    GOV_37_START = "2022-12-29"

    for r in records:
        date_str = r.get("decision_date", "") or ""
        gov_num = r.get("government_number")
        if not date_str or gov_num is None:
            continue

        result.total_scanned += 1

        if str(gov_num) == "37" and date_str < GOV_37_START:
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="date_vs_government",
                severity="high",
                field="government_number + decision_date",
                current_value=f"gov={gov_num}, date={date_str}",
                description=f"Government 37 started {GOV_37_START} but decision dated {date_str}"
            ))

    result.summary = {"mismatches": result.issues_found}
    return result


def _strip_hebrew_prefix(word: str) -> str:
    """Strip common Hebrew prefixes (ב,ל,מ,ה,ו,כ,ש) from a word.

    Supports up to 2 prefix layers (e.g., "ובחינוך" → "בחינוך" → "חינוך").
    Only strips when the remainder is 3+ chars to avoid over-stripping.
    """
    prefixes = "בלמהוכש"
    result = word
    # Strip up to 2 prefix layers
    for _ in range(2):
        if len(result) > 3 and result[0] in prefixes:
            result = result[1:]
        else:
            break
    return result


def _strip_hebrew_suffix(word: str) -> str:
    """Strip common Hebrew suffixes (ים, ות, ן, ית, יים, יות) from a word.

    Only strips when the remainder is 3+ chars.
    """
    # Order matters: longer suffixes first
    suffixes = ["יות", "יים", "ות", "ים", "ית", "ין", "ן"]
    for suffix in suffixes:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def _word_in_text(word: str, text: str) -> bool:
    """Check if a Hebrew word appears in text, accounting for prefix and suffix variations.

    Multi-tier matching:
    1. Exact substring match
    2. Prefix-stripped match (up to 2 layers)
    3. Suffix-stripped match
    4. Both prefix+suffix stripped
    5. Word with common prefixes added
    6. Stem of word with common prefixes in text
    """
    if not word or not text:
        return False

    # 1. Exact match
    if word in text:
        return True

    # 2. Strip prefixes from search word and look in text
    stripped_prefix = _strip_hebrew_prefix(word)
    if stripped_prefix != word and stripped_prefix in text:
        return True

    # 3. Strip suffixes from search word and look in text
    stripped_suffix = _strip_hebrew_suffix(word)
    if stripped_suffix != word and stripped_suffix in text:
        return True

    # 4. Strip both prefix and suffix
    stem = _strip_hebrew_suffix(stripped_prefix)
    if stem != word and stem != stripped_prefix and stem != stripped_suffix and stem in text:
        return True

    # 5. Try adding common prefixes to the word
    for prefix in "בלמהוכש":
        if (prefix + word) in text:
            return True

    # 6. Try adding common prefixes to the stem (prefix-stripped word)
    if stripped_prefix != word:
        for prefix in "בלמהוכש":
            if (prefix + stripped_prefix) in text:
                return True

    return False


def check_title_vs_content(records: List[Dict]) -> QAScanResult:
    """Check that title keywords appear in content.

    Handles Hebrew prefix variations (ב,ל,מ,ה,ו,כ,ש) to avoid
    false positives from morphological differences.
    """
    result = QAScanResult(check_name="title_vs_content", total_scanned=0, issues_found=0)

    stop_words = {"ו", "ה", "של", "את", "על", "עם", "או", "גם", "כל", "לא", "אם", "כי",
                  "זה", "זו", "אל", "בעניין", "בדבר", "לעניין", "החלטה", "הממשלה", "ממשלת",
                  "מספר", "לפי", "תיקון", "חוק", "מיום", "מס'"}

    for r in records:
        title = r.get("decision_title", "") or ""
        content = r.get("decision_content", "") or ""
        if not title or not content or len(title) < 10:
            continue

        # Skip records with bad content (scraping failures, Cloudflare)
        if len(content) < 100 or "Cloudflare" in content or "Just a moment" in content:
            continue

        result.total_scanned += 1

        # Extract meaningful title words (strip prefixes for matching)
        title_words = [w for w in title.split() if len(w) > 2 and w not in stop_words]
        if not title_words:
            continue

        hits = sum(1 for w in title_words if _word_in_text(w, content))
        match_rate = hits / len(title_words) if title_words else 0

        if match_rate < 0.2 and len(title_words) >= 3:
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="title_vs_content",
                severity="medium",
                field="decision_title + decision_content",
                current_value=f"title='{title[:100]}', match_rate={match_rate:.0%}",
                description=f"Only {hits}/{len(title_words)} title words found in content"
            ))

    result.summary = {"mismatches": result.issues_found}
    return result


def check_date_validity(records: List[Dict]) -> QAScanResult:
    """Check decision dates are within valid range."""
    result = QAScanResult(check_name="date_validity", total_scanned=0, issues_found=0)
    today_str = date.today().isoformat()

    for r in records:
        date_str = r.get("decision_date", "") or ""
        if not date_str:
            continue

        result.total_scanned += 1

        if date_str < "1948-01-01" or date_str > today_str:
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="date_validity",
                severity="high",
                field="decision_date",
                current_value=date_str,
                description=f"Date '{date_str}' outside valid range (1948 - today)"
            ))

    result.summary = {"invalid_dates": result.issues_found}
    return result


def check_content_quality(records: List[Dict]) -> QAScanResult:
    """Check content length and quality.

    Detects:
    - Too short content (<100 chars)
    - Navigation/footer text
    - Cloudflare challenge pages (bot protection captured instead of decision)
    """
    result = QAScanResult(check_name="content_quality", total_scanned=0, issues_found=0)

    nav_patterns = ["דלג לתוכן", "כל הזכויות", "תנאי שימוש", "מפת אתר", "צור קשר"]
    cloudflare_patterns = ["Just a moment", "Cloudflare", "Verify you are human", "Ray ID:"]
    too_short = 0
    has_nav = 0
    has_cloudflare = 0

    for r in records:
        content = r.get("decision_content", "") or ""
        if not content:
            continue

        result.total_scanned += 1

        # Check for Cloudflare challenge pages
        if any(p in content for p in cloudflare_patterns):
            has_cloudflare += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="content_quality",
                severity="high",
                field="decision_content",
                current_value=content[:100],
                description="Content is a Cloudflare challenge page — needs re-scraping"
            ))
            continue

        if len(content) < 100:
            too_short += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="content_quality",
                severity="medium",
                field="decision_content",
                current_value=content[:100],
                description=f"Content too short ({len(content)} chars)"
            ))

        for pattern in nav_patterns:
            if pattern in content:
                has_nav += 1
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="content_quality",
                    severity="low",
                    field="decision_content",
                    current_value=content[:100],
                    description=f"Content contains navigation text: '{pattern}'"
                ))
                break

    result.summary = {"too_short": too_short, "has_navigation": has_nav, "cloudflare_pages": has_cloudflare}
    return result


def check_tag_consistency(records: List[Dict]) -> QAScanResult:
    """Verify all tags match authorized lists."""
    result = QAScanResult(check_name="tag_consistency", total_scanned=0, issues_found=0)

    policy_set = set(POLICY_AREAS)
    body_set = set(GOVERNMENT_BODIES)

    unauthorized_policies = defaultdict(int)
    unauthorized_bodies = defaultdict(int)

    for r in records:
        result.total_scanned += 1

        # Check policy tags
        policy_str = r.get("tags_policy_area", "") or ""
        for tag in [t.strip() for t in policy_str.split(";") if t.strip()]:
            if tag not in policy_set:
                unauthorized_policies[tag] += 1
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="tag_consistency",
                    severity="medium",
                    field="tags_policy_area",
                    current_value=tag,
                    description=f"Unauthorized policy tag: '{tag}'"
                ))

        # Check government body tags
        body_str = r.get("tags_government_body", "") or ""
        for body in [b.strip() for b in body_str.split(";") if b.strip()]:
            if body not in body_set:
                unauthorized_bodies[body] += 1
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="tag_consistency",
                    severity="medium",
                    field="tags_government_body",
                    current_value=body,
                    description=f"Unauthorized government body: '{body}'"
                ))

    result.summary = {
        "unauthorized_policy_tags": dict(unauthorized_policies),
        "unauthorized_body_tags": dict(unauthorized_bodies)
    }
    return result


def check_content_completeness(records: List[Dict]) -> QAScanResult:
    """Check if content appears truncated or incomplete."""
    result = QAScanResult(check_name="content_completeness", total_scanned=0, issues_found=0)

    for r in records:
        content = r.get("decision_content", "") or ""
        if not content or len(content) < 50:
            continue

        result.total_scanned += 1

        # Check for truncation markers
        if content.rstrip().endswith("...") or "המשך התוכן" in content:
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="content_completeness",
                severity="medium",
                field="decision_content",
                current_value=content[-100:],
                description="Content appears truncated"
            ))

    result.summary = {"truncated": result.issues_found}
    return result


# =============================================================================
# New Scanners — Default/Fallback Pattern Detection
# =============================================================================

# Known AI fallback body combos (assigned when uncertain)
SUSPICIOUS_BODY_COMBOS = [
    "משרד הרווחה",                                           # sole body — 93% unrelated
    "משרד הרווחה; משרד הבריאות; משרד העבודה",                 # trio — 89% unrelated
    "משרד הרווחה; משרד החינוך; משרד הבריאות",                 # trio — 100% hallucination
]

# Known AI fallback policy tags
SUSPICIOUS_POLICY_TAGS = [
    "תרבות וספורט",  # sole tag — 90% unrelated
]

# Valid operativity values
VALID_OPERATIVITY_VALUES = {"אופרטיבית", "דקלרטיבית", ""}

# Typo → correction mapping for operativity
OPERATIVITY_TYPO_MAP = {
    "דקלרטיווית": "דקלרטיבית",
    "דלקרטיבית": "דקלרטיבית",
    "דקלרתיבית": "דקלרטיבית",
    "דקלרטיווי": "דקלרטיבית",
    "דיקלרטיבית": "דקלרטיבית",
    "דקלארטיבית": "דקלרטיבית",
    "אופריטיבית": "אופרטיבית",
    "אופרייטיבית": "אופרטיבית",
    "אופרנטיבית": "אופרטיבית",
    "אופרטיבי": "אופרטיבית",
    "אופרציה": "אופרטיבית",
}


def check_body_default_patterns(records: List[Dict]) -> QAScanResult:
    """Detect records where AI assigned a known fallback/default government body combo.

    Checks if any of the tagged body keywords actually appear in the decision content.
    If none appear → HIGH severity (likely hallucination/default).
    If some appear → LOW severity (might be partially correct).
    """
    result = QAScanResult(check_name="body_default_patterns", total_scanned=0, issues_found=0)

    high_count = 0
    low_count = 0
    combo_counts = defaultdict(lambda: {"total": 0, "flagged": 0})

    for r in records:
        bodies_str = (r.get("tags_government_body", "") or "").strip()
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""

        if not bodies_str or not content:
            continue

        # Skip garbage content
        if len(content) < 100 or "Cloudflare" in content or "Just a moment" in content:
            continue

        # Check if this record matches any suspicious combo
        if bodies_str not in SUSPICIOUS_BODY_COMBOS:
            continue

        result.total_scanned += 1
        combo_counts[bodies_str]["total"] += 1
        full_text = content + " " + title + " " + summary

        # Check if ANY body keyword appears in content
        bodies = [b.strip() for b in bodies_str.split(";") if b.strip()]
        found_bodies = [body for body in bodies if _is_body_in_text(body, full_text)]

        if not found_bodies:
            # No body keyword found → likely default/hallucination
            high_count += 1
            combo_counts[bodies_str]["flagged"] += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="body_default_patterns",
                severity="high",
                field="tags_government_body",
                current_value=bodies_str,
                description=f"Suspected default body combo — no body keywords found in content"
            ))
        elif len(found_bodies) < len(bodies):
            # Some found, some not → partially correct
            low_count += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="body_default_patterns",
                severity="low",
                field="tags_government_body",
                current_value=bodies_str,
                description=f"Partial match — found {len(found_bodies)}/{len(bodies)} bodies in content"
            ))

    result.summary = {
        "records_with_suspicious_combos": result.total_scanned,
        "high_severity_flagged": high_count,
        "low_severity_partial": low_count,
        "combo_breakdown": {k: v for k, v in combo_counts.items()},
    }
    return result


def check_policy_default_patterns(records: List[Dict]) -> QAScanResult:
    """Detect records where AI assigned a known fallback/default policy tag.

    Checks if any keywords for the suspicious tag appear in content/title.
    If no keyword found → HIGH severity (likely default assignment).
    """
    result = QAScanResult(check_name="policy_default_patterns", total_scanned=0, issues_found=0)

    high_count = 0
    tag_counts = defaultdict(lambda: {"total": 0, "flagged": 0})

    for r in records:
        policy_str = (r.get("tags_policy_area", "") or "").strip()
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""

        if not policy_str or not content:
            continue

        # Skip garbage content
        if len(content) < 100 or "Cloudflare" in content or "Just a moment" in content:
            continue

        # Check if this record has ONLY a suspicious tag (sole tag)
        tags = [t.strip() for t in policy_str.split(";") if t.strip()]
        if len(tags) != 1 or tags[0] not in SUSPICIOUS_POLICY_TAGS:
            continue

        tag = tags[0]
        result.total_scanned += 1
        tag_counts[tag]["total"] += 1

        # Check if any keyword for this tag appears in content/title
        keywords = POLICY_TAG_KEYWORDS.get(tag, [])
        full_text = content + " " + title
        found = any(_word_in_text(kw, full_text) for kw in keywords)

        if not found:
            high_count += 1
            tag_counts[tag]["flagged"] += 1
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="policy_default_patterns",
                severity="high",
                field="tags_policy_area",
                current_value=tag,
                description=f"Suspected default policy tag — no '{tag}' keywords found in content"
            ))

    result.summary = {
        "records_with_suspicious_tags": result.total_scanned,
        "high_severity_flagged": high_count,
        "tag_breakdown": {k: v for k, v in tag_counts.items()},
    }
    return result


def check_operativity_validity(records: List[Dict]) -> QAScanResult:
    """Detect corrupted or invalid operativity values (typos, encoding garbage).

    Valid values are 'אופרטיבית', 'דקלרטיבית', or empty.
    Anything else is flagged with a suggested correction.
    """
    result = QAScanResult(check_name="operativity_validity", total_scanned=0, issues_found=0)

    typo_counts = defaultdict(int)
    garbage_count = 0

    for r in records:
        op = (r.get("operativity", "") or "").strip()
        result.total_scanned += 1

        if op in VALID_OPERATIVITY_VALUES:
            continue

        result.issues_found += 1

        if op in OPERATIVITY_TYPO_MAP:
            correction = OPERATIVITY_TYPO_MAP[op]
            typo_counts[op] += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="operativity_validity",
                severity="high",
                field="operativity",
                current_value=op,
                expected_value=correction,
                description=f"Typo: '{op}' → should be '{correction}'"
            ))
        else:
            # Encoding corruption or unknown value
            garbage_count += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="operativity_validity",
                severity="high",
                field="operativity",
                current_value=repr(op),
                expected_value="",
                description=f"Corrupted/unknown operativity value: {repr(op)}"
            ))

    result.summary = {
        "invalid_values": result.issues_found,
        "known_typos": dict(typo_counts),
        "garbage_values": garbage_count,
    }
    return result


# =============================================================================
# Full Scan
# =============================================================================

# All available checks grouped by category
ALL_CHECKS = {
    # Phase 1 checks
    "operativity": check_operativity,
    "policy-relevance": check_policy_tag_relevance,
    "policy-fallback": check_policy_fallback_rate,
    # Phase 2 checks
    "operativity-vs-content": check_operativity_vs_content,
    "tag-body": check_tag_body_consistency,
    "committee-tag": check_committee_tag_consistency,
    "location-hallucination": check_location_hallucination,
    "government-body-hallucination": check_government_body_hallucination,
    "summary-quality": check_summary_quality,
    # Phase 3 checks
    "summary-vs-tags": check_summary_vs_tags,
    "location-vs-body": check_location_vs_body,
    "date-vs-government": check_date_vs_government,
    "title-vs-content": check_title_vs_content,
    "date-validity": check_date_validity,
    "content-quality": check_content_quality,
    "tag-consistency": check_tag_consistency,
    "content-completeness": check_content_completeness,
    # Phase 4 — Default/fallback pattern detection
    "body-default": check_body_default_patterns,
    "policy-default": check_policy_default_patterns,
    "operativity-validity": check_operativity_validity,
}

CROSS_FIELD_CHECKS = [
    "operativity-vs-content", "tag-body", "committee-tag",
    "summary-vs-tags", "location-vs-body", "date-vs-government", "title-vs-content",
    "body-default", "policy-default",
]


def run_scan(
    records: List[Dict],
    checks: List[str] = None
) -> QAReport:
    """
    Run QA scan on records.

    Args:
        records: List of record dictionaries
        checks: List of check names to run. None = all checks.
                 "cross-field" = all cross-field checks.

    Returns:
        QAReport with results
    """
    report = QAReport(
        timestamp=datetime.now().isoformat(),
        total_records=len(records)
    )

    if checks is None:
        checks_to_run = list(ALL_CHECKS.keys())
    elif checks == ["cross-field"]:
        checks_to_run = CROSS_FIELD_CHECKS
    else:
        checks_to_run = checks

    for check_name in checks_to_run:
        check_fn = ALL_CHECKS.get(check_name)
        if not check_fn:
            logger.warning(f"Unknown check: {check_name}")
            continue

        logger.info(f"Running check: {check_name}")
        scan_result = check_fn(records)
        report.scan_results.append(scan_result)
        logger.info(f"  → {scan_result.issues_found} issues found out of {scan_result.total_scanned} scanned")

    return report


# =============================================================================
# Fixers
# =============================================================================

def fix_operativity(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Re-classify operativity using improved prompt with keyword evidence.

    Args:
        records: Records to fix
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result showing changes)
    """
    result = QAScanResult(check_name="fix_operativity", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        content = r.get("decision_content", "") or ""
        current_op = r.get("operativity", "")
        if not content:
            continue

        result.total_scanned += 1

        # Count keyword evidence
        op_hits = sum(1 for kw in OPERATIVE_KEYWORDS if kw in content)
        decl_hits = sum(1 for kw in DECLARATIVE_KEYWORDS if kw in content)

        keyword_hint = ""
        if op_hits > decl_hits:
            keyword_hint = f"\nרמז: נמצאו {op_hits} ביטויים אופרטיביים ו-{decl_hits} ביטויים דקלרטיביים בטקסט."
        elif decl_hits > op_hits:
            keyword_hint = f"\nרמז: נמצאו {decl_hits} ביטויים דקלרטיביים ו-{op_hits} ביטויים אופרטיביים בטקסט."

        prompt = f"""נא לקבוע את סוג הפעילות של ההחלטה הממשלתית הבאה.
ענה במילה אחת בלבד: "אופרטיבית" או "דקלרטיבית".

הגדרות:
- אופרטיבית: החלטה שמחייבת פעולה מעשית, כמו הקצאת תקציב, מינוי, הקמת גוף, שינוי מדיניות, הוראה לביצוע.
  דוגמאות: "להקצות 50 מיליון ש"ח", "למנות ועדה", "לפעול להקמת...", "מטיל על משרד..."
- דקלרטיבית: החלטה עקרונית, הכרזה, הבעת עמדה, או רישום לפני הממשלה ללא חיוב לפעולה ספציפית.
  דוגמאות: "הממשלה רושמת בפניה", "מכירה בחשיבות", "קוראת לציבור", "מביעה הערכה"
{keyword_hint}

תוכן ההחלטה:
{content[:3000]}

סוג הפעילות:"""

        try:
            ai_result = make_openai_request_with_retry(prompt, max_tokens=50)
            ai_result = ai_result.strip().replace('"', '').replace("'", "")

            new_op = None
            if "אופרטיבית" in ai_result:
                new_op = "אופרטיבית"
            elif "דקלרטיבית" in ai_result:
                new_op = "דקלרטיבית"
            else:
                new_op = "לא ברור"

            if new_op != current_op:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="fix_operativity",
                    severity="high",
                    field="operativity",
                    current_value=current_op,
                    expected_value=new_op,
                    description=f"Changed: '{current_op}' → '{new_op}'"
                ))
                updates.append((r["decision_key"], {"operativity": new_op}))

        except Exception as e:
            logger.error(f"Failed to re-classify {r.get('decision_key')}: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "changes": result.issues_found,
        "change_rate": f"{(result.issues_found / result.total_scanned * 100):.1f}%" if result.total_scanned > 0 else "0%"
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_policy_tags(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Re-tag records that have only 'שונות' or low relevance tags.

    Args:
        records: Records to fix (should be pre-filtered to שונות-only or low-relevance)
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    from .ai import generate_policy_area_tags_strict

    result = QAScanResult(check_name="fix_policy_tags", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        current_tags = r.get("tags_policy_area", "") or ""
        if not content:
            continue

        result.total_scanned += 1

        try:
            new_tags = generate_policy_area_tags_strict(content, title, summary=summary)

            if new_tags and new_tags != current_tags and new_tags != "שונות":
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="fix_policy_tags",
                    severity="medium",
                    field="tags_policy_area",
                    current_value=current_tags,
                    expected_value=new_tags,
                    description=f"Changed: '{current_tags}' → '{new_tags}'"
                ))
                updates.append((r["decision_key"], {"tags_policy_area": new_tags}))

        except Exception as e:
            logger.error(f"Failed to re-tag {r.get('decision_key')}: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "changes": result.issues_found
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_location_tags(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Remove hallucinated location tags (locations not found in content).
    No AI calls needed — pure text filtering.

    Args:
        records: Records to fix
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    result = QAScanResult(check_name="fix_location_tags", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        locations_str = r.get("tags_location", "") or ""
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        if not locations_str or not content:
            continue

        result.total_scanned += 1
        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        full_text = content + " " + title + " " + summary

        def _location_in_text(loc, text):
            """Check if location is in text, handling multi-word locations."""
            if _word_in_text(loc, text):
                return True
            loc_words = [w for w in loc.split() if len(w) > 2]
            if loc_words:
                return any(_word_in_text(w, text) for w in loc_words)
            return False

        valid_locations = [loc for loc in locations if _location_in_text(loc, full_text)]

        if len(valid_locations) < len(locations):
            new_value = ", ".join(valid_locations) if valid_locations else ""
            removed = [loc for loc in locations if loc not in valid_locations]

            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="fix_location_tags",
                severity="medium",
                field="tags_location",
                current_value=locations_str,
                expected_value=new_value,
                description=f"Removed hallucinated locations: {removed}"
            ))
            updates.append((r["decision_key"], {"tags_location": new_value}))

    result.summary = {
        "total_processed": result.total_scanned,
        "cleaned": result.issues_found
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_government_body_tags(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Remove hallucinated government body tags (bodies not mentioned in content).
    Uses abbreviation map for text matching.

    Args:
        records: Records to fix
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    result = QAScanResult(check_name="fix_government_body_tags", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        bodies_str = r.get("tags_government_body", "") or ""
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        committee = r.get("committee", "") or ""
        policy_tags_str = r.get("tags_policy_area", "") or ""
        if not bodies_str or not content:
            continue

        result.total_scanned += 1
        bodies = [b.strip() for b in bodies_str.split(";") if b.strip()]
        policy_tags = [t.strip() for t in policy_tags_str.split(";") if t.strip()]
        full_text = content + " " + title + " " + summary + " " + committee

        valid_bodies = []
        removed_bodies = []
        for body in bodies:
            if _is_body_in_text(body, full_text):
                valid_bodies.append(body)
            elif _is_body_semantically_relevant(body, policy_tags, content):
                # Body not mentioned literally but semantically implied by policy tags/keywords
                valid_bodies.append(body)
            else:
                removed_bodies.append(body)

        if removed_bodies:
            new_value = "; ".join(valid_bodies) if valid_bodies else ""
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=r.get("decision_key", ""),
                check_name="fix_government_body_tags",
                severity="medium",
                field="tags_government_body",
                current_value=bodies_str,
                expected_value=new_value,
                description=f"Removed hallucinated bodies: {removed_bodies}"
            ))
            updates.append((r["decision_key"], {"tags_government_body": new_value}))

    result.summary = {
        "total_processed": result.total_scanned,
        "cleaned": result.issues_found
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_summaries(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Re-generate summaries for flagged records (too short, too long, identical to title).

    Args:
        records: Records to fix (should be pre-filtered to problematic summaries)
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    from .ai import generate_summary

    result = QAScanResult(check_name="fix_summaries", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        current_summary = r.get("summary", "") or ""
        if not content:
            continue

        result.total_scanned += 1

        try:
            new_summary = generate_summary(content, title)

            if new_summary and new_summary != current_summary and 20 <= len(new_summary) <= 500:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="fix_summaries",
                    severity="medium",
                    field="summary",
                    current_value=current_summary[:100],
                    expected_value=new_summary[:100],
                    description=f"Re-generated summary ({len(current_summary)} → {len(new_summary)} chars)"
                ))
                updates.append((r["decision_key"], {"summary": new_summary}))

        except Exception as e:
            logger.error(f"Failed to re-generate summary for {r.get('decision_key')}: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "regenerated": result.issues_found
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


# =============================================================================
# New Fixers — Default/Fallback Pattern Corrections
# =============================================================================

def fix_operativity_typos(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Fix corrupted operativity values using the typo mapping. No AI cost.

    Fixes known typos to correct values. Encoding garbage (non-Hebrew chars,
    mojibake) is cleared to empty string for later AI re-classification.

    Args:
        records: Records to fix
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    result = QAScanResult(check_name="fix_operativity_typos", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        op = (r.get("operativity", "") or "").strip()
        result.total_scanned += 1

        if op in VALID_OPERATIVITY_VALUES:
            continue

        if op in OPERATIVITY_TYPO_MAP:
            new_value = OPERATIVITY_TYPO_MAP[op]
        else:
            # Encoding corruption or garbage → clear for later AI re-classification
            new_value = ""

        result.issues_found += 1
        result.issues.append(QAIssue(
            decision_key=r.get("decision_key", ""),
            check_name="fix_operativity_typos",
            severity="high",
            field="operativity",
            current_value=repr(op),
            expected_value=new_value,
            description=f"Fixed: {repr(op)} → '{new_value}'"
        ))
        updates.append((r["decision_key"], {"operativity": new_value}))

    result.summary = {
        "total_processed": result.total_scanned,
        "fixed": result.issues_found,
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_government_bodies_ai(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    AI re-tag government bodies for records flagged as defaults/hallucinations.

    Uses generate_government_body_tags_validated() to get new tags from content.
    Only updates if new tags differ from current AND are not empty.

    Args:
        records: Records to fix (should be pre-filtered to flagged records)
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    from .ai import generate_government_body_tags_validated

    result = QAScanResult(check_name="fix_government_bodies_ai", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        current_bodies = (r.get("tags_government_body", "") or "").strip()

        if not content or len(content) < 100:
            continue

        # Skip garbage content
        if "Cloudflare" in content or "Just a moment" in content:
            continue

        result.total_scanned += 1

        try:
            new_bodies = generate_government_body_tags_validated(content, title, summary)

            if new_bodies and new_bodies != current_bodies:
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="fix_government_bodies_ai",
                    severity="high",
                    field="tags_government_body",
                    current_value=current_bodies,
                    expected_value=new_bodies,
                    description=f"AI re-tagged: '{current_bodies}' → '{new_bodies}'"
                ))
                updates.append((r["decision_key"], {"tags_government_body": new_bodies}))

        except Exception as e:
            logger.error(f"Failed to re-tag bodies for {r.get('decision_key')}: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "re_tagged": result.issues_found,
        "change_rate": f"{(result.issues_found / result.total_scanned * 100):.1f}%" if result.total_scanned > 0 else "0%"
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_policy_tags_defaults(
    records: List[Dict],
    dry_run: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    AI re-tag policy area for records flagged with a default tag (e.g. "תרבות וספורט").

    Filters to records where the sole policy tag is a known default AND no relevant
    keywords appear in content. Uses generate_policy_area_tags_strict() to get new tags.
    Accepts new tags if different and not "שונות".

    Args:
        records: Records to fix (should be pre-filtered to flagged records)
        dry_run: If True, don't write to DB

    Returns:
        Tuple of (updates list, scan result)
    """
    from .ai import generate_policy_area_tags_strict

    result = QAScanResult(check_name="fix_policy_tags_defaults", total_scanned=0, issues_found=0)
    updates = []

    for r in records:
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        current_tags = (r.get("tags_policy_area", "") or "").strip()

        if not content or len(content) < 100:
            continue

        # Skip garbage content
        if "Cloudflare" in content or "Just a moment" in content:
            continue

        result.total_scanned += 1

        try:
            new_tags = generate_policy_area_tags_strict(content, title, summary)

            # Only accept if different, not empty, and not "שונות"
            if new_tags and new_tags != current_tags and new_tags.strip() != "שונות":
                result.issues_found += 1
                result.issues.append(QAIssue(
                    decision_key=r.get("decision_key", ""),
                    check_name="fix_policy_tags_defaults",
                    severity="high",
                    field="tags_policy_area",
                    current_value=current_tags,
                    expected_value=new_tags,
                    description=f"AI re-tagged: '{current_tags}' → '{new_tags}'"
                ))
                updates.append((r["decision_key"], {"tags_policy_area": new_tags}))

        except Exception as e:
            logger.error(f"Failed to re-tag policy for {r.get('decision_key')}: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "re_tagged": result.issues_found,
        "change_rate": f"{(result.issues_found / result.total_scanned * 100):.1f}%" if result.total_scanned > 0 else "0%"
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["errors"] = len(errors)

    return updates, result


def fix_cloudflare(records: List[Dict], dry_run: bool = True) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """Re-scrape Cloudflare-blocked records and regenerate all AI fields."""
    from ..scrapers.decision import scrape_decision_content_only
    from .ai import process_decision_with_ai

    result = QAScanResult(check_name="fix_cloudflare", total_scanned=0, issues_found=0)
    updates = []
    errors_list = []

    cloudflare_patterns = ["Just a moment", "Cloudflare", "Verify you are human", "Ray ID:"]

    for r in records:
        content = r.get("decision_content", "") or ""
        if not any(p in content for p in cloudflare_patterns):
            continue

        result.total_scanned += 1
        decision_key = r.get("decision_key", "")
        url = r.get("decision_url", "")

        if not url:
            errors_list.append(f"{decision_key}: no URL")
            continue

        if dry_run:
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=decision_key,
                check_name="fix_cloudflare",
                severity="high",
                field="decision_content",
                current_value=content[:80],
                description=f"Would re-scrape from: {url}"
            ))
            updates.append((decision_key, {"decision_content": "[would re-scrape]"}))
            continue

        # Execute: actually re-scrape
        logger.info(f"Re-scraping {decision_key} from {url}")
        new_content = scrape_decision_content_only(url)

        # Validate: not empty, not Cloudflare again, long enough
        if not new_content or len(new_content) < 100:
            errors_list.append(f"{decision_key}: re-scrape returned empty/short content ({len(new_content or '')} chars)")
            continue
        if any(p in new_content for p in cloudflare_patterns):
            errors_list.append(f"{decision_key}: still Cloudflare after re-scrape")
            continue

        # Re-process with AI
        try:
            decision_data = {
                'decision_content': new_content,
                'decision_title': r.get('decision_title', ''),
                'decision_number': r.get('decision_number', ''),
            }
            processed = process_decision_with_ai(decision_data)

            update_fields = {
                'decision_content': new_content,
                'summary': processed.get('summary', ''),
                'operativity': processed.get('operativity', ''),
                'tags_policy_area': processed.get('tags_policy_area', ''),
                'tags_government_body': processed.get('tags_government_body', ''),
                'tags_location': processed.get('tags_location', ''),
            }
            updates.append((decision_key, update_fields))
            result.issues_found += 1
            result.issues.append(QAIssue(
                decision_key=decision_key,
                check_name="fix_cloudflare",
                severity="high",
                field="decision_content",
                current_value=content[:80],
                description=f"Re-scraped: {len(new_content)} chars, AI re-processed"
            ))
            logger.info(f"  {decision_key}: re-scraped {len(new_content)} chars + AI processed")
        except Exception as e:
            errors_list.append(f"{decision_key}: AI processing failed: {e}")
            logger.error(f"  {decision_key}: AI failed: {e}")

    result.summary = {
        "total_processed": result.total_scanned,
        "re_scraped": result.issues_found,
        "errors": len(errors_list),
        "error_details": errors_list[:10],
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, batch_errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["batch_errors"] = len(batch_errors)

    return updates, result


# =============================================================================
# Special Category Tags Fixer
# =============================================================================

def fix_special_category_tags(
    records: List[Dict],
    dry_run: bool = True,
    review_existing: bool = True
) -> Tuple[List[Tuple[str, Dict]], QAScanResult]:
    """
    Add special category tags and optionally review existing policy tags.

    Special category tags:
    - החברה הערבית (Arab society)
    - החברה החרדית (Haredi society)
    - נשים ומגדר (Women & gender)
    - שיקום הצפון (Northern rehabilitation)
    - שיקום הדרום (Southern rehabilitation)

    Args:
        records: Records to process
        dry_run: If True, don't write to DB
        review_existing: If True, also review/correct existing policy tags

    Returns:
        Tuple of (updates list, scan result)
    """
    from .ai import (
        generate_special_category_tags,
        review_and_fix_policy_tags,
        SPECIAL_CATEGORY_TAGS
    )

    result = QAScanResult(
        check_name="fix_special_category_tags",
        total_scanned=0,
        issues_found=0,
        issues=[],
        summary={}
    )

    updates = []
    special_tag_counts = {tag: 0 for tag in SPECIAL_CATEGORY_TAGS}
    tags_fixed_count = 0
    errors_list = []

    for r in records:
        decision_key = r.get("decision_key", "")
        content = r.get("decision_content", "") or ""
        title = r.get("decision_title", "") or ""
        summary = r.get("summary", "") or ""
        current_tags = r.get("tags_policy_area", "") or ""
        decision_date = r.get("decision_date", "") or ""

        # Skip if no content
        if not content or len(content) < 100:
            continue

        result.total_scanned += 1

        try:
            if review_existing:
                # Full review: special tags + existing tag review
                new_tags, changes = review_and_fix_policy_tags(
                    content, title, current_tags, summary, str(decision_date)
                )

                if changes:  # Something changed
                    result.issues_found += 1

                    # Count special tags added
                    for tag in SPECIAL_CATEGORY_TAGS:
                        if tag in new_tags and tag not in current_tags:
                            special_tag_counts[tag] += 1

                    # Check if regular tags were fixed
                    if any("תגיות מדיניות:" in c for c in changes):
                        tags_fixed_count += 1

                    result.issues.append(QAIssue(
                        decision_key=decision_key,
                        check_name="fix_special_category_tags",
                        severity="medium",
                        field="tags_policy_area",
                        current_value=current_tags,
                        expected_value=new_tags,
                        description="; ".join(changes)
                    ))
                    updates.append((decision_key, {"tags_policy_area": new_tags}))
                    logger.info(f"  {decision_key}: {'; '.join(changes)}")

            else:
                # Simple mode: just add special tags
                special_tags = generate_special_category_tags(
                    content, title, summary, str(decision_date)
                )

                if special_tags:
                    # Parse current tags
                    current_list = [t.strip() for t in current_tags.split(';') if t.strip()]

                    # Add new special tags
                    new_special = [t for t in special_tags if t not in current_list]

                    if new_special:
                        result.issues_found += 1
                        new_tags_list = current_list + new_special
                        new_tags = "; ".join(new_tags_list)

                        for tag in new_special:
                            special_tag_counts[tag] += 1

                        result.issues.append(QAIssue(
                            decision_key=decision_key,
                            check_name="fix_special_category_tags",
                            severity="medium",
                            field="tags_policy_area",
                            current_value=current_tags,
                            expected_value=new_tags,
                            description=f"הוספה: {', '.join(new_special)}"
                        ))
                        updates.append((decision_key, {"tags_policy_area": new_tags}))
                        logger.info(f"  {decision_key}: added {new_special}")

        except Exception as e:
            errors_list.append(f"{decision_key}: {e}")
            logger.error(f"  {decision_key}: error: {e}")

    # Extract skipped decision keys from error list for retry later
    skipped_keys = [e.split(":")[0].strip() for e in errors_list if ":" in e]

    # Build summary
    result.summary = {
        "total_processed": result.total_scanned,
        "decisions_updated": result.issues_found,
        "special_tags_added": special_tag_counts,
        "existing_tags_fixed": tags_fixed_count,
        "review_mode": review_existing,
        "errors": len(errors_list),
        "error_details": errors_list[:10],
        "skipped_keys": skipped_keys,  # For completion runs
    }

    if not dry_run and updates:
        from .tag_migration import batch_update_records
        success, batch_errors = batch_update_records(updates)
        result.summary["applied"] = success
        result.summary["batch_errors"] = len(batch_errors)

    return updates, result


# =============================================================================
# All Available Fixers
# =============================================================================

ALL_FIXERS = {
    "operativity": fix_operativity,
    "policy-tags": fix_policy_tags,
    "locations": fix_location_tags,
    "government-bodies": fix_government_body_tags,
    "summaries": fix_summaries,
    "operativity-typos": fix_operativity_typos,
    "government-bodies-ai": fix_government_bodies_ai,
    "policy-tags-defaults": fix_policy_tags_defaults,
    "cloudflare": fix_cloudflare,
    "special-category": fix_special_category_tags,
}


# =============================================================================
# Pipeline Inline Validation
# =============================================================================

def validate_scraped_content(decision_data: Dict) -> Tuple[bool, Optional[str]]:
    """
    Validate scraped content quality BEFORE AI processing.
    Catches garbage content early to avoid wasting AI credits.
    Uses detect_cloudflare_block() from selenium utils for Cloudflare detection.

    Returns:
        (is_valid, error_message) — (True, None) if OK, (False, reason) if bad
    """
    from gov_scraper.utils.selenium import detect_cloudflare_block
    from bs4 import BeautifulSoup

    content = decision_data.get("decision_content", "") or ""

    # Critical: Cloudflare challenge page (shared detection with selenium.py)
    soup = BeautifulSoup(content, 'html.parser')
    block_reason = detect_cloudflare_block(soup)
    if block_reason:
        return (False, f"Cloudflare challenge page detected: {block_reason}")

    # High: Content too short (page probably didn't load)
    if len(content) < 40:
        return (False, f"Content too short ({len(content)} chars, minimum 40)")

    # High: No Hebrew content at all
    if not any('\u0590' <= char <= '\u05FF' for char in content):
        return (False, "No Hebrew content found")

    # Medium: Navigation text captured instead of decision content
    nav_patterns = ["דלג לתוכן האתר", "כל הזכויות שמורות"]
    if any(content.strip().startswith(pattern) for pattern in nav_patterns):
        return (False, "Navigation/footer text captured instead of decision content")

    return (True, None)


def apply_inline_fixes(decision_data: Dict) -> Dict:
    """
    Apply algorithmic fixes to AI-generated fields before database insertion.
    All fixes are $0 cost (no AI calls).

    Fixes:
    1. Operativity typos via OPERATIVITY_TYPO_MAP
    2. Remove locations not found in content text
    3. Remove government bodies not found in content and not semantically relevant
    """
    dec_num = decision_data.get("decision_number", "?")
    content = decision_data.get("decision_content", "") or ""
    title = decision_data.get("decision_title", "") or ""
    summary = decision_data.get("summary", "") or ""
    committee = decision_data.get("committee", "") or ""
    full_text = content + " " + title + " " + summary + " " + committee

    # Fix 1: Operativity typos
    operativity = decision_data.get("operativity", "") or ""
    if operativity and operativity not in VALID_OPERATIVITY_VALUES:
        if operativity in OPERATIVITY_TYPO_MAP:
            new_value = OPERATIVITY_TYPO_MAP[operativity]
            logger.info(f"[{dec_num}] Fixed operativity typo: '{operativity}' -> '{new_value}'")
            decision_data["operativity"] = new_value
        else:
            logger.warning(f"[{dec_num}] Unknown operativity value: '{operativity}' — clearing")
            decision_data["operativity"] = ""

    # Fix 2: Remove locations not found in content
    locations_str = decision_data.get("tags_location", "") or ""
    if locations_str and content:
        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        valid_locations = [loc for loc in locations if _word_in_text(loc, content)]
        if len(valid_locations) < len(locations):
            removed = [loc for loc in locations if loc not in valid_locations]
            logger.info(f"[{dec_num}] Removed hallucinated locations: {removed}")
            decision_data["tags_location"] = ", ".join(valid_locations) if valid_locations else ""

    # Fix 3: Remove government bodies not in text and not semantically relevant
    bodies_str = decision_data.get("tags_government_body", "") or ""
    if bodies_str and content:
        bodies = [b.strip() for b in bodies_str.split(";") if b.strip()]
        policy_tags_str = decision_data.get("tags_policy_area", "") or ""
        policy_tags = [t.strip() for t in policy_tags_str.split(";") if t.strip()]

        valid_bodies = []
        for body in bodies:
            if _is_body_in_text(body, full_text):
                valid_bodies.append(body)
            elif _is_body_semantically_relevant(body, policy_tags, content):
                valid_bodies.append(body)
            else:
                logger.info(f"[{dec_num}] Removed hallucinated body: '{body}'")

        if len(valid_bodies) < len(bodies):
            decision_data["tags_government_body"] = "; ".join(valid_bodies) if valid_bodies else ""

    return decision_data


def validate_decision_inline(decision_data: Dict) -> List[str]:
    """
    Lightweight QA validation for the sync pipeline.
    Returns list of warning strings. Does NOT block insertion.

    Args:
        decision_data: Decision dictionary with all fields

    Returns:
        List of warning messages (empty = all OK)
    """
    warnings = []
    content = (decision_data.get("decision_content", "") or "").lower()

    # Check operativity is not unclear
    if decision_data.get("operativity") == "לא ברור":
        warnings.append("Operativity unclear — needs manual review")

    # Check policy tags are not only שונות
    policy_tags = decision_data.get("tags_policy_area", "")
    if policy_tags and policy_tags.strip() == "שונות":
        warnings.append("Only policy tag is 'שונות' (fallback)")

    # Check policy tag keyword relevance
    if policy_tags and content:
        tags = [t.strip() for t in policy_tags.split(";") if t.strip()]
        for tag in tags:
            if tag in ("שונות", "מנהלתי", "מינויים"):
                continue
            keywords = POLICY_TAG_KEYWORDS.get(tag, [])
            if keywords and not any(kw in content for kw in keywords):
                warnings.append(f"Policy tag '{tag}' has no keyword matches in content")

    # Check location tags appear in content
    locations_str = decision_data.get("tags_location", "")
    if locations_str and content:
        locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        for loc in locations:
            if loc.lower() not in content:
                warnings.append(f"Location '{loc}' not found in content")

    # Check government body tags appear in content
    bodies_str = decision_data.get("tags_government_body", "")
    if bodies_str and content:
        full_text = content + " " + (decision_data.get("decision_title", "") or "").lower()
        bodies = [b.strip() for b in bodies_str.split(";") if b.strip()]
        for body in bodies:
            abbreviations = BODY_ABBREVIATIONS.get(body, [body])
            if not any(abbr.lower() in full_text for abbr in abbreviations):
                warnings.append(f"Government body '{body}' not mentioned in content")

    # Check summary quality
    summary = decision_data.get("summary", "") or ""
    title = decision_data.get("decision_title", "") or ""
    if summary:
        if len(summary) < 20:
            warnings.append(f"Summary too short ({len(summary)} chars)")
        elif len(summary) > 500:
            warnings.append(f"Summary too long ({len(summary)} chars)")
        if title and summary.strip() == title.strip():
            warnings.append("Summary identical to title")

    # Check operative/declarative keyword match
    operativity = decision_data.get("operativity", "")
    if operativity and content:
        op_hits = sum(1 for kw in OPERATIVE_KEYWORDS if kw in content)
        decl_hits = sum(1 for kw in DECLARATIVE_KEYWORDS if kw in content)
        if decl_hits > 0 and op_hits == 0 and operativity == "אופרטיבית":
            warnings.append("Classified operative but content has only declarative keywords")
        elif op_hits > 0 and decl_hits == 0 and operativity == "דקלרטיבית":
            warnings.append("Classified declarative but content has only operative keywords")

    # Check for suspicious body default patterns
    bodies_str = decision_data.get("tags_government_body", "")
    if bodies_str and bodies_str.strip() in SUSPICIOUS_BODY_COMBOS:
        body_has_evidence = False
        for body in bodies_str.split(";"):
            body = body.strip()
            if _is_body_in_text(body, content + " " + (decision_data.get("decision_title", "") or "").lower()):
                body_has_evidence = True
                break
        if not body_has_evidence:
            warnings.append(f"Suspicious body default pattern: '{bodies_str.strip()}'")

    # Check for suspicious policy default patterns
    policy_str = decision_data.get("tags_policy_area", "")
    if policy_str:
        p_tags = [t.strip() for t in policy_str.split(";") if t.strip()]
        if len(p_tags) == 1 and p_tags[0] in SUSPICIOUS_POLICY_TAGS:
            tag_keywords = POLICY_TAG_KEYWORDS.get(p_tags[0], [])
            if tag_keywords and not any(_word_in_text(kw, content) for kw in tag_keywords):
                warnings.append(f"Suspicious policy default tag: '{p_tags[0]}'")

    return warnings


# =============================================================================
# Report Generation
# =============================================================================

def format_report(report: QAReport) -> str:
    """Format QA report for console output."""
    lines = [
        "=" * 60,
        f"QA SCAN REPORT — {report.timestamp}",
        f"Total records: {report.total_records}",
        f"Total issues: {report.total_issues}",
        f"Issues by severity: {report.issues_by_severity}",
        "=" * 60,
    ]

    for scan in report.scan_results:
        lines.append("")
        lines.append(f"--- {scan.check_name} ---")
        lines.append(f"  Scanned: {scan.total_scanned}")
        lines.append(f"  Issues: {scan.issues_found}")
        if scan.summary:
            for key, val in scan.summary.items():
                if isinstance(val, dict):
                    lines.append(f"  {key}:")
                    for k2, v2 in val.items():
                        lines.append(f"    {k2}: {v2}")
                else:
                    lines.append(f"  {key}: {val}")

        # Show sample issues
        if scan.issues[:5]:
            lines.append(f"  Sample issues:")
            for issue in scan.issues[:5]:
                lines.append(f"    [{issue.severity}] {issue.decision_key}: {issue.description}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def export_report_json(report: QAReport, filepath: str):
    """Export QA report as JSON."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info(f"Report exported to {filepath}")
