"""Gemini integration for generating summaries and tags for government decisions."""

from google import genai
from google.genai import types
import json
import logging
import time
import os
from typing import Dict, Optional, List, Set

from ..config import GEMINI_API_KEY, GEMINI_MODEL, MAX_RETRIES, RETRY_DELAY, USE_UNIFIED_AI

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_tag_list(filename: str) -> List[str]:
    """Load tag list from a markdown file in project root."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    filepath = os.path.join(project_root, filename)

    tags = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and headers
                if not line or line.startswith('#') or ':' in line:
                    continue
                tags.append(line)

        logger.info(f"Loaded {len(tags)} tags from {filename}")
    except FileNotFoundError:
        logger.error(f"Tag file not found: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Error loading tags from {filepath}: {e}")
        raise

    return tags


# Load authorized tag lists from files
POLICY_AREAS = _load_tag_list('new_tags.md')
GOVERNMENT_BODIES = _load_tag_list('new_departments.md')

# Add fallback tag if not present
if "שונות" not in POLICY_AREAS:
    POLICY_AREAS.append("שונות")

# Initialize Gemini client - API key is required (validated in config.py)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = "אתה עוזר מקצועי המנתח החלטות ממשלה ישראליות. ענה בעברית בצורה קצרה ומדויקת."


def make_openai_request_with_retry(prompt: str, max_tokens: int = 500) -> str:
    """Make Gemini API request with retry logic. Raises exception if all retries fail."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Making Gemini request (attempt {attempt + 1}/{MAX_RETRIES})")

            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                ),
            )

            if not response.text:
                raise Exception("Gemini returned empty response (possibly blocked by safety filters)")

            result = response.text.strip()
            logger.info(f"Gemini request successful (attempt {attempt + 1})")
            return result

        except Exception as e:
            error_str = str(e)
            logger.warning(f"Gemini request failed (attempt {attempt + 1}): {e}")

            # Check for rate limit error (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Exponential backoff for rate limits: 30s, 60s, 120s, 240s, 480s
                wait_time = min(30 * (2 ** attempt), 480)  # Cap at 8 minutes
                logger.warning(f"Rate limit hit! Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            elif attempt < MAX_RETRIES - 1:
                # Regular linear backoff for other errors
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"All Gemini request attempts failed")
                raise Exception(f"Gemini API request failed after {MAX_RETRIES} attempts: {e}")

    raise Exception(f"Gemini API request failed after {MAX_RETRIES} attempts")


def _get_words(text: str) -> Set[str]:
    """Extract meaningful words (2+ chars, excluding stop words) from text."""
    stop_words = {"ו", "ה", "של", "את", "על", "עם", "או", "גם", "כל", "לא", "אם", "כי", "זה", "זו", "אל"}
    words = set()
    text = text.replace(",", " ").replace(";", " ")
    for word in text.split():
        word = word.strip()
        if len(word) > 2 and word not in stop_words:
            words.add(word)
    return words


def _log_truncation(content: str, limit: int, func_name: str) -> None:
    """Log warning when content is significantly truncated (>30% lost)."""
    if len(content) > limit:
        pct_lost = ((len(content) - limit) / len(content)) * 100
        if pct_lost > 30:
            logger.warning(
                f"{func_name}: {pct_lost:.0f}% content truncated "
                f"({len(content):,}→{limit:,} chars)"
            )


def get_smart_content(content: str, max_length: int = 4000) -> str:
    """
    Extract content intelligently for long decisions.

    For decisions longer than max_length, takes 70% from the beginning
    and 30% from the end to capture both intro and conclusions.

    Args:
        content: Full decision content
        max_length: Maximum output length (default 4000)

    Returns:
        Content string, either full or with middle section removed
    """
    if len(content) <= max_length:
        return content

    # Take beginning and end
    head_size = int(max_length * 0.7)  # 70% from beginning
    tail_size = max_length - head_size  # 30% from end

    return f"{content[:head_size]}\n\n[...תוכן מקוצץ...]\n\n{content[-tail_size:]}"


