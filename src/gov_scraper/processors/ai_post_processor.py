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
    2. Committee name normalization
    3. Summary completeness check
    4. Generic location removal
    5. Ministry validation against content

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

        # Then normalize committee names
        if gov_bodies:
            bodies = [b.strip() for b in gov_bodies.split(';')]
            normalized_bodies = []
            for body in bodies:
                normalized = normalize_committee_name(body)
                if normalized != body:
                    logger.debug(f"Normalized committee: '{body}' -> '{normalized}'")

                # Validate ministry context if we have the content
                if decision_content and not validate_ministry_context(decision_content, normalized):
                    logger.debug(f"Excluding ministry due to context: {normalized}")
                    continue

                normalized_bodies.append(normalized)

            # Remove duplicates after normalization
            normalized_bodies = list(dict.fromkeys(normalized_bodies))
            cleaned_data['tags_government_body'] = '; '.join(normalized_bodies) if normalized_bodies else ""

    # 3. Fix truncated summary
    if 'summary' in cleaned_data:
        cleaned_data['summary'] = fix_truncated_summary(cleaned_data['summary'])

    # 4. Filter generic locations
    if 'tags_location' in cleaned_data:
        location_str = cleaned_data['tags_location']
        if location_str:
            # Handle comma-separated locations
            locations = [l.strip() for l in location_str.split(',')]
            filtered = filter_generic_locations(locations)
            cleaned_data['tags_location'] = ', '.join(filtered) if filtered else ""

    # 5. Rebuild all_tags field with deduplication
    all_individual_tags = []

    if cleaned_data.get('tags_policy_area'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_policy_area'].split(';')])

    if cleaned_data.get('tags_government_body'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_government_body'].split(';')])

    if cleaned_data.get('tags_location'):
        all_individual_tags.extend([t.strip() for t in cleaned_data['tags_location'].split(',')])

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