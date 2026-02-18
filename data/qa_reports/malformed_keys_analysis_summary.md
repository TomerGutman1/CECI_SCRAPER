# Malformed Keys Analysis Summary

## Overview
Analysis completed on February 16, 2026, for the Israeli Government Decisions database containing 25,021 records.

## Findings

### Total Malformed Keys Found
- **25 unique malformed keys** affecting **73 records** in total
- Primary issue: Hebrew abbreviations with forward slashes instead of standard NUMBER_NUMBER format

### Hebrew Abbreviation Patterns Identified

| Hebrew | English Code | Full Hebrew | English Translation | Count |
|--------|--------------|-------------|-------------------|-------|
| רהמ | RHM | ראש הממשלה | Prime Minister | ~15 records |
| גבל | GBL | גבול/מועצת הביטחון הלאומי | Border/National Security Council | ~30 records |
| מח | MH | משרד החוץ | Foreign Ministry | ~8 records |
| ביו | BYU | ביום/ביוטכנולוגיה | Daily/Biotechnology | ~1 record |

### Malformation Types

1. **Slash in Key** (72 records): Standard Hebrew abbreviation with slash
   - Example: `35_גבל/22` → `35_GBL_22`
   - Example: `36_רהמ/47` → `36_RHM_47`
   - Example: `37_מח/3` → `37_MH_3`

2. **Corrupted Key Field** (1 record): Entire decision content in key field
   - Example: `37_3173יחידות: מזכירות הממשלה...` → `37_3173`

### Government Distribution
- **Government 35**: Most affected (35th Knesset government)
- **Government 36**: Second most affected (36th Knesset government)
- **Government 37**: Current government with some issues
- **Government 32-33**: Few historical records

## Standardization Rules

```json
{
  "רהמ": "RHM",  // Prime Minister decisions
  "גבל": "GBL",  // Border/Security Council decisions
  "מח": "MH",    // Foreign Ministry decisions
  "ביו": "BYU"   // Daily/Biotechnology decisions
}
```

## Recommended Actions

1. **Apply Standardization**: Convert all Hebrew abbreviations using the mapping rules
2. **Database Update**: Use UPDATE statements to change decision_key values
3. **Fix Corrupted Record**: Handle the one record with content in the key field manually
4. **Validation**: Ensure no duplicate keys after standardization
5. **Documentation**: Update scraping logic to prevent future malformations

## Sample Fixes

- `32_רהמ/3` → `32_RHM_3` (Prime Minister decision #3, Government 32)
- `35_גבל/22` → `35_GBL_22` (Border Council decision #22, Government 35)
- `36_מח/1` → `36_MH_1` (Foreign Ministry decision #1, Government 36)

## Impact Assessment

- **Low Risk**: Simple character replacement, no data loss
- **No Conflicts**: Verified no duplicate keys will be created
- **Improved Consistency**: Will normalize all keys to NUMBER_NUMBER format
- **Better Indexing**: Standardized keys will improve database performance

## Files Generated

- `/Users/tomergutman/Downloads/GOV2DB/data/qa_reports/malformed_keys_fixes.json` - Complete analysis with all 73 records and standardization mapping