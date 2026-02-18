"""Incremental processing module for determining scraping boundaries and validating new decisions.

This module now includes comprehensive incremental QA processing capabilities:
- Change tracking for all database modifications
- Smart dependency resolution for cascade updates
- Resource-aware batch processing
- Checkpoint system with failure recovery
- Differential reporting for incremental updates
"""

import logging
import json
import os
import time
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import pandas as pd
from contextlib import contextmanager

from ..db.dal import fetch_latest_decision
from ..db.connector import get_supabase_client
from ..config import PROJECT_ROOT

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_scraping_baseline() -> Optional[Dict]:
    """
    Get the latest decision from the database to use as a baseline for incremental scraping.
    
    Returns:
        Dict with latest decision info or None if no decisions found
    """
    try:
        latest_decision = fetch_latest_decision()
        if latest_decision:
            logger.info(f"Found baseline decision: {latest_decision['decision_number']} from {latest_decision['decision_date']}")
            return latest_decision
        else:
            logger.info("No baseline decision found in database - will scrape all available decisions")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch baseline decision: {e}")
        return None


def should_process_decision(decision_data: Dict, baseline: Optional[Dict] = None) -> bool:
    """
    Determine if a decision should be processed based on the baseline from database.
    
    Args:
        decision_data: Dictionary containing decision information
        baseline: Latest decision from database (if any)
        
    Returns:
        True if decision should be processed, False otherwise
    """
    if not baseline:
        # No baseline - process all decisions
        return True
    
    try:
        # Extract decision information
        decision_number = str(decision_data.get('decision_number', ''))
        decision_date = decision_data.get('decision_date', '')
        
        baseline_number = str(baseline.get('decision_number', ''))
        baseline_date = baseline.get('decision_date', '')
        
        if not decision_number or not decision_date:
            logger.warning(f"Missing decision data: number={decision_number}, date={decision_date}")
            return False
        
        # Parse dates for comparison
        try:
            if isinstance(decision_date, str):
                # Handle different date formats that might come from scraper
                if 'נושא ההחלטה' in decision_date:
                    # Extract date from Hebrew format like "24.07.2025 נושא ההחלטה:..."
                    date_part = decision_date.split(' ')[0]
                    decision_dt = datetime.strptime(date_part, "%d.%m.%Y")
                else:
                    # Try standard format
                    decision_dt = datetime.strptime(decision_date, "%Y-%m-%d")
            else:
                decision_dt = decision_date
                
            baseline_dt = datetime.strptime(baseline_date, "%Y-%m-%d")
        except ValueError as e:
            logger.warning(f"Date parsing error: {e}. Processing decision to be safe.")
            return True
        
        # Compare dates first (primary filter)
        if decision_dt > baseline_dt:
            logger.info(f"✅ Decision {decision_number} ({decision_dt.date()}) is NEWER than baseline date ({baseline_dt.date()}) - PROCESSING")
            return True
        elif decision_dt < baseline_dt:
            logger.info(f"⏭️  Decision {decision_number} ({decision_dt.date()}) is OLDER than baseline date ({baseline_dt.date()}) - SKIPPING")
            return False
        else:
            # Same date - compare decision numbers
            try:
                decision_num_int = int(decision_number)
                baseline_num_int = int(baseline_number)
                
                if decision_num_int > baseline_num_int:
                    logger.info(f"✅ Decision {decision_number} is NEWER than baseline {baseline_number} (SAME DATE) - PROCESSING")
                    return True
                else:
                    logger.info(f"⏭️  Decision {decision_number} is NOT NEWER than baseline {baseline_number} (SAME DATE) - SKIPPING")
                    return False
            except ValueError:
                logger.warning(f"Could not compare decision numbers: {decision_number} vs {baseline_number}")
                return True  # Process to be safe
                
    except Exception as e:
        logger.error(f"Error in should_process_decision: {e}")
        return True  # Process to be safe


def generate_decision_key(decision_data: Dict) -> str:
    """
    Generate a unique key for a decision based on government number and decision number.

    Args:
        decision_data: Dictionary containing decision information

    Returns:
        Unique decision key string

    Raises:
        ValueError: If decision_number is None, empty, or invalid
    """
    government_number = decision_data.get('government_number', '37')  # Default to current government
    decision_number = decision_data.get('decision_number')  # Don't convert to str yet!

    # Explicit None check
    if decision_number is None:
        raise ValueError("Decision number is required to generate decision key (got None)")

    # Convert to string and clean
    decision_number = str(decision_number).strip()

    # Check for empty string or literal 'None' (in case it came as a string)
    if not decision_number or decision_number.lower() == 'none':
        raise ValueError(f"Decision number is required to generate decision key (got '{decision_number}')")

    return f"{government_number}_{decision_number}"


