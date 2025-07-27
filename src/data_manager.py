"""Data management and CSV output for government decisions."""

import pandas as pd
import os
import logging
from typing import List, Dict
from datetime import datetime

from config import OUTPUT_DIR, OUTPUT_FILE, CSV_COLUMNS

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_output_directory():
    """Ensure the output directory exists."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        logger.info(f"Created output directory: {OUTPUT_DIR}")


def prepare_decision_data(decision_data: Dict[str, str], row_id: int) -> Dict[str, str]:
    """
    Prepare decision data for CSV output by ensuring all required columns are present.
    
    Args:
        decision_data: Raw decision data dictionary
        row_id: Row ID for the CSV
        
    Returns:
        Dictionary with all CSV columns
    """
    # Start with empty data for all columns
    prepared_data = {col: '' for col in CSV_COLUMNS}
    
    # Set the ID
    prepared_data['id'] = str(row_id)
    
    # Map the existing data
    field_mapping = {
        'decision_date': 'decision_date',
        'decision_number': 'decision_number', 
        'committee': 'committee',
        'decision_title': 'decision_title',
        'decision_content': 'decision_content',
        'decision_url': 'decision_url',
        'summary': 'summary',
        'operativity': 'operativity',
        'tags_policy_area': 'tags_policy_area',
        'tags_government_body': 'tags_government_body',
        'tags_location': 'tags_location',
        'all_tags': 'all_tags',
        'government_number': 'government_number',
        'prime_minister': 'prime_minister',
        'decision_key': 'decision_key'
    }
    
    for csv_col, data_key in field_mapping.items():
        if data_key in decision_data:
            prepared_data[csv_col] = str(decision_data[data_key])
    
    return prepared_data


def save_decisions_to_csv(decisions_data: List[Dict[str, str]], filename: str = None) -> str:
    """
    Save decisions data to CSV file.
    
    Args:
        decisions_data: List of decision data dictionaries
        filename: Optional custom filename
        
    Returns:
        Path to the saved CSV file
    """
    ensure_output_directory()
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"decisions_data_{timestamp}.csv"
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if not decisions_data:
        logger.warning("No decisions data to save")
        return filepath
    
    logger.info(f"Preparing {len(decisions_data)} decisions for CSV output")
    
    # Prepare all data for CSV
    prepared_data = []
    for i, decision in enumerate(decisions_data, 1):
        prepared_decision = prepare_decision_data(decision, i)
        prepared_data.append(prepared_decision)
    
    # Create DataFrame
    df = pd.DataFrame(prepared_data, columns=CSV_COLUMNS)
    
    # Save to CSV with UTF-8 BOM encoding for Hebrew text compatibility
    try:
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"Successfully saved {len(decisions_data)} decisions to {filepath}")
        
        # Log some statistics
        logger.info(f"CSV Statistics:")
        logger.info(f"  - Total rows: {len(df)}")
        logger.info(f"  - Decisions with content: {len(df[df['decision_content'] != ''])}")
        logger.info(f"  - Decisions with summaries: {len(df[df['summary'] != ''])}")
        logger.info(f"  - File size: {os.path.getsize(filepath) / 1024:.1f} KB")
        
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save CSV file: {e}")
        raise


def load_existing_decisions(filepath: str = None) -> pd.DataFrame:
    """
    Load existing decisions from CSV file.
    
    Args:
        filepath: Path to CSV file (optional)
        
    Returns:
        DataFrame with existing decisions
    """
    if filepath is None:
        filepath = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
            logger.info(f"Loaded {len(df)} existing decisions from {filepath}")
            return df
        except Exception as e:
            logger.error(f"Failed to load existing CSV file: {e}")
            return pd.DataFrame(columns=CSV_COLUMNS)
    else:
        logger.info("No existing CSV file found")
        return pd.DataFrame(columns=CSV_COLUMNS)


def append_decisions_to_csv(new_decisions: List[Dict[str, str]], filepath: str = None) -> str:
    """
    Append new decisions to existing CSV file.
    
    Args:
        new_decisions: List of new decision data
        filepath: Path to existing CSV file
        
    Returns:
        Path to the updated CSV file
    """
    if filepath is None:
        filepath = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    # Load existing data
    existing_df = load_existing_decisions(filepath)
    
    # Get the next ID
    next_id = len(existing_df) + 1
    
    # Prepare new data
    prepared_new_data = []
    for decision in new_decisions:
        prepared_decision = prepare_decision_data(decision, next_id)
        prepared_new_data.append(prepared_decision)
        next_id += 1
    
    # Combine with existing data
    new_df = pd.DataFrame(prepared_new_data, columns=CSV_COLUMNS)
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    
    # Save the combined data
    combined_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    logger.info(f"Appended {len(new_decisions)} new decisions to {filepath}")
    
    return filepath


def validate_decision_data(decision_data: Dict[str, str]) -> List[str]:
    """
    Validate decision data and return list of issues.
    
    Args:
        decision_data: Decision data to validate
        
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    # Check required fields
    required_fields = ['decision_number', 'decision_url']
    for field in required_fields:
        if not decision_data.get(field):
            issues.append(f"Missing required field: {field}")
    
    # Check content length
    content = decision_data.get('decision_content', '')
    if len(content) < 50:
        issues.append("Decision content is too short (less than 50 characters)")
    
    # Check URL format
    url = decision_data.get('decision_url', '')
    if url and not url.startswith('https://www.gov.il'):
        issues.append("Invalid URL format")
    
    return issues


if __name__ == "__main__":
    # Test data management
    test_decisions = [
        {
            'decision_number': '2980',
            'decision_date': '2025-04-27',
            'committee': 'הממשלה ה- 37',
            'decision_title': 'בדיקת מערכת נתונים',
            'decision_content': 'זוהי החלטה לבדיקת מערכת ניהול הנתונים ושמירת המידע בפורמט CSV.',
            'decision_url': 'https://www.gov.il/he/pages/dec2980-2025',
            'summary': 'החלטה לבדיקת מערכת נתונים',
            'operativity': 'אופרטיבית',
            'tags_policy_area': 'טכנולוגיה',
            'tags_government_body': 'הממשלה',
            'tags_location': '',
            'all_tags': 'טכנולוגיה; הממשלה',
            'government_number': '37',
            'prime_minister': 'בנימין נתניהו',
            'decision_key': '37_2980'
        }
    ]
    
    try:
        filepath = save_decisions_to_csv(test_decisions, "test_decisions.csv")
        print(f"Test CSV saved to: {filepath}")
        
        # Validate the test data
        issues = validate_decision_data(test_decisions[0])
        if issues:
            print(f"Validation issues: {issues}")
        else:
            print("Data validation passed")
            
    except Exception as e:
        print(f"Error: {e}")