def _ai_summary_fallback(summary: str, valid_tags: List[str], tag_type: str) -> Optional[str]:
    """AI fallback - analyze summary to find the best matching tag."""
    if not summary:
        return None

    tags_str = " | ".join(valid_tags)
    tag_type_hebrew = "תחום מדיניות" if tag_type == "policy" else "גוף ממשלתי"

    prompt = f"""נתון תקציר של החלטת ממשלה:
"{summary[:1500]}"

בחר את ה{tag_type_hebrew} המתאים ביותר מהרשימה הבאה:
{tags_str}

חשוב:
- החזר רק תג אחד מדויק מהרשימה
- העתק את הטקסט המדויק מהרשימה
- אל תוסיף הסברים

{tag_type_hebrew}:"""

    try:
        result = make_openai_request_with_retry(prompt, max_tokens=100)
        result = result.strip().strip('"').strip("'")

        # Verify result is in valid tags
        if result in valid_tags:
            return result
        else:
            logger.warning(f"AI fallback returned '{result}' which is not in valid tags list")
    except Exception as e:
        logger.warning(f"AI fallback failed: {e}")

    return None


def validate_tag_3_steps(
    tag: str,
    valid_tags: List[str],
    summary: str = None,
    tag_type: str = "policy"
) -> str:
    """
    Validate tag using 3-step algorithm:
    1. Exact match
    2. Word-based Jaccard similarity (>= 50%)
    3. AI fallback (analyze summary)

    Args:
        tag: Tag returned from GPT
        valid_tags: List of authorized tags
        summary: Decision summary (for step 3)
        tag_type: "policy" or "government"

    Returns:
        Validated tag or "שונות" (policy) / "" (government)
    """
    tag = tag.strip()
    if not tag:
        return "שונות" if tag_type == "policy" else ""

    # Step 1: Exact Match
    if tag in valid_tags:
        logger.debug(f"Tag '{tag}' validated: exact match")
        return tag

    # Step 2: Word Overlap (Jaccard >= 50%)
    tag_words = _get_words(tag)
    if len(tag_words) >= 2:
        best_match = None
        best_score = 0.5  # Minimum 50%

        for valid_tag in valid_tags:
            valid_words = _get_words(valid_tag)
            if not valid_words:
                continue

            intersection = len(tag_words & valid_words)
            union = len(tag_words | valid_words)
            score = intersection / union if union > 0 else 0

            if score > best_score:
                best_score = score
                best_match = valid_tag

        if best_match:
            logger.info(f"Tag '{tag}' → '{best_match}' (word overlap: {best_score:.2f})")
            return best_match

    # Step 3: AI Fallback (analyze summary)
    if summary:
        logger.info(f"Tag '{tag}' failed fuzzy match, trying AI fallback...")
        ai_match = _ai_summary_fallback(summary, valid_tags, tag_type)
        if ai_match:
            logger.info(f"Tag '{tag}' → '{ai_match}' (AI summary fallback)")
            return ai_match

    # Failed all steps
    logger.warning(f"Tag '{tag}' failed all validation steps")
    return "שונות" if tag_type == "policy" else ""


def generate_summary(decision_content: str, decision_title: str) -> str:
    """Generate a concise summary of the decision.

    Note: Full content is passed to Gemini (no truncation).
    Gemini 2.0 Flash supports 1M tokens - max decision is ~15K tokens.
    """
    prompt = f"""
נא לסכם את ההחלטה הממשלתית הבאה במשפט או שניים קצרים ומדויקים:

כותרת: {decision_title}

תוכן ההחלטה:
{decision_content}

סיכום:"""

    return make_openai_request_with_retry(prompt, max_tokens=200)