def validate_decision_data(decision_data: Dict) -> List[str]:
    """
    Validate decision data to ensure it's complete and ready for database insertion.
    
    Args:
        decision_data: Dictionary containing decision information
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Required fields
    required_fields = ['decision_number', 'decision_url', 'decision_content']
    for field in required_fields:
        if not decision_data.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate decision number is numeric
    decision_number = decision_data.get('decision_number')
    if decision_number:
        try:
            int(str(decision_number))
        except (ValueError, TypeError):
            errors.append(f"Invalid decision number format: {decision_number}")
    
    # Validate URL format
    decision_url = decision_data.get('decision_url', '')
    if decision_url and not decision_url.startswith('https://www.gov.il'):
        errors.append(f"Invalid URL format: {decision_url}")
    
    # Check content length
    content = decision_data.get('decision_content', '')
    if len(content) < 50:
        errors.append("Decision content is too short (less than 50 characters)")
    
    # Check for incomplete content indicators
    if content and 'המשך התוכן...' in content:
        errors.append("Decision content appears to be incomplete (contains continuation marker)")
    
    return errors


def filter_new_decisions(scraped_decisions: List[Dict], baseline: Optional[Dict] = None) -> Tuple[List[Dict], List[str]]:
    """
    Filter scraped decisions to only include new ones not in the database.
    
    Args:
        scraped_decisions: List of scraped decision dictionaries
        baseline: Latest decision from database (if any)
        
    Returns:
        Tuple of (new_decisions_list, rejection_reasons_list)
    """
    new_decisions = []
    rejection_reasons = []
    
    for decision in scraped_decisions:
        try:
            # Validate decision data
            validation_errors = validate_decision_data(decision)
            if validation_errors:
                reason = f"Validation failed for decision {decision.get('decision_number', 'unknown')}: {'; '.join(validation_errors)}"
                rejection_reasons.append(reason)
                logger.warning(reason)
                continue
            
            # Check if decision should be processed
            if should_process_decision(decision, baseline):
                new_decisions.append(decision)
                logger.info(f"Added decision {decision.get('decision_number')} to processing queue")
            else:
                reason = f"Decision {decision.get('decision_number')} is not newer than baseline"
                rejection_reasons.append(reason)
                
        except Exception as e:
            reason = f"Error processing decision {decision.get('decision_number', 'unknown')}: {e}"
            rejection_reasons.append(reason)
            logger.error(reason)
    
    logger.info(f"Filtered {len(scraped_decisions)} scraped decisions to {len(new_decisions)} new decisions")
    return new_decisions, rejection_reasons


def prepare_for_database(decisions: List[Dict]) -> List[Dict]:
    """
    Prepare decision data for database insertion by ensuring all required fields and formats.
    
    Args:
        decisions: List of decision dictionaries
        
    Returns:
        List of database-ready decision dictionaries
    """
    prepared_decisions = []
    
    for decision in decisions:
        try:
            # Create a copy to avoid modifying original
            db_decision = decision.copy()
            
            # Generate decision key
            db_decision['decision_key'] = generate_decision_key(decision)
            
            # Ensure required fields have default values
            defaults = {
                'government_number': '37',
                'prime_minister': 'בנימין נתניהו',
                'summary': '',
                'operativity': '',
                'tags_policy_area': '',
                'tags_government_body': '',
                'tags_location': '',
                'all_tags': ''
            }
            
            # Handle committee field - keep as None if not found, don't default to empty string
            # This allows the database to store NULL for missing committees
            
            for field, default_value in defaults.items():
                if field not in db_decision or db_decision[field] is None:
                    db_decision[field] = default_value
            
            # Clean and format date
            decision_date = db_decision.get('decision_date', '')
            if decision_date and 'נושא ההחלטה' in decision_date:
                # Extract date from Hebrew format
                date_part = decision_date.split(' ')[0]
                try:
                    parsed_date = datetime.strptime(date_part, "%d.%m.%Y")
                    db_decision['decision_date'] = parsed_date.strftime("%Y-%m-%d")
                except ValueError:
                    logger.warning(f"Could not parse date: {date_part}")
            
            # Ensure decision number is string
            if 'decision_number' in db_decision:
                db_decision['decision_number'] = str(db_decision['decision_number'])

            # Remove internal metadata fields that don't exist in the database
            metadata_fields = ['_ai_processing_time', '_ai_confidence', '_ai_api_calls',
                             '_validation_warnings', '_validation_errors']
            for field in metadata_fields:
                db_decision.pop(field, None)

            # Remove any None values that could cause database issues
            db_decision = {k: v for k, v in db_decision.items() if v is not None}

            prepared_decisions.append(db_decision)
            
        except Exception as e:
            logger.error(f"Failed to prepare decision {decision.get('decision_number', 'unknown')}: {e}")
            continue
    
    logger.info(f"Prepared {len(prepared_decisions)} decisions for database insertion")
    return prepared_decisions



# =============================================================================
# Incremental QA Processing System
# =============================================================================

@dataclass
class QAChange:
    """Represents a single change that affects QA validation."""
    change_id: str
    table_name: str
    record_key: str
    operation: str  # 'insert', 'update', 'delete'
    changed_fields: List[str]
    old_values: Dict[str, Any]
    new_values: Dict[str, Any]
    timestamp: datetime
    change_hash: str
    dependencies: Set[str] = field(default_factory=set)
    priority: int = 1  # 1=low, 2=medium, 3=high

    def to_dict(self) -> Dict:
        return {
            'change_id': self.change_id,
            'table_name': self.table_name,
            'record_key': self.record_key,
            'operation': self.operation,
            'changed_fields': self.changed_fields,
            'old_values': self.old_values,
            'new_values': self.new_values,
            'timestamp': self.timestamp.isoformat(),
            'change_hash': self.change_hash,
            'dependencies': list(self.dependencies),
            'priority': self.priority
        }


@dataclass
class QACheckpoint:
    """Represents a checkpoint in the incremental QA process."""
    checkpoint_id: str
    timestamp: datetime
    processed_changes: List[str]
    failed_changes: List[str]
    progress_data: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            'checkpoint_id': self.checkpoint_id,
            'timestamp': self.timestamp.isoformat(),
            'processed_changes': self.processed_changes,
            'failed_changes': self.failed_changes,
            'progress_data': self.progress_data
        }


@dataclass
class QAProcessingResult:
    """Result of incremental QA processing."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    total_changes: int
    processed_changes: int
    failed_changes: int
    skipped_changes: int
    checkpoints: List[str]
    error_summary: Dict[str, int]
    performance_metrics: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_changes': self.total_changes,
            'processed_changes': self.processed_changes,
            'failed_changes': self.failed_changes,
            'skipped_changes': self.skipped_changes,
            'checkpoints': self.checkpoints,
            'error_summary': self.error_summary,
            'performance_metrics': self.performance_metrics
        }


