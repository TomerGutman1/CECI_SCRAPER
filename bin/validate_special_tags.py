#!/usr/bin/env python3
"""
Validate special category tags - check for false positives.

Fetches decisions with new special tags and shows excerpts for manual verification.
"""

import sys
import os
import random

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client

SPECIAL_TAGS = [
    "החברה הערבית",
    "החברה החרדית",
    "נשים ומגדר",
    "שיקום הצפון",
    "שיקום הדרום",
]

def fetch_decisions_with_special_tags(limit_per_tag=20):
    """Fetch decisions containing each special tag."""
    client = get_supabase_client()

    results = {}
    for tag in SPECIAL_TAGS:
        response = client.table('israeli_government_decisions').select(
            'decision_key, decision_title, decision_date, tags_policy_area, decision_content, summary'
        ).ilike('tags_policy_area', f'%{tag}%').order('decision_date', desc=True).limit(limit_per_tag).execute()

        results[tag] = response.data if response.data else []

    return results

def validate_tag_relevance(decision, tag):
    """Check if decision content supports the tag."""
    content = (decision.get('decision_content') or '').lower()
    title = (decision.get('decision_title') or '').lower()
    summary = (decision.get('summary') or '').lower()
    full_text = f"{title} {content} {summary}"

    # Keywords for each tag
    keywords = {
        "החברה הערבית": ["ערבי", "ערבית", "בדואי", "בדואים", "מגזר ערבי", "922", "550", "דרוזי", "דרוזים"],
        "החברה החרדית": ["חרדי", "חרדית", "חרדים", "ישיבות", "לימודי ליבה", "גיוס חרדים", "נתיבות חכמה"],
        "נשים ומגדר": ["נשים", "מגדר", "מגדרי", "שוויון מגדרי", "הטרדה מינית", "קידום נשים", "שכר שווה"],
        "שיקום הצפון": ["שיקום הצפון", "מפוני הצפון", "מלחמת הצפון", "יישובי הצפון", "גבול צפון"],
        "שיקום הדרום": ["שיקום הדרום", "עוטף עזה", "7 באוקטובר", "מנהלת תקומה", "חטופים", "מפוני הדרום", "נפגעי אירועי", "אירועי השביעי"],
    }

    tag_keywords = keywords.get(tag, [])
    found_keywords = [kw for kw in tag_keywords if kw in full_text]

    return found_keywords

def main():
    print("=" * 70)
    print("בדיקת False Positives לתגיות קטגוריות מיוחדות")
    print("=" * 70)

    print("\nמביא החלטות עם תגיות מיוחדות...")
    results = fetch_decisions_with_special_tags(limit_per_tag=20)

    total_checked = 0
    total_validated = 0
    issues = []

    for tag, decisions in results.items():
        print(f"\n{'='*60}")
        print(f"תגית: {tag} ({len(decisions)} החלטות)")
        print("=" * 60)

        for i, dec in enumerate(decisions[:20], 1):
            total_checked += 1
            found_keywords = validate_tag_relevance(dec, tag)

            status = "✅" if found_keywords else "⚠️"
            if found_keywords:
                total_validated += 1
            else:
                issues.append({
                    "tag": tag,
                    "decision_key": dec.get('decision_key'),
                    "title": dec.get('decision_title', '')[:80]
                })

            print(f"\n{i}. {status} {dec.get('decision_key')} ({dec.get('decision_date')})")
            print(f"   כותרת: {dec.get('decision_title', '')[:100]}")
            print(f"   תגיות: {dec.get('tags_policy_area', '')}")

            if found_keywords:
                print(f"   מילות מפתח שנמצאו: {', '.join(found_keywords)}")
            else:
                print(f"   ⚠️ לא נמצאו מילות מפתח תומכות!")
                # Show content excerpt for manual review
                content = dec.get('decision_content', '')[:300]
                print(f"   תוכן (קטע): {content}...")

    # Summary
    print("\n" + "=" * 70)
    print("סיכום")
    print("=" * 70)
    print(f"סה\"כ נבדקו: {total_checked}")
    print(f"אומתו (מילות מפתח נמצאו): {total_validated} ({100*total_validated/total_checked:.1f}%)")
    print(f"לבדיקה ידנית: {len(issues)} ({100*len(issues)/total_checked:.1f}%)")

    if issues:
        print("\nהחלטות לבדיקה ידנית:")
        for issue in issues:
            print(f"  - [{issue['tag']}] {issue['decision_key']}: {issue['title']}")

if __name__ == "__main__":
    main()
