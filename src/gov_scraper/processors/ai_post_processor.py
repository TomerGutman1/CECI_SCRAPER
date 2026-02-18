"""Post-processing validator for AI results.

This module provides final cleanup and validation of AI processing results
to fix common issues identified in manual QA.
"""

import re
import logging
from typing import Dict, List, Optional, Set
import os
import sys

# Setup path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# Try importing committee mappings
try:
    from config.committee_mappings import normalize_committee_name
except ImportError:
    def normalize_committee_name(name):
        return name

logger = logging.getLogger(__name__)


def _load_authorized_list(filename: str) -> Set[str]:
    """Load authorized tag/body list from file."""
    filepath = os.path.join(os.path.dirname(__file__), '..', '..', '..', filename)
    filepath = os.path.abspath(filepath)
    tags = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or ':' in line:
                    continue
                tags.add(line)
    except FileNotFoundError:
        logger.error(f"Authorized list not found: {filepath}")
    return tags


# Load authorized lists once at module level
AUTHORIZED_POLICY_AREAS = _load_authorized_list('new_tags.md')
AUTHORIZED_POLICY_AREAS.add("שונות")  # Fallback tag always allowed
AUTHORIZED_GOVERNMENT_BODIES = _load_authorized_list('new_departments.md')

# Log for verification
logger.info(f"Post-processor loaded {len(AUTHORIZED_POLICY_AREAS)} authorized policy areas, "
            f"{len(AUTHORIZED_GOVERNMENT_BODIES)} authorized government bodies")


# Generic location tags to filter out
GENERIC_LOCATIONS = {
    "ישראל",
    "Israel",
    "מדינת ישראל",
    "State of Israel",
    "הארץ",
    "ארץ ישראל"
}

# Military-related terms that shouldn't trigger police tagging
MILITARY_TERMS = {
    "גלי צה\"ל", "גלגל\"צ", "גלי צהל", "גלגלצ",
    "רדיו צבאי", "תחנת השידור הצבאית",
    "צה\"ל", "צבא", "חיל האוויר", "חיל הים",
    "יחידה צבאית", "בסיס צבאי", "מחנה צבאי"
}

# Finance/economy terms that shouldn't trigger media tagging
FINANCE_TERMS = {
    "קרן גידור", "hedge fund", "השקעות", "שוק ההון",
    "בורסה", "ניירות ערך", "רשות ניירות ערך",
    "קרנות השקעה", "קרנות נאמנות", "מכשירים פיננסיים"
}

