"""OpenAI integration for generating summaries and tags for government decisions."""

import openai
import logging
import time
from typing import Dict, Optional, List

from ..config import OPENAI_API_KEY, OPENAI_MODEL, MAX_RETRIES, RETRY_DELAY

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authorized policy area tags (37 Hebrew labels)
POLICY_AREAS = [
    "ביטחון לאומי וצבא",
    "ביטחון פנים וחירום אזרחי",
    "דיפלומטיה ויחסים בינלאומיים",
    "הגירה וקליטת עלייה",
    "תעסוקה ושוק העבודה",
    "כלכלה מאקרו ותקציב",
    "פיננסים, ביטוח ומסים",
    "פיתוח כלכלי ותחרות",
    "יוקר המחיה ושוק הצרכן",
    "תחבורה ציבורית ותשתיות דרך",
    "בטיחות בדרכים ורכב",
    "אנרגיה ומתחדשות",
    "מים ותשתיות מים",
    "סביבה, אקלים ומגוון ביולוגי",
    "רשות הטבע והגנים ונוף",
    "חקלאות ופיתוח הכפר",
    "דיור, נדלן ותכנון",
    "שלטון מקומי ופיתוח פריפריה",
    "בריאות ורפואה",
    "רווחה ושירותים חברתיים",
    "אזרחים ותיקים",
    "שוויון חברתי וזכויות אדם",
    "מיעוטים ואוכלוסיות ייחודיות",
    "מילואים ותמיכה בלוחמים",
    "חינוך ",
    "השכלה גבוהה ומחקר",
    "תרבות ואמנות",
    "ספורט ואורח חיים פעיל",
    "מורשת ולאום",
    "תיירות ופנאי",
    "דת ומוסדות דת",
    "טכנולוגיה, חדשנות ודיגיטל",
    "סייבר ואבטחת מידע",
    "תקשורת ומדיה",
    "משפט, חקיקה ורגולציה",
    "מינהל ציבורי ושירות המדינה",
    "סחר חוץ ותעשייה יצואנית",
    "שונות"
]

# Initialize OpenAI client
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    logger.warning("OpenAI API key not found. AI processing will be skipped.")
    client = None


def make_openai_request_with_retry(prompt: str, max_tokens: int = 500) -> Optional[str]:
    """Make OpenAI API request with retry logic."""
    if not client:
        logger.warning("OpenAI client not initialized. Returning empty response.")
        return ""
    
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
                return ""
    
    return ""


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate simple character-based similarity between two strings."""
    if not str1 or not str2:
        return 0.0
    
    # Convert to sets of characters for basic similarity
    set1 = set(str1.lower())
    set2 = set(str2.lower())
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    return intersection / union if union > 0 else 0.0


def find_closest_tag(tag: str) -> Optional[str]:
    """Find the closest matching tag from POLICY_AREAS using fuzzy matching."""
    if not tag:
        return None
    
    # Direct mapping for common variations
    tag_mappings = {
        "מדע וטכנולוגיה": "טכנולוגיה, חדשנות ודיגיטל",
        "תעשייה יצואנית": "סחר חוץ ותעשייה יצואנית",
        "דיפלומטיה ויחסים בינ״ל": "דיפלומטיה ויחסים בינלאומיים",
        "דיפלומטיה ויחסים בינלאומיים": "דיפלומטיה ויחסים בינלאומיים",
        "ביטחון לאומי וצה״ל": "ביטחון לאומי וצבא",
        "בריאות ורפואה": "בריאות ורפואה",
        "חינוך": "חינוך ",
        "תחבורה": "תחבורה ציבורית ותשתיות דרך",
        "אנרגיה": "אנרגיה ומתחדשות",
        "סביבה": "סביבה, אקלים ומגוון ביולוגי",
        "תרבות": "תרבות ואמנות",
        "ספורט": "ספורט ואורח חיים פעיל",
        "דיור": "דיור, נדלן ותכנון",
        "רווחה": "רווחה ושירותים חברתיים",
        "חקלאות": "חקלאות ופיתוח הכפר",
        "מחקר": "השכלה גבוהה ומחקר",
        "תעסוקה": "תעסוקה ושוק העבודה",
        "כלכלה": "כלכלה מאקרו ותקציב",
        "מסים": "פיננסים, ביטוח ומסים",
        "ביטוח": "פיננסים, ביטוח ומסים",
        "תיירות": "תיירות ופנאי",
        "משפט": "משפט, חקיקה ורגולציה",
        "חקיקה": "משפט, חקיקה ורגולציה",
        "ביטחון פנים": "ביטחון פנים וחירום אזרחי",
        "מינהל": "מינהל ציבורי ושירות המדינה",
        "אחר": "שונות",
        "שונות": "שונות"
    }
    
    # Check direct mappings first
    if tag in tag_mappings:
        return tag_mappings[tag]
    
    # Check if tag is a substring of any valid tag
    for valid_tag in POLICY_AREAS:
        if tag in valid_tag or valid_tag in tag:
            return valid_tag
    
    # Simple character-based similarity for very close matches
    best_match = None
    highest_similarity = 0.7  # Minimum similarity threshold
    
    for valid_tag in POLICY_AREAS:
        similarity = calculate_similarity(tag, valid_tag)
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match = valid_tag
    
    return best_match


def create_strict_policy_prompt(decision_content: str) -> str:
    """Create a strict prompt for policy area classification."""
    # Create the policy area list string (pipe-separated)
    policy_areas_str = " | ".join(POLICY_AREAS)
    
    # Format the prompt according to the specification
    system_prompt = (
        f"""You are a **strict classifier**.

