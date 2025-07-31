"""Incremental processing module for determining scraping boundaries and validating new decisions."""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

from ..db.dal import fetch_latest_decision

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
        
        # Compare dates first
        if decision_dt > baseline_dt:
            logger.info(f"Decision {decision_number} ({decision_dt.date()}) is newer than baseline ({baseline_dt.date()})")
            return True
        elif decision_dt < baseline_dt:
            logger.info(f"Decision {decision_number} ({decision_dt.date()}) is older than baseline ({baseline_dt.date()})")
            return False
        else:
            # Same date - compare decision numbers
            try:
                decision_num_int = int(decision_number)
                baseline_num_int = int(baseline_number)
                
                if decision_num_int > baseline_num_int:
                    logger.info(f"Decision {decision_number} is newer than baseline {baseline_number} (same date)")
                    return True
                else:
                    logger.info(f"Decision {decision_number} is not newer than baseline {baseline_number}")
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
    """
    government_number = decision_data.get('government_number', '37')  # Default to current government
    decision_number = str(decision_data.get('decision_number', ''))
    
    if not decision_number:
        raise ValueError("Decision number is required to generate decision key")
    
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
            
            # Remove any None values that could cause database issues
            db_decision = {k: v for k, v in db_decision.items() if v is not None}
            
            prepared_decisions.append(db_decision)
            
        except Exception as e:
            logger.error(f"Failed to prepare decision {decision.get('decision_number', 'unknown')}: {e}")
            continue
    
    logger.info(f"Prepared {len(prepared_decisions)} decisions for database insertion")
    return prepared_decisions


if __name__ == "__main__":
    # Test the incremental processor
    try:
        baseline = get_scraping_baseline()
        print(f"Baseline decision: {baseline}")
        
        # Test decision validation
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
        
    except Exception as e:
        print(f"Test failed: {e}")