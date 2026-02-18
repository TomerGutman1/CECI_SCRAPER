#!/usr/bin/env python3
"""Check suspicious tagging cases."""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client

# Suspicious cases to investigate
SUSPICIOUS = [
    ("37_3272", "החברה הערבית"),  # יום המודעות למחלת הסרטן
    ("37_2903", "נשים ומגדר"),   # מדענית ראשית - just because feminine?
    ("37_2900", "נשים ומגדר"),   # ראש היחידה לרישוי - is this a woman?
    ("37_3612", "שיקום הדרום"),  # קידום מדיניות הממשלה - too generic?
]

def check_decision(key, tag):
    client = get_supabase_client()
    resp = client.table('israeli_government_decisions').select(
        'decision_key, decision_title, decision_content, tags_policy_area, summary'
    ).eq('decision_key', key).execute()

    if not resp.data:
        print(f"Not found: {key}")
        return

    dec = resp.data[0]
    content = dec.get('decision_content', '')[:2000]

    print(f"\n{'='*70}")
    print(f"Key: {key}")
    print(f"Tag being verified: {tag}")
    print(f"Title: {dec.get('decision_title')}")
    print(f"All tags: {dec.get('tags_policy_area')}")
    print(f"Summary: {dec.get('summary')}")
    print(f"\nContent (first 2000 chars):")
    print(content)
    print("=" * 70)

for key, tag in SUSPICIOUS:
    check_decision(key, tag)