TASK
----
Look at the Hebrew government-decision text I will send.
Choose **only the policy-area tags that are clearly, explicitly present** in the text.

RULES
1. Prefer **one** tag.
2. Return **two** tags *only* if the decision text discusses **two distinct areas
   with roughly equal weight**.
3. Return **three** tags *only* if **three** areas are each mentioned **explicitly**.
4. If you are not sure, return just the single best tag.
5. Use the authorised list *exactly* - copy the EXACT text from the list below.
6. Respond with the tags **only**, separated by a semicolon + space ("; ").  
   No explanations, no line breaks, no extra text.
7. If nothing matches well, use "שונות".
8. Keep tags unique per decision, 
   i.e. if a decision is tagged with "בריאות ורפואה" and "בריאות ורפואה" again, 
   it should be returned as "בריאות ורפואה" only.

CRITICAL: Use EXACT text from this list:
{policy_areas_str}

Examples:
- Health decision → "בריאות ורפואה"
- Technology decision → "טכנולוגיה, חדשנות ודיגיטל"  
- Defense decision → "ביטחון לאומי וצבא"
- Education decision → "חינוך "

Remember: Copy the EXACT tag text from the authorized list above."""
    )
    
    return system_prompt


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


def generate_policy_area_tags_strict(decision_content: str, decision_title: str) -> str:
    """Generate policy area tags using strict classification with authorized list."""
    system_prompt = create_strict_policy_prompt(decision_content)
    
    prompt = f"""
{system_prompt}

כותרת: {decision_title}
תוכן: {decision_content[:2000]}

Tags:"""
    
    result = make_openai_request_with_retry(prompt, max_tokens=200)
    
    if not result:
        return "שונות"
    
    # Clean and validate the response
    result = result.strip().replace('"', '').replace("'", "")
    
    # Split by semicolon and validate each tag
    raw_tags = [tag.strip() for tag in result.split(';') if tag.strip()]
    validated_tags = []
    
    for tag in raw_tags:
        # First check if it's exactly in our list
        if tag in POLICY_AREAS:
            validated_tags.append(tag)
        else:
            # Try to find closest match
            closest = find_closest_tag(tag)
            if closest:
                validated_tags.append(closest)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in validated_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    # Return up to 3 tags
    final_tags = unique_tags[:3]
    
    if not final_tags:
        return "שונות"
    
    return "; ".join(final_tags)


def generate_government_body_tags(decision_content: str, decision_title: str) -> str:
    """Generate government body tags."""
    prompt = f"""
נא לזהות את הגופים הממשלתיים הרלוונטיים להחלטה הבאה.
רשום עד 5 גופים, מופרדים בפסיק.

דוגמאות לגופים: הממשלה, הכנסת, בית המשפט העליון, משרד החינוך, משרד הביטחון, משרד האוצר, משרד הבריאות, משרד החוץ, צה"ל, משטרת ישראל, ועדת השרים, ועדת הכנסת.

כותרת: {decision_title}
תוכן: {decision_content[:1500]}

גופים ממשלתיים:"""
    
    return make_openai_request_with_retry(prompt, max_tokens=150)


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
    
    Args:
        decision_data: Dictionary containing basic decision data
        
    Returns:
        Updated dictionary with AI-generated fields
    """
    logger.info(f"Processing decision {decision_data.get('decision_number', 'unknown')} with AI")
    
    decision_content = decision_data.get('decision_content', '')
    decision_title = decision_data.get('decision_title', '')
    
    if not decision_content:
        logger.warning("No decision content provided for AI processing")
        # Return empty AI fields
        decision_data.update({
            'summary': '',
            'operativity': '',
            'tags_policy_area': '',
            'tags_government_body': '',
            'tags_location': '',
            'all_tags': ''
        })
        return decision_data
    
    # Generate all AI fields
    try:
        summary = generate_summary(decision_content, decision_title)
        operativity = generate_operativity(decision_content)
        policy_areas = generate_policy_area_tags_strict(decision_content, decision_title)
        government_bodies = generate_government_body_tags(decision_content, decision_title)
        locations = generate_location_tags(decision_content, decision_title)
        
        # Combine all tags
        all_tags_parts = []
        if policy_areas: all_tags_parts.append(policy_areas)
        if government_bodies: all_tags_parts.append(government_bodies)
        if locations: all_tags_parts.append(locations)
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
        
        logger.info(f"AI processing completed for decision {decision_data.get('decision_number')}")
        
    except Exception as e:
        logger.error(f"AI processing failed for decision {decision_data.get('decision_number')}: {e}")
        # Fill with empty values on failure
        decision_data.update({
            'summary': '',
            'operativity': '',
            'tags_policy_area': '',
            'tags_government_body': '',
            'tags_location': '',
            'all_tags': ''
        })
    
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