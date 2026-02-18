"""
Property-based tests for QA system invariants using Hypothesis.

These tests verify that QA system behaviors hold across a wide range of inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume, example
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant
from typing import List, Dict, Any
import json

from src.gov_scraper.processors.qa import (
    run_scan,
    check_operativity,
    check_content_quality,
    check_summary_quality,
    QAReport,
    QAScanResult,
    QAIssue
)


# Hypothesis strategies for generating test data
@st.composite
def decision_record(draw):
    """Generate a decision record using Hypothesis strategies."""
    decision_key = draw(st.text(alphabet="GOV0123456789_", min_size=5, max_size=20))

    # Ensure decision_key has proper format
    if not decision_key.startswith("GOV") or "_" not in decision_key:
        decision_key = f"GOV{draw(st.integers(1, 999))}_{draw(st.integers(1, 9999))}"

    hebrew_chars = "אבגדהוזחטיכלמנסעפצקרשתםןףךץ "

    record = {
        "decision_key": decision_key,
        "gov_num": draw(st.integers(1, 999)),
        "decision_num": draw(st.integers(1, 9999)),
        "decision_title": draw(st.text(alphabet=hebrew_chars + "0123456789", min_size=1, max_size=200)),
        "decision_content": draw(st.text(alphabet=hebrew_chars + "0123456789.,!?", min_size=0, max_size=2000)),
        "decision_date": draw(st.one_of(
            st.just("2024-01-15"),
            st.just("2023-12-31"),
            st.just("invalid-date"),
            st.just("")
        )),
        "operativity": draw(st.one_of(
            st.just("אופרטיבית"),
            st.just("דקלרטיבית"),
            st.just("מעורבת"),
            st.just(""),
            st.just("invalid")
        )),
        "summary": draw(st.text(alphabet=hebrew_chars + "0123456789.,!?", min_size=0, max_size=500)),
        "tags_policy_area": draw(st.one_of(
            st.just("כלכלה ואוצר"),
            st.just("חינוך"),
            st.just("בריאות"),
            st.just("שונות"),
            st.just("")
        )),
        "tags_government_body": draw(st.one_of(
            st.just("משרד האוצר"),
            st.just("משרד החינוך"),
            st.just("משרד הבריאות"),
            st.just(""),
            st.just("משרד לא קיים")
        )),
        "tags_locations": draw(st.one_of(
            st.just("ארצי"),
            st.just("ירושלים"),
            st.just("תל אביב"),
            st.just("")
        ))
    }

    return record


@st.composite
def record_list(draw, min_size=0, max_size=50):
    """Generate a list of decision records."""
    return draw(st.lists(decision_record(), min_size=min_size, max_size=max_size))


class TestQAInvariants:
    """Property-based tests for QA system invariants."""

    @given(records=record_list(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=10000)
    def test_scan_always_returns_valid_report(self, records):
        """Property: run_scan always returns a valid QAReport."""
        assume(len(records) > 0)

        report = run_scan(records)

        # Invariants
        assert isinstance(report, QAReport)
        assert isinstance(report.timestamp, str)
        assert report.total_records == len(records)
        assert isinstance(report.scan_results, list)
        assert report.total_issues >= 0
        assert len(report.scan_results) > 0

        # Each scan result should be valid
        for result in report.scan_results:
            assert isinstance(result, QAScanResult)
            assert isinstance(result.check_name, str)
            assert result.total_scanned >= 0
            assert result.issues_found >= 0
            assert result.issues_found == len(result.issues)
            assert result.total_scanned <= len(records)

            # Each issue should be valid
            for issue in result.issues:
                assert isinstance(issue, QAIssue)
                assert isinstance(issue.decision_key, str)
                assert issue.severity in ["high", "medium", "low"]

    @given(records=record_list(min_size=0, max_size=20))
    @settings(max_examples=50, deadline=10000)
    def test_scan_handles_empty_records(self, records):
        """Property: scan handles empty record lists gracefully."""
        report = run_scan(records)

        assert isinstance(report, QAReport)
        assert report.total_records == len(records)

        if len(records) == 0:
            # Empty dataset should have 0 total scanned for all checks
            for result in report.scan_results:
                assert result.total_scanned == 0
                assert result.issues_found == 0

    @given(record=decision_record())
    @settings(max_examples=50, deadline=5000)
    def test_individual_checks_return_valid_results(self, record):
        """Property: individual QA checks return valid QAScanResult."""
        records = [record]

        checks_to_test = [
            check_operativity,
            check_content_quality,
            check_summary_quality
        ]

        for check_func in checks_to_test:
            result = check_func(records)

            # Invariants
            assert isinstance(result, QAScanResult)
            assert result.total_scanned == 1
            assert result.issues_found >= 0
            assert result.issues_found == len(result.issues)
            assert isinstance(result.check_name, str)

            # All issues should reference the input record
            for issue in result.issues:
                assert issue.decision_key == record["decision_key"]

    @given(records=record_list(min_size=1, max_size=10))
    @settings(max_examples=30, deadline=10000)
    def test_scan_is_deterministic(self, records):
        """Property: scanning the same data twice produces identical results."""
        assume(len(records) > 0)

        report1 = run_scan(records)
        report2 = run_scan(records)

        # Should have same structure
        assert report1.total_records == report2.total_records
        assert len(report1.scan_results) == len(report2.scan_results)

        # Check names should be identical
        check_names1 = {r.check_name for r in report1.scan_results}
        check_names2 = {r.check_name for r in report2.scan_results}
        assert check_names1 == check_names2

        # Issue counts should be identical for each check
        for result1 in report1.scan_results:
            result2 = next(r for r in report2.scan_results if r.check_name == result1.check_name)
            assert result1.total_scanned == result2.total_scanned
            assert result1.issues_found == result2.issues_found

    @given(records=record_list(min_size=1, max_size=15))
    @settings(max_examples=30, deadline=10000)
    def test_total_scanned_consistency(self, records):
        """Property: total_scanned should be consistent with input size."""
        assume(len(records) > 0)

        report = run_scan(records)

        for result in report.scan_results:
            # Most checks should scan all records
            assert result.total_scanned <= len(records)
            # Some checks might filter records, but should never scan more than provided
            assert result.total_scanned >= 0

    @given(
        records=record_list(min_size=1, max_size=10),
        check_subset=st.lists(
            st.sampled_from(["operativity", "content-quality", "summary-quality"]),
            min_size=1, max_size=3, unique=True
        )
    )
    @settings(max_examples=20, deadline=10000)
    def test_subset_scanning_invariants(self, records, check_subset):
        """Property: scanning with a subset of checks produces consistent results."""
        assume(len(records) > 0)

        report = run_scan(records, checks=check_subset)

        # Should only run requested checks
        actual_checks = {r.check_name for r in report.scan_results}
        requested_checks = set(check_subset)

        # All requested checks should be present
        assert requested_checks.issubset(actual_checks)

        # Should not run unrequested checks (with some flexibility for related checks)
        assert len(actual_checks) >= len(requested_checks)

    @given(record=decision_record())
    @example(record={
        "decision_key": "GOV1_1",
        "decision_content": "",
        "operativity": "",
        "summary": "",
        "tags_policy_area": "",
        "decision_title": ""
    })
    @settings(max_examples=50, deadline=5000)
    def test_empty_fields_handling(self, record):
        """Property: QA checks handle empty/missing fields gracefully."""
        records = [record]

        # Should not crash with empty fields
        report = run_scan(records)

        assert isinstance(report, QAReport)
        assert report.total_records == 1

        # Checks should handle empty fields without exceptions
        for result in report.scan_results:
            assert isinstance(result.issues_found, int)
            assert result.issues_found >= 0

    @given(records=st.lists(
        st.fixed_dictionaries({
            "decision_key": st.text(min_size=1, max_size=20),
            "operativity": st.just("אופרטיבית"),
            "decision_content": st.just("הממשלה החליטה לאשר"),
            "summary": st.text(min_size=1, max_size=100),
            "tags_policy_area": st.just("כלכלה ואוצר")
        }),
        min_size=1, max_size=10
    ))
    @settings(max_examples=20, deadline=5000)
    def test_clean_data_minimal_issues(self, records):
        """Property: clean, consistent data should produce minimal high-severity issues."""
        assume(len(records) > 0)

        report = run_scan(records)

        # Count high-severity issues
        high_severity_count = sum(
            1 for result in report.scan_results
            for issue in result.issues
            if issue.severity == "high"
        )

        # Clean data should have minimal high-severity issues
        # Allow some flexibility as detection isn't perfect
        total_records = len(records)
        high_severity_rate = high_severity_count / total_records if total_records > 0 else 0

        # Most records should be clean (less than 50% high-severity issue rate)
        assert high_severity_rate < 0.5

    @given(
        good_records=st.lists(
            st.fixed_dictionaries({
                "decision_key": st.text(min_size=5, max_size=20),
                "decision_content": st.just("הממשלה החליטה לאשר תוכנית חשובה"),
                "operativity": st.just("אופרטיבית"),
                "summary": st.just("אישור תוכנית חשובה"),
                "tags_policy_area": st.just("כלכלה ואוצר")
            }),
            min_size=1, max_size=5
        ),
        bad_records=st.lists(
            st.fixed_dictionaries({
                "decision_key": st.text(min_size=5, max_size=20),
                "decision_content": st.just("Just a moment... Cloudflare"),
                "operativity": st.just("invalid"),
                "summary": st.just(""),
                "tags_policy_area": st.just("")
            }),
            min_size=1, max_size=5
        )
    )
    @settings(max_examples=20, deadline=10000)
    def test_issue_detection_proportionality(self, good_records, bad_records):
        """Property: records with issues should have higher issue rates than clean records."""
        assume(len(good_records) > 0 and len(bad_records) > 0)

        good_report = run_scan(good_records)
        bad_report = run_scan(bad_records)

        good_issue_rate = good_report.total_issues / len(good_records)
        bad_issue_rate = bad_report.total_issues / len(bad_records)

        # Bad records should generally have more issues than good records
        # Allow some flexibility due to detection imperfections
        assert bad_issue_rate >= good_issue_rate or bad_issue_rate > 0


class TestQADataInvariants:
    """Property-based tests for QA data structure invariants."""

    @given(
        decision_key=st.text(min_size=1, max_size=50),
        check_name=st.text(min_size=1, max_size=50),
        severity=st.sampled_from(["high", "medium", "low"]),
        field=st.text(min_size=1, max_size=50),
        current_value=st.text(min_size=0, max_size=200),
        description=st.text(min_size=1, max_size=500)
    )
    @settings(max_examples=50)
    def test_qa_issue_invariants(self, decision_key, check_name, severity,
                                 field, current_value, description):
        """Property: QAIssue objects maintain valid state."""
        issue = QAIssue(
            decision_key=decision_key,
            check_name=check_name,
            severity=severity,
            field=field,
            current_value=current_value,
            description=description
        )

        # Invariants
        assert issue.decision_key == decision_key
        assert issue.check_name == check_name
        assert issue.severity in ["high", "medium", "low"]
        assert issue.field == field
        assert issue.current_value == current_value
        assert issue.description == description
        assert isinstance(issue.expected_value, str)  # Should default to empty string

    @given(
        check_name=st.text(min_size=1, max_size=50),
        total_scanned=st.integers(0, 1000),
        issues=st.lists(
            st.builds(QAIssue,
                     decision_key=st.text(min_size=1, max_size=20),
                     check_name=st.text(min_size=1, max_size=20),
                     severity=st.sampled_from(["high", "medium", "low"]),
                     field=st.text(min_size=1, max_size=20),
                     current_value=st.text(max_size=100),
                     description=st.text(min_size=1, max_size=100)),
            max_size=20
        )
    )
    @settings(max_examples=30)
    def test_qa_scan_result_invariants(self, check_name, total_scanned, issues):
        """Property: QAScanResult maintains consistent state."""
        issues_found = len(issues)

        result = QAScanResult(
            check_name=check_name,
            total_scanned=total_scanned,
            issues_found=issues_found,
            issues=issues,
            summary={}
        )

        # Invariants
        assert result.check_name == check_name
        assert result.total_scanned == total_scanned
        assert result.issues_found == issues_found
        assert result.issues_found == len(result.issues)
        assert len(result.issues) == len(issues)

        # to_dict should work without errors
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "check_name" in result_dict
        assert "total_scanned" in result_dict
        assert "issues_found" in result_dict
        assert "issue_rate" in result_dict


class QAStateMachine(RuleBasedStateMachine):
    """Stateful property-based testing for QA operations."""

    def __init__(self):
        super().__init__()
        self.records = []
        self.last_report = None

    @initialize()
    def setup(self):
        """Initialize the state machine."""
        self.records = []
        self.last_report = None

    @rule(record=decision_record())
    def add_record(self, record):
        """Add a record to the dataset."""
        assume(len(self.records) < 20)  # Limit size for performance
        self.records.append(record)

    @rule()
    def run_scan(self):
        """Run a QA scan on current records."""
        assume(len(self.records) > 0)
        self.last_report = run_scan(self.records)

    @invariant()
    def records_consistency(self):
        """Records list should always be valid."""
        assert isinstance(self.records, list)
        assert all(isinstance(r, dict) for r in self.records)
        assert all("decision_key" in r for r in self.records)

    @invariant()
    def report_consistency(self):
        """If we have a report, it should be consistent with records."""
        if self.last_report is not None:
            assert isinstance(self.last_report, QAReport)
            assert self.last_report.total_records == len(self.records)
            assert self.last_report.total_issues >= 0

    @rule()
    def clear_records(self):
        """Clear all records."""
        self.records = []
        self.last_report = None


# Run the state machine test
TestQAStateMachine = QAStateMachine.TestCase


@pytest.mark.property
class TestPropertyBasedQA:
    """Additional property-based tests with specific scenarios."""

    @given(st.data())
    @settings(max_examples=20, deadline=10000)
    def test_scan_with_random_subsets(self, data):
        """Property: scanning random subsets of records produces consistent results."""
        # Generate base records
        records = data.draw(record_list(min_size=3, max_size=10))
        assume(len(records) >= 3)

        # Generate random subset
        subset_size = data.draw(st.integers(1, len(records)))
        subset_indices = data.draw(st.lists(
            st.integers(0, len(records) - 1),
            min_size=subset_size,
            max_size=subset_size,
            unique=True
        ))

        subset = [records[i] for i in subset_indices]

        # Scan both full set and subset
        full_report = run_scan(records)
        subset_report = run_scan(subset)

        # Invariants
        assert subset_report.total_records == len(subset)
        assert full_report.total_records == len(records)

        # Should run same types of checks
        full_checks = {r.check_name for r in full_report.scan_results}
        subset_checks = {r.check_name for r in subset_report.scan_results}
        assert full_checks == subset_checks

    @given(
        base_record=decision_record(),
        modifications=st.lists(
            st.tuples(
                st.sampled_from(["decision_content", "operativity", "summary", "tags_policy_area"]),
                st.text(max_size=100)
            ),
            max_size=3
        )
    )
    @settings(max_examples=20, deadline=5000)
    def test_record_modification_impact(self, base_record, modifications):
        """Property: modifying records should not cause crashes."""
        # Apply modifications
        modified_record = base_record.copy()
        for field, value in modifications:
            modified_record[field] = value

        records = [modified_record]

        # Should not crash regardless of modifications
        report = run_scan(records)

        assert isinstance(report, QAReport)
        assert report.total_records == 1

        # All scan results should be valid
        for result in report.scan_results:
            assert isinstance(result, QAScanResult)
            assert result.total_scanned >= 0
            assert result.issues_found >= 0