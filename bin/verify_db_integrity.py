#!/usr/bin/env python3
"""
Database Integrity Verification Script for GOV2DB

This script verifies the integrity fixes implemented in migration 004:
- Checks for remaining duplicate decision_keys
- Validates URL patterns and consistency
- Reports on constraint enforcement
- Provides detailed statistics on database health

Usage:
    python bin/verify_db_integrity.py
    python bin/verify_db_integrity.py --comprehensive
    python bin/verify_db_integrity.py --fix-issues  # Not implemented - use migration instead
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any

# Add the project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.db.dal import validate_decision_urls
from src.gov_scraper.scrapers.decision import validate_url_against_decision_key

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseIntegrityChecker:
    """Comprehensive database integrity verification for GOV2DB."""

    def __init__(self):
        self.client = get_supabase_client()
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'checks_performed': [],
            'issues_found': [],
            'statistics': {},
            'recommendations': []
        }

    def run_all_checks(self, comprehensive: bool = False) -> Dict[str, Any]:
        """
        Run all integrity checks.

        Args:
            comprehensive: If True, run extensive checks (slower)

        Returns:
            Dict with all check results
        """
        logger.info("Starting database integrity verification...")

        # Basic integrity checks
        self.check_duplicate_keys()
        self.check_constraint_enforcement()
        self.check_malformed_keys()
        self.check_missing_required_data()

        # URL integrity checks
        if comprehensive:
            self.check_url_integrity_comprehensive()
        else:
            self.check_url_integrity_sample()

        # Statistical analysis
        self.gather_database_statistics()

        # Generate recommendations
        self.generate_recommendations()

        logger.info("Database integrity verification complete")
        return self.results

    def check_duplicate_keys(self):
        """Check for remaining duplicate decision_keys."""
        logger.info("Checking for duplicate decision_keys...")

        try:
            # Query to find duplicates
            query = """
            SELECT decision_key, COUNT(*) as count
            FROM israeli_government_decisions
            GROUP BY decision_key
            HAVING COUNT(*) > 1
            ORDER BY count DESC, decision_key
            """

            response = self.client.rpc('execute_sql', {'query': query}).execute()

            if response.data:
                duplicate_count = len(response.data)
                total_affected = sum(row['count'] for row in response.data)

                self.results['issues_found'].append({
                    'type': 'DUPLICATE_KEYS',
                    'severity': 'CRITICAL',
                    'count': duplicate_count,
                    'total_affected_records': total_affected,
                    'sample_keys': [row['decision_key'] for row in response.data[:5]],
                    'message': f"Found {duplicate_count} decision_keys with duplicates affecting {total_affected} records"
                })

                logger.error(f"CRITICAL: {duplicate_count} duplicate decision_keys found!")
            else:
                logger.info("✅ No duplicate decision_keys found")
                self.results['statistics']['duplicate_keys'] = 0

            self.results['checks_performed'].append('duplicate_keys')

        except Exception as e:
            logger.error(f"Failed to check duplicates: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'HIGH',
                'message': f"Duplicate check failed: {e}"
            })

    def check_constraint_enforcement(self):
        """Verify that unique constraints are properly enforced."""
        logger.info("Checking constraint enforcement...")

        try:
            # Test unique constraint by attempting duplicate insertion
            test_key = f"TEST_CONSTRAINT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Try to insert test record
            test_record = {
                'decision_key': test_key,
                'government_number': '999',
                'decision_number': '999',
                'decision_title': 'Test Record',
                'decision_content': 'Test Content'
            }

            # First insert should succeed
            self.client.table("israeli_government_decisions").insert([test_record]).execute()

            # Second insert should fail due to unique constraint
            constraint_working = False
            try:
                self.client.table("israeli_government_decisions").insert([test_record]).execute()
                # If we reach here, constraint is NOT working
                self.results['issues_found'].append({
                    'type': 'CONSTRAINT_NOT_ENFORCED',
                    'severity': 'CRITICAL',
                    'message': "Unique constraint on decision_key is not enforced"
                })
            except Exception as constraint_error:
                if 'unique' in str(constraint_error).lower() or 'duplicate' in str(constraint_error).lower():
                    constraint_working = True
                    logger.info("✅ Unique constraint is properly enforced")
                else:
                    logger.warning(f"Unexpected constraint error: {constraint_error}")

            # Clean up test record
            self.client.table("israeli_government_decisions").delete().eq("decision_key", test_key).execute()

            if constraint_working:
                self.results['statistics']['unique_constraint_enforced'] = True
            else:
                self.results['statistics']['unique_constraint_enforced'] = False

            self.results['checks_performed'].append('constraint_enforcement')

        except Exception as e:
            logger.error(f"Failed to check constraints: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'HIGH',
                'message': f"Constraint check failed: {e}"
            })

    def check_malformed_keys(self):
        """Check for malformed decision_key formats."""
        logger.info("Checking for malformed decision_keys...")

        try:
            # Get all decision keys
            response = (
                self.client.table("israeli_government_decisions")
                .select("decision_key, government_number, decision_number")
                .execute()
            )

            records = response.data
            malformed_keys = []

            for record in records:
                key = record['decision_key']
                if not key:
                    malformed_keys.append({
                        'key': key,
                        'issue': 'NULL_KEY',
                        'government_number': record.get('government_number'),
                        'decision_number': record.get('decision_number')
                    })
                    continue

                # Check valid patterns
                valid_standard = bool(re.match(r'^\d+_\d+$', key))
                valid_special = bool(re.match(r'^\d+_(COMMITTEE|SECURITY|ECON|SPECIAL)_\d+$', key))

                if not (valid_standard or valid_special):
                    malformed_keys.append({
                        'key': key,
                        'issue': 'INVALID_FORMAT',
                        'government_number': record.get('government_number'),
                        'decision_number': record.get('decision_number')
                    })

            if malformed_keys:
                self.results['issues_found'].append({
                    'type': 'MALFORMED_KEYS',
                    'severity': 'MEDIUM',
                    'count': len(malformed_keys),
                    'sample_keys': malformed_keys[:10],
                    'message': f"Found {len(malformed_keys)} malformed decision_keys"
                })
                logger.warning(f"Found {len(malformed_keys)} malformed decision_keys")
            else:
                logger.info("✅ All decision_keys are properly formatted")

            self.results['statistics']['malformed_keys'] = len(malformed_keys)
            self.results['checks_performed'].append('malformed_keys')

        except Exception as e:
            logger.error(f"Failed to check malformed keys: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'HIGH',
                'message': f"Malformed key check failed: {e}"
            })

    def check_missing_required_data(self):
        """Check for missing required data fields."""
        logger.info("Checking for missing required data...")

        try:
            # Check for NULL or empty required fields
            checks = [
                ('decision_title', 'NULL OR decision_title = \'\''),
                ('decision_content', 'NULL OR decision_content = \'\''),
                ('decision_key', 'NULL OR decision_key = \'\''),
                ('government_number', 'NULL OR government_number = \'\''),
                ('decision_number', 'NULL OR decision_number = \'\'')
            ]

            missing_data_summary = {}

            for field, condition in checks:
                response = (
                    self.client.table("israeli_government_decisions")
                    .select("id")
                    .filter(field, 'is', None)  # Supabase syntax for NULL check
                    .execute()
                )

                count = len(response.data) if response.data else 0
                missing_data_summary[field] = count

                if count > 0:
                    severity = 'HIGH' if field in ['decision_key', 'decision_title'] else 'MEDIUM'
                    self.results['issues_found'].append({
                        'type': 'MISSING_REQUIRED_DATA',
                        'severity': severity,
                        'field': field,
                        'count': count,
                        'message': f"Found {count} records with missing {field}"
                    })
                    logger.warning(f"Found {count} records with missing {field}")

            self.results['statistics']['missing_data'] = missing_data_summary
            self.results['checks_performed'].append('missing_required_data')

            # Check if any critical fields are missing
            critical_missing = sum(
                missing_data_summary[field] for field in ['decision_key', 'decision_title', 'decision_content']
            )

            if critical_missing == 0:
                logger.info("✅ No missing critical data found")

        except Exception as e:
            logger.error(f"Failed to check missing data: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'HIGH',
                'message': f"Missing data check failed: {e}"
            })

    def check_url_integrity_sample(self, sample_size: int = 1000):
        """Check URL integrity for a sample of records."""
        logger.info(f"Checking URL integrity for {sample_size} records...")

        try:
            url_results = validate_decision_urls(limit=sample_size)

            if 'error' in url_results:
                self.results['issues_found'].append({
                    'type': 'URL_CHECK_FAILED',
                    'severity': 'MEDIUM',
                    'message': f"URL validation failed: {url_results['error']}"
                })
                return

            # Process URL validation results
            validity_rate = url_results.get('validity_rate', 0)
            invalid_count = url_results.get('invalid_urls', 0)

            if invalid_count > 0:
                severity = 'HIGH' if validity_rate < 0.95 else 'MEDIUM'
                self.results['issues_found'].append({
                    'type': 'URL_INTEGRITY_ISSUES',
                    'severity': severity,
                    'count': invalid_count,
                    'validity_rate': validity_rate,
                    'sample_issues': url_results.get('problematic_records', [])[:5],
                    'systematic_issues': url_results.get('systematic_issues', []),
                    'message': f"Found {invalid_count} URL integrity issues (validity: {validity_rate:.2%})"
                })
                logger.warning(f"URL integrity issues: {invalid_count}/{sample_size} invalid ({validity_rate:.2%} valid)")
            else:
                logger.info(f"✅ URL integrity check passed ({validity_rate:.2%} valid)")

            self.results['statistics']['url_validation'] = url_results
            self.results['checks_performed'].append('url_integrity_sample')

        except Exception as e:
            logger.error(f"Failed to check URL integrity: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'MEDIUM',
                'message': f"URL integrity check failed: {e}"
            })

    def check_url_integrity_comprehensive(self):
        """Comprehensive URL integrity check for all records."""
        logger.info("Running comprehensive URL integrity check...")

        try:
            # Get total record count first
            count_response = (
                self.client.table("israeli_government_decisions")
                .select("id", count="exact")
                .execute()
            )

            total_records = count_response.count
            logger.info(f"Checking URL integrity for all {total_records} records...")

            # Process in chunks to avoid memory issues
            chunk_size = 5000
            all_results = {
                'total_checked': 0,
                'valid_urls': 0,
                'invalid_urls': 0,
                'missing_urls': 0,
                'problematic_records': [],
                'systematic_issues': []
            }

            for offset in range(0, total_records, chunk_size):
                logger.info(f"Processing records {offset} to {min(offset + chunk_size, total_records)}...")

                chunk_results = validate_decision_urls(limit=chunk_size)
                if 'error' not in chunk_results:
                    # Aggregate results
                    all_results['total_checked'] += chunk_results.get('total_checked', 0)
                    all_results['valid_urls'] += chunk_results.get('valid_urls', 0)
                    all_results['invalid_urls'] += chunk_results.get('invalid_urls', 0)
                    all_results['missing_urls'] += chunk_results.get('missing_urls', 0)
                    all_results['problematic_records'].extend(chunk_results.get('problematic_records', []))
                    all_results['systematic_issues'].extend(chunk_results.get('systematic_issues', []))

            # Calculate final statistics
            validity_rate = (
                all_results['valid_urls'] / all_results['total_checked']
                if all_results['total_checked'] > 0 else 0
            )
            all_results['validity_rate'] = validity_rate

            # Report results
            if all_results['invalid_urls'] > 0:
                severity = 'CRITICAL' if validity_rate < 0.90 else 'HIGH' if validity_rate < 0.95 else 'MEDIUM'
                self.results['issues_found'].append({
                    'type': 'COMPREHENSIVE_URL_ISSUES',
                    'severity': severity,
                    'total_invalid': all_results['invalid_urls'],
                    'validity_rate': validity_rate,
                    'systematic_issues_count': len(all_results['systematic_issues']),
                    'message': f"Comprehensive URL check: {all_results['invalid_urls']} invalid URLs ({validity_rate:.2%} valid)"
                })

            self.results['statistics']['comprehensive_url_validation'] = all_results
            self.results['checks_performed'].append('url_integrity_comprehensive')

            logger.info(f"Comprehensive URL check complete: {validity_rate:.2%} valid")

        except Exception as e:
            logger.error(f"Failed comprehensive URL check: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'HIGH',
                'message': f"Comprehensive URL check failed: {e}"
            })

    def gather_database_statistics(self):
        """Gather general database statistics."""
        logger.info("Gathering database statistics...")

        try:
            # Total records
            count_response = (
                self.client.table("israeli_government_decisions")
                .select("id", count="exact")
                .execute()
            )
            total_records = count_response.count

            # Records by government
            govt_response = (
                self.client.table("israeli_government_decisions")
                .select("government_number")
                .execute()
            )

            govt_distribution = {}
            for record in govt_response.data:
                gov_num = record['government_number']
                govt_distribution[gov_num] = govt_distribution.get(gov_num, 0) + 1

            # Date range
            date_response = (
                self.client.table("israeli_government_decisions")
                .select("decision_date")
                .order("decision_date", desc=False)
                .limit(1)
                .execute()
            )
            earliest_date = date_response.data[0]['decision_date'] if date_response.data else None

            date_response = (
                self.client.table("israeli_government_decisions")
                .select("decision_date")
                .order("decision_date", desc=True)
                .limit(1)
                .execute()
            )
            latest_date = date_response.data[0]['decision_date'] if date_response.data else None

            self.results['statistics'].update({
                'total_records': total_records,
                'government_distribution': govt_distribution,
                'date_range': {
                    'earliest': earliest_date,
                    'latest': latest_date
                },
                'unique_governments': len(govt_distribution)
            })

            logger.info(f"Database contains {total_records} records across {len(govt_distribution)} governments")
            self.results['checks_performed'].append('database_statistics')

        except Exception as e:
            logger.error(f"Failed to gather statistics: {e}")
            self.results['issues_found'].append({
                'type': 'CHECK_FAILED',
                'severity': 'LOW',
                'message': f"Statistics gathering failed: {e}"
            })

    def generate_recommendations(self):
        """Generate recommendations based on found issues."""
        recommendations = []

        # Check for critical issues
        critical_issues = [issue for issue in self.results['issues_found'] if issue['severity'] == 'CRITICAL']
        high_issues = [issue for issue in self.results['issues_found'] if issue['severity'] == 'HIGH']

        if critical_issues:
            recommendations.append({
                'priority': 'IMMEDIATE',
                'category': 'CRITICAL_FIXES',
                'action': 'Run migration 004 immediately to fix duplicate keys and constraints',
                'reason': f"Found {len(critical_issues)} critical issues that prevent normal operation"
            })

        if any(issue['type'] == 'DUPLICATE_KEYS' for issue in self.results['issues_found']):
            recommendations.append({
                'priority': 'IMMEDIATE',
                'category': 'DUPLICATES',
                'action': 'Execute database/migrations/004_fix_duplicates_and_constraints.sql',
                'reason': 'Duplicate decision_keys violate database integrity'
            })

        if any(issue['type'] == 'CONSTRAINT_NOT_ENFORCED' for issue in self.results['issues_found']):
            recommendations.append({
                'priority': 'IMMEDIATE',
                'category': 'CONSTRAINTS',
                'action': 'Add unique constraint on decision_key column',
                'reason': 'Unique constraints are not enforced, allowing duplicates'
            })

        # URL integrity issues
        url_issues = [issue for issue in self.results['issues_found'] if 'URL' in issue['type']]
        if url_issues:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'URL_INTEGRITY',
                'action': 'Review and fix URL construction logic in scraper',
                'reason': 'URL mismatches indicate systematic scraping issues'
            })

        # Missing data
        missing_data_issues = [issue for issue in self.results['issues_found'] if issue['type'] == 'MISSING_REQUIRED_DATA']
        if missing_data_issues:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'DATA_QUALITY',
                'action': 'Re-scrape records with missing required data',
                'reason': 'Missing titles and content affect data completeness'
            })

        # General health
        total_issues = len(self.results['issues_found'])
        if total_issues == 0:
            recommendations.append({
                'priority': 'LOW',
                'category': 'MAINTENANCE',
                'action': 'Schedule regular integrity checks',
                'reason': 'Database appears healthy - maintain with regular monitoring'
            })

        self.results['recommendations'] = recommendations

    def print_summary(self):
        """Print a human-readable summary of results."""
        print("\n" + "="*60)
        print("DATABASE INTEGRITY VERIFICATION REPORT")
        print("="*60)
        print(f"Timestamp: {self.results['timestamp']}")
        print(f"Checks Performed: {len(self.results['checks_performed'])}")

        # Statistics
        stats = self.results.get('statistics', {})
        print(f"\nDatabase Statistics:")
        print(f"  Total Records: {stats.get('total_records', 'N/A')}")
        print(f"  Unique Governments: {stats.get('unique_governments', 'N/A')}")
        print(f"  Date Range: {stats.get('date_range', {}).get('earliest', 'N/A')} to {stats.get('date_range', {}).get('latest', 'N/A')}")

        # Issues
        issues = self.results.get('issues_found', [])
        print(f"\nIssues Found: {len(issues)}")

        if issues:
            critical = [i for i in issues if i['severity'] == 'CRITICAL']
            high = [i for i in issues if i['severity'] == 'HIGH']
            medium = [i for i in issues if i['severity'] == 'MEDIUM']

            if critical:
                print(f"  🔴 CRITICAL: {len(critical)}")
                for issue in critical:
                    print(f"     - {issue['message']}")

            if high:
                print(f"  🟠 HIGH: {len(high)}")
                for issue in high:
                    print(f"     - {issue['message']}")

            if medium:
                print(f"  🟡 MEDIUM: {len(medium)}")
                for issue in medium:
                    print(f"     - {issue['message']}")

        else:
            print("  ✅ No issues found - database appears healthy!")

        # Recommendations
        recommendations = self.results.get('recommendations', [])
        if recommendations:
            print(f"\nRecommendations ({len(recommendations)}):")
            for rec in recommendations:
                priority_icon = "🚨" if rec['priority'] == 'IMMEDIATE' else "⚠️" if rec['priority'] == 'HIGH' else "📋"
                print(f"  {priority_icon} {rec['priority']}: {rec['action']}")

        print("="*60)

    def save_report(self, filename: str = None):
        """Save detailed report to JSON file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data/qa_reports/db_integrity_report_{timestamp}.json"

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        logger.info(f"Detailed report saved to: {filename}")
        return filename


def main():
    parser = argparse.ArgumentParser(description="Verify database integrity for GOV2DB")
    parser.add_argument(
        '--comprehensive',
        action='store_true',
        help='Run comprehensive checks (slower, checks all records)'
    )
    parser.add_argument(
        '--save-report',
        type=str,
        help='Save detailed JSON report to specified file'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress detailed output, only show summary'
    )

    args = parser.parse_args()

    # Initialize checker
    checker = DatabaseIntegrityChecker()

    # Run checks
    results = checker.run_all_checks(comprehensive=args.comprehensive)

    # Print summary unless quiet
    if not args.quiet:
        checker.print_summary()

    # Save report
    if args.save_report:
        checker.save_report(args.save_report)
    else:
        # Auto-save with timestamp
        report_file = checker.save_report()
        print(f"\nDetailed report saved: {report_file}")

    # Exit with appropriate code
    critical_issues = [i for i in results['issues_found'] if i['severity'] == 'CRITICAL']
    if critical_issues:
        sys.exit(1)  # Critical issues found
    elif results['issues_found']:
        sys.exit(2)  # Non-critical issues found
    else:
        sys.exit(0)  # All checks passed


if __name__ == "__main__":
    main()