def generate_operativity(decision_content: str) -> str:
    """Determine the operational status of the decision."""
    prompt = f"""נא לקבוע את סוג הפעילות של ההחלטה הממשלתית הבאה.
ענה במילה אחת בלבד: "אופרטיבית" או "דקלרטיבית".

הגדרות:
- אופרטיבית: החלטה שמחייבת פעולה מעשית עם השפעה תקציבית, מדינית, או מבצעית.
  דוגמאות אופרטיביות:
  1. "להקצות 50 מיליון ש"ח לפיתוח תשתיות" - הקצאת תקציב
  2. "מטיל על משרד הבריאות לגבש תוכנית" - הוראת ביצוע
  3. "לאשר את ההסכם הקיבוצי עם ההסתדרות" - אישור הסכם מחייב
  4. "לשנות את כללי הרגולציה בתחום הבנקאות" - שינוי מדיניות
  5. "להגדיל את מספר המלגות ל-500 בשנה" - שינוי כמותי מחייב

- דקלרטיבית: החלטה פורמלית, הכרזה, הבעת עמדה, מינוי, הקמת ועדה לבחינה, או רישום.
  דוגמאות דקלרטיביות:
  1. "למנות את ד"ר שרה כהן למנהלת המחלקה" - מינוי לתפקיד (פעולה רישומית)
  2. "הממשלה רושמת בפניה את חשיבות החינוך" - רישום
  3. "להקים ועדה לבחינת הנושא" - הקמת ועדה (אינה יוצרת שינוי מעשי)
  4. "הממשלה מביעה הערכה לפעילות הארגונים" - הבעת עמדה
  5. "הממשלה מכירה בחשיבות שיתוף הציבור" - הכרה עקרונית

שים לב: מינויים לתפקידים והקמת ועדות לבחינה הן פעולות פורמליות/רישומיות ולכן דקלרטיביות.

תוכן ההחלטה:
{decision_content}

סוג הפעילות:"""

    result = make_openai_request_with_retry(prompt, max_tokens=50)

    # Clean and validate the response
    if result:
        result = result.strip().replace('"', '').replace("'", "")
        if "אופרטיבית" in result:
            return "אופרטיבית"
        elif "דקלרטיבית" in result:
            return "דקלרטיבית"

    # Flag as unclear instead of defaulting to operative
    logger.warning("Operativity classification unclear — flagging as 'לא ברור'")
    return "לא ברור"


def generate_policy_area_tags_strict(
    decision_content: str,
    decision_title: str,
    summary: str = None
) -> str:
    """
    Generate policy area tags with validation against new_tags.md.

    Args:
        decision_content: Full decision text
        decision_title: Decision title
        summary: Decision summary (used for validation fallback)

    Returns:
        Semicolon-separated tags (1-3 tags)
    """
    # Create improved prompt with full authorized list
    tags_str = " | ".join(POLICY_AREAS)

    prompt = f"""אתה מסווג החלטות ממשלה לפי תחומי מדיניות.

תחומי המדיניות המורשים:
{tags_str}

נא לסווג את ההחלטה הבאה:

כותרת: {decision_title}
תוכן: {decision_content}

הנחיות:
- בחר 1-3 תחומים מהרשימה למעלה
- העדף תג אחד אם אפשרי
- השתמש ב-2-3 תגים רק אם ההחלטה מכסה מספר תחומים באופן שווה
- העתק את הטקסט המדויק מהרשימה
- הפרד תגים ב-;

תחומי מדיניות:"""

    result = make_openai_request_with_retry(prompt, max_tokens=200)

    if not result:
        return "שונות"

    # Clean response
    result = result.strip().replace('"', '').replace("'", "")

    # Validate each tag using 3-step validation
    tags = [t.strip() for t in result.split(';') if t.strip()]
    validated_tags = []

    for tag in tags:
        validated = validate_tag_3_steps(tag, POLICY_AREAS, summary, "policy")
        if validated and validated not in validated_tags:
            validated_tags.append(validated)

    # If all failed
    if not validated_tags:
        return "שונות"

    # Limit to 3 tags
    return "; ".join(validated_tags[:3])


