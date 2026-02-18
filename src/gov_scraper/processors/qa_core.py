#!/usr/bin/env python3
"""
QA Core Module for GOV2DB
==========================

Core quality assurance functionality shared across monitoring and processing systems.

Provides:
- QAProcessor class for running QA checks
- Common QA utilities and helpers
- Quality metrics calculations
- Issue severity assessment
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from .qa import run_scan, QAScanResult

logger = logging.getLogger(__name__)

@dataclass
class QACheckConfig:
    """Configuration for a QA check."""
    name: str
    enabled: bool = True
    severity_threshold: str = 'medium'
    max_issues: int = 100
    timeout_seconds: int = 60

class QAProcessor:
    """
    Core QA processing functionality.

    Provides a simplified interface for running QA checks
    and processing results.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._setup_default_checks()

    def _setup_default_checks(self):
        """Setup default QA check configuration."""
        self.default_checks = [
            'operativity',
            'policy-relevance',
            'government-body-hallucination',
            'location-hallucination',
            'tag-body',
            'summary-quality',
            'content-quality',
            'missing-fields'
        ]

    def run_qa_checks(
        self,
        records: List[Dict],
        checks: Optional[List[str]] = None
    ) -> List[QAScanResult]:
        """
        Run QA checks on provided records.

        Args:
            records: List of decision records to check
            checks: Specific checks to run (None for all)

        Returns:
            List of QA scan results
        """
        if not records:
            return []

        checks_to_run = checks or self.default_checks

        try:
            results = run_scan(records, checks=checks_to_run)
            return results if isinstance(results, list) else [results]
        except Exception as e:
            logger.error(f"Error running QA checks: {e}")
            return []

    def calculate_quality_score(self, results: List[QAScanResult]) -> float:
        """
        Calculate overall quality score from QA results.

        Returns score from 0-100 where 100 is perfect quality.
        """
        if not results:
            return 0.0

        total_records = sum(r.total_scanned for r in results if hasattr(r, 'total_scanned'))
        total_issues = sum(r.issues_found for r in results if hasattr(r, 'issues_found'))

        if total_records == 0:
            return 0.0

        # Calculate score based on issue rate
        issue_rate = total_issues / total_records
        quality_score = max(0, (1 - issue_rate) * 100)

        return round(quality_score, 2)

    def get_issue_summary(self, results: List[QAScanResult]) -> Dict[str, Any]:
        """Get summary of issues from QA results."""
        if not results:
            return {'total_issues': 0, 'by_severity': {}, 'by_check': {}}

        total_issues = 0
        by_severity = {}
        by_check = {}

        for result in results:
            if hasattr(result, 'issues_found'):
                total_issues += result.issues_found

            if hasattr(result, 'check_name'):
                by_check[result.check_name] = result.issues_found

        return {
            'total_issues': total_issues,
            'by_severity': by_severity,
            'by_check': by_check
        }