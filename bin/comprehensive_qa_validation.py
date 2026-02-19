#!/usr/bin/env python3
"""
Comprehensive QA Validation Script for GOV2DB
==============================================

This script performs comprehensive quality validation on all ~25,000 Israeli government
decisions to validate that AI improvements are working correctly.

Usage:
    python bin/comprehensive_qa_validation.py [--sample N] [--verbose] [--output PATH]

Features:
    - Government body whitelist compliance (45 authorized bodies)
    - Policy tag whitelist compliance (46 authorized tags)
    - No summary prefixes starting with "החלטת ממשלה"
    - Operativity distribution validation (target: 60-65% operative)
    - All_tags consistency (rebuilt from individual fields)
    - Date format validation (YYYY-MM-DD)
    - Decision key format (gov_num_decision_num)
    - Content length validation (flag if <100 chars)
    - No duplicate decision keys
    - Detailed statistics and reporting
"""

import sys
import os
import json
import argparse
import logging
import re
from collections import defaultdict, Counter
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional, Set, Any
import random

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.processors.ai_post_processor import (
    AUTHORIZED_POLICY_AREAS,
    AUTHORIZED_GOVERNMENT_BODIES,
    _SUMMARY_PREFIX_PATTERN
)

logger = logging.getLogger(__name__)

# Quality thresholds and targets
QUALITY_THRESHOLDS = {
    'operativity_target_min': 60.0,  # 60-65% operative target
    'operativity_target_max': 65.0,
    'min_content_length': 100,
    'max_missing_titles': 50,
    'max_whitelist_violations': 5.0,  # % threshold
    'overall_quality_target': 85.0,  # % for B+ grade
}

class QAValidationResult:
    """Container for comprehensive QA validation results."""

    def __init__(self):
        self.timestamp = datetime.now().isoformat()
        self.total_records = 0
        self.sample_size = 0

        # Issue tracking
        self.issues = defaultdict(list)
        self.issue_counts = defaultdict(int)

        # Statistics
        self.stats = {
            'government_body_compliance': 0.0,
            'policy_tag_compliance': 0.0,
            'summary_prefix_compliance': 0.0,
            'operativity_distribution': {'operative': 0, 'declarative': 0},
            'all_tags_consistency': 0.0,
            'date_format_compliance': 0.0,
            'decision_key_compliance': 0.0,
            'content_length_compliance': 0.0,
            'duplicate_keys': 0,
            'overall_quality_score': 0.0
        }

        # Distributions for analysis
        self.distributions = {
            'government_bodies': Counter(),
            'policy_tags': Counter(),
            'operativity': Counter(),
            'content_lengths': [],
            'decision_years': Counter()
        }

        # Records needing manual review
        self.manual_review_needed = []

    def add_issue(self, issue_type: str, decision_key: str, severity: str,
                  description: str, current_value: str = "", expected_value: str = ""):
        """Add a validation issue."""
        self.issues[issue_type].append({
            'decision_key': decision_key,
            'severity': severity,
            'description': description,
            'current_value': current_value[:200] if current_value else "",
            'expected_value': expected_value[:200] if expected_value else ""
        })
        self.issue_counts[f"{issue_type}_{severity}"] += 1

        # Flag for manual review if high severity
        if severity == 'high' and decision_key not in [r['decision_key'] for r in self.manual_review_needed]:
            self.manual_review_needed.append({
                'decision_key': decision_key,
                'issues': [issue_type],
                'severity': severity
            })

    def calculate_final_scores(self):
        """Calculate final quality scores and grades."""
        if self.total_records == 0:
            return

        # Calculate compliance percentages
        total_issues_by_type = {}
        for issue_type in ['government_body', 'policy_tag', 'summary_prefix',
                          'all_tags_consistency', 'date_format', 'decision_key',
                          'content_length']:
            total_issues_by_type[issue_type] = len(self.issues.get(issue_type, []))
            compliance = (1 - total_issues_by_type[issue_type] / self.total_records) * 100
            self.stats[f'{issue_type}_compliance'] = round(compliance, 2)

        # Operativity distribution analysis
        operative_pct = (self.distributions['operativity']['אופרטיבית'] / self.total_records) * 100
        operativity_target_met = (QUALITY_THRESHOLDS['operativity_target_min'] <=
                                operative_pct <= QUALITY_THRESHOLDS['operativity_target_max'])

        # Calculate overall quality score (weighted average)
        weights = {
            'government_body_compliance': 0.20,
            'policy_tag_compliance': 0.20,
            'summary_prefix_compliance': 0.15,
            'all_tags_consistency_compliance': 0.15,
            'date_format_compliance': 0.10,
            'decision_key_compliance': 0.10,
            'content_length_compliance': 0.10
        }

        weighted_score = sum(
            self.stats[metric] * weight
            for metric, weight in weights.items()
        )

        self.stats['overall_quality_score'] = round(weighted_score, 2)

        # Determine grade
        score = self.stats['overall_quality_score']
        if score >= 95:
            grade = "A+"
        elif score >= 90:
            grade = "A"
        elif score >= 85:
            grade = "A-"
        elif score >= 80:
            grade = "B+"
        elif score >= 75:
            grade = "B"
        elif score >= 70:
            grade = "B-"
        elif score >= 65:
            grade = "C+"
        elif score >= 60:
            grade = "C"
        else:
            grade = "D"

        self.stats['quality_grade'] = grade
        self.stats['operativity_target_met'] = operativity_target_met
        self.stats['operativity_percentage'] = round(operative_pct, 2)


