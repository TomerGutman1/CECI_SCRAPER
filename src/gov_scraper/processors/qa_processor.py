"""
QA Processor - Refactored QA engine using the new architecture.

This module integrates the new QA architecture with the existing system,
providing backward compatibility while leveraging the improved design.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Union
from dataclasses import asdict

from .qa_core import (
    QACheckFactory, AbstractQACheck, CompositeQACheck, ProgressManager,
    QAReport, QAScanResult, CheckSeverity
)
from .qa_checks import (
    ContentQualityCheck, DuplicateDetectionCheck,
    URLIntegrityCheck, DomainConsistencyCheck,
    TagValidationCheck, TagConsistencyCheck,
    DateConsistencyCheck, TemporalConsistencyCheck,
    DepartmentValidationCheck, DepartmentConsistencyCheck
)
from ..db.connector import get_supabase_client

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class QAProcessor:
    """
    Main QA processor using the new architecture.

    Provides a unified interface for running QA checks with advanced features
    like progress tracking, resumability, and flexible check configuration.
    """

    def __init__(self,
                 checkpoint_dir: str = "data/qa_checkpoints",
                 batch_size: int = 1000,
                 enable_progress_tracking: bool = True,
                 max_workers: int = 1):
        """
        Initialize QA processor.

        Args:
            checkpoint_dir: Directory for saving progress checkpoints
            batch_size: Default batch size for processing
            enable_progress_tracking: Enable progress tracking and resumability
            max_workers: Number of parallel workers (future enhancement)
        """
        self.checkpoint_dir = checkpoint_dir
        self.batch_size = batch_size
        self.enable_progress_tracking = enable_progress_tracking
        self.max_workers = max_workers

        # Initialize progress manager
        self.progress_manager = ProgressManager(checkpoint_dir)

        # Register all available checks
        self._register_checks()

        # Track registered check instances for reuse
        self._check_instances: Dict[str, AbstractQACheck] = {}

    def _register_checks(self) -> None:
        """Register all available QA checks with the factory."""
        # Content quality checks
        QACheckFactory.register("content_quality", ContentQualityCheck)
        QACheckFactory.register("duplicate_detection", DuplicateDetectionCheck)

        # URL integrity checks
        QACheckFactory.register("url_integrity", URLIntegrityCheck)
        QACheckFactory.register("domain_consistency", DomainConsistencyCheck)

        # Tag validation checks
        QACheckFactory.register("tag_validation", TagValidationCheck)
        QACheckFactory.register("tag_consistency", TagConsistencyCheck)

        # Date consistency checks
        QACheckFactory.register("date_consistency", DateConsistencyCheck)
        QACheckFactory.register("temporal_consistency", TemporalConsistencyCheck)

        # Department validation checks
        QACheckFactory.register("department_validation", DepartmentValidationCheck)
        QACheckFactory.register("department_consistency", DepartmentConsistencyCheck)

    def get_available_checks(self) -> List[str]:
        """Get list of available check names."""
        return QACheckFactory.get_available_checks()

    def create_check(self, check_name: str, **kwargs) -> AbstractQACheck:
        """
        Create a QA check instance.

        Args:
            check_name: Name of the check to create
            **kwargs: Configuration parameters for the check

        Returns:
            Configured QA check instance
        """
        # Apply default configurations
        default_config = {
            "batch_size": self.batch_size,
            "enable_progress_tracking": self.enable_progress_tracking
        }
        default_config.update(kwargs)

        return QACheckFactory.create(check_name, **default_config)

    def create_comprehensive_check(self,
                                 check_categories: List[str] = None,
                                 **kwargs) -> CompositeQACheck:
        """
        Create a comprehensive check combining multiple categories.

        Args:
            check_categories: Categories to include ('content', 'urls', 'tags', 'dates', 'departments', 'consistency')
            **kwargs: Configuration parameters

        Returns:
            Composite check instance
        """
        if check_categories is None:
            check_categories = ['content', 'urls', 'tags', 'dates', 'departments']

        check_mapping = {
            'content': ['content_quality'],
            'urls': ['url_integrity'],
            'tags': ['tag_validation'],
            'dates': ['date_consistency'],
            'departments': ['department_validation'],
            'consistency': ['tag_consistency', 'temporal_consistency', 'department_consistency', 'domain_consistency'],
            'duplicates': ['duplicate_detection']
        }

        sub_check_names = []
        for category in check_categories:
            if category in check_mapping:
                sub_check_names.extend(check_mapping[category])

        return QACheckFactory.create_composite_check(
            "comprehensive_qa",
            sub_check_names,
            description="Comprehensive QA check across multiple categories",
            **kwargs
        )

    def run_check(self,
                  check_name: str,
                  records: List[Dict],
                  **check_config) -> QAScanResult:
        """
        Run a single QA check.

        Args:
            check_name: Name of the check to run
            records: Records to analyze
            **check_config: Configuration for the specific check

        Returns:
            Scan result with findings
        """
        logger.info(f"Running QA check: {check_name}")

        # Create or reuse check instance
        check_key = f"{check_name}_{hash(frozenset(check_config.items()))}"
        if check_key not in self._check_instances:
            self._check_instances[check_key] = self.create_check(check_name, **check_config)

        check = self._check_instances[check_key]
        result = check.run(records)

        logger.info(f"Check {check_name} completed: {result.issues_found} issues found in {result.execution_time:.2f}s")

        return result

    def run_scan(self,
                 records: List[Dict],
                 checks: Union[List[str], str] = None,
                 check_configs: Dict[str, Dict] = None,
                 save_progress: bool = True) -> QAReport:
        """
        Run QA scan with multiple checks.

        Args:
            records: Records to analyze
            checks: List of check names or 'comprehensive' for all checks
            check_configs: Configuration for each check
            save_progress: Save progress checkpoints

        Returns:
            QA report with all results
        """
        start_time = datetime.now()
        logger.info(f"Starting QA scan on {len(records)} records")

        check_configs = check_configs or {}

        # Determine checks to run
        if checks == "comprehensive":
            check_names = self.get_available_checks()
        elif checks == "essential":
            check_names = ["content_quality", "tag_validation", "date_consistency", "department_validation"]
        elif checks == "consistency":
            check_names = ["tag_consistency", "temporal_consistency", "department_consistency", "domain_consistency"]
        elif isinstance(checks, list):
            check_names = checks
        elif checks is None:
            check_names = ["content_quality", "tag_validation", "date_consistency"]
        else:
            check_names = [checks]

        # Initialize report
        report = QAReport(
            timestamp=start_time.isoformat(),
            total_records=len(records)
        )

        # Run each check
        for i, check_name in enumerate(check_names):
            logger.info(f"Running check {i+1}/{len(check_names)}: {check_name}")

            try:
                config = check_configs.get(check_name, {})
                result = self.run_check(check_name, records, **config)
                report.scan_results.append(result)

                # Save progress checkpoint if enabled
                if save_progress and result.progress:
                    checkpoint_id = self.progress_manager.save_checkpoint(result.progress)
                    logger.debug(f"Saved checkpoint: {checkpoint_id}")

            except Exception as e:
                logger.error(f"Check {check_name} failed: {e}")
                # Create error result
                error_result = QAScanResult(
                    check_name=check_name,
                    total_scanned=len(records),
                    issues_found=0,
                    error=str(e),
                    execution_time=0.0
                )
                report.scan_results.append(error_result)

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        logger.info(f"QA scan completed in {total_time:.2f}s: {report.total_issues} total issues found")

        return report

    def run_focused_scan(self,
                        records: List[Dict],
                        focus_area: str,
                        **kwargs) -> QAReport:
        """
        Run focused scan on specific area.

        Args:
            records: Records to analyze
            focus_area: Area to focus on ('content', 'metadata', 'consistency', 'integrity')
            **kwargs: Additional configuration

        Returns:
            QA report focused on specific area
        """
        focus_mapping = {
            'content': ['content_quality', 'duplicate_detection'],
            'metadata': ['tag_validation', 'department_validation', 'date_consistency'],
            'consistency': ['tag_consistency', 'temporal_consistency', 'department_consistency'],
            'integrity': ['url_integrity', 'domain_consistency']
        }

        if focus_area not in focus_mapping:
            raise ValueError(f"Unknown focus area: {focus_area}. Available: {list(focus_mapping.keys())}")

        return self.run_scan(
            records=records,
            checks=focus_mapping[focus_area],
            **kwargs
        )

    def save_report(self,
                   report: QAReport,
                   output_path: str,
                   format: str = 'json') -> str:
        """
        Save QA report to file.

        Args:
            report: QA report to save
            output_path: Output file path
            format: Output format ('json' or 'summary')

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        elif format == 'summary':
            summary_text = self._generate_report_summary(report)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(summary_text)

        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Report saved to: {output_path}")
        return output_path

    def load_report(self, report_path: str) -> QAReport:
        """
        Load QA report from file.

        Args:
            report_path: Path to report file

        Returns:
            Loaded QA report
        """
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Reconstruct QAReport from dictionary
        scan_results = []
        for result_data in data.get('checks', []):
            # Convert back to QAScanResult
            # Note: This is simplified - full reconstruction would need more work
            result = QAScanResult(
                check_name=result_data['check_name'],
                total_scanned=result_data['total_scanned'],
                issues_found=result_data['issues_found'],
                summary=result_data['summary'],
                execution_time=float(result_data.get('execution_time', '0').rstrip('s'))
            )
            scan_results.append(result)

        return QAReport(
            timestamp=data['timestamp'],
            total_records=data['total_records'],
            scan_results=scan_results
        )

    def get_issue_distribution(self, report: QAReport) -> Dict[str, Any]:
        """
        Analyze issue distribution across checks and severity levels.

        Args:
            report: QA report to analyze

        Returns:
            Issue distribution analysis
        """
        distribution = {
            'by_check': {},
            'by_severity': {'high': 0, 'medium': 0, 'low': 0, 'critical': 0},
            'top_issues': [],
            'coverage_stats': {}
        }

        total_issues = 0
        all_issues = []

        for result in report.scan_results:
            distribution['by_check'][result.check_name] = {
                'issues': result.issues_found,
                'rate': result.issue_rate,
                'scanned': result.total_scanned
            }

            # Collect all issues for analysis
            all_issues.extend(result.issues)
            total_issues += result.issues_found

        # Analyze by severity
        for issue in all_issues:
            severity = issue.severity.value if hasattr(issue, 'severity') else 'unknown'
            if severity in distribution['by_severity']:
                distribution['by_severity'][severity] += 1

        # Find most common issue descriptions
        issue_descriptions = {}
        for issue in all_issues:
            desc_key = issue.description[:50] + "..." if len(issue.description) > 50 else issue.description
            issue_descriptions[desc_key] = issue_descriptions.get(desc_key, 0) + 1

        distribution['top_issues'] = sorted(
            issue_descriptions.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Coverage statistics
        distribution['coverage_stats'] = {
            'total_issues': total_issues,
            'checks_run': len(report.scan_results),
            'checks_with_issues': len([r for r in report.scan_results if r.issues_found > 0]),
            'avg_issues_per_check': total_issues / len(report.scan_results) if report.scan_results else 0
        }

        return distribution

    def _generate_report_summary(self, report: QAReport) -> str:
        """Generate human-readable report summary."""
        lines = [
            "=" * 80,
            "QA SCAN REPORT SUMMARY",
            "=" * 80,
            f"Timestamp: {report.timestamp}",
            f"Total Records Scanned: {report.total_records:,}",
            f"Total Issues Found: {report.total_issues:,}",
            f"Checks Run: {len(report.scan_results)}",
            "",
            "ISSUES BY SEVERITY:",
        ]

        severity_counts = report.issues_by_severity
        for severity, count in severity_counts.items():
            lines.append(f"  {severity.upper()}: {count:,}")

        lines.extend([
            "",
            "RESULTS BY CHECK:",
            "-" * 40
        ])

        for result in report.scan_results:
            lines.append(f"{result.check_name}:")
            lines.append(f"  Issues: {result.issues_found:,} / {result.total_scanned:,} ({result.issue_rate:.1f}%)")
            if result.execution_time:
                lines.append(f"  Time: {result.execution_time:.2f}s")
            if result.error:
                lines.append(f"  Error: {result.error}")
            lines.append("")

        # Add top issues if available
        distribution = self.get_issue_distribution(report)
        if distribution['top_issues']:
            lines.extend([
                "TOP ISSUE TYPES:",
                "-" * 20
            ])
            for desc, count in distribution['top_issues'][:5]:
                lines.append(f"{count:,}x: {desc}")

        lines.extend([
            "",
            "=" * 80
        ])

        return "\n".join(lines)

    def cleanup_checkpoints(self, keep_latest: int = 10) -> None:
        """Clean up old progress checkpoints."""
        self.progress_manager.cleanup_old_checkpoints(keep_latest)


# Backward compatibility functions for the existing CLI
def run_scan(records: List[Dict], checks: List[str] = None) -> QAReport:
    """
    Backward-compatible scan function.

    Args:
        records: List of record dictionaries
        checks: List of check names to run

    Returns:
        QA report with results
    """
    processor = QAProcessor()
    return processor.run_scan(records, checks)


def get_legacy_check_mapping() -> Dict[str, str]:
    """
    Map legacy check names to new check names.

    Returns:
        Mapping of old names to new names
    """
    return {
        # Legacy names from original qa.py
        "operativity": "tag_validation",
        "policy-relevance": "tag_validation",
        "policy-fallback": "tag_validation",
        "operativity-vs-content": "content_quality",
        "tag-body": "department_validation",
        "committee-tag": "tag_validation",
        "location-hallucination": "department_validation",
        "government-body-hallucination": "department_validation",
        "summary-quality": "content_quality",
        "summary-vs-tags": "tag_validation",
        "location-vs-body": "department_validation",
        "date-vs-government": "date_consistency",
        "title-vs-content": "content_quality",
        "date-validity": "date_consistency",
        "content-quality": "content_quality",
        "tag-consistency": "tag_consistency",
        "content-completeness": "content_quality",
        "body-default": "department_validation",
        "policy-default": "tag_validation",
        "operativity-validity": "tag_validation"
    }


def run_legacy_check(check_name: str, records: List[Dict]) -> QAScanResult:
    """
    Run legacy check with new architecture.

    Args:
        check_name: Legacy check name
        records: Records to analyze

    Returns:
        Scan result
    """
    processor = QAProcessor()
    mapping = get_legacy_check_mapping()

    new_check_name = mapping.get(check_name, check_name)
    return processor.run_check(new_check_name, records)