# Government body normalization map.
# Maps unauthorized/variant names → authorized name (from new_departments.md) or None (drop).
BODY_NORMALIZATION = {
    # DROP: Generic / not a specific executive body
    "מזכירות הממשלה": None,
    "ממשלה": None,
    "הממשלה": None,
    "הכנסת": None,
    "כנסת ישראל": None,
    "כנסת": None,
    "ועדת החוץ והביטחון של הכנסת": None,  # Knesset committee, not executive
    "ועדת החוץ והביטחון": None,  # Knesset committee variant
    # MAP: Committee variations → authorized "ועדת השרים"
    "ועדת השרים לענייני חקיקה": "ועדת השרים",
    "וועדת השרים לענייני חקיקה": "ועדת השרים",
    "ועדת השרים לתיקוני חקיקה": "ועדת השרים",
    "ועדת שרים לענייני חקיקה": "ועדת השרים",
    "ועדת שרים לתיקוני חקיקה": "ועדת השרים",
    "ועדת השרים לענייני ביטחון לאומי": "ועדת השרים",
    "ועדת שרים לענייני ביטחון לאומי": "ועדת השרים",  # variant without ה
    "ועדת השרים לענייני דיור": "ועדת השרים",
    "ועדת השרים לסמלים וטקסים": "ועדת השרים",
    "ועדת שרים": "ועדת השרים",
    # MAP: Common name variations → authorized names
    "המשרד לביטחון הלאומי": "המשרד לביטחון לאומי",
    "משרד הביטחון הלאומי": "המשרד לביטחון לאומי",
    "משרד לביטחון לאומי": "המשרד לביטחון לאומי",
    "משרד הביטחון הפנים": "המשרד לביטחון פנים",
    "המשרד לביטחון הפנים": "המשרד לביטחון פנים",
    "משרד האנרגיה": "משרד האנרגיה והתשתיות",
    "משרד התשתיות": "משרד האנרגיה והתשתיות",
    "משרד הכלכלה": "משרד הכלכלה והתעשייה",
    "משרד הכלכלה והתעשיה": "משרד הכלכלה והתעשייה",  # single yod variant
    "משרד התעשייה": "משרד הכלכלה והתעשייה",
    "משרד התחבורה": "משרד התחבורה והבטיחות בדרכים",
    "משרד השיכון": "משרד השיכון והבינוי",
    "משרד הבינוי": "משרד השיכון והבינוי",
    "משרד הבינוי והשיכון": "משרד השיכון והבינוי",
    "משרד החקלאות": "משרד החקלאות ופיתוח הכפר",
    "משרד המדע": "משרד החדשנות המדע והטכנולוגיה",
    "משרד המדע והטכנולוגיה": "משרד החדשנות המדע והטכנולוגיה",
    "משרד החדשנות": "משרד החדשנות המדע והטכנולוגיה",
    "משרד העלייה": "משרד העלייה והקליטה",
    "משרד הקליטה": "משרד העלייה והקליטה",
    "משרד התרבות": "משרד התרבות והספורט",
    "משרד הספורט": "משרד התרבות והספורט",
    "משרד ראש הממשלה": "משרד רה\"מ",
    "רשות שירות המדינה": "נציבות שירות המדינה",
    "רח\"ל": "רשות החירום הלאומית (רח\"ל)",
    "רשות החירום הלאומית": "רשות החירום הלאומית (רח\"ל)",
    "היועמ\"ש": "היועץ המשפטי לממשלה",
    "היועמש": "היועץ המשפטי לממשלה",
    "היועץ המשפטי": "היועץ המשפטי לממשלה",
    "מל\"ג": "מל\"ג/ות\"ת",
    "ות\"ת": "מל\"ג/ות\"ת",
    "המועצה להשכלה גבוהה": "מל\"ג/ות\"ת",
}

# Regex pattern for summary prefix to strip
_SUMMARY_PREFIX_PATTERN = re.compile(
    r'^החלטת ממשלה מספר\s*\S+\s*'  # "החלטת ממשלה מספר 3856"
    r'(?:מיום\s*\S+\s*)?'            # optional "מיום 08.02.2026"
    r'(?:עוסקת ב|מאשרת את|קובעת כי|דנה ב|מחליטה על|בנושא)?'  # optional connector
)

# Operativity override patterns: (regex, forced_classification)
OPERATIVITY_OVERRIDES = [
    # Declarative: opposing/supporting a bill is a position statement
    (re.compile(r'להתנגד להצעת חוק'), "דקלרטיבית"),
    (re.compile(r'לתמוך בהצעת חוק'), "דקלרטיבית"),
    (re.compile(r'להביע התנגדות'), "דקלרטיבית"),
    (re.compile(r'להביע תמיכה'), "דקלרטיבית"),
    # Declarative: principle-only approvals without action
    (re.compile(r'לאשר עקרונית(?!.*להסמיך)(?!.*להקצות)(?!.*תקציב)'), "דקלרטיבית"),
    # Declarative: noting/recording
    (re.compile(r'הממשלה רושמת לפניה'), "דקלרטיבית"),
    (re.compile(r'הממשלה מביעה הערכה'), "דקלרטיבית"),
    (re.compile(r'הממשלה מכירה בחשיבות'), "דקלרטיבית"),
]


def _fuzzy_match(tag: str, authorized: Set[str], threshold: float = 0.5) -> Optional[str]:
    """Find best fuzzy match for a tag in the authorized set using word overlap.

    Args:
        tag: The tag to match
        authorized: Set of authorized tags
        threshold: Minimum Jaccard similarity (default 0.5)

    Returns:
        Best matching authorized tag, or None if no match above threshold
    """
    tag_words = set(tag.split())
    if len(tag_words) < 2:
        return None

    best_match = None
    best_score = threshold - 0.001  # Use >= threshold semantics

    for auth_tag in authorized:
        auth_words = set(auth_tag.split())
        if not auth_words:
            continue
        intersection = len(tag_words & auth_words)
        union = len(tag_words | auth_words)
        score = intersection / union if union > 0 else 0
        if score > best_score:
            best_score = score
            best_match = auth_tag

    return best_match


