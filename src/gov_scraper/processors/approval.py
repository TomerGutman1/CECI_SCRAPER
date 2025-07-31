"""User approval workflow manager for database insertions."""

import os
import logging
from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def display_decision_summary(decisions: List[Dict]) -> None:
    """
    Display a summary of decisions for user review.
    
    Args:
        decisions: List of decision dictionaries to summarize
    """
    if not decisions:
        print("No decisions to display.")
        return
    
    print("\n" + "=" * 80)
    print("DECISIONS SUMMARY FOR APPROVAL")
    print("=" * 80)
    print(f"Total decisions found: {len(decisions)}")
    print()
    
    # Display summary statistics
    dates = [d.get('decision_date', '') for d in decisions if d.get('decision_date')]
    if dates:
        print(f"Date range: {min(dates)} to {max(dates)}")
    
    numbers = [d.get('decision_number', '') for d in decisions if d.get('decision_number')]
    if numbers:
        try:
            num_numbers = [int(str(n)) for n in numbers if str(n).isdigit()]
            if num_numbers:
                print(f"Decision numbers: {min(num_numbers)} to {max(num_numbers)}")
        except:
            print(f"Decision numbers: {len(numbers)} found")
    
    print()


def display_detailed_decisions(decisions: List[Dict], max_display: int = 5) -> None:
    """
    Display detailed information about decisions.
    
    Args:
        decisions: List of decision dictionaries
        max_display: Maximum number of decisions to display in detail
    """
    if not decisions:
        return
    
    print("\nDETAILED DECISION PREVIEW:")
    print("-" * 60)
    
    for i, decision in enumerate(decisions[:max_display], 1):
        print(f"\n{i}. Decision #{decision.get('decision_number', 'N/A')}")
        print(f"   Date: {decision.get('decision_date', 'N/A')}")
        print(f"   Title: {decision.get('decision_title', 'N/A')[:80]}...")
        print(f"   Committee: {decision.get('committee', 'N/A')}")
        print(f"   URL: {decision.get('decision_url', 'N/A')}")
        print(f"   Content length: {len(decision.get('decision_content', ''))} characters")
        print(f"   Has AI summary: {'Yes' if decision.get('summary') else 'No'}")
        print(f"   Decision key: {decision.get('decision_key', 'N/A')}")
    
    if len(decisions) > max_display:
        print(f"\n... and {len(decisions) - max_display} more decisions")


def create_preview_csv(decisions: List[Dict], filename: Optional[str] = None) -> str:
    """
    Create a preview CSV file for user review.
    
    Args:
        decisions: List of decision dictionaries
        filename: Optional filename for the CSV
        
    Returns:
        Path to the created CSV file
    """
    if not decisions:
        raise ValueError("No decisions to create preview CSV")
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"preview_decisions_{timestamp}.csv"
    
    # Ensure data directory exists
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    filepath = os.path.join(data_dir, filename)
    
    # Create DataFrame and save
    df = pd.DataFrame(decisions)
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    logger.info(f"Created preview CSV: {filepath}")
    return filepath


def get_user_approval(decisions: List[Dict], baseline_decision: Optional[Dict] = None) -> bool:
    """
    Get user approval for inserting decisions into the database.
    
    Args:
        decisions: List of decision dictionaries to be inserted
        baseline_decision: Latest decision from database (for context)
        
    Returns:
        True if user approves insertion, False otherwise
    """
    if not decisions:
        print("No decisions to approve.")
        return False
    
    # Display summary
    display_decision_summary(decisions)
    
    # Show baseline context
    if baseline_decision:
        print(f"\nLATEST DECISION IN DATABASE:")
        print(f"  Number: {baseline_decision.get('decision_number', 'N/A')}")
        print(f"  Date: {baseline_decision.get('decision_date', 'N/A')}")
        print(f"  Title: {baseline_decision.get('decision_title', 'N/A')[:60]}...")
    
    # Display detailed preview
    display_detailed_decisions(decisions)
    
    # Create preview CSV
    try:
        preview_file = create_preview_csv(decisions)
        print(f"\n📄 Preview CSV created: {preview_file}")
        print("   You can review this file before approving the insertion.")
    except Exception as e:
        logger.warning(f"Failed to create preview CSV: {e}")
    
    # Get user decision
    print("\n" + "=" * 80)
    print("APPROVAL REQUIRED")
    print("=" * 80)
    print(f"Ready to insert {len(decisions)} new decisions into the database.")
    print("This action will:")
    print("  - Insert new government decisions")
    print("  - Skip any duplicates automatically")
    print("  - Log all operations for audit trail")
    print()
    
    while True:
        response = input("Do you want to proceed with database insertion? (y/n/d for details): ").lower().strip()
        
        if response in ['y', 'yes']:
            print("✅ Approval granted. Proceeding with database insertion...")
            return True
        elif response in ['n', 'no']:
            print("❌ Insertion cancelled by user.")
            return False
        elif response in ['d', 'details']:
            print("\nShowing more details...")
            display_detailed_decisions(decisions, max_display=len(decisions))
            continue
        else:
            print("Please enter 'y' for yes, 'n' for no, or 'd' for more details.")


