#!/usr/bin/env python3
"""
Process missing decisions that can't be scraped normally.

Handles:
- PDF-only decisions: downloads PDF, extracts text
- Minimal content pages: uses whatever text exists
- Missing decision 36_1022: constructs correct manifest entry

Usage:
    python bin/process_missing_decisions.py                # Scrape + AI + save
    python bin/process_missing_decisions.py --push         # Also push to DB
    python bin/process_missing_decisions.py --ai-only      # Skip scrape, reuse raw
"""

import json
import io
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.processors.ai import process_decision_with_ai
from src.gov_scraper.processors.qa import apply_inline_fixes
from src.gov_scraper.processors.incremental import prepare_for_database
from src.gov_scraper.scrapers.decision import _build_result_from_meta
from src.gov_scraper.config import get_pm_for_decision

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'scraped')
RAW_OUTPUT = os.path.join(OUTPUT_DIR, 'missing_decisions_raw.json')
FINAL_OUTPUT = os.path.join(OUTPUT_DIR, 'missing_decisions.json')

# The 16 unknown-drop keys from audit
MISSING_KEYS = {
    '27_3145', '29_5', '32_3356', '33_2078', '34_181', '34_3232',
    '36_1416', '36_1745', '37_1699', '37_1700', '37_2653', '37_2731',
    '37_2754', '37_2856', '37_2857', '37_2941'
}

# The real 1022 that's missing due to catalog number collision
EXTRA_ENTRIES = [
    {
        'url': 'https://www.gov.il/he/pages/dec1022_2022',
        'title': 'הצללה וקירור של המרחב העירוני באמצעות עצי רחוב במסגרת היערכות לשינויי האקלים',
        'decision_number': '1022',
        'decision_date': '2022-01-23',
        'government_number': '36',
        'prime_minister': 'נפתלי בנט',
        'committee': None,
        'description': 'החלטה מספר 1022 של הממשלה מיום 23.01.2022',
        'decision_key': '36_1022'
    }
]


def get_session():
    """Create a curl_cffi session with the openapi-gc gateway header set."""
    from curl_cffi import requests as curl_requests
    s = curl_requests.Session(impersonate='safari')
    s.headers.update({
        "x-client-id": "9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc",
        "Origin": "https://www.gov.il",
        "Referer": "https://www.gov.il",
    })
    return s


# Migrated 2026-05-11: gov.il moved ContentPageWebApi to openapi-gc gateway.
CONTENT_PAGE_API_BASE = (
    "https://openapi-gc.digital.gov.il/pub/cio/govil/rest/contentpage/v1/api/content-pages"
)


def fetch_api_data(slug: str, session) -> Optional[dict]:
    """Fetch Content Page API data for a slug from the openapi-gc gateway."""
    api_url = f"{CONTENT_PAGE_API_BASE}/{slug}?culture=he"
    try:
        resp = session.get(api_url, timeout=15)
        if resp.status_code == 200 and resp.text and resp.text.lstrip().startswith("{"):
            return resp.json()
        if resp.status_code != 200:
            logger.warning(f"API {resp.status_code} for {slug}: body[:120]={resp.text[:120]!r}")
    except Exception as e:
        logger.error(f"API call failed for {slug}: {e}")
    return None


def download_and_extract_pdf(pdf_url: str, session) -> Optional[str]:
    """Download a PDF and extract text content."""
    import pdfplumber

    try:
        resp = session.get(pdf_url, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"PDF download failed ({resp.status_code}): {pdf_url}")
            return None

        pdf_bytes = resp.content
        text_parts = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text.strip())

        full_text = '\n'.join(text_parts)
        if full_text:
            logger.info(f"Extracted {len(full_text)} chars from PDF")
            return full_text
        else:
            logger.warning(f"PDF had no extractable text: {pdf_url}")
            return None

    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return None


def scrape_decision_with_pdf_fallback(entry: dict, session) -> Optional[Dict[str, str]]:
    """
    Scrape a decision, falling back to PDF extraction if no inline content.

    Returns a dict in the same format as scrape_decision_via_api().
    """
    url = entry.get('url', '')
    slug = url.split('/pages/')[-1] if '/pages/' in url else ''
    dec_num = entry.get('decision_number', '?')
    key = entry.get('decision_key', '?')

    if not slug:
        logger.error(f"[{key}] Cannot extract slug from URL: {url}")
        return None

    api_data = fetch_api_data(slug, session)
    if not api_data:
        logger.warning(f"[{key}] No API data for slug {slug}")
        return None

    # Try inline HTML first (contentMain.htmlContents)
    html_contents = []
    content_main = api_data.get('contentMain', {})
    if isinstance(content_main, dict):
        html_contents = content_main.get('htmlContents', []) or []

    # Also check root-level htmlContents
    if not html_contents:
        html_contents = api_data.get('htmlContents', []) or []

    content = None
    if html_contents:
        from bs4 import BeautifulSoup
        html_parts = [item.get('sectionData', '') for item in html_contents if item.get('sectionData')]
        if html_parts:
            soup = BeautifulSoup(''.join(html_parts), 'html.parser')
            content = soup.get_text().strip()

    # If no inline content (or too short), try PDF
    if not content or len(content) < 40:
        logger.info(f"[{key}] No inline content ({len(content) if content else 0} chars), trying PDF...")

        files_data = api_data.get('contentSub', {}).get('filesToDownload', {})
        if isinstance(files_data, dict):
            for group in files_data.get('filesGroupItems', []):
                for item in group.get('items', []):
                    pdf_url = item.get('url', '')
                    fname = item.get('fileName', '')
                    if pdf_url and fname.lower().endswith('.pdf'):
                        logger.info(f"[{key}] Downloading PDF: {fname}")
                        pdf_text = download_and_extract_pdf(pdf_url, session)
                        if pdf_text and len(pdf_text) > len(content or ''):
                            content = pdf_text
                            break
                if content and len(content) >= 40:
                    break

    if not content or len(content) < 20:
        logger.warning(f"[{key}] No content found (inline or PDF)")
        return None

    # Enrich metadata from API
    enriched_meta = dict(entry)
    content_head = api_data.get('contentHead', {})
    if isinstance(content_head, dict):
        api_title = content_head.get('title')
        if api_title:
            enriched_meta['title'] = api_title

    return _build_result_from_meta(enriched_meta, content)


