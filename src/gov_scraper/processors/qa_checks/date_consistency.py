"""
Date Consistency Checks Module

Implements comprehensive date validation including:
- Date format validation
- Date range validation
- Cross-field date consistency
- Government period alignment
- Historical accuracy checks
"""

import re
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Set, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass

from ..qa_core import AbstractQACheck, QAIssue, CheckSeverity

logger = logging.getLogger(__name__)


@dataclass
class GovernmentPeriod:
    """Israeli government period information."""
    number: int
    start_date: date
    end_date: Optional[date]
    prime_minister: str


# Israeli government periods (approximate dates)
GOVERNMENT_PERIODS = [
    GovernmentPeriod(30, date(2009, 3, 31), date(2013, 3, 18), "בנימין נתניהו"),
    GovernmentPeriod(32, date(2013, 3, 18), date(2015, 5, 14), "בנימין נתניהו"),
    GovernmentPeriod(33, date(2015, 5, 14), date(2019, 4, 9), "בנימין נתניהו"),
    GovernmentPeriod(34, date(2019, 4, 9), date(2020, 5, 17), "בנימין נתניהו"),
    GovernmentPeriod(35, date(2021, 6, 13), date(2022, 12, 29), "נפתלי בנט/יאיר לפיד"),
    GovernmentPeriod(36, date(2022, 12, 29), date(2024, 11, 13), "בנימין נתניהו"),
    GovernmentPeriod(37, date(2024, 11, 13), None, "בנימין נתניהו"),
]