def enforce_policy_whitelist(tags_str: str) -> str:
    """Enforce that all policy tags are from the authorized list.

    Tags not on the list are fuzzy-matched or dropped.
    """
    if not tags_str or not AUTHORIZED_POLICY_AREAS:
        return tags_str

    tags = [t.strip() for t in tags_str.split(';') if t.strip()]
    validated = []

    for tag in tags:
        if tag in AUTHORIZED_POLICY_AREAS:
            validated.append(tag)
        else:
            match = _fuzzy_match(tag, AUTHORIZED_POLICY_AREAS)
            if match:
                logger.info(f"Policy tag fuzzy matched: '{tag}' -> '{match}'")
                validated.append(match)
            else:
                logger.warning(f"Dropping unauthorized policy tag: '{tag}'")

    # Deduplicate preserving order
    validated = list(dict.fromkeys(validated))

    if not validated:
        return "שונות"

    return '; '.join(validated)


def enforce_body_whitelist(tags_str: str) -> str:
    """Enforce that all government bodies are from the authorized list.

    Bodies not on the list are fuzzy-matched or dropped.
    """
    if not tags_str or not AUTHORIZED_GOVERNMENT_BODIES:
        return tags_str

    bodies = [b.strip() for b in tags_str.split(';') if b.strip()]
    validated = []

    for body in bodies:
        if body in AUTHORIZED_GOVERNMENT_BODIES:
            validated.append(body)
        else:
            match = _fuzzy_match(body, AUTHORIZED_GOVERNMENT_BODIES)
            if match:
                logger.info(f"Gov body fuzzy matched: '{body}' -> '{match}'")
                validated.append(match)
            else:
                logger.warning(f"Dropping unauthorized gov body: '{body}'")

    # Deduplicate preserving order
    validated = list(dict.fromkeys(validated))

    return '; '.join(validated) if validated else ""


def strip_summary_prefix(summary: str) -> str:
    """Remove wasteful 'החלטת ממשלה מספר...' prefix from summaries.

    Args:
        summary: The summary text

    Returns:
        Summary with prefix removed, first letter capitalized for Hebrew
    """
    if not summary:
        return summary

    cleaned = _SUMMARY_PREFIX_PATTERN.sub('', summary).strip()

    # If regex removed everything or nearly everything, keep original
    if len(cleaned) < 10:
        return summary

    logger.debug(f"Stripped summary prefix: '{summary[:50]}...' -> '{cleaned[:50]}...'")
    return cleaned


def normalize_government_body(body: str) -> Optional[str]:
    """Normalize a government body name using the BODY_NORMALIZATION map.

    Args:
        body: The government body name from AI output

    Returns:
        Normalized name, or None if should be dropped
    """
    stripped = body.strip()
    if not stripped:
        return None

    # Check exact match in normalization map
    if stripped in BODY_NORMALIZATION:
        result = BODY_NORMALIZATION[stripped]
        if result is None:
            logger.debug(f"Dropping unauthorized gov body: '{stripped}'")
        else:
            logger.debug(f"Normalized gov body: '{stripped}' -> '{result}'")
        return result

    # Try with וו→ו normalization (common Hebrew spelling variant for committees)
    if "וו" in stripped:
        single_vav = stripped.replace("וו", "ו")
        if single_vav in BODY_NORMALIZATION:
            result = BODY_NORMALIZATION[single_vav]
            if result is None:
                logger.debug(f"Dropping unauthorized gov body (וו→ו): '{stripped}'")
            else:
                logger.debug(f"Normalized gov body (וו→ו): '{stripped}' -> '{result}'")
            return result

    return stripped


def validate_operativity(operativity: str, decision_content: str) -> str:
    """Override AI operativity classification for unambiguous patterns.

    Args:
        operativity: AI-determined operativity ("אופרטיבית" or "דקלרטיבית")
        decision_content: Full decision text

    Returns:
        Validated/overridden operativity classification
    """
    if not decision_content:
        return operativity

    for pattern, forced_class in OPERATIVITY_OVERRIDES:
        if pattern.search(decision_content):
            if operativity != forced_class:
                logger.debug(
                    f"Operativity override: '{operativity}' -> '{forced_class}' "
                    f"(matched pattern: {pattern.pattern})"
                )
                return forced_class

    return operativity