class ComprehensiveQAValidator:
    """Main QA validation engine."""

    def __init__(self, sample_size: Optional[int] = None, verbose: bool = False):
        self.sample_size = sample_size
        self.verbose = verbose
        self.supabase = get_supabase_client()
        self.result = QAValidationResult()

    def fetch_records(self) -> List[Dict[str, Any]]:
        """Fetch records for validation (all or sample)."""
        logger.info("Fetching records from database...")

        try:
            if self.sample_size:
                # For sampling, get total count first
                count_response = self.supabase.table('israeli_government_decisions').select(
                    'decision_key', count='exact'
                ).execute()
                total_count = count_response.count
                logger.info(f"Total records in database: {total_count:,}")

                # Simple random sampling with limit
                query = self.supabase.table('israeli_government_decisions').select(
                    'decision_key, decision_number, government_number, decision_date, decision_title, '
                    'decision_content, summary, operativity, tags_policy_area, '
                    'tags_government_body, tags_location, all_tags'
                ).limit(self.sample_size * 3)  # Get more to ensure good sampling

                response = query.execute()
                all_records = response.data

                # Random sample
                if len(all_records) > self.sample_size:
                    records = random.sample(all_records, self.sample_size)
                else:
                    records = all_records

                logger.info(f"Using random sample of {len(records)} records from {total_count:,} total")
            else:
                # All records with pagination
                all_records = []
                page_size = 1000
                offset = 0

                while True:
                    query = self.supabase.table('israeli_government_decisions').select(
                        'decision_key, decision_number, government_number, decision_date, decision_title, '
                        'decision_content, summary, operativity, tags_policy_area, '
                        'tags_government_body, tags_location, all_tags'
                    ).range(offset, offset + page_size - 1).order('decision_key')

                    response = query.execute()
                    batch = response.data

                    if not batch:
                        break

                    all_records.extend(batch)
                    offset += page_size

                    if self.verbose:
                        logger.info(f"Fetched {len(all_records):,} records so far...")

                    # Safety break if we exceed expected count significantly
                    if len(all_records) > 30000:
                        logger.warning("Fetched more than 30,000 records, breaking to avoid infinite loop")
                        break

                records = all_records
                logger.info(f"Fetched all {len(records):,} records via pagination")

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise

        self.result.total_records = len(records)
        self.result.sample_size = len(records)
        return records

    def validate_government_body_whitelist(self, record: Dict[str, Any]):
        """Check government body whitelist compliance."""
        decision_key = record['decision_key']
        gov_bodies_str = record.get('tags_government_body', '') or ''

        if not gov_bodies_str.strip():
            return  # Empty is acceptable

        bodies = [b.strip() for b in gov_bodies_str.split(';') if b.strip()]
        unauthorized_bodies = []

        for body in bodies:
            if body not in AUTHORIZED_GOVERNMENT_BODIES:
                unauthorized_bodies.append(body)

        if unauthorized_bodies:
            self.result.add_issue(
                'government_body', decision_key, 'high',
                f"Unauthorized government bodies: {', '.join(unauthorized_bodies)}",
                ', '.join(unauthorized_bodies)
            )

        # Track distribution
        for body in bodies:
            self.result.distributions['government_bodies'][body] += 1

    def validate_policy_tag_whitelist(self, record: Dict[str, Any]):
        """Check policy tag whitelist compliance."""
        decision_key = record['decision_key']
        policy_tags_str = record.get('tags_policy_area', '') or ''

        if not policy_tags_str.strip():
            self.result.add_issue(
                'policy_tag', decision_key, 'medium',
                "Missing policy tags",
                "", "At least one policy tag required"
            )
            return

        tags = [t.strip() for t in policy_tags_str.split(';') if t.strip()]
        unauthorized_tags = []

        for tag in tags:
            if tag not in AUTHORIZED_POLICY_AREAS:
                unauthorized_tags.append(tag)

        if unauthorized_tags:
            self.result.add_issue(
                'policy_tag', decision_key, 'high',
                f"Unauthorized policy tags: {', '.join(unauthorized_tags)}",
                ', '.join(unauthorized_tags)
            )

        # Track distribution
        for tag in tags:
            self.result.distributions['policy_tags'][tag] += 1

    def validate_summary_prefix(self, record: Dict[str, Any]):
        """Check for forbidden summary prefixes."""
        decision_key = record['decision_key']
        summary = record.get('summary', '') or ''

        if not summary:
            self.result.add_issue(
                'summary_prefix', decision_key, 'medium',
                "Missing summary", "", "Summary required"
            )
            return

        if _SUMMARY_PREFIX_PATTERN.match(summary):
            self.result.add_issue(
                'summary_prefix', decision_key, 'medium',
                "Summary starts with forbidden prefix 'החלטת ממשלה מספר'",
                summary[:100], "Clean summary without prefix"
            )

    def validate_operativity_distribution(self, record: Dict[str, Any]):
        """Track operativity distribution."""
        operativity = record.get('operativity', '')
        if operativity:
            self.result.distributions['operativity'][operativity] += 1
        else:
            self.result.add_issue(
                'operativity', record['decision_key'], 'medium',
                "Missing operativity classification", "", "אופרטיבית or דקלרטיבית"
            )

    def validate_all_tags_consistency(self, record: Dict[str, Any]):
        """Check if all_tags is consistent with individual tag fields."""
        decision_key = record['decision_key']
        all_tags_str = record.get('all_tags', '') or ''

        # Rebuild expected all_tags from individual fields
        expected_tags = []

        policy_tags = record.get('tags_policy_area', '') or ''
        if policy_tags:
            expected_tags.extend([t.strip() for t in policy_tags.split(';') if t.strip()])

        gov_bodies = record.get('tags_government_body', '') or ''
        if gov_bodies:
            expected_tags.extend([b.strip() for b in gov_bodies.split(';') if b.strip()])

        locations = record.get('tags_location', '') or ''
        if locations:
            expected_tags.extend([l.strip() for l in locations.split(',') if l.strip()])

        # Remove duplicates while preserving order
        expected_tags = list(dict.fromkeys(expected_tags))
        expected_all_tags = '; '.join(expected_tags)

        # Compare with actual all_tags
        actual_tags = [t.strip() for t in all_tags_str.split(';') if t.strip()]
        actual_tags_set = set(actual_tags)
        expected_tags_set = set(expected_tags)

        if actual_tags_set != expected_tags_set:
            missing = expected_tags_set - actual_tags_set
            extra = actual_tags_set - expected_tags_set

            description = []
            if missing:
                description.append(f"Missing from all_tags: {', '.join(missing)}")
            if extra:
                description.append(f"Extra in all_tags: {', '.join(extra)}")

            self.result.add_issue(
                'all_tags_consistency', decision_key, 'medium',
                '; '.join(description),
                all_tags_str, expected_all_tags
            )

    def validate_date_format(self, record: Dict[str, Any]):
        """Validate date format (YYYY-MM-DD)."""
        decision_key = record['decision_key']
        decision_date = record.get('decision_date', '')

        if not decision_date:
            self.result.add_issue(
                'date_format', decision_key, 'high',
                "Missing decision date", "", "YYYY-MM-DD format"
            )
            return

        # Check format
        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        if not date_pattern.match(decision_date):
            self.result.add_issue(
                'date_format', decision_key, 'high',
                "Invalid date format",
                decision_date, "YYYY-MM-DD format"
            )
            return

        # Check if date is reasonable (1948-2027)
        try:
            year = int(decision_date[:4])
            if year < 1948 or year > 2027:
                self.result.add_issue(
                    'date_format', decision_key, 'medium',
                    f"Date year out of reasonable range: {year}",
                    decision_date, "Year between 1948-2027"
                )
            else:
                self.result.distributions['decision_years'][year] += 1
        except ValueError:
            self.result.add_issue(
                'date_format', decision_key, 'high',
                "Cannot parse date year",
                decision_date, "YYYY-MM-DD format"
            )

    def validate_decision_key_format(self, record: Dict[str, Any]):
        """Validate decision key format (government_number_decision_number)."""
        decision_key = record['decision_key']
        gov_num = record.get('government_number')
        decision_num = record.get('decision_number', '')

        if not decision_key:
            self.result.add_issue(
                'decision_key', decision_key or 'UNKNOWN', 'high',
                "Missing decision_key", "", "government_number_decision_number format"
            )
            return

        # Check format consistency
        expected_key = f"{gov_num}_{decision_num}"
        if decision_key != expected_key:
            self.result.add_issue(
                'decision_key', decision_key, 'medium',
                "Decision key doesn't match government_number_decision_number pattern",
                decision_key, expected_key
            )

    def validate_content_length(self, record: Dict[str, Any]):
        """Check content length and flag suspiciously short content."""
        decision_key = record['decision_key']
        content = record.get('decision_content', '') or ''

        content_length = len(content)
        self.result.distributions['content_lengths'].append(content_length)

        if content_length < QUALITY_THRESHOLDS['min_content_length']:
            severity = 'high' if content_length < 50 else 'medium'
            self.result.add_issue(
                'content_length', decision_key, severity,
                f"Content too short: {content_length} chars",
                str(content_length), f">= {QUALITY_THRESHOLDS['min_content_length']} chars"
            )

    def check_duplicate_keys(self, records: List[Dict[str, Any]]):
        """Check for duplicate decision keys."""
        keys = [record['decision_key'] for record in records]
        key_counts = Counter(keys)

        duplicates = {key: count for key, count in key_counts.items() if count > 1}

        for key, count in duplicates.items():
            self.result.add_issue(
                'duplicate_keys', key, 'high',
                f"Duplicate decision key appears {count} times",
                str(count), "1 (unique)"
            )

        self.result.stats['duplicate_keys'] = len(duplicates)

    def validate_single_record(self, record: Dict[str, Any]):
        """Run all validations on a single record."""
        self.validate_government_body_whitelist(record)
        self.validate_policy_tag_whitelist(record)
        self.validate_summary_prefix(record)
        self.validate_operativity_distribution(record)
        self.validate_all_tags_consistency(record)
        self.validate_date_format(record)
        self.validate_decision_key_format(record)
        self.validate_content_length(record)

    def run_validation(self) -> QAValidationResult:
        """Run comprehensive validation on all records."""
        logger.info("Starting comprehensive QA validation...")

        # Fetch records
        records = self.fetch_records()

        # Check for duplicates first
        self.check_duplicate_keys(records)

        # Validate each record
        for i, record in enumerate(records):
            if self.verbose and (i + 1) % 1000 == 0:
                logger.info(f"Processed {i + 1}/{len(records)} records...")

            self.validate_single_record(record)

        # Calculate final scores
        self.result.calculate_final_scores()

        logger.info("Comprehensive QA validation completed")
        return self.result


