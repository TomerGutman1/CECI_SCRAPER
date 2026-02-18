#!/usr/bin/env python3
"""
Phase 4: Structural Integrity Check
==================================

Comprehensive database structural integrity validation for Israeli government decisions.
Checks key formats, field consistency, date validation, and unique constraints.
"""

import os
import sys
import json
import logging
import re
from datetime import datetime, date
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.gov_scraper.db.connector import get_supabase_client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StructuralIntegrityChecker:
    """Comprehensive structural integrity checker for the database."""

    def __init__(self):
        self.client = get_supabase_client()
        self.issues = []
        self.stats = defaultdict(int)

    def check_decision_key_format(self, records: List[Dict]) -> Dict:
        """
        Check decision_key format: must match pattern {government_number}_{decision_number}

        Returns:
            Dict with malformed keys, format violations, and statistics
        """
        logger.info("Checking decision_key format integrity...")

        # Expected pattern: number_number (e.g., "35_1234")
        key_pattern = re.compile(r'^(\d+)_(\d+)$')

        results = {
            'total_checked': 0,
            'malformed_keys': [],
            'format_violations': [],
            'null_keys': [],
            'empty_keys': [],
            'duplicate_keys': [],
            'pattern_analysis': defaultdict(int)
        }

        seen_keys = set()

        for record in records:
            results['total_checked'] += 1
            decision_key = record.get('decision_key')

            # Check for NULL/None keys
            if decision_key is None:
                results['null_keys'].append({
                    'id': record.get('id'),
                    'government_number': record.get('government_number'),
                    'decision_number': record.get('decision_number')
                })
                continue

            # Check for empty keys
            if not decision_key or decision_key.strip() == '':
                results['empty_keys'].append({
                    'id': record.get('id'),
                    'government_number': record.get('government_number'),
                    'decision_number': record.get('decision_number')
                })
                continue

            # Check for duplicates
            if decision_key in seen_keys:
                results['duplicate_keys'].append(decision_key)
            seen_keys.add(decision_key)

            # Check format pattern
            match = key_pattern.match(str(decision_key))
            if not match:
                results['malformed_keys'].append({
                    'decision_key': decision_key,
                    'id': record.get('id'),
                    'government_number': record.get('government_number'),
                    'decision_number': record.get('decision_number')
                })
                # Analyze malformed pattern
                if '_' not in str(decision_key):
                    results['pattern_analysis']['no_underscore'] += 1
                elif str(decision_key).count('_') > 1:
                    results['pattern_analysis']['multiple_underscores'] += 1
                else:
                    results['pattern_analysis']['non_numeric_parts'] += 1

        return results

    def check_field_consistency(self, records: List[Dict]) -> Dict:
        """
        Verify consistency between government_number/decision_number fields and decision_key.

        Returns:
            Dict with inconsistencies and mismatches
        """
        logger.info("Checking field consistency...")

        results = {
            'total_checked': 0,
            'government_number_mismatches': [],
            'decision_number_mismatches': [],
            'missing_government_number': [],
            'missing_decision_number': [],
            'field_inconsistencies': []
        }

        key_pattern = re.compile(r'^(\d+)_(\d+)$')

        for record in records:
            results['total_checked'] += 1

            decision_key = record.get('decision_key', '')
            gov_num = record.get('government_number')
            dec_num = record.get('decision_number')

            # Skip malformed keys (already caught in previous check)
            match = key_pattern.match(str(decision_key))
            if not match:
                continue

            key_gov_num, key_dec_num = match.groups()

            # Check government_number consistency
            if gov_num is None:
                results['missing_government_number'].append({
                    'decision_key': decision_key,
                    'id': record.get('id')
                })
            elif str(gov_num) != key_gov_num:
                results['government_number_mismatches'].append({
                    'decision_key': decision_key,
                    'id': record.get('id'),
                    'field_value': gov_num,
                    'key_value': key_gov_num
                })

            # Check decision_number consistency
            if dec_num is None:
                results['missing_decision_number'].append({
                    'decision_key': decision_key,
                    'id': record.get('id')
                })
            elif str(dec_num) != key_dec_num:
                results['decision_number_mismatches'].append({
                    'decision_key': decision_key,
                    'id': record.get('id'),
                    'field_value': dec_num,
                    'key_value': key_dec_num
                })

        return results

    def check_date_validation(self, records: List[Dict]) -> Dict:
        """
        Validate date fields for range and format correctness.

        Returns:
            Dict with date anomalies and validation results
        """
        logger.info("Checking date validation...")

        results = {
            'total_checked': 0,
            'null_dates': [],
            'invalid_formats': [],
            'out_of_range_dates': [],
            'future_dates': [],
            'pre_1948_dates': [],
            'date_statistics': defaultdict(int)
        }

        current_date = datetime.now().date()
        min_date = date(1948, 5, 14)  # Israel independence date
        max_date = date(2026, 12, 31)  # Reasonable future limit

        for record in records:
            results['total_checked'] += 1

            decision_date = record.get('decision_date')

            # Check for NULL dates
            if decision_date is None:
                results['null_dates'].append({
                    'decision_key': record.get('decision_key'),
                    'id': record.get('id')
                })
                continue

            # Try to parse date
            try:
                if isinstance(decision_date, str):
                    parsed_date = datetime.strptime(decision_date, '%Y-%m-%d').date()
                elif isinstance(decision_date, date):
                    parsed_date = decision_date
                elif isinstance(decision_date, datetime):
                    parsed_date = decision_date.date()
                else:
                    raise ValueError(f"Unknown date type: {type(decision_date)}")

                # Check date ranges
                if parsed_date < min_date:
                    results['pre_1948_dates'].append({
                        'decision_key': record.get('decision_key'),
                        'id': record.get('id'),
                        'date': str(parsed_date)
                    })
                elif parsed_date > max_date:
                    results['out_of_range_dates'].append({
                        'decision_key': record.get('decision_key'),
                        'id': record.get('id'),
                        'date': str(parsed_date)
                    })
                elif parsed_date > current_date:
                    results['future_dates'].append({
                        'decision_key': record.get('decision_key'),
                        'id': record.get('id'),
                        'date': str(parsed_date)
                    })

                # Collect statistics
                year = parsed_date.year
                results['date_statistics'][f'year_{year}'] += 1

            except (ValueError, TypeError) as e:
                results['invalid_formats'].append({
                    'decision_key': record.get('decision_key'),
                    'id': record.get('id'),
                    'date_value': str(decision_date),
                    'error': str(e)
                })

        return results

    def check_required_fields(self, records: List[Dict]) -> Dict:
        """
        Check for NULL values in required fields.

        Returns:
            Dict with NULL field violations
        """
        logger.info("Checking required fields...")

        required_fields = [
            'decision_key', 'decision_date', 'government_number',
            'decision_number', 'decision_title', 'decision_content'
        ]

        results = {
            'total_checked': 0,
            'null_violations': defaultdict(list),
            'empty_violations': defaultdict(list)
        }

        for record in records:
            results['total_checked'] += 1

            for field in required_fields:
                value = record.get(field)

                if value is None:
                    results['null_violations'][field].append({
                        'decision_key': record.get('decision_key'),
                        'id': record.get('id')
                    })
                elif isinstance(value, str) and value.strip() == '':
                    results['empty_violations'][field].append({
                        'decision_key': record.get('decision_key'),
                        'id': record.get('id')
                    })

        return results

    def check_unique_constraints(self, records: List[Dict]) -> Dict:
        """
        Check for unique constraint violations.

        Returns:
            Dict with constraint violation details
        """
        logger.info("Checking unique constraints...")

        results = {
            'total_checked': 0,
            'decision_key_duplicates': [],
            'id_duplicates': [],
            'duplicate_groups': defaultdict(list)
        }

        decision_key_counts = Counter()
        id_counts = Counter()

        for record in records:
            results['total_checked'] += 1

            decision_key = record.get('decision_key')
            record_id = record.get('id')

            if decision_key:
                decision_key_counts[decision_key] += 1
                results['duplicate_groups'][decision_key].append({
                    'id': record_id,
                    'date': record.get('decision_date'),
                    'title': (record.get('decision_title') or '')[:100]
                })

            if record_id:
                id_counts[record_id] += 1

        # Find actual duplicates
        for key, count in decision_key_counts.items():
            if count > 1:
                results['decision_key_duplicates'].append({
                    'decision_key': key,
                    'count': count,
                    'records': results['duplicate_groups'][key]
                })

        for record_id, count in id_counts.items():
            if count > 1:
                results['id_duplicates'].append({
                    'id': record_id,
                    'count': count
                })

        return results

    def assess_severity(self, all_results: Dict) -> Dict:
        """
        Assess overall severity of structural integrity issues.

        Returns:
            Dict with severity assessment and recommendations
        """
        severity_assessment = {
            'overall_severity': 'low',
            'critical_issues': [],
            'high_priority_issues': [],
            'medium_priority_issues': [],
            'recommendations': []
        }

        # Critical issues (data corruption level)
        if all_results['unique_constraints']['decision_key_duplicates']:
            severity_assessment['overall_severity'] = 'critical'
            severity_assessment['critical_issues'].append(
                f"Found {len(all_results['unique_constraints']['decision_key_duplicates'])} duplicate decision_keys"
            )

        if all_results['required_fields']['null_violations']['decision_key']:
            severity_assessment['overall_severity'] = 'critical'
            severity_assessment['critical_issues'].append(
                f"Found {len(all_results['required_fields']['null_violations']['decision_key'])} records with NULL decision_key"
            )

        # High priority issues (data integrity problems)
        if all_results['key_format']['malformed_keys']:
            if severity_assessment['overall_severity'] not in ['critical']:
                severity_assessment['overall_severity'] = 'high'
            severity_assessment['high_priority_issues'].append(
                f"Found {len(all_results['key_format']['malformed_keys'])} malformed decision_keys"
            )

        if all_results['field_consistency']['government_number_mismatches']:
            if severity_assessment['overall_severity'] not in ['critical']:
                severity_assessment['overall_severity'] = 'high'
            severity_assessment['high_priority_issues'].append(
                f"Found {len(all_results['field_consistency']['government_number_mismatches'])} government_number inconsistencies"
            )

        if all_results['date_validation']['pre_1948_dates'] or all_results['date_validation']['out_of_range_dates']:
            if severity_assessment['overall_severity'] not in ['critical']:
                severity_assessment['overall_severity'] = 'high'
            severity_assessment['high_priority_issues'].append(
                f"Found dates outside valid range (1948-2026)"
            )

        # Medium priority issues
        if all_results['date_validation']['future_dates']:
            severity_assessment['medium_priority_issues'].append(
                f"Found {len(all_results['date_validation']['future_dates'])} future dates"
            )

        # Generate recommendations
        if severity_assessment['critical_issues']:
            severity_assessment['recommendations'].append("IMMEDIATE ACTION REQUIRED: Fix duplicate keys and NULL values")

        if severity_assessment['high_priority_issues']:
            severity_assessment['recommendations'].append("High priority: Fix malformed keys and field inconsistencies")

        if not severity_assessment['critical_issues'] and not severity_assessment['high_priority_issues']:
            severity_assessment['recommendations'].append("Database structural integrity is good")

        return severity_assessment

    def run_full_check(self, limit: Optional[int] = None) -> Dict:
        """
        Run complete structural integrity check.

        Args:
            limit: Optional limit on number of records to check

        Returns:
            Complete results dictionary
        """
        logger.info("Starting Phase 4: Structural Integrity Check")

        # Fetch records
        if limit:
            query = self.client.table('israeli_government_decisions').select('*').limit(limit)
            response = query.execute()
            records = response.data
        else:
            # Fetch all records in batches to avoid pagination limits
            records = []
            page_size = 1000
            offset = 0

            while True:
                query = self.client.table('israeli_government_decisions').select('*').range(offset, offset + page_size - 1)
                response = query.execute()
                batch = response.data

                if not batch:
                    break

                records.extend(batch)
                logger.info(f"Fetched {len(records)} records so far...")

                if len(batch) < page_size:
                    break

                offset += page_size

        logger.info(f"Checking {len(records)} records for structural integrity...")

        # Run all checks
        results = {
            'metadata': {
                'check_name': 'Phase 4: Structural Integrity Check',
                'timestamp': datetime.now().isoformat(),
                'total_records_checked': len(records),
                'database_table': 'israeli_government_decisions'
            },
            'key_format': self.check_decision_key_format(records),
            'field_consistency': self.check_field_consistency(records),
            'date_validation': self.check_date_validation(records),
            'required_fields': self.check_required_fields(records),
            'unique_constraints': self.check_unique_constraints(records)
        }

        # Add severity assessment
        results['severity_assessment'] = self.assess_severity(results)

        return results


