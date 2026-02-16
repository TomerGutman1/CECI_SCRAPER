# Architectural Decisions

## Tech Stack Decisions

### Python + Selenium (Chosen)
**Why:** Gov.il heavily uses JavaScript rendering. Selenium provides reliable browser automation for dynamic content.
**Alternatives Considered:** Scrapy (rejected - couldn't handle JS), Playwright (not mature enough in 2024)

### Gemini 2.0 Flash for AI
**Why:** Best Hebrew language support, fast response times, good cost-performance ratio
**Alternatives Considered:** GPT-4 (more expensive), Claude (limited Hebrew), local models (poor Hebrew quality)

### Supabase for Database
**Why:** Managed PostgreSQL with built-in auth, RLS, and REST API. Good free tier.
**Alternatives Considered:** Raw PostgreSQL (more maintenance), MongoDB (less structured), Firebase (not ideal for relational data)

### undetected-chromedriver
**Why:** Bypasses Cloudflare and other anti-bot detection
**Decision Date:** February 2026 when Cloudflare started blocking

## Design Decisions

### Incremental Processing with Baseline
**Why:** Efficient daily syncs without re-processing everything. Baseline tracking prevents duplicates.
**Trade-off:** Can miss decisions published out of order (solved with safety modes)

### Tag Validation Algorithm
**Why:** Prevents AI hallucinations by validating against authorized lists
**Implementation:** 3-step validation (exact match → word overlap → AI fallback)

### Batch Processing (50 records)
**Why:** Balance between transaction size and error recovery
**Trade-off:** Larger batches are faster but harder to debug failures

### Decision Key Format
**Format:** `{government_number}_{decision_number}`
**Why:** Unique across all governments, human-readable, sortable

### Hebrew Text Normalization
**Why:** Remove RTL marks and zero-width spaces that break searches
**Trade-off:** Might lose some formatting nuances

### Randomized Sync Schedule
**Why:** Avoid predictable patterns that trigger anti-scraping measures
**Implementation:** 21-34 hour random intervals

## QA System Design

### Scanners vs Fixers Separation
**Why:** Safe read-only analysis separate from dangerous write operations
**Benefit:** Can run scans frequently without risk

### Stratified Sampling
**Why:** Representative sample across all years for testing
**Implementation:** 20% default, configurable, with seed for reproducibility

### Inline Validation (Non-blocking)
**Why:** Warn about issues without stopping the sync pipeline
**Trade-off:** Some bad data gets through but system stays running

## Deployment Decisions

### Docker Container
**Why:** Consistent environment, easy deployment, includes Chrome
**Base Image:** selenium/standalone-chrome (includes browser)

### No Frontend/UI
**Why:** Data consumed directly via Supabase console/API
**Trade-off:** Less user-friendly but much simpler to maintain