class DateConsistencyCheck(AbstractQACheck):
    """
    Comprehensive date validation and consistency checking.

    Checks for:
    - Date format validation
    - Date range plausibility
    - Cross-field date consistency
    - Government period alignment
    - Historical context validation
    """

    def __init__(self,
                 min_valid_date: date = date(1948, 5, 14),  # Israel independence
                 max_future_days: int = 365,
                 **kwargs):
        super().__init__(
            check_name="date_consistency",
            description="Validates date formats, ranges, and consistency",
            **kwargs
        )
        self.min_valid_date = min_valid_date
        self.max_valid_date = date.today() + timedelta(days=max_future_days)
        self.government_periods = {p.number: p for p in GOVERNMENT_PERIODS}

        # Common date formats in Israeli government documents
        self.date_formats = [
            "%Y-%m-%d",          # 2023-12-25
            "%d.%m.%Y",          # 25.12.2023
            "%d/%m/%Y",          # 25/12/2023
            "%d-%m-%Y",          # 25-12-2023
            "%Y/%m/%d",          # 2023/12/25
        ]

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate dates in a single record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Check date fields
        date_fields = ['decision_date', 'meeting_date', 'publication_date', 'created_at', 'updated_at']

        parsed_dates = {}
        for field in date_fields:
            date_value = record.get(field, '')
            if not date_value:
                continue

            # Parse and validate date
            date_issues, parsed_date = self._validate_date_field(decision_key, field, date_value)
            issues.extend(date_issues)

            if parsed_date:
                parsed_dates[field] = parsed_date

        # Cross-field date consistency checks
        if parsed_dates:
            consistency_issues = self._check_date_consistency(decision_key, parsed_dates)
            issues.extend(consistency_issues)

        # Government period alignment
        if 'decision_date' in parsed_dates:
            gov_issues = self._check_government_period_alignment(decision_key, record, parsed_dates['decision_date'])
            issues.extend(gov_issues)

        return issues

    def _validate_date_field(self, decision_key: str, field: str, date_value: str) -> Tuple[List[QAIssue], Optional[date]]:
        """Validate and parse a single date field."""
        issues = []
        parsed_date = None

        # Clean the date string
        cleaned_date = self._clean_date_string(date_value)

        # Try to parse the date
        for date_format in self.date_formats:
            try:
                parsed_date = datetime.strptime(cleaned_date, date_format).date()
                break
            except ValueError:
                continue

        if not parsed_date:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=date_value,
                description=f"Invalid date format: '{date_value}'",
                expected_value="Valid date in format YYYY-MM-DD or DD.MM.YYYY",
                original_value=date_value,
                cleaned_value=cleaned_date,
                attempted_formats=self.date_formats
            ))
            return issues, None

        # Validate date range
        if parsed_date < self.min_valid_date:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=date_value,
                description=f"Date too early: {parsed_date} (before {self.min_valid_date})",
                expected_value=f"Date after {self.min_valid_date}",
                parsed_date=parsed_date.isoformat(),
                min_valid_date=self.min_valid_date.isoformat()
            ))

        if parsed_date > self.max_valid_date:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=date_value,
                description=f"Date too far in future: {parsed_date} (after {self.max_valid_date})",
                expected_value=f"Date before {self.max_valid_date}",
                parsed_date=parsed_date.isoformat(),
                max_valid_date=self.max_valid_date.isoformat()
            ))

        # Check for suspicious dates
        suspicious_issues = self._check_suspicious_dates(decision_key, field, parsed_date)
        issues.extend(suspicious_issues)

        return issues, parsed_date

    def _check_date_consistency(self, decision_key: str, parsed_dates: Dict[str, date]) -> List[QAIssue]:
        """Check consistency between different date fields."""
        issues = []

        # Define expected date relationships
        date_relationships = [
            ('meeting_date', 'decision_date', 'Meeting should occur before or same day as decision'),
            ('decision_date', 'publication_date', 'Decision should occur before publication'),
            ('created_at', 'updated_at', 'Creation should occur before updates'),
        ]

        for earlier_field, later_field, description in date_relationships:
            if earlier_field in parsed_dates and later_field in parsed_dates:
                earlier_date = parsed_dates[earlier_field]
                later_date = parsed_dates[later_field]

                if earlier_date > later_date:
                    issues.append(self.create_issue(
                        decision_key=decision_key,
                        severity=CheckSeverity.MEDIUM,
                        field=f"{earlier_field}+{later_field}",
                        current_value=f"{earlier_field}: {earlier_date}, {later_field}: {later_date}",
                        description=f"Date order inconsistent: {description}",
                        expected_value=f"{earlier_field} <= {later_field}",
                        earlier_field=earlier_field,
                        later_field=later_field,
                        earlier_date=earlier_date.isoformat(),
                        later_date=later_date.isoformat()
                    ))

        # Check for unreasonable gaps
        if 'decision_date' in parsed_dates and 'publication_date' in parsed_dates:
            gap = (parsed_dates['publication_date'] - parsed_dates['decision_date']).days

            if gap > 365:  # More than a year between decision and publication
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field="publication_date",
                    current_value=f"{gap} days after decision",
                    description=f"Long gap between decision and publication: {gap} days",
                    expected_value="Publication within reasonable timeframe (< 1 year)",
                    gap_days=gap,
                    decision_date=parsed_dates['decision_date'].isoformat(),
                    publication_date=parsed_dates['publication_date'].isoformat()
                ))

        return issues

    def _check_government_period_alignment(self, decision_key: str, record: Dict, decision_date: date) -> List[QAIssue]:
        """Check if decision date aligns with government period."""
        issues = []

        # Extract government number from record
        gov_num = record.get('gov_num')
        if not gov_num:
            return issues

        try:
            gov_number = int(gov_num)
        except (ValueError, TypeError):
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field="gov_num",
                current_value=str(gov_num),
                description=f"Invalid government number format: '{gov_num}'",
                expected_value="Numeric government number",
                original_value=gov_num
            ))
            return issues

        # Check if government period exists
        if gov_number not in self.government_periods:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field="gov_num",
                current_value=str(gov_number),
                description=f"Unknown government number: {gov_number}",
                expected_value=f"Known government number: {list(self.government_periods.keys())}",
                government_number=gov_number,
                known_governments=list(self.government_periods.keys())
            ))
            return issues

        # Check date alignment with government period
        gov_period = self.government_periods[gov_number]

        if decision_date < gov_period.start_date:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field="decision_date",
                current_value=decision_date.isoformat(),
                description=f"Decision date {decision_date} before government {gov_number} start ({gov_period.start_date})",
                expected_value=f"Date after {gov_period.start_date}",
                decision_date=decision_date.isoformat(),
                government_number=gov_number,
                government_start=gov_period.start_date.isoformat()
            ))

        if gov_period.end_date and decision_date > gov_period.end_date:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field="decision_date",
                current_value=decision_date.isoformat(),
                description=f"Decision date {decision_date} after government {gov_number} end ({gov_period.end_date})",
                expected_value=f"Date before {gov_period.end_date}",
                decision_date=decision_date.isoformat(),
                government_number=gov_number,
                government_end=gov_period.end_date.isoformat()
            ))

        return issues

    def _check_suspicious_dates(self, decision_key: str, field: str, parsed_date: date) -> List[QAIssue]:
        """Check for suspicious or unlikely dates."""
        issues = []

        # Check for dates on unlikely days
        if field in ['decision_date', 'meeting_date']:
            # Government meetings rarely occur on Shabbat (Saturday = 5) or Sunday (6)
            if parsed_date.weekday() in [5, 6]:
                severity = CheckSeverity.LOW if parsed_date.weekday() == 6 else CheckSeverity.MEDIUM

                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=severity,
                    field=field,
                    current_value=parsed_date.isoformat(),
                    description=f"Government meeting/decision on {'Saturday' if parsed_date.weekday() == 5 else 'Sunday'}",
                    expected_value="Meeting on typical working days (Sunday-Thursday)",
                    weekday=parsed_date.strftime("%A"),
                    is_weekend=True
                ))

        # Check for dates on major holidays (simplified check)
        suspicious_dates = self._get_suspicious_dates(parsed_date.year)
        for holiday_date, holiday_name in suspicious_dates:
            if parsed_date == holiday_date:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.LOW,
                    field=field,
                    current_value=parsed_date.isoformat(),
                    description=f"Date falls on {holiday_name}",
                    expected_value="Date not on major holidays",
                    holiday=holiday_name,
                    is_holiday=True
                ))

        # Check for patterns suggesting automated generation
        if self._looks_like_generated_date(parsed_date):
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=parsed_date.isoformat(),
                description="Date pattern suggests automated generation (e.g., 01/01, 15/15)",
                expected_value="Realistic date pattern",
                suspicious_pattern=True
            ))

        return issues

    def _clean_date_string(self, date_str: str) -> str:
        """Clean and normalize date string."""
        # Remove extra whitespace
        cleaned = date_str.strip()

        # Remove common prefixes/suffixes
        prefixes_to_remove = ['תאריך:', 'date:', 'מיום']
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()

        # Handle Hebrew date separators
        cleaned = cleaned.replace('ב-', '').replace('ב', '')

        # Normalize separators
        cleaned = re.sub(r'[\.\/\-\s]+', '.', cleaned)

        # Remove trailing punctuation
        cleaned = cleaned.rstrip('.,;')

        return cleaned

    def _get_suspicious_dates(self, year: int) -> List[Tuple[date, str]]:
        """Get list of suspicious dates for a given year (major holidays)."""
        # This is a simplified implementation
        # In practice, you'd use a proper Hebrew calendar library
        suspicious_dates = []

        try:
            # Major holidays (approximate Gregorian dates)
            holidays = [
                (1, 1, "New Year's Day"),
                (12, 25, "Christmas Day"),
                (4, 1, "April Fool's Day"),
            ]

            for month, day, name in holidays:
                try:
                    holiday_date = date(year, month, day)
                    suspicious_dates.append((holiday_date, name))
                except ValueError:
                    pass

        except Exception:
            pass

        return suspicious_dates

    def _looks_like_generated_date(self, parsed_date: date) -> bool:
        """Check if date looks like it was automatically generated."""
        # Check for common patterns in fake dates
        day = parsed_date.day
        month = parsed_date.month

        # Dates like 01/01, 15/15, etc.
        if day == month and day in [1, 15]:
            return True

        # All same digits
        if day == 11 and month == 11:
            return True

        # Sequential patterns
        if day == month + 1 or day == month - 1:
            return True

        return False

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary statistics for date consistency check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "issue_rate": f"{(len(issues) / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }

        # Group issues by type
        issue_types = defaultdict(int)
        severity_counts = defaultdict(int)
        field_counts = defaultdict(int)
        date_ranges = defaultdict(int)

        for issue in issues:
            # Extract issue type from description
            desc = issue.description.lower()
            if "format" in desc:
                issue_type = "format_errors"
            elif "too early" in desc or "too late" in desc or "future" in desc:
                issue_type = "range_errors"
            elif "order" in desc or "consistency" in desc:
                issue_type = "consistency_errors"
            elif "government" in desc:
                issue_type = "government_alignment"
            elif "weekend" in desc or "holiday" in desc:
                issue_type = "suspicious_dates"
            elif "gap" in desc:
                issue_type = "timing_issues"
            else:
                issue_type = "other"

            issue_types[issue_type] += 1
            severity_counts[issue.severity.value] += 1
            field_counts[issue.field] += 1

        summary.update({
            "issues_by_type": dict(issue_types),
            "issues_by_severity": dict(severity_counts),
            "issues_by_field": dict(field_counts)
        })

        # Date quality metrics
        if issues:
            format_error_rate = issue_types.get("format_errors", 0) / len(issues) * 100
            consistency_rate = (1 - issue_types.get("consistency_errors", 0) / len(issues)) * 100

            summary.update({
                "format_error_rate": f"{format_error_rate:.1f}%",
                "consistency_rate": f"{consistency_rate:.1f}%",
                "supported_formats": self.date_formats,
                "valid_date_range": f"{self.min_valid_date} to {self.max_valid_date}",
                "government_periods_checked": len(self.government_periods)
            })

        return summary


