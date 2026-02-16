# Requirements

## Core Functionality

### Data Collection
- [x] Scrape decision URLs from catalog page
- [x] Extract decision details (number, date, title, content)
- [x] Handle Hebrew RTL text properly
- [x] URL recovery with 3-tier fallback
- [x] Cloudflare WAF bypass with undetected-chromedriver
- [x] Rate limiting and randomization

### AI Processing
- [x] Generate 1-2 sentence summaries
- [x] Classify operativity (operative vs declarative)
- [x] Tag policy areas (45 authorized categories)
- [x] Tag government bodies (44 authorized departments)
- [x] Extract location mentions
- [x] Special category tags (5 cross-cutting themes)
- [x] Tag validation to prevent hallucinations

### Data Management
- [x] Incremental processing (baseline tracking)
- [x] Duplicate prevention via decision_key
- [x] Batch insertion (50 records per transaction)
- [x] CSV export functionality
- [x] Backup before migrations

### Quality Assurance
- [x] 20 QA scanners for different issues
- [x] 8 fixers for common problems
- [x] Inline validation during sync
- [x] Stratified sampling for testing
- [x] Hebrew-aware text matching

### Operations
- [x] Daily automated sync
- [x] Safety modes (regular/extra-safe)
- [x] Approval workflow (can be bypassed)
- [x] Comprehensive logging
- [x] Health checks for Docker
- [x] Production deployment

## Current Issues (To Fix)

### Database Quality
- [ ] Remaining tag mismatches (~20% after fixes)
- [ ] Investigate duplicate records
- [ ] Verify data completeness for 2024-2026
- [ ] Fix edge cases in operativity classification

### Performance
- [ ] Optimize AI batch processing
- [ ] Reduce memory usage for large batches
- [ ] Improve error recovery

### Monitoring
- [ ] Add success metrics dashboard
- [ ] Alert on sync failures
- [ ] Track AI costs