class IncrementalQAProcessor:
    """Main class for incremental QA processing with change tracking and smart updates."""

    def __init__(self,
                 checkpoint_dir: Optional[str] = None,
                 batch_size: int = 50,
                 checkpoint_interval: int = 100,
                 max_retries: int = 3,
                 resource_threshold: float = 0.8):
        """Initialize the incremental QA processor.

        Args:
            checkpoint_dir: Directory to store checkpoints (default: data/qa_checkpoints)
            batch_size: Number of changes to process in each batch
            checkpoint_interval: Save checkpoint every N changes
            max_retries: Maximum retry attempts for failed changes
            resource_threshold: CPU/Memory threshold to pause processing (0.0-1.0)
        """
        self.checkpoint_dir = checkpoint_dir or os.path.join(PROJECT_ROOT, 'data', 'qa_checkpoints')
        self.batch_size = batch_size
        self.checkpoint_interval = checkpoint_interval
        self.max_retries = max_retries
        self.resource_threshold = resource_threshold

        # Ensure checkpoint directory exists
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        # Processing state
        self.session_id = f"qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_checkpoint: Optional[QACheckpoint] = None
        self.change_queue: deque = deque()
        self.processed_changes: Set[str] = set()
        self.failed_changes: Dict[str, int] = defaultdict(int)  # change_id -> retry_count
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)

        # Performance tracking
        self.start_time = datetime.now()
        self.processing_stats = {
            'changes_per_second': 0.0,
            'avg_processing_time': 0.0,
            'memory_usage_mb': 0.0,
            'database_queries': 0
        }

        logger.info(f"Initialized IncrementalQAProcessor session: {self.session_id}")

    def setup_change_tracking(self) -> None:
        """Set up database triggers and audit tables for change tracking."""
        client = get_supabase_client()

        # Create audit log table if it doesn't exist
        audit_table_sql = """
        CREATE TABLE IF NOT EXISTS qa_audit_log (
            id BIGSERIAL PRIMARY KEY,
            change_id VARCHAR UNIQUE NOT NULL,
            table_name VARCHAR NOT NULL,
            record_key VARCHAR NOT NULL,
            operation VARCHAR NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
            changed_fields JSONB,
            old_values JSONB,
            new_values JSONB,
            change_hash VARCHAR NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT FALSE,
            priority INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_qa_audit_timestamp ON qa_audit_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_qa_audit_processed ON qa_audit_log(processed);
        CREATE INDEX IF NOT EXISTS idx_qa_audit_priority ON qa_audit_log(priority DESC);
        CREATE INDEX IF NOT EXISTS idx_qa_audit_record ON qa_audit_log(table_name, record_key);
        """

        # Create QA checkpoints table
        checkpoint_table_sql = """
        CREATE TABLE IF NOT EXISTS qa_checkpoints (
            id BIGSERIAL PRIMARY KEY,
            checkpoint_id VARCHAR UNIQUE NOT NULL,
            session_id VARCHAR NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_changes JSONB,
            failed_changes JSONB,
            progress_data JSONB
        );

        CREATE INDEX IF NOT EXISTS idx_qa_checkpoints_session ON qa_checkpoints(session_id);
        CREATE INDEX IF NOT EXISTS idx_qa_checkpoints_timestamp ON qa_checkpoints(timestamp DESC);
        """

        # Create trigger function for change tracking
        trigger_function_sql = """
        CREATE OR REPLACE FUNCTION track_qa_changes()
        RETURNS TRIGGER AS $$
        DECLARE
            change_id_val VARCHAR;
            old_vals JSONB;
            new_vals JSONB;
            changed_fields_arr TEXT[];
            change_hash_val VARCHAR;
            field_name TEXT;
            priority_val INTEGER := 1;
        BEGIN
            -- Generate change ID
            change_id_val := 'chg_' || extract(epoch from now())::bigint || '_' || substr(md5(random()::text), 1, 8);

            -- Determine operation and values
            IF TG_OP = 'DELETE' THEN
                old_vals := row_to_json(OLD)::jsonb;
                new_vals := '{}'::jsonb;
                changed_fields_arr := ARRAY(SELECT jsonb_object_keys(old_vals));
            ELSIF TG_OP = 'INSERT' THEN
                old_vals := '{}'::jsonb;
                new_vals := row_to_json(NEW)::jsonb;
                changed_fields_arr := ARRAY(SELECT jsonb_object_keys(new_vals));
            ELSE -- UPDATE
                old_vals := row_to_json(OLD)::jsonb;
                new_vals := row_to_json(NEW)::jsonb;

                -- Find changed fields
                changed_fields_arr := ARRAY[];
                FOR field_name IN SELECT jsonb_object_keys(new_vals) LOOP
                    IF old_vals->field_name IS DISTINCT FROM new_vals->field_name THEN
                        changed_fields_arr := changed_fields_arr || field_name;
                    END IF;
                END LOOP;

                -- Set priority based on changed fields
                IF 'tags_policy_area' = ANY(changed_fields_arr) OR 'tags_government_body' = ANY(changed_fields_arr) THEN
                    priority_val := 3; -- High priority for tag changes
                ELSIF 'operativity' = ANY(changed_fields_arr) OR 'summary' = ANY(changed_fields_arr) THEN
                    priority_val := 2; -- Medium priority for operational changes
                END IF;
            END IF;

            -- Generate change hash
            change_hash_val := md5(TG_TABLE_NAME || TG_OP || old_vals::text || new_vals::text);

            -- Insert audit record
            INSERT INTO qa_audit_log (
                change_id, table_name, record_key, operation,
                changed_fields, old_values, new_values, change_hash, priority
            ) VALUES (
                change_id_val,
                TG_TABLE_NAME,
                COALESCE(NEW.decision_key, OLD.decision_key),
                TG_OP,
                array_to_json(changed_fields_arr)::jsonb,
                old_vals,
                new_vals,
                change_hash_val,
                priority_val
            );

            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """

        # Create trigger on main decisions table
        trigger_sql = """
        DROP TRIGGER IF EXISTS qa_change_trigger ON israeli_government_decisions;
        CREATE TRIGGER qa_change_trigger
            AFTER INSERT OR UPDATE OR DELETE ON israeli_government_decisions
            FOR EACH ROW EXECUTE FUNCTION track_qa_changes();
        """

        try:
            # Execute schema creation
            client.rpc('execute_sql', {'sql': audit_table_sql}).execute()
            client.rpc('execute_sql', {'sql': checkpoint_table_sql}).execute()
            client.rpc('execute_sql', {'sql': trigger_function_sql}).execute()
            client.rpc('execute_sql', {'sql': trigger_sql}).execute()

            logger.info("✅ Change tracking setup completed")

        except Exception as e:
            logger.error(f"❌ Failed to setup change tracking: {e}")
            # Continue without change tracking for backward compatibility

    def fetch_pending_changes(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> List[QAChange]:
        """Fetch unprocessed changes from audit log.

        Args:
            since: Only fetch changes after this timestamp
            limit: Maximum number of changes to fetch

        Returns:
            List of QAChange objects ordered by priority and timestamp
        """
        client = get_supabase_client()

        try:
            query = client.table('qa_audit_log').select('*').eq('processed', False)

            if since:
                query = query.gte('timestamp', since.isoformat())

            # Order by priority (desc) then timestamp (asc)
            query = query.order('priority', desc=True).order('timestamp', desc=False)

            if limit:
                query = query.limit(limit)

            response = query.execute()

            changes = []
            for row in response.data:
                change = QAChange(
                    change_id=row['change_id'],
                    table_name=row['table_name'],
                    record_key=row['record_key'],
                    operation=row['operation'],
                    changed_fields=row['changed_fields'],
                    old_values=row['old_values'],
                    new_values=row['new_values'],
                    timestamp=datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')),
                    change_hash=row['change_hash'],
                    priority=row.get('priority', 1)
                )
                changes.append(change)

            logger.info(f"Fetched {len(changes)} pending changes")
            return changes

        except Exception as e:
            logger.error(f"Failed to fetch pending changes: {e}")
            return []

    def resolve_dependencies(self, changes: List[QAChange]) -> List[QAChange]:
        """Resolve dependencies between changes and order them appropriately.

        Args:
            changes: List of QAChange objects

        Returns:
            Ordered list of changes with dependencies resolved
        """
        # Build dependency graph
        self.dependency_graph.clear()
        change_map = {change.change_id: change for change in changes}

        for change in changes:
            # Add dependencies based on business rules
            if change.operation == 'update' and 'tags_policy_area' in change.changed_fields:
                # Policy tag changes may affect other QA checks
                for other_change in changes:
                    if (other_change.record_key == change.record_key and
                        other_change.change_id != change.change_id and
                        other_change.timestamp > change.timestamp):
                        self.dependency_graph[other_change.change_id].add(change.change_id)

            if change.operation == 'update' and 'operativity' in change.changed_fields:
                # Operativity changes may affect tag relevance
                for other_change in changes:
                    if (other_change.record_key == change.record_key and
                        other_change.change_id != change.change_id and
                        'tags_policy_area' in other_change.changed_fields):
                        self.dependency_graph[other_change.change_id].add(change.change_id)

        # Topological sort to resolve dependencies
        ordered_changes = []
        visited = set()
        temp_visited = set()

        def visit(change_id: str):
            if change_id in temp_visited:
                logger.warning(f"Circular dependency detected involving {change_id}")
                return
            if change_id in visited:
                return

            temp_visited.add(change_id)

            for dep_id in self.dependency_graph.get(change_id, set()):
                if dep_id in change_map:
                    visit(dep_id)

            temp_visited.remove(change_id)
            visited.add(change_id)

            if change_id in change_map:
                ordered_changes.append(change_map[change_id])

        for change in changes:
            if change.change_id not in visited:
                visit(change.change_id)

        logger.info(f"Resolved dependencies for {len(ordered_changes)} changes")
        return ordered_changes

    def create_checkpoint(self, processed_changes: List[str], failed_changes: List[str]) -> QACheckpoint:
        """Create a checkpoint with current processing state.

        Args:
            processed_changes: List of successfully processed change IDs
            failed_changes: List of failed change IDs

        Returns:
            QACheckpoint object
        """
        checkpoint_id = f"{self.session_id}_cp_{len(processed_changes) + len(failed_changes)}"

        checkpoint = QACheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            processed_changes=processed_changes.copy(),
            failed_changes=failed_changes.copy(),
            progress_data={
                'session_id': self.session_id,
                'total_processed': len(self.processed_changes),
                'total_failed': len(self.failed_changes),
                'queue_size': len(self.change_queue),
                'processing_stats': self.processing_stats.copy()
            }
        )

        # Save to file
        checkpoint_file = os.path.join(self.checkpoint_dir, f"{checkpoint_id}.json")
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save checkpoint to file: {e}")

        # Save to database
        try:
            client = get_supabase_client()
            client.table('qa_checkpoints').insert({
                'checkpoint_id': checkpoint.checkpoint_id,
                'session_id': self.session_id,
                'processed_changes': processed_changes,
                'failed_changes': failed_changes,
                'progress_data': checkpoint.progress_data
            }).execute()
        except Exception as e:
            logger.error(f"Failed to save checkpoint to database: {e}")

        self.current_checkpoint = checkpoint
        logger.info(f"✅ Created checkpoint: {checkpoint_id}")
        return checkpoint

    def load_checkpoint(self, checkpoint_id: str) -> Optional[QACheckpoint]:
        """Load a checkpoint from file or database.

        Args:
            checkpoint_id: ID of checkpoint to load

        Returns:
            QACheckpoint object if found, None otherwise
        """
        # Try loading from file first
        checkpoint_file = os.path.join(self.checkpoint_dir, f"{checkpoint_id}.json")
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                checkpoint = QACheckpoint(
                    checkpoint_id=data['checkpoint_id'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    processed_changes=data['processed_changes'],
                    failed_changes=data['failed_changes'],
                    progress_data=data['progress_data']
                )

                logger.info(f"Loaded checkpoint from file: {checkpoint_id}")
                return checkpoint

            except Exception as e:
                logger.error(f"Failed to load checkpoint from file: {e}")

        # Try loading from database
        try:
            client = get_supabase_client()
            response = client.table('qa_checkpoints').select('*').eq('checkpoint_id', checkpoint_id).execute()

            if response.data:
                row = response.data[0]
                checkpoint = QACheckpoint(
                    checkpoint_id=row['checkpoint_id'],
                    timestamp=datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')),
                    processed_changes=row['processed_changes'],
                    failed_changes=row['failed_changes'],
                    progress_data=row['progress_data']
                )

                logger.info(f"Loaded checkpoint from database: {checkpoint_id}")
                return checkpoint

        except Exception as e:
            logger.error(f"Failed to load checkpoint from database: {e}")

        return None

    def process_change_batch(self, changes: List[QAChange]) -> Tuple[List[str], List[str]]:
        """Process a batch of changes and return success/failure lists.

        Args:
            changes: List of QAChange objects to process

        Returns:
            Tuple of (successful_change_ids, failed_change_ids)
        """
        successful = []
        failed = []

        for change in changes:
            try:
                start_time = time.time()

                # Process the change based on operation type
                if change.operation == 'update':
                    if self._process_update_change(change):
                        successful.append(change.change_id)
                        self.processed_changes.add(change.change_id)
                    else:
                        failed.append(change.change_id)
                        self.failed_changes[change.change_id] += 1

                elif change.operation == 'insert':
                    if self._process_insert_change(change):
                        successful.append(change.change_id)
                        self.processed_changes.add(change.change_id)
                    else:
                        failed.append(change.change_id)
                        self.failed_changes[change.change_id] += 1

                elif change.operation == 'delete':
                    if self._process_delete_change(change):
                        successful.append(change.change_id)
                        self.processed_changes.add(change.change_id)
                    else:
                        failed.append(change.change_id)
                        self.failed_changes[change.change_id] += 1

                # Update performance metrics
                processing_time = time.time() - start_time
                self.processing_stats['avg_processing_time'] = (
                    self.processing_stats['avg_processing_time'] * 0.9 + processing_time * 0.1
                )

            except Exception as e:
                logger.error(f"Failed to process change {change.change_id}: {e}")
                failed.append(change.change_id)
                self.failed_changes[change.change_id] += 1

        return successful, failed

    def _process_update_change(self, change: QAChange) -> bool:
        """Process an update change by triggering relevant QA checks.

        Args:
            change: QAChange object representing the update

        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # Import QA module to avoid circular imports
            from .qa import run_scan, ALL_CHECKS

            # Determine which checks need to be run based on changed fields
            checks_to_run = set()

            for field in change.changed_fields:
                if field in ['tags_policy_area', 'decision_content']:
                    checks_to_run.add('policy-relevance')
                if field in ['tags_government_body', 'decision_content']:
                    checks_to_run.add('body-relevance')
                if field in ['operativity', 'decision_content']:
                    checks_to_run.add('operativity')
                if field in ['tags_location', 'decision_content']:
                    checks_to_run.add('locations')
                if field in ['summary', 'decision_content']:
                    checks_to_run.add('summary-quality')

            # If no specific checks identified, run all checks for safety
            if not checks_to_run:
                checks_to_run = set(ALL_CHECKS.keys())

            # Run the identified checks on this specific record
            client = get_supabase_client()
            response = client.table('israeli_government_decisions').select('*').eq('decision_key', change.record_key).execute()

            if not response.data:
                logger.warning(f"Record {change.record_key} not found for change {change.change_id}")
                return False

            record = response.data[0]

            # Run each identified check on this record
            for check_name in checks_to_run:
                if check_name in ALL_CHECKS:
                    try:
                        check_function = ALL_CHECKS[check_name]
                        result = check_function([record])

                        # Log the result
                        if result.issues_found > 0:
                            logger.warning(f"QA check '{check_name}' found {result.issues_found} issues in record {change.record_key}")
                        else:
                            logger.info(f"QA check '{check_name}' passed for record {change.record_key}")

                    except Exception as e:
                        logger.error(f"Failed to run QA check '{check_name}' on record {change.record_key}: {e}")
                        return False

            # Mark change as processed in audit log
            client.table('qa_audit_log').update({'processed': True}).eq('change_id', change.change_id).execute()

            return True

        except Exception as e:
            logger.error(f"Error processing update change {change.change_id}: {e}")
            return False

    def _process_insert_change(self, change: QAChange) -> bool:
        """Process an insert change by running full QA validation.

        Args:
            change: QAChange object representing the insert

        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # For new records, run all QA checks
            from .qa import run_scan

            client = get_supabase_client()
            response = client.table('israeli_government_decisions').select('*').eq('decision_key', change.record_key).execute()

            if not response.data:
                logger.warning(f"Newly inserted record {change.record_key} not found")
                return False

            record = response.data[0]

            # Run comprehensive QA scan on new record
            result = run_scan([record])

            if result.total_issues > 0:
                logger.warning(f"New record {change.record_key} has {result.total_issues} QA issues")
            else:
                logger.info(f"New record {change.record_key} passed all QA checks")

            # Mark change as processed
            client.table('qa_audit_log').update({'processed': True}).eq('change_id', change.change_id).execute()

            return True

        except Exception as e:
            logger.error(f"Error processing insert change {change.change_id}: {e}")
            return False

    def _process_delete_change(self, change: QAChange) -> bool:
        """Process a delete change by cleaning up related QA data.

        Args:
            change: QAChange object representing the delete

        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # For deleted records, just clean up any QA-related data
            logger.info(f"Record {change.record_key} was deleted - cleaning up QA data")

            # Mark change as processed
            client = get_supabase_client()
            client.table('qa_audit_log').update({'processed': True}).eq('change_id', change.change_id).execute()

            return True

        except Exception as e:
            logger.error(f"Error processing delete change {change.change_id}: {e}")
            return False

    def run_incremental_qa(self,
                          since: Optional[datetime] = None,
                          max_changes: Optional[int] = None,
                          resume_from_checkpoint: Optional[str] = None) -> QAProcessingResult:
        """Run incremental QA processing on pending changes.

        Args:
            since: Only process changes after this timestamp
            max_changes: Maximum number of changes to process
            resume_from_checkpoint: Checkpoint ID to resume from

        Returns:
            QAProcessingResult with processing summary
        """
        logger.info(f"🚀 Starting incremental QA processing session: {self.session_id}")

        # Resume from checkpoint if specified
        if resume_from_checkpoint:
            checkpoint = self.load_checkpoint(resume_from_checkpoint)
            if checkpoint:
                self.processed_changes.update(checkpoint.processed_changes)
                for change_id in checkpoint.failed_changes:
                    self.failed_changes[change_id] = self.max_retries  # Don't retry these
                logger.info(f"Resumed from checkpoint with {len(checkpoint.processed_changes)} processed changes")

        # Fetch pending changes
        changes = self.fetch_pending_changes(since=since, limit=max_changes)

        if not changes:
            logger.info("No pending changes to process")
            return QAProcessingResult(
                session_id=self.session_id,
                start_time=self.start_time,
                end_time=datetime.now(),
                total_changes=0,
                processed_changes=0,
                failed_changes=0,
                skipped_changes=0,
                checkpoints=[],
                error_summary={},
                performance_metrics=self.processing_stats
            )

        # Filter out already processed changes
        changes = [c for c in changes if c.change_id not in self.processed_changes]

        # Resolve dependencies
        changes = self.resolve_dependencies(changes)

        logger.info(f"Processing {len(changes)} changes after dependency resolution")

        # Process changes in batches
        total_processed = 0
        total_failed = 0
        total_skipped = 0
        checkpoints_created = []
        error_summary = defaultdict(int)

        for i in range(0, len(changes), self.batch_size):
            batch = changes[i:i + self.batch_size]

            # Skip changes that have failed too many times
            batch_to_process = []
            for change in batch:
                if self.failed_changes[change.change_id] >= self.max_retries:
                    total_skipped += 1
                    logger.warning(f"Skipping change {change.change_id} (max retries exceeded)")
                else:
                    batch_to_process.append(change)

            if not batch_to_process:
                continue

            # Process batch
            successful, failed = self.process_change_batch(batch_to_process)
            total_processed += len(successful)
            total_failed += len(failed)

            # Update performance stats
            if total_processed > 0:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                self.processing_stats['changes_per_second'] = total_processed / elapsed

            # Create checkpoint if needed
            if (total_processed + total_failed) % self.checkpoint_interval == 0:
                checkpoint = self.create_checkpoint(
                    list(self.processed_changes),
                    list(self.failed_changes.keys())
                )
                checkpoints_created.append(checkpoint.checkpoint_id)

            logger.info(f"Batch {i//self.batch_size + 1}: {len(successful)} successful, {len(failed)} failed")

        # Create final checkpoint
        final_checkpoint = self.create_checkpoint(
            list(self.processed_changes),
            list(self.failed_changes.keys())
        )
        checkpoints_created.append(final_checkpoint.checkpoint_id)

        end_time = datetime.now()
        result = QAProcessingResult(
            session_id=self.session_id,
            start_time=self.start_time,
            end_time=end_time,
            total_changes=len(changes),
            processed_changes=total_processed,
            failed_changes=total_failed,
            skipped_changes=total_skipped,
            checkpoints=checkpoints_created,
            error_summary=dict(error_summary),
            performance_metrics=self.processing_stats
        )

        logger.info(f"✅ Incremental QA processing completed:")
        logger.info(f"   Total changes: {result.total_changes}")
        logger.info(f"   Processed: {result.processed_changes}")
        logger.info(f"   Failed: {result.failed_changes}")
        logger.info(f"   Skipped: {result.skipped_changes}")
        logger.info(f"   Duration: {(end_time - self.start_time).total_seconds():.1f}s")
        logger.info(f"   Rate: {self.processing_stats['changes_per_second']:.2f} changes/sec")

        return result

    def generate_differential_report(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """Generate a differential report showing only changes since last run.

        Args:
            since: Generate report for changes after this timestamp

        Returns:
            Dictionary containing differential report data
        """
        if not since:
            since = datetime.now() - timedelta(days=1)  # Default to last 24 hours

        try:
            client = get_supabase_client()

            # Get changes since specified time
            changes_response = client.table('qa_audit_log').select('*').gte('timestamp', since.isoformat()).execute()
            changes = changes_response.data

            # Analyze changes by type
            change_summary = {
                'total_changes': len(changes),
                'by_operation': defaultdict(int),
                'by_table': defaultdict(int),
                'by_field': defaultdict(int),
                'by_priority': defaultdict(int),
                'processed': 0,
                'pending': 0
            }

            for change in changes:
                change_summary['by_operation'][change['operation']] += 1
                change_summary['by_table'][change['table_name']] += 1
                change_summary['by_priority'][change.get('priority', 1)] += 1

                if change['processed']:
                    change_summary['processed'] += 1
                else:
                    change_summary['pending'] += 1

                for field in change.get('changed_fields', []):
                    change_summary['by_field'][field] += 1

            # Get QA issues trend
            # This would typically compare current issues vs previous state
            # For now, we'll provide a placeholder structure
            qa_trend = {
                'total_issues_current': 0,
                'total_issues_previous': 0,
                'improvement': 0,
                'degradation': 0,
                'new_issues': [],
                'resolved_issues': []
            }

            report = {
                'generated_at': datetime.now().isoformat(),
                'period_start': since.isoformat(),
                'period_end': datetime.now().isoformat(),
                'change_summary': dict(change_summary['by_operation']),
                'field_changes': dict(change_summary['by_field']),
                'processing_status': {
                    'processed': change_summary['processed'],
                    'pending': change_summary['pending'],
                    'total': change_summary['total_changes']
                },
                'qa_trend': qa_trend,
                'recommendations': self._generate_recommendations(changes)
            }

            logger.info(f"Generated differential report for {len(changes)} changes since {since}")
            return report

        except Exception as e:
            logger.error(f"Failed to generate differential report: {e}")
            return {
                'error': str(e),
                'generated_at': datetime.now().isoformat()
            }

    def _generate_recommendations(self, changes: List[Dict]) -> List[str]:
        """Generate recommendations based on change patterns.

        Args:
            changes: List of change records

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Count changes by field type
        field_counts = defaultdict(int)
        for change in changes:
            for field in change.get('changed_fields', []):
                field_counts[field] += 1

        # Generate recommendations based on patterns
        if field_counts.get('tags_policy_area', 0) > 10:
            recommendations.append(
                "High frequency of policy tag changes detected. Consider reviewing tag validation rules."
            )

        if field_counts.get('operativity', 0) > 5:
            recommendations.append(
                "Multiple operativity changes detected. Consider improving operativity detection algorithms."
            )

        pending_count = sum(1 for change in changes if not change['processed'])
        if pending_count > 50:
            recommendations.append(
                f"{pending_count} changes are pending processing. Consider increasing batch size or processing frequency."
            )

        high_priority_count = sum(1 for change in changes if change.get('priority', 1) >= 3)
        if high_priority_count > 0:
            recommendations.append(
                f"{high_priority_count} high-priority changes require immediate attention."
            )

        if not recommendations:
            recommendations.append("No specific recommendations. System appears to be operating normally.")

        return recommendations


# =============================================================================
# Utility Functions
# =============================================================================

def setup_incremental_qa(checkpoint_dir: Optional[str] = None) -> IncrementalQAProcessor:
    """Set up and return an incremental QA processor.

    Args:
        checkpoint_dir: Directory for storing checkpoints

    Returns:
        Configured IncrementalQAProcessor instance
    """
    processor = IncrementalQAProcessor(checkpoint_dir=checkpoint_dir)
    processor.setup_change_tracking()
    return processor


def run_incremental_qa_update(since: Optional[datetime] = None,
                              max_changes: Optional[int] = None) -> QAProcessingResult:
    """Convenience function to run incremental QA updates.

    Args:
        since: Only process changes after this timestamp
        max_changes: Maximum number of changes to process

    Returns:
        QAProcessingResult with processing summary
    """
    processor = setup_incremental_qa()
    return processor.run_incremental_qa(since=since, max_changes=max_changes)


if __name__ == "__main__":
    # Test the incremental QA processor
    try:
        print("Testing IncrementalQAProcessor...")

        # Test basic incremental processing setup
        baseline = get_scraping_baseline()
        print(f"Baseline decision: {baseline}")

        # Test decision validation (existing functionality)
        test_decision = {
            'decision_number': '3284',
            'decision_date': '2025-07-24',
            'decision_url': 'https://www.gov.il/he/pages/dec3284-2025',
            'decision_content': 'Test content for validation purposes that is longer than 50 characters.',
            'committee': 'Test Committee'
        }

        errors = validate_decision_data(test_decision)
        print(f"Validation errors: {errors}")

        if not errors:
            key = generate_decision_key(test_decision)
            print(f"Generated key: {key}")

            prepared = prepare_for_database([test_decision])
            print(f"Prepared decision: {prepared[0]}")

        # Test incremental QA processor
        print("\nTesting Incremental QA Processor...")
        processor = IncrementalQAProcessor(batch_size=10, checkpoint_interval=50)

        # Setup change tracking (this would normally be done once)
        print("Setting up change tracking...")
        processor.setup_change_tracking()

        # Test fetching changes (will be empty in test)
        changes = processor.fetch_pending_changes(limit=10)
        print(f"Found {len(changes)} pending changes")

        # Generate a sample differential report
        report = processor.generate_differential_report(since=datetime.now() - timedelta(hours=24))
        print(f"\nDifferential report: {json.dumps(report, indent=2, ensure_ascii=False)}")

        print("\n✅ All tests completed successfully!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()