def generate_report(result: QAValidationResult) -> Dict[str, Any]:
    """Generate comprehensive validation report."""

    # Executive summary
    executive_summary = {
        "overall_quality_grade": result.stats.get('quality_grade', 'Unknown'),
        "overall_quality_score": result.stats.get('overall_quality_score', 0),
        "total_records_analyzed": result.total_records,
        "total_issues_found": sum(result.issue_counts.values()),
        "records_needing_manual_review": len(result.manual_review_needed),
        "operativity_distribution": {
            "operative_percentage": result.stats.get('operativity_percentage', 0),
            "target_met": result.stats.get('operativity_target_met', False),
            "target_range": f"{QUALITY_THRESHOLDS['operativity_target_min']}-{QUALITY_THRESHOLDS['operativity_target_max']}%"
        },
        "key_achievements": [],
        "areas_for_improvement": []
    }

    # Determine achievements and improvements needed
    if result.stats.get('government_body_compliance', 0) >= 95:
        executive_summary["key_achievements"].append("Excellent government body whitelist compliance (95%+)")
    elif result.stats.get('government_body_compliance', 0) < 80:
        executive_summary["areas_for_improvement"].append("Government body whitelist compliance needs improvement")

    if result.stats.get('policy_tag_compliance', 0) >= 95:
        executive_summary["key_achievements"].append("Excellent policy tag whitelist compliance (95%+)")
    elif result.stats.get('policy_tag_compliance', 0) < 80:
        executive_summary["areas_for_improvement"].append("Policy tag whitelist compliance needs improvement")

    if result.stats.get('duplicate_keys', 0) == 0:
        executive_summary["key_achievements"].append("Zero duplicate decision keys (perfect uniqueness)")
    elif result.stats.get('duplicate_keys', 0) > 0:
        executive_summary["areas_for_improvement"].append(f"{result.stats['duplicate_keys']} duplicate decision keys found")

    # Detailed findings by category
    detailed_findings = {}

    for category in ['government_body', 'policy_tag', 'summary_prefix', 'operativity',
                    'all_tags_consistency', 'date_format', 'decision_key', 'content_length', 'duplicate_keys']:
        issues = result.issues.get(category, [])
        compliance = result.stats.get(f'{category}_compliance', 100.0)

        detailed_findings[category] = {
            "compliance_percentage": compliance,
            "total_issues": len(issues),
            "high_severity": len([i for i in issues if i['severity'] == 'high']),
            "medium_severity": len([i for i in issues if i['severity'] == 'medium']),
            "low_severity": len([i for i in issues if i['severity'] == 'low']),
            "sample_issues": issues[:5],  # Top 5 for review
            "grade": "A" if compliance >= 95 else "B+" if compliance >= 85 else "B" if compliance >= 75 else "C" if compliance >= 65 else "D"
        }

    # Statistics and distributions
    statistics = {
        "compliance_metrics": {
            "government_body_compliance": result.stats.get('government_body_compliance', 0),
            "policy_tag_compliance": result.stats.get('policy_tag_compliance', 0),
            "summary_prefix_compliance": result.stats.get('summary_prefix_compliance', 0),
            "all_tags_consistency_compliance": result.stats.get('all_tags_consistency_compliance', 0),
            "date_format_compliance": result.stats.get('date_format_compliance', 0),
            "decision_key_compliance": result.stats.get('decision_key_compliance', 0),
            "content_length_compliance": result.stats.get('content_length_compliance', 0)
        },
        "operativity_distribution": dict(result.distributions['operativity']),
        "most_common_government_bodies": result.distributions['government_bodies'].most_common(10),
        "most_common_policy_tags": result.distributions['policy_tags'].most_common(10),
        "decision_years_coverage": dict(result.distributions['decision_years']),
        "content_length_stats": {
            "min": min(result.distributions['content_lengths']) if result.distributions['content_lengths'] else 0,
            "max": max(result.distributions['content_lengths']) if result.distributions['content_lengths'] else 0,
            "avg": round(sum(result.distributions['content_lengths']) / len(result.distributions['content_lengths']), 2) if result.distributions['content_lengths'] else 0,
            "under_100_chars": len([l for l in result.distributions['content_lengths'] if l < 100])
        }
    }

    # Recommendations
    recommendations = {
        "immediate_actions": [],
        "iterative_improvements": [],
        "monitoring_suggestions": []
    }

    # Generate specific recommendations based on findings
    if result.stats.get('government_body_compliance', 100) < 95:
        recommendations["immediate_actions"].append("Review and correct unauthorized government body tags")

    if result.stats.get('policy_tag_compliance', 100) < 95:
        recommendations["immediate_actions"].append("Review and correct unauthorized policy tags")

    if result.stats.get('duplicate_keys', 0) > 0:
        recommendations["immediate_actions"].append("Investigate and resolve duplicate decision keys")

    if not result.stats.get('operativity_target_met', True):
        recommendations["iterative_improvements"].append("Adjust operativity classification to meet 60-65% operative target")

    if result.stats.get('content_length_compliance', 100) < 90:
        recommendations["iterative_improvements"].append("Investigate records with unusually short content")

    recommendations["monitoring_suggestions"].extend([
        "Run daily incremental QA checks",
        "Monitor compliance trends over time",
        "Set up alerts for whitelist violations",
        "Review manual flagged records quarterly"
    ])

    return {
        "validation_metadata": {
            "timestamp": result.timestamp,
            "total_records": result.total_records,
            "sample_size": result.sample_size,
            "is_full_dataset": result.sample_size == result.total_records
        },
        "executive_summary": executive_summary,
        "detailed_findings": detailed_findings,
        "statistics": statistics,
        "recommendations": recommendations,
        "records_for_manual_review": result.manual_review_needed[:100],  # Cap at 100
        "quality_thresholds_used": QUALITY_THRESHOLDS
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Comprehensive QA validation for GOV2DB')
    parser.add_argument('--sample', type=int, help='Sample size (default: all records)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('--output', type=str, help='Output file path',
                       default=f'data/qa_reports/comprehensive_qa_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducible sampling')

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set random seed for reproducible sampling
    random.seed(args.seed)

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Run validation
        validator = ComprehensiveQAValidator(sample_size=args.sample, verbose=args.verbose)
        result = validator.run_validation()

        # Generate report
        report = generate_report(result)

        # Save report
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Print summary
        print("\n" + "=" * 80)
        print("🔍 COMPREHENSIVE QA VALIDATION RESULTS")
        print("=" * 80)
        print(f"📊 Records Analyzed: {result.total_records:,}")
        print(f"🎯 Overall Quality Grade: {result.stats.get('quality_grade', 'Unknown')}")
        print(f"📈 Overall Quality Score: {result.stats.get('overall_quality_score', 0):.1f}%")
        print(f"⚠️  Total Issues Found: {sum(result.issue_counts.values()):,}")
        print(f"🔍 Manual Review Needed: {len(result.manual_review_needed)}")
        print()

        # Key metrics
        print("🏆 KEY COMPLIANCE METRICS:")
        metrics = [
            ("Government Bodies", result.stats.get('government_body_compliance', 0)),
            ("Policy Tags", result.stats.get('policy_tag_compliance', 0)),
            ("Summary Prefixes", result.stats.get('summary_prefix_compliance', 0)),
            ("All_tags Consistency", result.stats.get('all_tags_consistency_compliance', 0)),
            ("Date Format", result.stats.get('date_format_compliance', 0)),
            ("Decision Keys", result.stats.get('decision_key_compliance', 0)),
            ("Content Length", result.stats.get('content_length_compliance', 0))
        ]

        for metric_name, score in metrics:
            icon = "✅" if score >= 95 else "🟡" if score >= 85 else "⚠️" if score >= 70 else "❌"
            print(f"  {icon} {metric_name}: {score:.1f}%")

        print()

        # Operativity analysis
        operative_pct = result.stats.get('operativity_percentage', 0)
        target_met = result.stats.get('operativity_target_met', False)
        target_icon = "✅" if target_met else "🔄"
        print(f"⚖️  OPERATIVITY DISTRIBUTION:")
        print(f"  {target_icon} Operative: {operative_pct:.1f}% (target: 60-65%)")

        if result.stats.get('duplicate_keys', 0) > 0:
            print(f"⚠️  DUPLICATES: {result.stats['duplicate_keys']} duplicate decision keys found")
        else:
            print("✅ DUPLICATES: Zero duplicate keys (perfect uniqueness)")

        print()
        print(f"📄 Full report saved to: {args.output}")
        print("=" * 80)

        # Exit with appropriate code
        if result.stats.get('overall_quality_score', 0) >= QUALITY_THRESHOLDS['overall_quality_target']:
            print("🎉 Quality validation PASSED - meets production standards!")
            sys.exit(0)
        else:
            print("⚠️  Quality validation needs improvement before production deployment")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()