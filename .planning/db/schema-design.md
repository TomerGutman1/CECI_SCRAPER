# Database Schema Design

## Current Schema

### Table: `israeli_government_decisions`

```sql
CREATE TABLE israeli_government_decisions (
    decision_key VARCHAR PRIMARY KEY,  -- Format: {gov_num}_{decision_num}
    decision_number VARCHAR NOT NULL,
    decision_date DATE NOT NULL,
    decision_title TEXT NOT NULL,
    decision_content TEXT NOT NULL,
    committee_type VARCHAR,
    url VARCHAR,
    summary TEXT,
    operativity VARCHAR CHECK (operativity IN ('אופרטיבית', 'דקלרטיבית')),
    tags_policy_area TEXT,        -- Comma-separated, from new_tags.md
    tags_government_body TEXT,    -- Comma-separated, from new_departments.md
    tags_location TEXT,           -- Comma-separated locations
    government_number INTEGER DEFAULT 37,
    prime_minister VARCHAR DEFAULT 'בנימין נתניהו',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_decision_date ON israeli_government_decisions(decision_date DESC);
CREATE INDEX idx_government_number ON israeli_government_decisions(government_number);
CREATE INDEX idx_operativity ON israeli_government_decisions(operativity);
```

## Field Details

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| decision_key | VARCHAR | PRIMARY KEY | Composite key: `{gov}_{decision}` |
| decision_number | VARCHAR | NOT NULL | Original decision number (may contain letters) |
| decision_date | DATE | NOT NULL | Decision date in YYYY-MM-DD format |
| decision_title | TEXT | NOT NULL | Hebrew title |
| decision_content | TEXT | NOT NULL | Full Hebrew text (can be very long) |
| committee_type | VARCHAR | | Committee name if applicable |
| url | VARCHAR | | Source URL on gov.il |
| summary | TEXT | | AI-generated 1-2 sentence summary |
| operativity | VARCHAR | CHECK | Either 'אופרטיבית' or 'דקלרטיבית' |
| tags_policy_area | TEXT | | Comma-separated, validated against 45 tags |
| tags_government_body | TEXT | | Comma-separated, validated against 44 bodies |
| tags_location | TEXT | | Comma-separated location mentions |
| government_number | INTEGER | DEFAULT 37 | Israeli government number |
| prime_minister | VARCHAR | DEFAULT | Current PM name in Hebrew |
| created_at | TIMESTAMP | DEFAULT NOW | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW | Last modification time |

## Design Decisions

### Why Comma-Separated Tags (not normalized)
- Simpler queries for read-heavy workload
- Easier AI integration (returns comma-separated strings)
- Supabase REST API handles arrays well
- Trade-off: Less flexible for complex tag queries

### Why VARCHAR for decision_number (not INTEGER)
- Some decisions have letter suffixes (e.g., "dec3173a-2025")
- Preserves original format from source

### Why TEXT for content (not VARCHAR)
- Decisions can be very long (10K+ characters)
- No practical length limit needed

### Why decision_key composite
- Unique across all governments
- Human-readable format
- Allows for government transitions

## Known Issues to Fix

1. **No RLS Policies** - Currently using service role key (security risk)
2. **Missing Indexes** - Need indexes on tag fields for search
3. **No Audit Trail** - Should track who changed what
4. **No Versioning** - Can't track decision updates over time
5. **Tag Storage** - Comma-separated is limiting for complex queries

## Proposed Improvements

```sql
-- Add missing indexes
CREATE INDEX idx_tags_policy ON israeli_government_decisions USING GIN (string_to_array(tags_policy_area, ','));
CREATE INDEX idx_tags_body ON israeli_government_decisions USING GIN (string_to_array(tags_government_body, ','));

-- Add audit fields
ALTER TABLE israeli_government_decisions
ADD COLUMN last_qa_check TIMESTAMP,
ADD COLUMN qa_issues TEXT,
ADD COLUMN data_quality_score INTEGER;

-- Add full-text search
ALTER TABLE israeli_government_decisions
ADD COLUMN search_vector tsvector;

CREATE INDEX idx_search ON israeli_government_decisions USING GIN (search_vector);
```