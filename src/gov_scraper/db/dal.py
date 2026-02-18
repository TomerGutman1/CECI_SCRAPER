import os
import logging
import time
import re
from typing import List, Dict, Set, Tuple, Optional
import pandas as pd
from .connector import get_supabase_client
from .utils import read_decisions_csv, remove_unwanted_columns, drop_incomplete_rows, filter_new_rows
from ..config import MAX_RETRIES, RETRY_DELAY

def fetch_latest_decision():
    """
    Fetch the latest decision from the database.
    
    Returns:
        Dict with latest decision data or None if no decisions found
    """
    client = get_supabase_client()
    response = (
        client.table("israeli_government_decisions")
        .select("*")
        .gt("decision_date", "2023-01-01")
        .neq("decision_number", None)
        .neq("decision_content", "המשך התוכן...")
        .order("decision_date", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]
    return None


def check_existing_decision_keys(decision_keys: List[str]) -> Set[str]:
    """
    Check which decision keys already exist in the database.

    Args:
        decision_keys: List of decision keys to check

    Returns:
        Set of existing decision keys

    Raises:
        RuntimeError: If all retry attempts fail (to prevent silent duplicate insertion)
    """
    if not decision_keys:
        return set()

    client = get_supabase_client()
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            logging.debug(f"Checking {len(decision_keys)} decision keys (attempt {attempt + 1}/{MAX_RETRIES})")
            response = (
                client.table("israeli_government_decisions")
                .select("decision_key")
                .in_("decision_key", decision_keys)
                .execute()
            )

            existing_keys = {item['decision_key'] for item in response.data}
            logging.info(f"Found {len(existing_keys)} existing decision keys out of {len(decision_keys)} checked")
            return existing_keys

        except Exception as e:
            last_error = e
            logging.warning(f"Duplicate check failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)  # exponential: 2s, 4s, 6s, 8s
                logging.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    # FAIL LOUD — never return empty set on error!
    error_msg = f"Failed to check duplicate keys after {MAX_RETRIES} attempts. Last error: {last_error}"
    logging.error(error_msg)
    raise RuntimeError(error_msg)


def filter_duplicate_decisions(decisions: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Filter out decisions that already exist in the database.

    Args:
        decisions: List of decision dictionaries

    Returns:
        Tuple of (unique_decisions, duplicate_keys)

    Raises:
        RuntimeError: If duplicate check fails after retries (propagated from check_existing_decision_keys)
    """
    if not decisions:
        return [], []
    
    # Extract decision keys from the decisions
    decision_keys = []
    key_to_decision = {}
    
    for decision in decisions:
        decision_key = decision.get('decision_key')
        if decision_key:
            decision_keys.append(decision_key)
            key_to_decision[decision_key] = decision
    
    # Check which keys exist in database
    existing_keys = check_existing_decision_keys(decision_keys)
    
    # Filter out duplicates
    unique_decisions = []
    duplicate_keys = []
    
    for decision in decisions:
        decision_key = decision.get('decision_key')
        if decision_key in existing_keys:
            duplicate_keys.append(decision_key)
            logging.info(f"Skipping duplicate decision: {decision_key}")
        else:
            unique_decisions.append(decision)
    
    logging.info(f"Filtered {len(decisions)} decisions to {len(unique_decisions)} unique decisions")
    logging.info(f"Found {len(duplicate_keys)} duplicates: {duplicate_keys[:5]}{'...' if len(duplicate_keys) > 5 else ''}")
    
    return unique_decisions, duplicate_keys

def insert_decisions_batch(decisions: List[Dict], batch_size: int = 50) -> Tuple[int, List[str]]:
    """
    Insert decisions to database in batches with duplicate prevention, unique constraint handling, and retry logic.

    UPDATED: Now handles unique constraint violations gracefully after migration 004.

    Args:
        decisions: List of decision dictionaries to insert
        batch_size: Size of each batch for insertion

    Returns:
        Tuple of (successfully_inserted_count, error_messages)

    Raises:
        RuntimeError: If duplicate check fails (propagated from filter_duplicate_decisions)
    """
    if not decisions:
        return 0, []

    # First, filter out duplicates (may raise RuntimeError on repeated DB failures)
    unique_decisions, duplicate_keys = filter_duplicate_decisions(decisions)

    if not unique_decisions:
        logging.info("No unique decisions to insert after duplicate filtering")
        return 0, [f"All {len(decisions)} decisions were duplicates"]

    client = get_supabase_client()
    inserted_count = 0
    error_messages = []

    # Validate decision keys before insertion
    invalid_decisions = []
    for decision in unique_decisions:
        decision_key = decision.get('decision_key')
        if not decision_key or not _is_valid_decision_key_format(decision_key):
            invalid_decisions.append(decision)
            error_messages.append(f"Invalid decision_key format: {decision_key}")

    # Remove invalid decisions
    valid_decisions = [d for d in unique_decisions if d not in invalid_decisions]
    if invalid_decisions:
        logging.warning(f"Removed {len(invalid_decisions)} decisions with invalid key formats")

    # Process in batches
    for i in range(0, len(valid_decisions), batch_size):
        batch = valid_decisions[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(valid_decisions) + batch_size - 1) // batch_size

        # Clean the batch data once
        clean_batch = [{k: v for k, v in d.items() if v is not None} for d in batch]

        # Try batch insert with retries (3 attempts for batch)
        batch_inserted = False
        for attempt in range(3):
            try:
                logging.info(f"Inserting batch {batch_num}/{total_batches} ({len(batch)} decisions) - attempt {attempt + 1}/3")
                client.table("israeli_government_decisions").insert(clean_batch).execute()
                inserted_count += len(batch)
                logging.info(f"Successfully inserted batch {batch_num}: {len(batch)} decisions")
                batch_inserted = True
                break

            except Exception as e:
                error_str = str(e).lower()

                # Handle unique constraint violations specifically
                if 'unique constraint' in error_str or 'duplicate key' in error_str:
                    logging.warning(f"Batch {batch_num} failed due to unique constraint violation: {e}")
                    error_messages.append(f"Batch {batch_num}: Unique constraint violation")
                    # Don't retry batch - fall back to individual inserts immediately
                    break
                else:
                    logging.warning(f"Batch {batch_num} insert failed (attempt {attempt + 1}/3): {e}")
                    if attempt < 2:
                        time.sleep(RETRY_DELAY * (attempt + 1))

        # If batch still failed after retries, try individual insertion with constraint handling
        if not batch_inserted:
            logging.warning(f"Batch {batch_num} failed. Falling back to individual insertion with constraint handling.")

            for decision in batch:
                clean_decision = {k: v for k, v in decision.items() if v is not None}
                decision_key = decision.get('decision_key', 'unknown')

                # Try individual insert with unique constraint handling
                success = _insert_single_decision_with_constraint_handling(
                    client, clean_decision, decision_key
                )

                if success:
                    inserted_count += 1
                    logging.info(f"Successfully inserted individual decision: {decision_key}")
                else:
                    error_msg = f"Failed to insert {decision_key} after constraint handling"
                    logging.error(error_msg)
                    error_messages.append(error_msg)

    logging.info(f"Batch insertion complete: {inserted_count} inserted, {len(duplicate_keys)} duplicates skipped")
    if error_messages:
        logging.warning(f"Encountered {len(error_messages)} errors during insertion")

    return inserted_count, error_messages


def _is_valid_decision_key_format(decision_key: str) -> bool:
    """
    Validate decision_key format against database constraints.

    Valid formats after migration 004:
    - Standard: {gov_num}_{decision_num} (e.g., "37_1234")
    - Special: {gov_num}_{type}_{num} (e.g., "37_COMMITTEE_5")
    """
    if not decision_key or not isinstance(decision_key, str):
        return False

    # Standard format: digits_digits
    if re.match(r'^\d+_\d+$', decision_key):
        return True

    # Special format: digits_TYPE_digits
    if re.match(r'^\d+_(COMMITTEE|SECURITY|ECON|SPECIAL)_\d+$', decision_key):
        return True

    return False


def _insert_single_decision_with_constraint_handling(
    client, clean_decision: Dict, decision_key: str
) -> bool:
    """
    Insert a single decision with proper unique constraint violation handling.

    Returns:
        bool: True if successfully inserted, False otherwise
    """
    for attempt in range(2):
        try:
            client.table("israeli_government_decisions").insert([clean_decision]).execute()
            return True

        except Exception as e:
            error_str = str(e).lower()

            if 'unique constraint' in error_str or 'duplicate key' in error_str:
                if 'decision_key' in error_str:
                    logging.warning(f"Decision {decision_key} already exists (unique constraint)")
                    # This is expected - record already exists, don't retry
                    return False
                else:
                    logging.warning(f"Unique constraint violation on different field for {decision_key}: {e}")
                    return False
            else:
                # Other errors - retry once
                if attempt == 0:
                    logging.warning(f"Retrying individual insert for {decision_key}: {e}")
                    time.sleep(RETRY_DELAY)
                else:
                    logging.error(f"Failed to insert {decision_key} after retry: {e}")
                    return False

    return False


def batch_deduplicate_decisions() -> Tuple[int, List[str]]:
    """
    Find and remove duplicate decisions from the database.
    CRITICAL: Run this before migration 004 or it will fail due to unique constraints.

    Returns:
        Tuple of (removed_count, error_messages)
    """
    client = get_supabase_client()
    error_messages = []
    removed_count = 0

    try:
        # Find all duplicates
        response = client.rpc(
            'find_duplicate_decision_keys'
        ).execute()

        if response.data:
            duplicate_keys = [row['decision_key'] for row in response.data]
            logging.info(f"Found {len(duplicate_keys)} decision_keys with duplicates")

            for decision_key in duplicate_keys[:10]:  # Process in small batches
                try:
                    # Get all records for this key
                    records_response = (
                        client.table("israeli_government_decisions")
                        .select("*")
                        .eq("decision_key", decision_key)
                        .order("created_at", desc=True)
                        .order("id", desc=True)
                        .execute()
                    )

                    records = records_response.data
                    if len(records) > 1:
                        # Keep the newest record (first in sorted list)
                        keep_record = records[0]
                        remove_records = records[1:]

                        logging.info(f"Removing {len(remove_records)} duplicates for {decision_key}, keeping record ID {keep_record['id']}")

                        # Remove duplicates
                        for record in remove_records:
                            client.table("israeli_government_decisions").delete().eq("id", record["id"]).execute()
                            removed_count += 1

                except Exception as e:
                    error_msg = f"Failed to deduplicate {decision_key}: {e}"
                    logging.error(error_msg)
                    error_messages.append(error_msg)

        logging.info(f"Batch deduplication complete: {removed_count} duplicates removed")
        return removed_count, error_messages

    except Exception as e:
        error_msg = f"Batch deduplication failed: {e}"
        logging.error(error_msg)
        return 0, [error_msg]


def validate_decision_urls(limit: int = 1000) -> Dict[str, any]:
    """
    Validate URLs against decision keys in the database.

    Args:
        limit: Maximum number of records to validate

    Returns:
        Dict with validation statistics and problematic records
    """
    client = get_supabase_client()

    try:
        # Fetch records for validation
        response = (
            client.table("israeli_government_decisions")
            .select("id, decision_key, decision_url, government_number, decision_number")
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )

        records = response.data
        logging.info(f"Validating URLs for {len(records)} records")

        validation_results = {
            'total_checked': len(records),
            'valid_urls': 0,
            'invalid_urls': 0,
            'missing_urls': 0,
            'problematic_records': [],
            'url_patterns': {},
            'systematic_issues': []
        }

        for record in records:
            record_id = record['id']
            decision_key = record['decision_key']
            url = record['decision_url']

            if not url:
                validation_results['missing_urls'] += 1
                continue

            # Import validation function
            try:
                from ..scrapers.decision import validate_url_against_decision_key
                validation = validate_url_against_decision_key(url, decision_key)

                if validation['valid']:
                    validation_results['valid_urls'] += 1
                else:
                    validation_results['invalid_urls'] += 1
                    validation_results['problematic_records'].append({
                        'id': record_id,
                        'decision_key': decision_key,
                        'url': url,
                        'issues': validation['issues'],
                        'difference': validation.get('difference', 0)
                    })

                # Track URL patterns
                pattern = validation.get('url_pattern', 'unknown')
                validation_results['url_patterns'][pattern] = validation_results['url_patterns'].get(pattern, 0) + 1

                # Detect systematic issues
                if validation.get('difference', 0) > 1000000:
                    validation_results['systematic_issues'].append({
                        'decision_key': decision_key,
                        'difference': validation['difference'],
                        'type': 'large_offset'
                    })

            except ImportError:
                logging.warning("Could not import URL validation function")
                break

        # Calculate statistics
        validation_results['validity_rate'] = (
            validation_results['valid_urls'] / validation_results['total_checked']
            if validation_results['total_checked'] > 0 else 0
        )

        logging.info(
            f"URL validation complete: {validation_results['valid_urls']}/{validation_results['total_checked']} "
            f"valid ({validation_results['validity_rate']:.2%})"
        )

        return validation_results

    except Exception as e:
        logging.error(f"URL validation failed: {e}")
        return {'error': str(e)}


def _insert_rows_to_db(rows):
    """Legacy function - use insert_decisions_batch instead."""
    client = get_supabase_client()
    try:
        response = client.table("israeli_government_decisions").insert(rows).execute()
        inserted = len(rows)
        logging.info(f"Inserted {inserted} new rows.")
        print(f"Inserted {inserted} new rows.")
        return inserted
    except Exception as e:
        logging.error(f"Failed to insert rows: {e}")
        print(f"Failed to insert rows: {e}")
        return 0

def save_new_rows_from_table_to_db():
    """
    Reads decisions.csv, filters for new/valid rows, removes unwanted columns, skips incomplete rows, and inserts new rows to Supabase.
    Prints a summary and logs actions.
    """
    logging.basicConfig(filename="logs/db.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "decisions.csv"))
    df = read_decisions_csv(csv_path)
    if df is None:
        return

    latest_decision = fetch_latest_decision()
    if not latest_decision:
        logging.info("No latest decision found. Terminating script.")
        print("No latest decision found. Terminating script.")
        return

    last_date = latest_decision.get("decision_date")
    last_num = str(latest_decision.get("decision_number"))

    df = remove_unwanted_columns(df, ["id", "created_at", "updated_at", "decision_date_db"])
    df, skipped_missing = drop_incomplete_rows(df, ["decision_date", "decision_number", "decision_url"])
    df, skipped_old = filter_new_rows(df, last_date, last_num)

    # Convert any NaN values to None for DB compatibility
    df = df.where(pd.notna(df), None)
    new_rows = df.to_dict(orient="records")

    # Remove "embedding" attribute if it exists and is null in any row
    for row in new_rows:
        if "embedding" in row and pd.isna(row["embedding"]):
            del row["embedding"]

    # Convert decision_number to integer and then back to string
    for row in new_rows:
        if "decision_number" in row:
            row["decision_number"] = str(int(row["decision_number"])) if pd.notna(row["decision_number"]) else None

    skipped_total = skipped_missing + skipped_old

    if not new_rows:
        logging.info("No new rows to insert.")
        print(f"No new rows to insert. Skipped {skipped_total} rows.")
        return

    inserted = _insert_rows_to_db(new_rows)
    print(f"Inserted {inserted} new rows. Skipped {skipped_total} rows.")
    logging.info(f"Inserted {inserted} new rows. Skipped {skipped_total} rows.")

if __name__ == "__main__":
    save_new_rows_from_table_to_db()