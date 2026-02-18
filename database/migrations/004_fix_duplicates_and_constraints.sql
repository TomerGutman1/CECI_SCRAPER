-- ===================================================================
-- Critical Database Integrity Fix: Duplicate Removal and Unique Constraints
-- ===================================================================
-- ISSUE: 7,230 unique decision_keys with duplicates (36% of database)
-- IMPACT: Violates data integrity, causes query errors, inflated counts
-- SOLUTION: Remove duplicates, enforce unique constraints, prevent re-occurrence
--
-- Migration: 004_fix_duplicates_and_constraints.sql
-- Date: 2026-02-18
-- Critical Priority: MUST run immediately
-- ===================================================================

BEGIN;

-- Create audit table for tracking duplicate removal
CREATE TABLE IF NOT EXISTS duplicate_removal_audit (
    id SERIAL PRIMARY KEY,
    operation_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    operation_type VARCHAR(50) NOT NULL,
    decision_key VARCHAR(100),
    records_affected INTEGER DEFAULT 0,
    details JSONB,
    status VARCHAR(20) DEFAULT 'SUCCESS'
);

-- Log start of migration
INSERT INTO duplicate_removal_audit (operation_type, details)
VALUES ('MIGRATION_START', jsonb_build_object(
    'migration', '004_fix_duplicates_and_constraints',
    'description', 'Fix duplicate decision_keys and add unique constraints'
));

-- ===================================================================
-- 1. ANALYZE CURRENT DUPLICATE SITUATION
-- ===================================================================

-- Create temporary table for duplicate analysis
CREATE TEMP TABLE duplicate_analysis AS
WITH duplicate_stats AS (
    SELECT
        decision_key,
        COUNT(*) as occurrence_count,
        MIN(id) as oldest_id,
        MAX(id) as newest_id,
        MIN(created_at) as first_created,
        MAX(created_at) as last_created,
        ARRAY_AGG(id ORDER BY id) as all_ids
    FROM israeli_government_decisions
    WHERE decision_key IS NOT NULL
      AND decision_key != ''
    GROUP BY decision_key
    HAVING COUNT(*) > 1
)
SELECT
    decision_key,
    occurrence_count,
    oldest_id,
    newest_id,
    first_created,
    last_created,
    all_ids,
    -- Determine which record to keep (newest by created_at, fallback to highest id)
    CASE
        WHEN last_created > first_created THEN
            (SELECT id FROM israeli_government_decisions
             WHERE decision_key = ds.decision_key
             ORDER BY created_at DESC, id DESC LIMIT 1)
        ELSE newest_id
    END as keep_id
FROM duplicate_stats ds;

-- Log duplicate analysis
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
SELECT
    'DUPLICATE_ANALYSIS',
    COUNT(*),
    jsonb_build_object(
        'total_duplicate_keys', COUNT(*),
        'total_affected_records', SUM(occurrence_count),
        'max_occurrences', MAX(occurrence_count),
        'avg_occurrences', ROUND(AVG(occurrence_count), 2)
    )
FROM duplicate_analysis;

-- ===================================================================
-- 2. BACKUP DUPLICATE RECORDS
-- ===================================================================

-- Create backup table for duplicate records being removed
CREATE TABLE duplicate_records_backup AS
SELECT
    d.*,
    CURRENT_TIMESTAMP as backup_timestamp,
    'DUPLICATE_REMOVAL_004' as backup_reason
FROM israeli_government_decisions d
INNER JOIN duplicate_analysis da ON d.decision_key = da.decision_key
WHERE d.id != da.keep_id;

-- Log backup creation
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
SELECT
    'BACKUP_CREATED',
    COUNT(*),
    jsonb_build_object(
        'backup_table', 'duplicate_records_backup',
        'backup_timestamp', CURRENT_TIMESTAMP
    )
FROM duplicate_records_backup;

-- ===================================================================
-- 3. IDENTIFY AND HANDLE SPECIAL CASES
-- ===================================================================

-- Check for records where duplicates have different content
CREATE TEMP TABLE content_different_duplicates AS
WITH duplicate_content_analysis AS (
    SELECT
        da.decision_key,
        da.occurrence_count,
        COUNT(DISTINCT d.decision_title) as unique_titles,
        COUNT(DISTINCT d.decision_content) as unique_contents,
        COUNT(DISTINCT d.decision_date) as unique_dates,
        COUNT(DISTINCT d.committee) as unique_committees
    FROM duplicate_analysis da
    JOIN israeli_government_decisions d ON d.decision_key = da.decision_key
    GROUP BY da.decision_key, da.occurrence_count
)
SELECT *
FROM duplicate_content_analysis
WHERE unique_titles > 1 OR unique_contents > 1 OR unique_dates > 1 OR unique_committees > 1;

