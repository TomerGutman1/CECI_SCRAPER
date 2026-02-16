# Roadmap

## Phase -1: Already Built ✅
- Web scraping pipeline
- AI processing with Gemini
- Database schema and operations
- Production deployment
- Daily sync automation
- QA system (20 scanners, 8 fixers)
- Tag migration for 25K records
- Special category tags

## Phase 0: Adopt & Stabilize (Current)
**Goal:** Organize project structure and prepare for DB fixes

- [x] Streamline CLAUDE.md documentation
- [x] Create .planning structure
- [x] Extract implementation details to separate docs
- [ ] Add standard slash commands
- [ ] Update project hooks
- [ ] Commit changes

## Phase 1: Database Quality Audit
**Goal:** Identify and document all data quality issues

- [ ] Run full DB scan for duplicates
- [ ] Analyze tag mismatch patterns
- [ ] Check data completeness by year
- [ ] Document findings in DB-INVESTIGATION-PLAN.md
- [ ] Create fix priority list

## Phase 2: Critical DB Fixes
**Goal:** Fix highest-impact data quality issues

- [ ] Remove duplicate records
- [ ] Fix remaining operativity misclassifications
- [ ] Re-tag records with high-confidence mismatches
- [ ] Re-scrape truncated content
- [ ] Verify all 2024-2026 decisions present

## Phase 3: Monitoring & Reliability
**Goal:** Prevent future issues with better monitoring

- [ ] Add success metrics tracking
- [ ] Implement alert system for failures
- [ ] Create data quality dashboard
- [ ] Add automatic retry for failed syncs
- [ ] Track AI costs and usage

## Phase 4: Performance Optimization
**Goal:** Improve efficiency and reduce costs

- [ ] Optimize AI batch processing
- [ ] Reduce memory usage
- [ ] Implement caching for common operations
- [ ] Parallelize QA scanning
- [ ] Optimize database queries

## Phase 5: Enhanced Analysis
**Goal:** Add more value through deeper analysis

- [ ] Trend analysis across years
- [ ] Decision impact scoring
- [ ] Related decisions linking
- [ ] Minister/committee analytics
- [ ] Export to various formats (JSON, Excel, etc.)

## Future Ideas (Backlog)
- API endpoint for external access
- Real-time sync (not just daily)
- English translation of summaries
- Visual dashboard
- Historical decisions pre-1993
- Integration with Knesset data