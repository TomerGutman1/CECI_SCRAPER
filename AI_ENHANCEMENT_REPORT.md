
=== AI ENHANCEMENT PROCESSING REPORT ===
Generated: /Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json (75.3 MB)
Original:  /Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json (75.6 MB)

OVERVIEW:
Total Decisions Processed: 25,021
File Size Change: -0.3 MB

=== GOVERNMENT BODY VALIDATION ===
Total Original Bodies: 18,119
Total Enhanced Bodies: 15,769
Bodies Removed: 2,350
Bodies Normalized: 0
Decisions with Bodies Removed: 2,174

Most Frequently Dropped Bodies:
  משרד רה"מ: 279 times
  משרד הכלכלה והתעשייה: 240 times
  משרד האנרגיה והתשתיות: 218 times
  משרד הביטחון: 185 times
  משטרת ישראל: 174 times
  מנהל התכנון: 146 times
  שונות: 114 times
  ועדת השרים: 103 times
  משרד החדשנות המדע והטכנולוגיה: 96 times
  משרד הבריאות: 90 times

Normalization Examples:

=== SUMMARY PREFIX STRIPPING ===
Summaries with Prefixes Stripped: 0
Average Length Reduction: 0.0 characters
Total Original Summary Length: 5,800,232 chars
Total Enhanced Summary Length: 5,800,434 chars
Length Reduction: -202 chars (-0.0%)

Examples:

=== POLICY TAG VALIDATION ===
Original Unique Tags: 45
Enhanced Unique Tags: 45
Decisions with Tag Changes: 0
Total Tags Dropped: 0
Unauthorized Tags Found in Original: 0

Most Common Original Tags:
  חקיקה, משפט ורגולציה: 7,458
  תקציב, פיננסים, ביטוח ומיסוי: 4,925
  מינהל ציבורי ושירות המדינה: 4,338
  מדיני ביטחוני: 2,979
  מינויים: 2,627
  חוץ הסברה ותפוצות: 2,215
  רווחה ושירותים חברתיים: 2,137
  בריאות ורפואה: 2,112
  דיור, נדלן ותכנון: 2,062
  תחבורה ובטיחות בדרכים: 1,938

Most Common Enhanced Tags:
  חקיקה, משפט ורגולציה: 7,458
  תקציב, פיננסים, ביטוח ומיסוי: 4,925
  מינהל ציבורי ושירות המדינה: 4,338
  מדיני ביטחוני: 2,979
  מינויים: 2,627
  חוץ הסברה ותפוצות: 2,215
  רווחה ושירותים חברתיים: 2,137
  בריאות ורפואה: 2,112
  דיור, נדלן ותכנון: 2,062
  תחבורה ובטיחות בדרכים: 1,938

Some Unauthorized Tags in Original Data:

=== OPERATIVITY CLASSIFICATION ===
Total Operativity Changes: 956
Operative → Declarative: 956
Declarative → Operative: 0

Examples:
  34_3201: אופרטיבית → דקלרטיבית | הצעת חוק התקשורת (בזק ושידורים) (תיקון - קליטה בטלפון נייד ב...
  34_2577: אופרטיבית → דקלרטיבית | הצעת חוק בתי המשפט (תיקון - מינוי מומחה מטעם בית המשפט בתביע...
  34_2354: אופרטיבית → דקלרטיבית | הצעת חוק תאגידי מים וביוב (תיקון - צמצום מספר תאגידי המים וה...
  34_2124: אופרטיבית → דקלרטיבית | הצעת חוק שירות המילואים (תיקון - זכויות עובד שבן זוגו משרת ש...
  32_3868: אופרטיבית → דקלרטיבית | הצעת חוק-יסוד: תקציב המדינה לשנת 2012 של ח"כ דליה איציק ואחר...

=== ALL_TAGS REBUILDING ===
Decisions with all_tags Changes: 25,001
Average Original all_tags Length: 61.9 chars
Average Enhanced all_tags Length: 56.4 chars

Deduplication Examples:
  31_1542: 6 tags → 7 tags (1 duplicates removed)
  31_1105: 8 tags → 9 tags (1 duplicates removed)
  37_2802: 7 tags → 5 tags (1 duplicates removed)
  37_2338: 4 tags → 4 tags (1 duplicates removed)
  37_2217: 9 tags → 10 tags (1 duplicates removed)

=== IMPACT SUMMARY ===
✅ Government Body Cleanup: 2,350 irrelevant bodies removed
✅ Summary Optimization: 0 prefixes stripped
✅ Tag Validation: 0 decisions improved
✅ Operativity Correction: 956 classifications fixed
✅ Deduplication: 25,001 decisions with cleaner tags
✅ File Size Optimization: 0.3 MB saved

The AI enhancement process has successfully applied all improvements from the
post-processing pipeline to the production backup, resulting in cleaner,
more accurate, and more consistent government decision data.