class TemporalConsistencyCheck(AbstractQACheck):
    """
    Specialized check for temporal consistency across the dataset.

    Looks for temporal patterns and anomalies in decision sequences.
    """

    def __init__(self, **kwargs):
        super().__init__(
            check_name="temporal_consistency",
            description="Validates temporal patterns and decision sequences",
            **kwargs
        )
        self.decision_sequences = defaultdict(list)

    def run(self, records: List[Dict]) -> 'QAScanResult':
        """Override run to perform cross-record temporal analysis."""
        from ..qa_core import QAScanResult
        import time

        start_time = time.time()
        self._init_progress(len(records))

        # Collect and sort decisions by government and date
        gov_decisions = defaultdict(list)

        for record in records:
            decision_date_str = record.get('decision_date', '')
            gov_num = record.get('gov_num', '')

            if not decision_date_str or not gov_num:
                continue

            # Try to parse date
            decision_date = None
            for date_format in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
                try:
                    decision_date = datetime.strptime(decision_date_str.strip(), date_format).date()
                    break
                except ValueError:
                    continue

            if decision_date:
                gov_decisions[gov_num].append({
                    'decision_key': record.get('decision_key', 'unknown'),
                    'decision_date': decision_date,
                    'decision_num': record.get('decision_num', ''),
                    'record': record
                })

        # Sort decisions by date within each government
        all_issues = []
        for gov_num, decisions in gov_decisions.items():
            decisions.sort(key=lambda x: x['decision_date'])

            # Check for temporal anomalies
            temporal_issues = self._analyze_temporal_sequence(gov_num, decisions)
            all_issues.extend(temporal_issues)

        self._complete_progress()
        execution_time = time.time() - start_time

        return QAScanResult(
            check_name=self.check_name,
            total_scanned=len(records),
            issues_found=len(all_issues),
            issues=all_issues,
            summary=self._generate_temporal_summary(all_issues, len(records), gov_decisions),
            execution_time=execution_time,
            progress=self._progress
        )

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Not used in temporal consistency check - override run instead."""
        return []

    def _analyze_temporal_sequence(self, gov_num: str, decisions: List[Dict]) -> List[QAIssue]:
        """Analyze temporal sequence of decisions within a government."""
        issues = []

        if len(decisions) < 2:
            return issues

        # Check for date gaps and overlaps
        for i in range(1, len(decisions)):
            prev_decision = decisions[i-1]
            curr_decision = decisions[i]

            date_gap = (curr_decision['decision_date'] - prev_decision['decision_date']).days

            # Check for decisions on the same date with sequential numbers
            if date_gap == 0:
                prev_num = prev_decision.get('decision_num', '')
                curr_num = curr_decision.get('decision_num', '')

                try:
                    prev_int = int(prev_num)
                    curr_int = int(curr_num)

                    # Check if numbers are not sequential
                    if curr_int != prev_int + 1 and abs(curr_int - prev_int) > 1:
                        issues.append(self.create_issue(
                            decision_key=curr_decision['decision_key'],
                            severity=CheckSeverity.LOW,
                            field="decision_num",
                            current_value=f"#{curr_num} after #{prev_num}",
                            description=f"Non-sequential decision numbers on same date in gov {gov_num}",
                            expected_value="Sequential decision numbers for same-day decisions",
                            government=gov_num,
                            date=curr_decision['decision_date'].isoformat(),
                            prev_number=prev_int,
                            curr_number=curr_int,
                            gap=abs(curr_int - prev_int)
                        ))

                except (ValueError, TypeError):
                    pass

            # Check for unreasonable date gaps
            elif date_gap > 365:  # More than a year between consecutive decisions
                issues.append(self.create_issue(
                    decision_key=curr_decision['decision_key'],
                    severity=CheckSeverity.LOW,
                    field="decision_date",
                    current_value=curr_decision['decision_date'].isoformat(),
                    description=f"Large time gap between decisions: {date_gap} days",
                    expected_value="Reasonable gaps between consecutive government decisions",
                    government=gov_num,
                    gap_days=date_gap,
                    prev_decision_date=prev_decision['decision_date'].isoformat(),
                    curr_decision_date=curr_decision['decision_date'].isoformat()
                ))

        return issues

    def _generate_temporal_summary(self, issues: List[QAIssue], total_scanned: int, gov_decisions: Dict) -> Dict[str, Any]:
        """Generate summary for temporal consistency check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "governments_analyzed": len(gov_decisions)
        }

        # Calculate temporal statistics
        gov_stats = {}
        for gov_num, decisions in gov_decisions.items():
            if len(decisions) >= 2:
                dates = [d['decision_date'] for d in decisions]
                date_span = (max(dates) - min(dates)).days

                gov_stats[gov_num] = {
                    "decision_count": len(decisions),
                    "date_span_days": date_span,
                    "avg_gap_days": date_span / (len(decisions) - 1) if len(decisions) > 1 else 0,
                    "first_decision": min(dates).isoformat(),
                    "last_decision": max(dates).isoformat()
                }

        summary["government_statistics"] = gov_stats

        # Issue analysis
        gap_issues = [i for i in issues if "gap" in i.description.lower()]
        sequence_issues = [i for i in issues if "sequential" in i.description.lower()]

        summary.update({
            "temporal_gap_issues": len(gap_issues),
            "sequence_issues": len(sequence_issues),
            "avg_decisions_per_government": sum(len(decisions) for decisions in gov_decisions.values()) / len(gov_decisions) if gov_decisions else 0
        })

        return summary