# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Israeli government decisions scraper project designed to extract, process, and analyze government decisions from the official Israeli government website (`https://www.gov.il/he/collectors/policies`). The project combines web scraping, Hebrew text processing, and AI-powered content analysis.
## Objective

Create a Python script to scrape and process government decisions from the official Israeli government database:

* Base URL:

  ```
  https://www.gov.il/he/collectors/policies?Type=30280ed5-306f-4f0b-a11d-cacf05d36648
  ```
* Pagination format:

  ```
  https://www.gov.il/he/collectors/policies?Type=30280ed5-306f-4f0b-a11d-cacf05d36648&skip=10&limit=1000
  ```

## Required Data Extraction

Each decision URL should yield these parameters:

### Directly from the text

* `decision_date`: Specified after "תאריך פרסום:"
* `decision_number`: Specified clearly as "מספר החלטה:"
* `committee`: Specified clearly after "ועדות שרים:"
* `decision_title`: From the page content
* `decision_content`: Full textual content
* `decision_url`: The direct URL of the decision page
* `government_number`: Currently fixed as `37`
* `prime_minister`: Currently fixed as `בנימין נתניהו`
* `decision_key`: Concatenation of `government_number` and `decision_number` (e.g., `37_3719`)

### Generated via OpenAI GPT

* `summary`: Concise summary of the decision content
* `operativity`: Operational status or implications
* `tags_policy_area`: Policy areas related
* `tags_government_body`: Relevant government bodies
* `tags_location`: Relevant geographic locations
* `all_tags`: Aggregation of all decision tags

## Project Setup and Structure

Create a well-organized project with the following structure:

```
gov_decisions_scraper/
├── data/
│   └── decisions_data.csv
├── logs/
│   └── scraper.log
├── src/
│   ├── scraper.py
│   ├── parser.py
│   ├── gpt_utils.py
│   └── config.py
├── requirements.txt
└── .env
```

## Current State

This repository contains **specifications and sample data** rather than implemented code. Key files:
- `guidelines for scraper.txt` - Complete implementation specifications
- `israeli_government_decisions_rows (1).csv` - Sample dataset with 99 processed decisions
- `page_0_source.html` - Raw HTML from target website for testing
- `raw_text6.txt` - Extracted text content

## Target Architecture

The guidelines specify implementing this structure:
```
src/
├── scraper.py        # Main pagination and HTTP handling
├── parser.py         # BeautifulSoup HTML parsing for Hebrew content
├── gpt_utils.py      # OpenAI API integration for content analysis
└── config.py         # URLs, retry logic, headers configuration
```

## Data Schema

The system processes 19 fields per decision:
- **Direct extraction** (from Hebrew labels): `decision_date` (תאריך פרסום), `decision_number` (מספר החלטה), `committee` (ועדות שרים)
- **Fixed values**: `government_number` (37), `prime_minister` (בנימין נתניהו)
- **AI-generated**: `summary`, `operativity`, `tags_policy_area`, `tags_government_body`, `tags_location`, `all_tags`

## Development Commands

When implementing, use these patterns:
```bash
# Setup
pip install -r requirements.txt

# Environment
echo "OPENAI_API_KEY=your_key" > .env

# Run scraper
python src/scraper.py

# Test with small batch
python src/scraper.py --limit 10
```

## Critical Implementation Requirements

**Error Handling**: 5-retry logic required for all HTTP requests and OpenAI API calls with comprehensive logging to `logs/scraper.log`

**Hebrew Text Processing**: Extract data using specific Hebrew labels ("תאריך פרסום:", "מספר החלטה:", "ועדות שרים:")

**Pagination**: Handle `skip` and `limit` parameters for large datasets (initial run: 100-200 decisions, subsequent: ~10)

**CSV Output**: Use UTF-8-BOM encoding for Hebrew text compatibility

**AI Integration**: Use GPT-3.5-Turbo for automated summarization and policy area tagging

## Dependencies

Core libraries: `requests`, `beautifulsoup4`, `pandas`, `openai`, `python-dotenv`, `logging`