def deduplicate_tags(tags_string: str, separator: str = ';') -> str:
    """Remove duplicate tags from a separated string while preserving order.

    Args:
        tags_string: String of tags separated by separator
        separator: The separator used (default ';')

    Returns:
        String with unique tags, preserving original order
    """
    if not tags_string:
        return ""

    # Split and strip whitespace
    tags = [t.strip() for t in tags_string.split(separator)]

    # Remove duplicates while preserving order
    unique_tags = list(dict.fromkeys(tags))

    # Rejoin with separator and space
    return f"{separator} ".join(unique_tags)

def fix_truncated_summary(summary: str) -> str:
    """Fix truncated summaries to ensure they end properly.

    Args:
        summary: The summary text to check and fix

    Returns:
        Fixed summary with proper ending
    """
    if not summary:
        return summary

    summary = summary.strip()

    # Check if summary ends properly (with punctuation)
    if summary and not summary[-1] in '.!?׃:':
        # If it looks truncated, add ellipsis
        if not summary.endswith('...'):
            # Check if last word might be incomplete by looking for common Hebrew word endings
            last_word = summary.split()[-1] if summary.split() else ""
            # Common incomplete endings in Hebrew that suggest truncation (abbreviated words)
            if any(last_word.endswith(ending) for ending in ["הכ", "הו", "המ", "וו", "הת", "הש", "הצ", "הפ"]) or \
               len(last_word) <= 2:
                # Remove potential incomplete word
                last_space = summary.rfind(' ')
                if last_space > 0:
                    summary = summary[:last_space].rstrip()
            # Add proper ending
            summary = summary + '...'
            logger.debug(f"Fixed truncated summary ending")

    return summary

def filter_generic_locations(locations: List[str]) -> List[str]:
    """Remove generic location tags that don't add value.

    Args:
        locations: List of location tags

    Returns:
        Filtered list with only specific locations
    """
    filtered = []
    for location in locations:
        if location and location not in GENERIC_LOCATIONS:
            filtered.append(location)

    if filtered != locations:
        logger.debug(f"Filtered generic locations: {set(locations) - set(filtered)}")

    return filtered

def validate_ministry_context(decision_content: str, ministry: str) -> bool:
    """Validate if a ministry tag is appropriate for the decision content.

    Args:
        decision_content: The full decision text
        ministry: The ministry tag to validate

    Returns:
        True if the ministry is appropriate, False otherwise
    """
    content_lower = decision_content.lower()

    # Check for military content incorrectly tagged as police
    if ministry == "משטרת ישראל":
        for term in MILITARY_TERMS:
            if term.lower() in content_lower:
                logger.debug(f"Excluding police tag due to military term: {term}")
                return False

    # Check for finance content incorrectly tagged as media
    if ministry in ["תקשורת ומדיה", "משרד התקשורת"]:
        for term in FINANCE_TERMS:
            if term.lower() in content_lower:
                logger.debug(f"Excluding media tag due to finance term: {term}")
                return False

    return True