def generate_government_body_tags(decision_content: str, decision_title: str) -> str:
    """Generate government body tags (legacy - no validation)."""
    prompt = f"""
נא לזהות את הגופים הממשלתיים הרלוונטיים להחלטה הבאה.
רשום עד 5 גופים, מופרדים בפסיק.

דוגמאות לגופים: הממשלה, הכנסת, בית המשפט העליון, משרד החינוך, משרד הביטחון, משרד האוצר, משרד הבריאות, משרד החוץ, צה"ל, משטרת ישראל, ועדת השרים, ועדת הכנסת.

כותרת: {decision_title}
תוכן: {decision_content}

גופים ממשלתיים:"""

    return make_openai_request_with_retry(prompt, max_tokens=150)


def generate_government_body_tags_validated(
    decision_content: str,
    decision_title: str,
    summary: str = None
) -> str:
    """
    Generate government body tags with validation against new_departments.md.

    Args:
        decision_content: Full decision text
        decision_title: Decision title
        summary: Decision summary (used for validation fallback)

    Returns:
        Semicolon-separated tags (1-3 tags) or empty string
    """
    # Create prompt with full authorized list
    bodies_str = " | ".join(GOVERNMENT_BODIES)

    prompt = f"""אתה מזהה גופים ממשלתיים הרלוונטיים להחלטת ממשלה.

גופים ממשלתיים מורשים:
{bodies_str}

נא לזהות את הגופים הרלוונטיים להחלטה הבאה:

כותרת: {decision_title}
תוכן: {decision_content}

הנחיות:
- בחר 1-3 גופים מהרשימה למעלה
- בחר רק גופים שמוזכרים במפורש בהחלטה
- העתק את השם המדויק מהרשימה
- הפרד גופים ב-;

גופים ממשלתיים:"""

    result = make_openai_request_with_retry(prompt, max_tokens=150)

    if not result:
        return ""

    # Clean response
    result = result.strip().replace('"', '').replace("'", "")

    # Validate each body using 3-step validation
    bodies = [b.strip() for b in result.split(';') if b.strip()]
    validated_bodies = []

    for body in bodies:
        validated = validate_tag_3_steps(body, GOVERNMENT_BODIES, summary, "government")
        if validated and validated not in validated_bodies:
            validated_bodies.append(validated)

    # Limit to 3 bodies
    if not validated_bodies:
        return ""

    return "; ".join(validated_bodies[:3])


# Special category tags for cross-cutting policy areas
SPECIAL_CATEGORY_TAGS = [
    "החברה הערבית",
    "החברה החרדית",
    "נשים ומגדר",
    "שיקום הצפון",
    "שיקום הדרום",
]


