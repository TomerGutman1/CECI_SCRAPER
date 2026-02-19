#!/usr/bin/env python3
"""
Test script to verify AI tag assignment improvements.
"""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gov_scraper.processors.ai import process_decision_with_ai

# Sample test decision from recent data
test_decision = {
    "decision_title": "מינוי מנהל הרשות הלאומית לביטחון קהילתי",
    "decision_content": """מזכירות הממשלהמינוי מנהל הרשות הלאומית לביטחון קהילתיהחלטה מספר 3856 של ממשלה מיום 08.02.2026סוג: החלטות ממשלהמספר החלטה: 3856יחידות: מזכירות הממשלהתאריך תחולה: 08.02.2026ממשלה: הממשלה ה- 37תאריך פרסום: 08.02.2026 נושא ההחלטה:מינוי מנהל הרשות הלאומית לביטחון קהילתי מחליטים:בהתאם לסעיף 4 לחוק הרשות הלאומית לביטחון קהילתי, התשע\"ז-2017 ובהתאם לסעיף 23 לחוק שירות המדינה (מינויים), התשי\"ט-1959, על-פי הצעת השר לביטחון לאומי, למנות את אביטל חן לתפקיד מנהל הרשות לביטחון קהילתי לתקופה של ארבע שנים אשר ניתן יהיה להאריכה בארבע שנים נוספות. המינוי ייכנס לתוקף ביום י\"ב באדר התשפ\"ו (1 במרץ 2026). הנוסח המחייב של החלטות הממשלה הינו הנוסח השמור במזכירות הממשלה. הנוסח המחייב של הצעות חוק ודברי חקיקה הנזכרים בהחלטות הינו הנוסח המתפרסם ברשומות. החלטות תקציביות כפופות לחוק התקציב השנתי.""",
    "decision_date": "2026-02-08"
}

# Test case: PM travel (should be "מנהלתי", not multiple tags)
test_decision_2 = {
    "decision_title": "נסיעת ראש הממשלה לארצות הברית",
    "decision_content": """מזכירות הממשלהנסיעת ראש הממשלה לארצות הבריתהחלטה מספר 3864 של ממשלה מיום 10.02.2026סוג: החלטות ממשלהמספר החלטה: 3864יחידות: מזכירות הממשלהתאריך תחולה: 12.02.2026ממשלה: הממשלה ה- 37תאריך פרסום: 12.02.2026 נושא ההחלטה:נסיעת ראש הממשלה לארצות הבריתמחליטים: הממשלה רושמת לפניה את נסיעת ראש הממשלה לארצות הברית, לפגישה עם נשיא ארצות הברית, מיום 10.02.2026 עד יום 13.02.2026.ראש הממשלה מביא לידיעת השרים, בהתאם לסעיף 31 בתקנון לעבודת הממשלה, כי הוא ימנה את השר ישראל כ\"ץ לממלא-מקום יושב-ראש ועדת השרים לענייני ביטחון לאומי בעת היעדרו מן הארץ, מיום 10.02.2026 עד יום 13.02.2026 או עד לשובו של ראש הממשלה לארץ, לפי המוקדם מביניהם.מ ח ל י ט י ם, בהתאם לסעיף 16(ג) לחוק יסוד: הממשלה, לקבוע כי השר יריב לוין ימלא את מקום ראש הממשלה לצורך זימון ישיבות הממשלה וניהולן (אם יהיה צורך בכך) בעת היעדרו מן הארץ, מיום 10.02.2026 עד יום 13.02.2026 או עד לשובו של ראש הממשלה לארץ, לפי המוקדם מביניהם.ההחלטה התקבלה בהתאם לסעיף 19(א) בתקנון לעבודת הממשלה. הנוסח המחייב של החלטות הממשלה הינו הנוסח השמור במזכירות הממשלה. הנוסח המחייב של הצעות חוק ודברי חקיקה הנזכרים בהחלטות הינו הנוסח המתפרסם ברשומות. החלטות תקציביות כפופות לחוק התקציב השנתי.""",
    "decision_date": "2026-02-12"
}

def test_ai_improvements():
    """Test the improved AI prompting on sample decisions."""

    print("🧪 Testing AI Tag Assignment Improvements")
    print("="*60)

    test_cases = [
        ("Appointment Decision", test_decision),
        ("PM Travel Decision", test_decision_2)
    ]

    for test_name, decision in test_cases:
        print(f"\n📋 Test Case: {test_name}")
        print(f"Title: {decision['decision_title']}")

        try:
            # Process with improved AI
            result = process_decision_with_ai(decision, use_unified=True)

            print(f"✅ Summary: {result['summary'][:100]}...")
            print(f"✅ Operativity: {result['operativity']}")
            print(f"✅ Policy Areas: {result['tags_policy_area']}")
            print(f"✅ Government Bodies: {result['tags_government_body']}")
            print(f"✅ Locations: {result['tags_location']}")

            # Analyze tag count and relevance
            policy_tags = [tag.strip() for tag in result['tags_policy_area'].split(';') if tag.strip()]
            print(f"📊 Tag Count: {len(policy_tags)}")

            # Expected vs actual for specific test cases
            if test_name == "Appointment Decision":
                expected = ["מינויים"]
                if policy_tags == expected:
                    print("✅ PASS: Correctly tagged as appointment")
                else:
                    print(f"❌ FAIL: Expected {expected}, got {policy_tags}")

            elif test_name == "PM Travel Decision":
                expected = ["מנהלתי"]
                if len(policy_tags) == 1 and policy_tags[0] in ["מנהלתי", "מינויים"]:
                    print("✅ PASS: Correctly avoided over-tagging")
                else:
                    print(f"❌ FAIL: Over-tagged. Expected single administrative tag, got {policy_tags}")

        except Exception as e:
            print(f"❌ ERROR: {e}")

        print("-" * 40)

if __name__ == "__main__":
    test_ai_improvements()