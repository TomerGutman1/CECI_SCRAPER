"""
QA Integration Example

Demonstrates how to use the new QA architecture for various scenarios.
"""

import sys
import os
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.gov_scraper.processors.qa_processor import QAProcessor
from src.gov_scraper.processors.qa_core import CheckSeverity
from src.gov_scraper.db.connector import get_supabase_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_basic_scan():
    """Basic QA scan example."""
    logger.info("=== Basic QA Scan Example ===")

    # Sample records for testing
    sample_records = [
        {
            "decision_key": "36_123",
            "decision_date": "2023-12-25",
            "government_body": "משרד החינוך",
            "policy_areas": ["חינוך"],
            "decision_content": "החלטה בנושא שיפור מערכת החינוך בישראל",
            "decision_link": "https://www.gov.il/decisions/36_123",
            "operativity": "אופרטיבית"
        },
        {
            "decision_key": "36_124",
            "decision_date": "2023-12-26",
            "government_body": "משרד הבריאות",
            "policy_areas": ["בריאות ורפואה"],
            "decision_content": "החלטה על שיפור שירותי הבריאות",
            "decision_link": "https://www.gov.il/decisions/36_124",
            "operativity": "דקלרטיבית"
        }
    ]

    # Create processor
    processor = QAProcessor()

    # Run basic scan
    report = processor.run_scan(
        records=sample_records,
        checks="essential"  # Content, tags, dates, departments
    )

    logger.info(f"Scan completed: {report.total_issues} issues found")

    # Save report
    report_path = "data/qa_reports/basic_scan_example.json"
    processor.save_report(report, report_path, format='json')

    # Save summary
    summary_path = "data/qa_reports/basic_scan_summary.txt"
    processor.save_report(report, summary_path, format='summary')

    return report


def example_comprehensive_scan():
    """Comprehensive QA scan with all checks."""
    logger.info("=== Comprehensive QA Scan Example ===")

    # Load records from database
    supabase = get_supabase_client()
    response = supabase.table('israeli_government_decisions').select('*').limit(100).execute()
    records = response.data

    logger.info(f"Loaded {len(records)} records from database")

    # Create processor with custom configuration
    processor = QAProcessor(
        batch_size=50,  # Smaller batches for demonstration
        enable_progress_tracking=True
    )

    # Configure individual checks
    check_configs = {
        "content_quality": {
            "duplicate_threshold": 0.9,
            "min_content_length": 100
        },
        "url_integrity": {
            "check_accessibility": False,  # Skip HTTP checks for speed
            "request_timeout": 5
        },
        "tag_validation": {
            "check_content_relevance": True,
            "min_relevance_score": 0.2
        },
        "date_consistency": {
            "max_future_days": 90
        }
    }

    # Run comprehensive scan
    report = processor.run_scan(
        records=records,
        checks="comprehensive",
        check_configs=check_configs
    )

    logger.info(f"Comprehensive scan completed: {report.total_issues} issues found")

    # Analyze issue distribution
    distribution = processor.get_issue_distribution(report)
    logger.info(f"Issues by severity: {distribution['by_severity']}")
    logger.info(f"Checks with issues: {distribution['coverage_stats']['checks_with_issues']}")

    # Save detailed report
    timestamp = report.timestamp.replace(':', '-').split('.')[0]
    report_path = f"data/qa_reports/comprehensive_scan_{timestamp}.json"
    processor.save_report(report, report_path)

    return report


def example_focused_scans():
    """Example of focused scans on specific areas."""
    logger.info("=== Focused QA Scans Example ===")

    # Sample problematic records
    problematic_records = [
        {
            "decision_key": "35_999",
            "decision_date": "invalid-date",  # Date issue
            "government_body": "משרד לא קיים",  # Department issue
            "policy_areas": ["תג_לא_מורשה"],  # Tag issue
            "decision_content": "תוכן קצר",  # Content issue
            "decision_link": "not-a-url"  # URL issue
        }
    ]

    processor = QAProcessor()

    # Run focused scans
    focus_areas = ['content', 'metadata', 'consistency', 'integrity']

    for area in focus_areas:
        logger.info(f"Running focused scan: {area}")

        report = processor.run_focused_scan(
            records=problematic_records,
            focus_area=area
        )

        logger.info(f"{area} scan: {report.total_issues} issues found")

        # Save focused report
        report_path = f"data/qa_reports/focused_{area}_scan.json"
        processor.save_report(report, report_path)