def generate_special_category_tags(
    decision_content: str,
    decision_title: str,
    summary: str = None,
    decision_date: str = None
) -> List[str]:
    """
    Identify special category tags using AI analysis.

    These are cross-cutting tags that identify decisions related to:
    - Arab society (החברה הערבית)
    - Haredi society (החברה החרדית)
    - Women & gender (נשים ומגדר)
    - Northern rehabilitation (שיקום הצפון) - post-2023-24 war
    - Southern rehabilitation (שיקום הדרום) - post-October 7

    Args:
        decision_content: Full decision text
        decision_title: Decision title
        summary: Optional summary
        decision_date: Optional date for context (YYYY-MM-DD)

    Returns:
        List of applicable special category tags (0-3)
    """
    # Build date context if available
    date_context = ""
    if decision_date:
        date_context = f"תאריך ההחלטה: {decision_date}\n"

    prompt = f"""אתה מסווג החלטות ממשלה ישראליות לקטגוריות מיוחדות.

הקטגוריות המיוחדות הן:
1. החברה הערבית - החלטות הנוגעות לאוכלוסייה הערבית בישראל, המגזר הערבי, הבדואים, יישובים ערביים, תוכניות כמו 922/550, שילוב ערבים בתעסוקה, חינוך ערבי
2. החברה החרדית - החלטות הנוגעות לאוכלוסייה החרדית, גיוס חרדים, לימודי ליבה, שילוב חרדים בתעסוקה, ישיבות, כוללים
3. נשים ומגדר - החלטות הנוגעות לשוויון מגדרי, קידום נשים, הטרדה מינית, זכויות נשים, ייצוג נשים, אלימות במשפחה, נשות הליבה
4. שיקום הצפון - החלטות הנוגעות לשיקום יישובי צפון הארץ לאחר מלחמת 2023-24, מפוני הצפון, הגליל, קריית שמונה, מטולה, יישובי הספר הצפוניים
5. שיקום הדרום - החלטות הנוגעות לשיקום יישובי עוטף עזה לאחר 7 באוקטובר 2023, מנהלת תקומה, החטופים, שדרות, אשקלון, נתיבות, כפר עזה, בארי, רעים

{date_context}כותרת: {decision_title}
תוכן: {decision_content}
{f'תקציר: {summary}' if summary else ''}

הנחיות חשובות:
- בחר רק קטגוריות שרלוונטיות בבירור להחלטה
- אם ההחלטה נוגעת בנושא רק באופן שולי, אל תסווג
- שיקום הצפון/דרום רלוונטי בעיקר להחלטות מאוקטובר 2023 ואילך
- החזר JSON בפורמט: {{"tags": ["קטגוריה1", "קטגוריה2"]}}
- אם אין קטגוריה מתאימה, החזר: {{"tags": []}}

תשובה (JSON בלבד):"""

    try:
        result = make_openai_request_with_retry(prompt, max_tokens=100)
        result = result.strip()

        # Parse JSON response - clean up if needed
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
            result = result.strip()

        parsed = json.loads(result)
        tags = parsed.get("tags", [])

        # Validate against authorized list
        validated = [t for t in tags if t in SPECIAL_CATEGORY_TAGS]

        if validated:
            logger.info(f"Special category tags identified: {validated}")

        return validated[:3]  # Max 3 tags

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response for special tags: {result}")
        # Try to extract tags manually
        extracted = []
        for tag in SPECIAL_CATEGORY_TAGS:
            if tag in result:
                extracted.append(tag)
        return extracted[:3]

    except Exception as e:
        logger.error(f"Error generating special category tags: {e}")
        return []