-- Log content analysis
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
SELECT
    'CONTENT_ANALYSIS',
    COUNT(*),
    jsonb_build_object(
        'keys_with_different_content', COUNT(*),
        'description', 'Decision keys where duplicates have different content - these need manual review'
    )
FROM content_different_duplicates;

-- ===================================================================
-- 4. REMOVE DUPLICATE RECORDS
-- ===================================================================

-- Delete duplicate records (keep the newest/highest ID)
WITH records_to_delete AS (
    SELECT d.id
    FROM israeli_government_decisions d
    INNER JOIN duplicate_analysis da ON d.decision_key = da.decision_key
    WHERE d.id != da.keep_id
)
DELETE FROM israeli_government_decisions
WHERE id IN (SELECT id FROM records_to_delete);

-- Log deletion results
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
VALUES (
    'DUPLICATES_REMOVED',
    (SELECT COUNT(*) FROM duplicate_records_backup),
    jsonb_build_object(
        'description', 'Removed duplicate records, kept newest record for each decision_key',
        'backup_available', true
    )
);

-- ===================================================================
-- 5. HANDLE MALFORMED DECISION KEYS
-- ===================================================================

-- Identify malformed keys (non-standard format)
CREATE TEMP TABLE malformed_keys AS
SELECT
    id,
    decision_key,
    government_number,
    decision_number,
    decision_title,
    decision_date,
    CASE
        -- Hebrew committee codes
        WHEN decision_key ~ '^[0-9]+_רהמ/[0-9]+$' THEN
            government_number || '_COMMITTEE_' || REGEXP_REPLACE(decision_key, '^[0-9]+_רהמ/([0-9]+)$', '\1')
        WHEN decision_key ~ '^[0-9]+_מח/[0-9]+$' THEN
            government_number || '_SECURITY_' || REGEXP_REPLACE(decision_key, '^[0-9]+_מח/([0-9]+)$', '\1')
        WHEN decision_key ~ '^[0-9]+_ביו/[0-9]+$' THEN
            government_number || '_ECON_' || REGEXP_REPLACE(decision_key, '^[0-9]+_ביו/([0-9]+)$', '\1')
        -- Other patterns with Hebrew or special characters
        ELSE government_number || '_SPECIAL_' || REGEXP_REPLACE(decision_key, '[^0-9]', '', 'g')
    END as corrected_key
FROM israeli_government_decisions
WHERE decision_key IS NOT NULL
  AND decision_key != ''
  AND NOT decision_key ~ '^[0-9]+_[0-9]+$';

-- Update malformed keys
UPDATE israeli_government_decisions d
SET
    decision_key = mk.corrected_key,
    updated_at = CURRENT_TIMESTAMP
FROM malformed_keys mk
WHERE d.id = mk.id;

-- Log malformed key fixes
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
SELECT
    'MALFORMED_KEYS_FIXED',
    COUNT(*),
    jsonb_build_object(
        'description', 'Fixed malformed decision_key formats',
        'pattern_committee', COUNT(*) FILTER (WHERE corrected_key LIKE '%_COMMITTEE_%'),
        'pattern_security', COUNT(*) FILTER (WHERE corrected_key LIKE '%_SECURITY_%'),
        'pattern_econ', COUNT(*) FILTER (WHERE corrected_key LIKE '%_ECON_%'),
        'pattern_special', COUNT(*) FILTER (WHERE corrected_key LIKE '%_SPECIAL_%')
    )
FROM malformed_keys;

-- ===================================================================
-- 6. CREATE UNIQUE CONSTRAINT
-- ===================================================================

-- Verify no duplicates remain before adding constraint
DO $$
DECLARE
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT decision_key, COUNT(*)
        FROM israeli_government_decisions
        WHERE decision_key IS NOT NULL AND decision_key != ''
        GROUP BY decision_key
        HAVING COUNT(*) > 1
    ) dups;

    IF duplicate_count > 0 THEN
        RAISE EXCEPTION 'Cannot add unique constraint: % duplicate decision_keys still exist', duplicate_count;
    END IF;

    INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
    VALUES (
        'CONSTRAINT_VALIDATION',
        duplicate_count,
        jsonb_build_object('status', 'PASSED', 'remaining_duplicates', 0)
    );
END $$;

-- Add unique constraint on decision_key
ALTER TABLE israeli_government_decisions
ADD CONSTRAINT uk_israeli_govt_decisions_decision_key
UNIQUE (decision_key);

-- Add not null constraint to prevent null keys
ALTER TABLE israeli_government_decisions
ALTER COLUMN decision_key SET NOT NULL;

-- Add check constraint for key format validation
ALTER TABLE israeli_government_decisions
ADD CONSTRAINT ck_decision_key_format
CHECK (
    decision_key ~ '^[0-9]+_[0-9]+[א-ת]?$' OR              -- Standard: 37_1234 or 37_1234א
    decision_key ~ '^[0-9]+_[0-9]+[a-z]?$' OR              -- With English letter: 37_1234a
    decision_key ~ '^[0-9]+_(COMMITTEE|SECURITY|ECON|SPECIAL)_[0-9]+$'  -- Special types
);