def phase_a_scrape(entries: List[dict]) -> List[dict]:
    """Phase A: Scrape all decisions (API + PDF fallback)."""
    logger.info(f"PHASE A: Scraping {len(entries)} decisions...")
    session = get_session()
    results = []

    for i, entry in enumerate(entries, 1):
        key = entry.get('decision_key', '?')
        logger.info(f"[{i}/{len(entries)}] Scraping {key}...")

        result = scrape_decision_with_pdf_fallback(entry, session)
        if result:
            results.append(result)
            logger.info(f"[{key}] OK — {len(result.get('decision_content', ''))} chars")
        else:
            logger.warning(f"[{key}] FAILED — no content")

        time.sleep(0.3)

    logger.info(f"Phase A complete: {len(results)}/{len(entries)} scraped")
    return results


def phase_b_ai_process(scraped: List[dict]) -> List[dict]:
    """Phase B: AI process each decision with Gemini."""
    logger.info(f"PHASE B: AI processing {len(scraped)} decisions...")
    results = []

    for i, decision in enumerate(scraped, 1):
        key = decision.get('decision_key', '?')
        logger.info(f"[{i}/{len(scraped)}] AI processing {key}...")

        try:
            processed = process_decision_with_ai(decision)
            if processed:
                processed = apply_inline_fixes(processed)
                results.append(processed)
                logger.info(f"[{key}] AI OK — summary: {processed.get('summary', '')[:60]}...")
            else:
                logger.warning(f"[{key}] AI returned None")
        except Exception as e:
            logger.error(f"[{key}] AI failed: {e}")

        time.sleep(1)

    logger.info(f"Phase B complete: {len(results)}/{len(scraped)} processed")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Process missing decisions (PDF + AI)')
    parser.add_argument('--push', action='store_true', help='Push to DB after processing')
    parser.add_argument('--ai-only', action='store_true', help='Skip scraping, reuse raw data')
    parser.add_argument('--verbose', action='store_true', help='Debug logging')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 70)
    print("PROCESS MISSING DECISIONS (PDF + AI Pipeline)")
    print("=" * 70)

    # Load manifest entries for the 16 missing keys + the extra 1022
    manifest_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'catalog_manifest.json')
    manifest = json.load(open(manifest_path, 'r', encoding='utf-8'))
    entries = [e for e in manifest if e.get('decision_key') in MISSING_KEYS]
    entries.extend(EXTRA_ENTRIES)

    # Check which are already in DB
    client = get_supabase_client()
    all_keys = [e['decision_key'] for e in entries]
    resp = client.table('israeli_government_decisions').select('decision_key').in_('decision_key', all_keys).execute()
    existing = {r['decision_key'] for r in resp.data}

    if existing:
        logger.info(f"Skipping {len(existing)} already in DB: {existing}")
        entries = [e for e in entries if e['decision_key'] not in existing]

    if not entries:
        print("All decisions already in DB. Nothing to do.")
        return

    print(f"\nProcessing {len(entries)} decisions:")
    for e in entries:
        print(f"  {e['decision_key']} — {e.get('title', '')[:60]}")

    # Phase A: Scrape
    if args.ai_only and os.path.exists(RAW_OUTPUT):
        logger.info(f"Loading existing raw data from {RAW_OUTPUT}")
        scraped = json.load(open(RAW_OUTPUT, 'r', encoding='utf-8'))
    else:
        scraped = phase_a_scrape(entries)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(RAW_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(scraped, f, ensure_ascii=False, indent=2)
        logger.info(f"Raw data saved to {RAW_OUTPUT}")

    if not scraped:
        print("\nNo decisions were scraped successfully.")
        return

    # Phase B: AI
    processed = phase_b_ai_process(scraped)

    if not processed:
        print("\nNo decisions were AI-processed successfully.")
        return

    # Save final output
    with open(FINAL_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(processed)} processed decisions to {FINAL_OUTPUT}")

    # Phase 3: Push to DB
    if args.push:
        print(f"\nPushing {len(processed)} decisions to DB...")
        from src.gov_scraper.db.dal import insert_decisions_batch

        # Prepare for DB
        db_ready = prepare_for_database(processed)
        inserted, errors = insert_decisions_batch(db_ready)

        print(f"Inserted: {inserted}")
        if errors:
            print(f"Errors: {len(errors)}")
            for e in errors[:5]:
                print(f"  {e}")
    else:
        print(f"\nDry run complete. Use --push to insert into DB.")
        print(f"Or run: python bin/push_local.py --file {FINAL_OUTPUT} --push")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Entries to process: {len(entries)}")
    print(f"  Scraped:           {len(scraped)}")
    print(f"  AI processed:      {len(processed)}")
    failed_keys = set(e['decision_key'] for e in entries) - set(p['decision_key'] for p in processed)
    if failed_keys:
        print(f"  Failed ({len(failed_keys)}):")
        for k in sorted(failed_keys):
            print(f"    {k}")


if __name__ == '__main__':
    main()