def example_custom_check():
    """Example of creating and using a custom QA check."""
    logger.info("=== Custom QA Check Example ===")

    from src.gov_scraper.processors.qa_core import AbstractQACheck, CheckSeverity

    class CustomBusinessLogicCheck(AbstractQACheck):
        """Custom check for business logic validation."""

        def __init__(self, **kwargs):
            super().__init__(
                check_name="custom_business_logic",
                description="Validates business-specific rules",
                **kwargs
            )

        def _validate_record(self, record):
            issues = []
            decision_key = record.get('decision_key', 'unknown')

            # Example business rule: Educational decisions must have education ministry
            policy_areas = record.get('policy_areas', [])
            government_body = record.get('government_body', '')

            if isinstance(policy_areas, str):
                policy_areas = [tag.strip() for tag in policy_areas.split(',') if tag.strip()]

            if "חינוך" in policy_areas and "חינוך" not in government_body:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field="government_body",
                    current_value=government_body,
                    description="Education policy decision not from education ministry",
                    expected_value="משרד החינוך or related body",
                    business_rule="education_ministry_consistency"
                ))

            return issues

        def _generate_summary(self, issues, total_scanned):
            rule_violations = {}
            for issue in issues:
                rule = issue.metadata.get('business_rule', 'unknown')
                rule_violations[rule] = rule_violations.get(rule, 0) + 1

            return {
                "total_scanned": total_scanned,
                "total_violations": len(issues),
                "violations_by_rule": rule_violations
            }

    # Register custom check
    from src.gov_scraper.processors.qa_core import QACheckFactory
    QACheckFactory.register("custom_business_logic", CustomBusinessLogicCheck)

    # Test custom check
    test_records = [
        {
            "decision_key": "test_1",
            "policy_areas": ["חינוך"],
            "government_body": "משרד הביטחון"  # Wrong ministry for education
        }
    ]

    processor = QAProcessor()
    result = processor.run_check("custom_business_logic", test_records)

    logger.info(f"Custom check found {result.issues_found} business rule violations")


def example_progress_tracking():
    """Example of progress tracking and resumability."""
    logger.info("=== Progress Tracking Example ===")

    # Create large dataset for demonstration
    large_records = []
    for i in range(1000):
        large_records.append({
            "decision_key": f"test_{i}",
            "decision_date": "2023-01-01",
            "government_body": "משרד החינוך",
            "policy_areas": ["חינוך"],
            "decision_content": f"החלטה מספר {i} בנושא חינוך"
        })

    processor = QAProcessor(
        batch_size=100,  # Small batches to see progress
        enable_progress_tracking=True
    )

    # Run scan with progress tracking
    report = processor.run_scan(
        records=large_records,
        checks=["content_quality", "tag_validation"]
    )

    logger.info(f"Processed {len(large_records)} records with progress tracking")

    # List available checkpoints
    checkpoints = processor.progress_manager.list_checkpoints()
    logger.info(f"Available checkpoints: {len(checkpoints)}")

    # Cleanup old checkpoints
    processor.cleanup_checkpoints(keep_latest=5)


def example_composite_check():
    """Example of creating and using composite checks."""
    logger.info("=== Composite Check Example ===")

    from src.gov_scraper.processors.qa_core import QACheckFactory

    # Create comprehensive content validation check
    content_composite = QACheckFactory.create_composite_check(
        "content_validation_suite",
        ["content_quality", "duplicate_detection"],
        description="Complete content validation suite"
    )

    # Create metadata validation check
    metadata_composite = QACheckFactory.create_composite_check(
        "metadata_validation_suite",
        ["tag_validation", "date_consistency", "department_validation"],
        description="Complete metadata validation suite"
    )

    test_records = [
        {
            "decision_key": "composite_test_1",
            "decision_date": "2023-12-25",
            "government_body": "משרד החינוך",
            "policy_areas": ["חינוך"],
            "decision_content": "תוכן החלטה מפורט בנושא חינוך וחדשנות"
        }
    ]

    # Run composite checks
    content_result = content_composite.run(test_records)
    metadata_result = metadata_composite.run(test_records)

    logger.info(f"Content validation: {content_result.issues_found} issues")
    logger.info(f"Metadata validation: {metadata_result.issues_found} issues")


def main():
    """Run all examples."""
    # Ensure output directory exists
    os.makedirs("data/qa_reports", exist_ok=True)

    try:
        # Run examples
        example_basic_scan()
        example_focused_scans()
        example_custom_check()
        example_progress_tracking()
        example_composite_check()

        # Only run comprehensive scan if database is available
        try:
            example_comprehensive_scan()
        except Exception as e:
            logger.warning(f"Skipping comprehensive scan (database not available): {e}")

        logger.info("All examples completed successfully!")

    except Exception as e:
        logger.error(f"Example failed: {e}")
        raise


if __name__ == "__main__":
    main()