def review_and_fix_policy_tags(
    decision_content: str,
    decision_title: str,
    current_tags: str,
    summary: str = None,
    decision_date: str = None
) -> tuple:
    """
    Review existing policy tags and add special category tags if relevant.

    This function:
    1. Identifies special category tags that should be added
    2. Reviews existing policy tags for relevance
    3. Returns corrected tags and a change log

    Args:
        decision_content: Full decision text
        decision_title: Decision title
        current_tags: Current semicolon-separated policy tags
        summary: Optional summary
        decision_date: Optional date (YYYY-MM-DD)

    Returns:
        Tuple of (new_tags_string, changes_list)
        - new_tags_string: Updated semicolon-separated tags
        - changes_list: List of changes made (for audit trail)
    """
    changes = []

    # Parse current tags
    current_tag_list = [t.strip() for t in current_tags.split(';') if t.strip()]

    # Check which special tags are already present
    existing_special = [t for t in current_tag_list if t in SPECIAL_CATEGORY_TAGS]
    existing_regular = [t for t in current_tag_list if t not in SPECIAL_CATEGORY_TAGS]

    # Build prompt for comprehensive review
    tags_str = " | ".join(POLICY_AREAS)
    special_tags_str = " | ".join(SPECIAL_CATEGORY_TAGS)

    date_context = f"תאריך ההחלטה: {decision_date}\n" if decision_date else ""

    prompt = f"""אתה בודק ומשפר תיוג של החלטות ממשלה ישראליות.

משימה כפולה:
1. זהה אם ההחלטה רלוונטית לאחת מ-5 הקטגוריות המיוחדות
2. בדוק אם התגיות הקיימות מתאימות - אם לא, תקן

קטגוריות מיוחדות (הוסף אם רלוונטי):
{special_tags_str}

הסברים לקטגוריות מיוחדות:
- החברה הערבית: אוכלוסייה ערבית, מגזר ערבי, בדואים, תכניות 922/550
- החברה החרדית: אוכלוסייה חרדית, גיוס חרדים, לימודי ליבה, תעסוקה
- נשים ומגדר: שוויון מגדרי, קידום נשים, הטרדה מינית
- שיקום הצפון: שיקום יישובי צפון לאחר מלחמת 2023-24
- שיקום הדרום: שיקום עוטף עזה לאחר 7 באוקטובר, מנהלת תקומה

תגיות קיימות: {current_tags}
{date_context}כותרת: {decision_title}
{f'תקציר: {summary}' if summary else ''}
תוכן: {decision_content[:2500]}

תחומי מדיניות מורשים (לתיקון תגיות):
{tags_str}

הנחיות:
1. החזר JSON עם שני שדות:
   - special_tags: רשימת קטגוריות מיוחדות להוספה (או רשימה ריקה)
   - fixed_tags: תגיות מדיניות מתוקנות (או null אם אין שינוי)
2. הוסף קטגוריה מיוחדת רק אם רלוונטית בבירור
3. תקן תגיות רק אם ברור שהן שגויות (למשל "שונות" כאשר יש תג ספציפי יותר)
4. שמור על מקסימום 3 תגיות מדיניות רגילות

פורמט תשובה (JSON בלבד):
{{"special_tags": ["קטגוריה"], "fixed_tags": "תג1; תג2" או null}}

תשובה:"""

    try:
        result = make_openai_request_with_retry(prompt, max_tokens=200)
        result = result.strip()

        # Parse JSON response - clean up if needed
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
            result = result.strip()

        parsed = json.loads(result)

        # Process special tags
        new_special_tags = parsed.get("special_tags", [])
        validated_special = [t for t in new_special_tags if t in SPECIAL_CATEGORY_TAGS]

        # Process fixed tags
        fixed_tags_str = parsed.get("fixed_tags")

        # Build final tag list
        if fixed_tags_str and fixed_tags_str != "null":
            # AI suggested changes to regular tags
            fixed_tag_list = [t.strip() for t in fixed_tags_str.split(';') if t.strip()]
            # Validate against authorized list
            validated_fixed = []
            for tag in fixed_tag_list:
                validated = validate_tag_3_steps(tag, POLICY_AREAS, summary, "policy")
                if validated and validated not in validated_fixed:
                    validated_fixed.append(validated)
            final_regular = validated_fixed[:3]

            if set(final_regular) != set(existing_regular):
                changes.append(f"תגיות מדיניות: {'; '.join(existing_regular)} → {'; '.join(final_regular)}")
        else:
            # Keep existing regular tags
            final_regular = existing_regular

        # Add new special tags
        for tag in validated_special:
            if tag not in existing_special:
                changes.append(f"הוספה: {tag}")

        # Combine all tags
        all_special = list(set(existing_special + validated_special))
        final_tags = final_regular + all_special

        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in final_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        new_tags_str = "; ".join(unique_tags)

        return new_tags_str, changes

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response for tag review: {result}")
        # Fall back to just adding special tags if detected in text
        special_only = generate_special_category_tags(
            decision_content, decision_title, summary, decision_date
        )
        if special_only:
            for tag in special_only:
                if tag not in current_tag_list:
                    changes.append(f"הוספה: {tag}")
            new_tags = current_tag_list + [t for t in special_only if t not in current_tag_list]
            return "; ".join(new_tags), changes
        return current_tags, []

    except Exception as e:
        logger.error(f"Error reviewing tags: {e}")
        return current_tags, []


