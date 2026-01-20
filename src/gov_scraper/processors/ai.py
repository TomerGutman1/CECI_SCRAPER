"""OpenAI integration for generating summaries and tags for government decisions."""

import openai
import logging
import time
import os
from typing import Dict, Optional, List, Set

from ..config import OPENAI_API_KEY, OPENAI_MODEL, MAX_RETRIES, RETRY_DELAY

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

# Initialize OpenAI client - API key is required (validated in config.py)
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI(api_key=OPENAI_API_KEY)


def make_openai_request_with_retry(prompt: str, max_tokens: int = 500) -> str:
    """Make OpenAI API request with retry logic. Raises exception if all retries fail."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Making OpenAI request (attempt {attempt + 1}/{MAX_RETRIES})")
            
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "אתה עוזר מקצועי המנתח החלטות ממשלה ישראליות. ענה בעברית בצורה קצרה ומדויקת."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            logger.info(f"OpenAI request successful (attempt {attempt + 1})")
            return result
            
        except Exception as e:
            logger.warning(f"OpenAI request failed (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"All OpenAI request attempts failed")
                raise Exception(f"OpenAI API request failed after {MAX_RETRIES} attempts: {e}")

    raise Exception(f"OpenAI API request failed after {MAX_RETRIES} attempts")


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


def _ai_summary_fallback(summary: str, valid_tags: List[str], tag_type: str) -> Optional[str]:
    """AI fallback - analyze summary to find the best matching tag."""
    if not summary:
        return None

    tags_str = " | ".join(valid_tags)
    tag_type_hebrew = "תחום מדיניות" if tag_type == "policy" else "גוף ממשלתי"

    prompt = f"""נתון תקציר של החלטת ממשלה:
"{summary[:1000]}"

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
    """Generate a concise summary of the decision."""
    prompt = f"""
נא לסכם את ההחלטה הממשלתית הבאה במשפט או שניים קצרים ומדויקים:

כותרת: {decision_title}

תוכן ההחלטה:
{decision_content[:2000]}

סיכום:"""
    
    return make_openai_request_with_retry(prompt, max_tokens=200)


def generate_operativity(decision_content: str) -> str:
    """Determine the operational status of the decision."""
    prompt = f"""
נא לקבוע את סוג הפעילות של ההחלטה הממשלתית הבאה. 
ענה במילה אחת בלבד: "אופרטיבית" (החלטה שמחייבת פעולה מעשית) או "דקלרטיבית" (החלטה עקרונית או הכרזה).

תוכן ההחלטה:
{decision_content[:1500]}

סוג הפעילות:"""
    
    result = make_openai_request_with_retry(prompt, max_tokens=50)
    
    # Clean and validate the response
    if result:
        result = result.strip().replace('"', '').replace("'", "")
        if "אופרטיבית" in result:
            return "אופרטיבית"
        elif "דקלרטיבית" in result:
            return "דקלרטיבית"
    
    # Default to operational if unclear
    return "אופרטיבית"


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
תוכן: {decision_content[:2000]}

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
תוכן: {decision_content[:1500]}

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
תוכן: {decision_content[:1500]}

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


def generate_location_tags(decision_content: str, decision_title: str) -> str:
    """Generate geographic location tags - returns empty string if no locations found."""
    prompt = f"""
נא לזהות מקומות גיאוגרפיים שמוזכרים במפורש בטקסט ההחלטה הבאה.
חשוב: רק אם יש מקומות שמוזכרים ישירות בטקסט - רשום אותם מופרדים בפסיק.
אם אין מקומות ספציפיים המוזכרים בטקסט, השב "אין".
חשוב: אל תכתוב "ריק", "לא מוזכר", או הסברים אחרים - רק "אין" או שמות המקומות.

דוגמאות למקומות שיכולים להיות מוזכרים: ירושלים, תל אביב, חיפה, באר שבע, הגליל, הנגב, יהודה ושומרון, עזה, גולן, צפון, דרום, מרכז.

כותרת: {decision_title}
תוכן: {decision_content[:1500]}

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


def process_decision_with_ai(decision_data: Dict[str, str]) -> Dict[str, str]:
    """
    Process a decision with AI to generate all required fields.
    Uses validated tags from new_tags.md and new_departments.md.

    Args:
        decision_data: Dictionary containing basic decision data

    Returns:
        Updated dictionary with AI-generated fields

    Raises:
        ValueError: If decision content is missing
        Exception: If AI processing fails
    """
    logger.info(f"Processing decision {decision_data.get('decision_number', 'unknown')} with AI")

    decision_content = decision_data.get('decision_content', '')
    decision_title = decision_data.get('decision_title', '')

    if not decision_content:
        raise ValueError(f"Decision {decision_data.get('decision_number', 'unknown')} has no content")

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
        'all_tags': all_tags
    })

    logger.info(f"AI processing completed: policy={policy_areas}, govt={government_bodies}")

    return decision_data


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