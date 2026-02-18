"""Committee name mappings for consistent tagging.

This module maps various committee name variations to their canonical forms.
Used to ensure committees are tagged consistently regardless of how they appear
in the original decision text.
"""

# Committee name variations to canonical form mapping
COMMITTEE_TO_TAG_MAPPING = {
    # Cabinet committees
    "וועדת שרים לתיקוני חקיקה (תחק)": "וועדת שרים לתיקוני חקיקה",
    "ועדת שרים לתיקוני חקיקה": "וועדת שרים לתיקוני חקיקה",
    "ועדת השרים לתיקוני חקיקה": "וועדת שרים לתיקוני חקיקה",
    "תחק": "וועדת שרים לתיקוני חקיקה",

    "ועדת השרים לענייני חקיקה": "ועדת השרים לענייני חקיקה",
    "וועדת השרים לענייני חקיקה": "ועדת השרים לענייני חקיקה",
    "ועדת שרים לענייני חקיקה": "ועדת השרים לענייני חקיקה",

    "הקבינט המדיני-ביטחוני": "הקבינט המדיני-ביטחוני",
    "הקבינט המדיני ביטחוני": "הקבינט המדיני-ביטחוני",
    "קבינט ביטחוני": "הקבינט המדיני-ביטחוני",

    "ועדת שרים לענייני ביטחון לאומי": "ועדת שרים לענייני ביטחון לאומי",
    "וועדת שרים לענייני ביטחון לאומי": "ועדת שרים לענייני ביטחון לאומי",
    "ועדת השרים לענייני ביטחון לאומי": "ועדת שרים לענייני ביטחון לאומי",

    "ועדת שרים לעניינים כלכליים": "ועדת שרים לעניינים כלכליים",
    "וועדת שרים לעניינים כלכליים": "ועדת שרים לעניינים כלכליים",
    "ועדת השרים לעניינים כלכליים": "ועדת שרים לעניינים כלכליים",

    "ועדת שרים לענייני חברה ושירותים": "ועדת שרים לענייני חברה ושירותים",
    "וועדת שרים לענייני חברה ושירותים": "ועדת שרים לענייני חברה ושירותים",
    "ועדת השרים לענייני חברה ושירותים": "ועדת שרים לענייני חברה ושירותים",

    # Housing committee variations
    "ועדת שרים לענייני דיור": "ועדת שרים לענייני דיור",
    "וועדת שרים לענייני דיור": "ועדת שרים לענייני דיור",
    "הוועדה לענייני דיור": "ועדת שרים לענייני דיור",
    "ועדת הדיור": "ועדת שרים לענייני דיור",

    # Symbols committee variations
    "ועדת השרים לסמלים וטקסים": "ועדת השרים לסמלים וטקסים",
    "וועדת השרים לסמלים וטקסים": "ועדת השרים לסמלים וטקסים",
    "ועדת סמלים וטקסים": "ועדת השרים לסמלים וטקסים",

    # Jerusalem affairs
    "ועדת שרים לענייני ירושלים": "ועדת שרים לענייני ירושלים",
    "וועדת שרים לענייני ירושלים": "ועדת שרים לענייני ירושלים",
    "ועדת השרים לענייני ירושלים": "ועדת שרים לענייני ירושלים",

    # Other committees
    "ועדת שרים לקידום השילוב של אזרחי ישראל הערבים בשוק העבודה": "ועדת שרים לקידום השילוב של אזרחי ישראל הערבים",
    "ועדת שרים לשילוב הערבים": "ועדת שרים לקידום השילוב של אזרחי ישראל הערבים",
}

def normalize_committee_name(committee_name: str) -> str:
    """Normalize a committee name to its canonical form.

    Args:
        committee_name: The committee name as it appears in the text

    Returns:
        The canonical form of the committee name, or the original if no mapping exists
    """
    if not committee_name:
        return committee_name

    # Remove extra whitespace
    committee_name = ' '.join(committee_name.split())

    # Check for exact match first
    if committee_name in COMMITTEE_TO_TAG_MAPPING:
        return COMMITTEE_TO_TAG_MAPPING[committee_name]

    # Check for partial matches (e.g., if the text contains the committee name as part of a larger string)
    for variation, canonical in COMMITTEE_TO_TAG_MAPPING.items():
        if variation in committee_name:
            return canonical

    # Return original if no mapping found
    return committee_name

def get_all_committee_variations() -> list:
    """Get all known committee name variations for detection.

    Returns:
        List of all committee name variations
    """
    return list(COMMITTEE_TO_TAG_MAPPING.keys())

def get_canonical_committees() -> set:
    """Get unique canonical committee names.

    Returns:
        Set of canonical committee names
    """
    return set(COMMITTEE_TO_TAG_MAPPING.values())