def main():
    """Main execution function."""
    checker = StructuralIntegrityChecker()

    # Run full check (use limit for testing)
    # results = checker.run_full_check(limit=1000)  # Test with 1000 records
    results = checker.run_full_check()  # Full database check

    # Save results
    os.makedirs('data/qa_reports', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'data/qa_reports/phase4_structure_{timestamp}.json'

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Results saved to: {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("PHASE 4: STRUCTURAL INTEGRITY CHECK SUMMARY")
    print("="*60)

    metadata = results['metadata']
    print(f"Records checked: {metadata['total_records_checked']:,}")
    print(f"Timestamp: {metadata['timestamp']}")

    # Key format issues
    key_format = results['key_format']
    print(f"\nKEY FORMAT ISSUES:")
    print(f"  Malformed keys: {len(key_format['malformed_keys'])}")
    print(f"  NULL keys: {len(key_format['null_keys'])}")
    print(f"  Empty keys: {len(key_format['empty_keys'])}")
    print(f"  Duplicate keys: {len(key_format['duplicate_keys'])}")

    # Field consistency
    field_consistency = results['field_consistency']
    print(f"\nFIELD CONSISTENCY:")
    print(f"  Government number mismatches: {len(field_consistency['government_number_mismatches'])}")
    print(f"  Decision number mismatches: {len(field_consistency['decision_number_mismatches'])}")
    print(f"  Missing government numbers: {len(field_consistency['missing_government_number'])}")
    print(f"  Missing decision numbers: {len(field_consistency['missing_decision_number'])}")

    # Date validation
    date_validation = results['date_validation']
    print(f"\nDATE VALIDATION:")
    print(f"  NULL dates: {len(date_validation['null_dates'])}")
    print(f"  Invalid formats: {len(date_validation['invalid_formats'])}")
    print(f"  Pre-1948 dates: {len(date_validation['pre_1948_dates'])}")
    print(f"  Out of range dates: {len(date_validation['out_of_range_dates'])}")
    print(f"  Future dates: {len(date_validation['future_dates'])}")

    # Required fields
    required_fields = results['required_fields']
    print(f"\nREQUIRED FIELDS:")
    for field, violations in required_fields['null_violations'].items():
        if violations:
            print(f"  {field} NULL violations: {len(violations)}")

    # Severity assessment
    severity = results['severity_assessment']
    print(f"\nSEVERITY ASSESSMENT: {severity['overall_severity'].upper()}")

    if severity['critical_issues']:
        print("CRITICAL ISSUES:")
        for issue in severity['critical_issues']:
            print(f"  ❌ {issue}")

    if severity['high_priority_issues']:
        print("HIGH PRIORITY ISSUES:")
        for issue in severity['high_priority_issues']:
            print(f"  ⚠️  {issue}")

    if severity['recommendations']:
        print("RECOMMENDATIONS:")
        for rec in severity['recommendations']:
            print(f"  💡 {rec}")

    print(f"\nDetailed results saved to: {output_file}")
    return results


if __name__ == '__main__':
    results = main()