def post_process_ai_results(decision_data: Dict, decision_content: str = "") -> Dict:
    """Final cleanup and validation of AI results.

    This function performs:
    1. Deduplication of all tag fields
    2. Government body normalization (drop unauthorized, remap variants, committee names)
    3. Summary prefix stripping + truncation fix
    3b. Operativity validation against content patterns
    4. Generic location removal
    4b. Whitelist enforcement — strip any tag/body not in authorized lists
    5. Deterministic all_tags rebuild from individual fields

    Args:
        decision_data: The AI processing results
        decision_content: Optional full decision text for context validation

    Returns:
        Cleaned and validated decision data
    """
    # Create a copy to avoid modifying the original
    cleaned_data = decision_data.copy()

    # 1. Fix and deduplicate policy area tags
    if 'tags_policy_area' in cleaned_data:
        cleaned_data['tags_policy_area'] = deduplicate_tags(cleaned_data['tags_policy_area'])

    # 2. Fix and deduplicate government body tags
    if 'tags_government_body' in cleaned_data:
        # First deduplicate
        gov_bodies = deduplicate_tags(cleaned_data['tags_government_body'])

        # Then normalize: body normalization map → committee mappings → context validation
        if gov_bodies:
            bodies = [b.strip() for b in gov_bodies.split(';')]
            normalized_bodies = []
            for body in bodies:
                # Step 1: Apply BODY_NORMALIZATION map (drop/remap unauthorized names)
                normalized = normalize_government_body(body)
                if normalized is None:
                    continue

                # Step 2: Apply committee name normalization
                committee_normalized = normalize_committee_name(normalized)
                if committee_normalized != normalized:
                    logger.debug(f"Normalized committee: '{normalized}' -> '{committee_normalized}'")
                    normalized = committee_normalized
                    # Re-check BODY_NORMALIZATION after committee normalization
                    # (suffix removal may now match a known variant)
                    re_normalized = normalize_government_body(normalized)
                    if re_normalized is None:
                        continue
                    normalized = re_normalized

                # Step 3: Validate ministry context if we have the content
                if decision_content and not validate_ministry_context(decision_content, normalized):
                    logger.debug(f"Excluding ministry due to context: {normalized}")
                    continue

                normalized_bodies.append(normalized)

            # Remove duplicates after normalization
            normalized_bodies = list(dict.fromkeys(normalized_bodies))
            cleaned_data['tags_government_body'] = '; '.join(normalized_bodies) if normalized_bodies else ""

    # 3. Fix summary: strip prefix, then fix truncation
    if 'summary' in cleaned_data:
        cleaned_data['summary'] = strip_summary_prefix(cleaned_data['summary'])
        cleaned_data['summary'] = fix_truncated_summary(cleaned_data['summary'])

    # 3b. Validate operativity against content patterns
    if 'operativity' in cleaned_data and decision_content:
        cleaned_data['operativity'] = validate_operativity(
            cleaned_data['operativity'], decision_content
        )

    # 4. Filter generic locations
    if 'tags_location' in cleaned_data:
        location_str = cleaned_data['tags_location']
        if location_str:
            # Handle comma-separated locations
            locations = [l.strip() for l in location_str.split(',')]
            filtered = filter_generic_locations(locations)
            cleaned_data['tags_location'] = ', '.join(filtered) if filtered else ""

    # 4b. Enforce whitelists — only authorized tags and bodies allowed
    if cleaned_data.get('tags_policy_area'):
        cleaned_data['tags_policy_area'] = enforce_policy_whitelist(cleaned_data['tags_policy_area'])
    if cleaned_data.get('tags_government_body'):
        cleaned_data['tags_government_body'] = enforce_body_whitelist(cleaned_data['tags_government_body'])

    # 5. Rebuild all_tags deterministically from individual fields
    all_individual_tags = []

    if cleaned_data.get('tags_policy_area'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_policy_area'].split(';')])

    if cleaned_data.get('tags_government_body'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_government_body'].split(';')])

    if cleaned_data.get('tags_location'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_location'].split(',')])

    # Include special categories if stored separately
    if cleaned_data.get('tags_special_categories'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_special_categories'].split(';')])

    # Remove duplicates while preserving order
    unique_all_tags = list(dict.fromkeys(all_individual_tags))
    cleaned_data['all_tags'] = '; '.join(unique_all_tags)

    return cleaned_data

def validate_and_clean_batch(decisions: List[Dict], decision_contents: Optional[Dict[str, str]] = None) -> List[Dict]:
    """Process a batch of decisions for cleanup.

    Args:
        decisions: List of decision data dictionaries
        decision_contents: Optional mapping of decision_key to full content

    Returns:
        List of cleaned decision data
    """
    cleaned_decisions = []

    for decision in decisions:
        decision_key = decision.get('decision_key', '')
        content = decision_contents.get(decision_key, '') if decision_contents else ""

        cleaned = post_process_ai_results(decision, content)
        cleaned_decisions.append(cleaned)

    logger.info(f"Post-processed {len(cleaned_decisions)} decisions")
    return cleaned_decisions