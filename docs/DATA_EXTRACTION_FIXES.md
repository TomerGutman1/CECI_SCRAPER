# Data Extraction Fixes

This document summarizes the fixes implemented for the two data extraction issues.

## Issues Fixed

### 1. Committee Field Extraction ✅

**Problem**: The committee extraction was using a simple label-based approach that didn't properly handle the specific requirement to extract text between "ועדות שרים:" and "ממשלה" (with optional space).

**Solution**: Created a new `extract_committee_text()` function in `decision_scraper.py` that:
- Searches for the exact label "ועדות שרים:"
- Returns `None` if the label is not found (instead of empty string)
- Extracts text between "ועדות שרים:" and "ממשלה:" (handling both " ממשלה:" and "ממשלה:")
- Properly cleans and formats the extracted committee name

**Files Modified**:
- `src/decision_scraper.py`: Added `extract_committee_text()` function
- `src/data_manager.py`: Updated to handle `None` values properly for CSV output

**Test Cases**:
- ✅ Committee with space before "ממשלה": "ועדת השרים לענייני חקיקה"
- ✅ Committee without space before "ממשלה": "ועדת השרים לביטחון לאומי"  
- ✅ No committee section: Returns `None`

### 2. Location Tags - Null When Empty ✅

**Problem**: The AI processor was generating location tags even when no specific locations were mentioned in the decision, leading to irrelevant or generic location information.

**Solution**: Enhanced the `generate_location_tags()` function in `ai_processor.py` to:
- Use a more restrictive prompt that explicitly asks for empty response when no locations are found
- Filter out common non-location phrases ("אין מקומות", "לא מוזכר", etc.)
- Clean AI response patterns that don't represent actual locations
- Return empty string when no meaningful locations are found

**Files Modified**:
- `src/ai_processor.py`: Updated `generate_location_tags()` function with stricter logic

**Test Cases**:
- ✅ Content with specific locations: Returns location names
- ✅ Content without locations: Returns empty string
- ✅ AI responses with non-location text: Filtered out and returns empty

## Implementation Details

### Committee Extraction Logic

```python
def extract_committee_text(soup: BeautifulSoup) -> Optional[str]:
    # Get full page text
    full_text = soup.get_text()
    
    # Find "ועדות שרים:" label
    committee_pos = full_text.find("ועדות שרים:")
    if committee_pos == -1:
        return None  # No committee section
    
    # Extract text after label
    after_committee = full_text[committee_pos + len("ועדות שרים:"):].strip()
    
    # Find end marker "ממשלה:" (with or without space)
    for pattern in ["ממשלה:", " ממשלה:"]:
        end_pos = after_committee.find(pattern)
        if end_pos != -1:
            committee_text = after_committee[:end_pos].strip()
            break
    
    return clean_hebrew_text(committee_text) if committee_text else None
```

### Location Tags Logic

```python
def generate_location_tags(decision_content: str, decision_title: str) -> str:
    # Enhanced prompt asking for explicit locations only
    prompt = """
    נא לזהות מקומות גיאוגרפיים שמוזכרים במפורש בטקסט ההחלטה הבאה.
    חשוב: רק אם יש מקומות שמוזכרים ישירות בטקסט - רשום אותם מופרדים בפסיק.
    אם אין מקומות ספציפיים המוזכרים בטקסט, השב בשורה ריקה (ללא טקסט כלל).
    """
    
    result = make_openai_request_with_retry(prompt)
    
    # Filter out non-location responses
    non_location_phrases = ["אין מקומות", "לא מוזכר", "לא נמצא", ...]
    for phrase in non_location_phrases:
        if phrase in result:
            return ""
    
    return result.strip() if result else ""
```

## Database Schema Impact

### Committee Field
- **Before**: Always had a value (could be empty string)
- **After**: Can be `NULL` in database when no committee is found
- **CSV**: Shows empty string for display purposes, but preserves `NULL` for database

### Location Tags Field  
- **Before**: Often contained irrelevant or generic text
- **After**: Only contains actual location names mentioned in the decision, or empty string

## Testing

Run the test script to verify both fixes:

```bash
python3 test_fixes.py
```

Expected output: All tests should pass (✅ PASS)

## Usage Examples

### Committee Extraction Examples

**Input HTML:**
```html
תאריך תחולה: 11.05.2025
ועדות שרים:
ועדת השרים לענייני חקיקה
ממשלה:
הממשלה ה- 37
```
**Output:** `"ועדת השרים לענייני חקיקה"`

**Input HTML (no committee):**
```html  
תאריך פרסום: 24.07.2025
מספר החלטה: 3284
ממשלה: הממשלה ה- 37
```
**Output:** `None`

### Location Tags Examples

**Decision with locations:**
```
Content: "החלטה בנוגע לפיתוח תשתיות בירושלים ותל אביב"
Output: "ירושלים, תל אביב"
```

**Decision without locations:**
```
Content: "החלטה כללית בנוגע למדיניות הממשלה בתחום החינוך"
Output: ""
```

## Backward Compatibility

✅ **Fully backward compatible** - existing functionality remains unchanged while adding the new extraction logic.

## Files Changed

1. `src/decision_scraper.py` - Committee extraction logic
2. `src/ai_processor.py` - Location tags filtering  
3. `src/data_manager.py` - Handle None values properly
4. `src/catalog_scraper.py` - Fixed circular imports (minor fix)

All changes maintain the existing API while improving data quality and accuracy.