def generate_location_tags(decision_content: str, decision_title: str) -> str:
    """Generate geographic location tags - returns empty string if no locations found."""
    prompt = f"""
נא לזהות מקומות גיאוגרפיים שמוזכרים במפורש בטקסט ההחלטה הבאה.
חשוב: רק אם יש מקומות שמוזכרים ישירות בטקסט - רשום אותם מופרדים בפסיק.
אם אין מקומות ספציפיים המוזכרים בטקסט, השב "אין".
חשוב: אל תכתוב "ריק", "לא מוזכר", או הסברים אחרים - רק "אין" או שמות המקומות.

דוגמאות למקומות שיכולים להיות מוזכרים: ירושלים, תל אביב, חיפה, באר שבע, הגליל, הנגב, יהודה ושומרון, עזה, גולן, צפון, דרום, מרכז.

כותרת: {decision_title}
תוכן: {decision_content}

מקומות גיאוגרפיים (אם מוזכרים):"""
    
    result = make_openai_request_with_retry(prompt, max_tokens=150)
    
    if result:
        # Clean the result and check if it contains actual location names
        result = result.strip()
        
        # If the result contains common non-location phrases, ignore it
        non_location_phrases = [
            "אין מקומות", "לא מוזכר", "לא נמצא", "ללא מיקום", "ללא מקום", 
            "לא ספציפי", "כללי", "לא נמצאו", "אין", "ללא", "לא", "ריק",
            "empty", "none", "null", "לא קיים", "לא זמין"
        ]
        
        for phrase in non_location_phrases:
            if phrase in result:
                return ""
        
        # If result is very short and doesn't look like place names, ignore it
        if len(result) < 3:
            return ""
        
        # Clean up common AI response patterns
        result = result.replace("מקומות גיאוגרפיים:", "").strip()
        result = result.replace("מיקומים:", "").strip()
        
        # If after cleaning there's nothing meaningful left, return empty
        if not result or result.isspace():
            return ""
        
        return result
    
    return ""


