# Project Brief - GOV2DB

## What
Automated scraper and analyzer for Israeli government decisions, extracting data from gov.il, enriching with AI-generated summaries and tags, and storing in a structured database.

## Who
- **End Users:** Researchers, journalists, NGOs, and citizens interested in Israeli government policy
- **Operators:** Data team maintaining the daily sync and quality

## Why
Government decisions are published as unstructured Hebrew text on gov.il, making it difficult to search, analyze trends, or track policy changes over time. This system creates a searchable, categorized database of all decisions since 1993.

## MVP Features (Completed)
- [x] Web scraping from gov.il catalog
- [x] Individual decision page extraction
- [x] AI summarization (Gemini 2.0 Flash)
- [x] Policy area tagging (45 categories)
- [x] Government body tagging (44 departments)
- [x] Location extraction
- [x] Operativity classification (operative/declarative)
- [x] Incremental processing (baseline tracking)
- [x] Database storage (Supabase)
- [x] Production deployment (Docker on CECI server)
- [x] Daily automated sync

## Current Stack
- **Language:** Python 3.8+
- **Scraping:** Selenium + undetected-chromedriver + BeautifulSoup4
- **AI:** Google Gemini 2.0 Flash
- **Database:** Supabase (PostgreSQL)
- **Deployment:** Docker container on Ubuntu server
- **Scheduling:** Cron with randomization (anti-detection)

## Out of Scope
- Frontend/UI (database is consumed via direct Supabase access)
- Real-time processing (batch daily sync is sufficient)
- Historical decisions before 1993
- Non-Hebrew content translation