-- Log constraint creation
INSERT INTO duplicate_removal_audit (operation_type, details)
VALUES (
    'CONSTRAINTS_ADDED',
    jsonb_build_object(
        'unique_constraint', 'uk_israeli_govt_decisions_decision_key',
        'not_null_constraint', 'decision_key SET NOT NULL',
        'check_constraint', 'ck_decision_key_format',
        'status', 'SUCCESS'
    )
);

-- ===================================================================
-- 7. CREATE INDEXES FOR PERFORMANCE
-- ===================================================================

-- Index for decision_key uniqueness (automatically created by unique constraint)
-- Additional composite index for common queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decision_key_govt_date
ON israeli_government_decisions (decision_key, government_number, decision_date DESC);

-- Index for detecting potential duplicates during inserts
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_govt_decision_number_date
ON israeli_government_decisions (government_number, decision_number, decision_date DESC)
WHERE decision_number IS NOT NULL;

-- Log index creation
INSERT INTO duplicate_removal_audit (operation_type, details)
VALUES (
    'INDEXES_CREATED',
    jsonb_build_object(
        'decision_key_index', 'idx_decision_key_govt_date',
        'duplicate_detection_index', 'idx_govt_decision_number_date',
        'status', 'SUCCESS'
    )
);

-- ===================================================================
-- 8. UPDATE TABLE STATISTICS
-- ===================================================================

-- Update table statistics for query optimization
ANALYZE israeli_government_decisions;

-- Log final statistics
INSERT INTO duplicate_removal_audit (operation_type, records_affected, details)
SELECT
    'MIGRATION_COMPLETE',
    COUNT(*),
    jsonb_build_object(
        'total_records_remaining', COUNT(*),
        'unique_decision_keys', COUNT(DISTINCT decision_key),
        'duplicate_records_removed', (SELECT COUNT(*) FROM duplicate_records_backup),
        'malformed_keys_fixed', (
            SELECT records_affected
            FROM duplicate_removal_audit
            WHERE operation_type = 'MALFORMED_KEYS_FIXED'
        ),
        'constraints_added', 3,
        'indexes_created', 2,
        'backup_table', 'duplicate_records_backup'
    )
FROM israeli_government_decisions;

COMMIT;

-- ===================================================================
-- ROLLBACK INSTRUCTIONS (if needed)
-- ===================================================================

/*
-- TO ROLLBACK THIS MIGRATION (USE WITH EXTREME CAUTION):

BEGIN;

-- 1. Drop constraints
ALTER TABLE israeli_government_decisions DROP CONSTRAINT IF EXISTS uk_israeli_govt_decisions_decision_key;
ALTER TABLE israeli_government_decisions DROP CONSTRAINT IF EXISTS ck_decision_key_format;
ALTER TABLE israeli_government_decisions ALTER COLUMN decision_key DROP NOT NULL;

-- 2. Restore backed up records (if needed)
INSERT INTO israeli_government_decisions
SELECT
    id, government_number, decision_number, decision_date, decision_title,
    decision_content, committee, committee_type, operativity, summary,
    tags_policy_area, tags_government_body, tags_location, url,
    prime_minister, created_at, updated_at, decision_key
FROM duplicate_records_backup;

-- 3. Drop backup table
DROP TABLE duplicate_records_backup;

-- 4. Drop audit table
DROP TABLE duplicate_removal_audit;

COMMIT;

-- WARNING: This rollback will restore the duplicate problem!
-- Only use if migration causes critical issues.
*/

-- ===================================================================
-- VERIFICATION QUERIES
-- ===================================================================

/*
-- After migration, run these queries to verify success:

-- 1. Check for remaining duplicates
SELECT decision_key, COUNT(*) as count
FROM israeli_government_decisions
GROUP BY decision_key
HAVING COUNT(*) > 1;
-- Expected result: No rows

-- 2. Check constraint enforcement
INSERT INTO israeli_government_decisions (decision_key, government_number, decision_number)
VALUES ('TEST_DUPLICATE', 999, 9999);
INSERT INTO israeli_government_decisions (decision_key, government_number, decision_number)
VALUES ('TEST_DUPLICATE', 999, 9999);
-- Expected result: Unique constraint violation error

-- 3. Check malformed key validation
INSERT INTO israeli_government_decisions (decision_key, government_number, decision_number)
VALUES ('INVALID_FORMAT!@#', 999, 9999);
-- Expected result: Check constraint violation error

-- 4. Review audit log
SELECT * FROM duplicate_removal_audit ORDER BY operation_timestamp;

-- 5. Check backup table
SELECT COUNT(*) FROM duplicate_records_backup;
-- Expected: Number of duplicate records that were removed
*/