def process_decision_with_ai(decision_data: Dict[str, str], use_unified: bool = None) -> Dict[str, str]:
    """
    Process a decision with AI to generate all required fields.

    NEW: Now uses unified AI processing by default (1-2 API calls vs 5-6).
    Falls back to individual calls if unified processing fails.

    Args:
        decision_data: Dictionary containing basic decision data
        use_unified: Whether to use new unified processing (default: from config)

    Returns:
        Updated dictionary with AI-generated fields

    Raises:
        ValueError: If decision content is missing
        Exception: If AI processing fails
    """
    logger.info(f"Processing decision {decision_data.get('decision_number', 'unknown')} with AI")

    decision_content = decision_data.get('decision_content', '')
    decision_title = decision_data.get('decision_title', '')
    decision_date = decision_data.get('decision_date', '')

    if not decision_content:
        raise ValueError(f"Decision {decision_data.get('decision_number', 'unknown')} has no content")

    # Use config default if not specified
    if use_unified is None:
        use_unified = USE_UNIFIED_AI

    if use_unified:
        try:
            # NEW UNIFIED PROCESSING (1 API call)
            from .unified_ai import create_unified_processor

            processor = create_unified_processor(POLICY_AREAS, GOVERNMENT_BODIES)
            result = processor.process_decision_unified(
                decision_content, decision_title, decision_date
            )

            # Convert unified result to legacy format
            policy_areas_str = "; ".join(result.policy_areas) if result.policy_areas else "שונות"
            government_bodies_str = "; ".join(result.government_bodies) if result.government_bodies else ""
            locations_str = ", ".join(result.locations) if result.locations else ""

            # Include special categories in policy areas if found
            all_policy_tags = result.policy_areas + result.special_categories
            policy_areas_str = "; ".join(all_policy_tags[:4]) if all_policy_tags else "שונות"  # Max 4 tags

            # Combine all tags
            all_tags_parts = []
            if policy_areas_str:
                all_tags_parts.append(policy_areas_str)
            if government_bodies_str:
                all_tags_parts.append(government_bodies_str)
            if locations_str:
                all_tags_parts.append(locations_str)
            all_tags = '; '.join(all_tags_parts)

            # Update decision data with unified results
            decision_data.update({
                'summary': result.summary,
                'operativity': result.operativity,
                'tags_policy_area': policy_areas_str,
                'tags_government_body': government_bodies_str,
                'tags_location': locations_str,
                'all_tags': all_tags,
                # Add metadata for monitoring
                '_ai_processing_time': result.processing_time,
                '_ai_confidence': result.tags_confidence,
                '_ai_api_calls': result.api_calls_used
            })

            logger.info(f"Unified AI processing completed in {result.processing_time:.2f}s with {result.api_calls_used} API calls")
            logger.info(f"Results: policy={policy_areas_str}, govt={government_bodies_str}")

            return decision_data

        except Exception as e:
            logger.warning(f"Unified processing failed: {e}, falling back to individual calls")
            # Fall through to legacy processing

    # LEGACY PROCESSING (5-6 API calls)
    logger.info("Using legacy individual AI calls")

    # Step 1: Generate summary (needed for validation)
    summary = generate_summary(decision_content, decision_title)

    # Step 2: Generate operativity
    operativity = generate_operativity(decision_content)

    # Step 3: Policy area tags (with summary for validation)
    policy_areas = generate_policy_area_tags_strict(
        decision_content,
        decision_title,
        summary=summary
    )

    # Step 4: Government body tags (with validation!)
    government_bodies = generate_government_body_tags_validated(
        decision_content,
        decision_title,
        summary=summary
    )

    # Step 5: Location tags (unchanged)
    locations = generate_location_tags(decision_content, decision_title)

    # Validate critical fields
    if not summary or not policy_areas:
        raise Exception(f"AI processing produced empty critical fields")

    # Combine all tags
    all_tags_parts = []
    if policy_areas:
        all_tags_parts.append(policy_areas)
    if government_bodies:
        all_tags_parts.append(government_bodies)
    if locations:
        all_tags_parts.append(locations)
    all_tags = '; '.join(all_tags_parts)

    # Update decision data
    decision_data.update({
        'summary': summary,
        'operativity': operativity,
        'tags_policy_area': policy_areas,
        'tags_government_body': government_bodies,
        'tags_location': locations,
        'all_tags': all_tags,
        # Add metadata for comparison
        '_ai_processing_time': 0.0,  # Not tracked in legacy
        '_ai_confidence': 0.7,       # Default confidence
        '_ai_api_calls': 6           # Approximate legacy calls
    })

    logger.info(f"Legacy AI processing completed: policy={policy_areas}, govt={government_bodies}")

    return decision_data


# LEGACY WRAPPER - Maintains backward compatibility
def process_decision_with_ai_legacy(decision_data: Dict[str, str]) -> Dict[str, str]:
    """Legacy wrapper for backward compatibility."""
    return process_decision_with_ai(decision_data, use_unified=False)


if __name__ == "__main__":
    # Test AI processing
    test_data = {
        'decision_number': '2980',
        'decision_title': 'בדיקת מערכת הבינה המלאכותית',
        'decision_content': 'זוהי החלטה לבדיקת מערכת עיבוד הטקסט בבינה מלאכותית. ההחלטה נועדה לבחון את יכולות המערכת לנתח טקסט בעברית ולהפיק סיכומים ותגיות רלוונטיות.'
    }
    
    try:
        processed_data = process_decision_with_ai(test_data)
        print("AI Processing Results:")
        for key, value in processed_data.items():
            print(f"{key}: {value}")
    except Exception as e:
        print(f"Error: {e}")