def confirm_insertion_results(inserted_count: int, duplicate_count: int, error_messages: List[str]) -> None:
    """
    Display the results of database insertion to the user.
    
    Args:
        inserted_count: Number of decisions successfully inserted
        duplicate_count: Number of duplicates skipped
        error_messages: List of error messages encountered
    """
    print("\n" + "=" * 80)
    print("DATABASE INSERTION RESULTS")
    print("=" * 80)
    
    if inserted_count > 0:
        print(f"✅ Successfully inserted: {inserted_count} decisions")
    
    if duplicate_count > 0:
        print(f"⚠️  Duplicates skipped: {duplicate_count} decisions")
    
    if error_messages:
        print(f"❌ Errors encountered: {len(error_messages)}")
        print("\nError details:")
        for i, error in enumerate(error_messages[:3], 1):  # Show first 3 errors
            print(f"  {i}. {error}")
        if len(error_messages) > 3:
            print(f"  ... and {len(error_messages) - 3} more errors (check logs)")
    
    total_processed = inserted_count + duplicate_count + len(error_messages)
    print(f"\nTotal decisions processed: {total_processed}")
    print(f"Success rate: {(inserted_count / total_processed * 100):.1f}%" if total_processed > 0 else "N/A")
    
    print("\n📊 Summary:")
    if inserted_count > 0:
        print(f"  - {inserted_count} new decisions added to database")
    if duplicate_count > 0:
        print(f"  - {duplicate_count} decisions already existed (skipped)")
    if error_messages:
        print(f"  - {len(error_messages)} decisions failed to insert")
    
    print("\n✅ Database operation completed.")


def interactive_decision_review(decisions: List[Dict]) -> List[Dict]:
    """
    Allow user to interactively review and select decisions for insertion.
    
    Args:
        decisions: List of decision dictionaries
        
    Returns:
        List of approved decisions
    """
    if not decisions:
        return []
    
    print("\n" + "=" * 80)
    print("INTERACTIVE DECISION REVIEW")
    print("=" * 80)
    print("Review each decision individually and choose which to insert.")
    print("Commands: (y)es, (n)o, (s)kip remaining, (a)ll remaining, (q)uit")
    print()
    
    approved_decisions = []
    
    for i, decision in enumerate(decisions, 1):
        print(f"\nDecision {i}/{len(decisions)}:")
        print(f"  Number: {decision.get('decision_number', 'N/A')}")
        print(f"  Date: {decision.get('decision_date', 'N/A')}")
        print(f"  Title: {decision.get('decision_title', 'N/A')[:80]}...")
        print(f"  Committee: {decision.get('committee', 'N/A')}")
        print(f"  Content preview: {decision.get('decision_content', '')[:150]}...")
        
        while True:
            response = input(f"Include this decision? (y/n/s/a/q): ").lower().strip()
            
            if response in ['y', 'yes']:
                approved_decisions.append(decision)
                print("  ✅ Added")
                break
            elif response in ['n', 'no']:
                print("  ❌ Skipped")
                break
            elif response in ['s', 'skip']:
                print("  ⏭️  Skipping remaining decisions")
                return approved_decisions
            elif response in ['a', 'all']:
                print("  ✅ Adding all remaining decisions")
                approved_decisions.extend(decisions[i-1:])
                return approved_decisions
            elif response in ['q', 'quit']:
                print("  🚪 Quitting review")
                return approved_decisions
            else:
                print("  Please enter y/n/s/a/q")
    
    print(f"\n✅ Review complete. {len(approved_decisions)} decisions selected for insertion.")
    return approved_decisions


if __name__ == "__main__":
    # Test the approval manager
    test_decisions = [
        {
            'decision_number': '3284',
            'decision_date': '2025-07-24',
            'decision_title': 'Test Decision 1',
            'committee': 'Test Committee',
            'decision_content': 'This is test content for decision 1' * 10,
            'decision_url': 'https://www.gov.il/he/pages/dec3284-2025',
            'decision_key': '37_3284',
            'summary': 'Test summary'
        },
        {
            'decision_number': '3285',
            'decision_date': '2025-07-25',
            'decision_title': 'Test Decision 2',
            'committee': 'Test Committee 2',
            'decision_content': 'This is test content for decision 2' * 10,
            'decision_url': 'https://www.gov.il/he/pages/dec3285-2025',
            'decision_key': '37_3285',
            'summary': 'Test summary 2'
        }
    ]
    
    baseline = {
        'decision_number': '3283',
        'decision_date': '2025-07-23',
        'decision_title': 'Previous Decision'
    }
    
    print("Testing approval manager...")
    try:
        approved = get_user_approval(test_decisions, baseline)
        print(f"User approval result: {approved}")
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test error: {e}")