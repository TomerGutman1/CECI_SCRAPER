"""
Unit tests for QA data classes and structures.
"""

import pytest
from datetime import datetime
from src.gov_scraper.processors.qa import QAIssue, QAScanResult, QAReport


class TestQAIssue:
    """Test the QAIssue data class."""

    def test_qa_issue_creation(self):
        """Test creating a QA issue."""
        issue = QAIssue(
            decision_key="GOV1_1",
            check_name="operativity",
            severity="high",
            field="operativity",
            current_value="דקלרטיבית",
            description="Operativity mismatch detected",
            expected_value="אופרטיבית"
        )

        assert issue.decision_key == "GOV1_1"
        assert issue.check_name == "operativity"
        assert issue.severity == "high"
        assert issue.field == "operativity"
        assert issue.current_value == "דקלרטיבית"
        assert issue.description == "Operativity mismatch detected"
        assert issue.expected_value == "אופרטיבית"

    def test_qa_issue_without_expected_value(self):
        """Test creating a QA issue without expected value."""
        issue = QAIssue(
            decision_key="GOV1_2",
            check_name="content-quality",
            severity="medium",
            field="decision_content",
            current_value="Short content",
            description="Content too short"
        )

        assert issue.expected_value == ""  # Default empty string

    @pytest.mark.parametrize("severity", ["high", "medium", "low"])
    def test_qa_issue_severity_levels(self, severity):
        """Test QA issue with different severity levels."""
        issue = QAIssue(
            decision_key="GOV1_TEST",
            check_name="test-check",
            severity=severity,
            field="test_field",
            current_value="test_value",
            description="Test issue"
        )

        assert issue.severity == severity


class TestQAScanResult:
    """Test the QAScanResult data class."""

    def test_qa_scan_result_creation(self):
        """Test creating a QA scan result."""
        issues = [
            QAIssue("GOV1_1", "operativity", "high", "operativity", "wrong", "Issue 1"),
            QAIssue("GOV1_2", "operativity", "medium", "operativity", "wrong", "Issue 2")
        ]

        result = QAScanResult(
            check_name="operativity",
            total_scanned=100,
            issues_found=2,
            issues=issues,
            summary={"accuracy": "98%", "processed": 100}
        )

        assert result.check_name == "operativity"
        assert result.total_scanned == 100
        assert result.issues_found == 2
        assert len(result.issues) == 2
        assert result.summary["accuracy"] == "98%"

    def test_qa_scan_result_to_dict(self):
        """Test converting QA scan result to dictionary."""
        issues = [
            QAIssue("GOV1_1", "operativity", "high", "operativity", "דקלרטיבית", "Mismatch detected"),
            QAIssue("GOV1_2", "operativity", "medium", "operativity", "לא ברור", "Unclear classification")
        ]

        result = QAScanResult(
            check_name="operativity",
            total_scanned=50,
            issues_found=2,
            issues=issues,
            summary={"processed": 50, "accuracy": "96%"}
        )

        result_dict = result.to_dict()

        assert result_dict["check_name"] == "operativity"
        assert result_dict["total_scanned"] == 50
        assert result_dict["issues_found"] == 2
        assert result_dict["issue_rate"] == "4.0%"
        assert result_dict["summary"]["processed"] == 50
        assert len(result_dict["sample_issues"]) == 2

        # Check sample issue format
        sample_issue = result_dict["sample_issues"][0]
        assert "decision_key" in sample_issue
        assert "severity" in sample_issue
        assert "field" in sample_issue
        assert "current_value" in sample_issue
        assert "description" in sample_issue

    def test_qa_scan_result_issue_rate_calculation(self):
        """Test issue rate calculation."""
        # Test with issues
        result_with_issues = QAScanResult(
            check_name="test",
            total_scanned=100,
            issues_found=25,
            issues=[],
            summary={}
        )

        result_dict = result_with_issues.to_dict()
        assert result_dict["issue_rate"] == "25.0%"

        # Test with no records scanned
        result_no_records = QAScanResult(
            check_name="test",
            total_scanned=0,
            issues_found=0,
            issues=[],
            summary={}
        )

        result_dict = result_no_records.to_dict()
        assert result_dict["issue_rate"] == "0%"

    def test_qa_scan_result_sample_issues_limit(self):
        """Test that sample issues are limited to 10."""
        issues = [
            QAIssue(f"GOV1_{i}", "test", "low", "field", "value", f"Issue {i}")
            for i in range(15)  # Create 15 issues
        ]

        result = QAScanResult(
            check_name="test",
            total_scanned=100,
            issues_found=15,
            issues=issues,
            summary={}
        )

        result_dict = result.to_dict()
        assert len(result_dict["sample_issues"]) == 10  # Should be limited to 10

    def test_qa_scan_result_long_current_value_truncation(self):
        """Test that long current values are truncated in sample issues."""
        long_content = "א" * 300  # 300 Hebrew characters

        issues = [
            QAIssue("GOV1_1", "test", "high", "content", long_content, "Long content issue")
        ]

        result = QAScanResult(
            check_name="test",
            total_scanned=1,
            issues_found=1,
            issues=issues,
            summary={}
        )

        result_dict = result.to_dict()
        sample_issue = result_dict["sample_issues"][0]
        assert len(sample_issue["current_value"]) <= 200  # Should be truncated


class TestQAReport:
    """Test the QAReport data class."""

    def test_qa_report_creation(self):
        """Test creating a QA report."""
        scan_results = [
            QAScanResult("operativity", 100, 5, [], {"accuracy": "95%"}),
            QAScanResult("content-quality", 100, 3, [], {"issues": 3})
        ]

        report = QAReport(
            timestamp="2024-01-15T10:30:00",
            total_records=100,
            scan_results=scan_results
        )

        assert report.timestamp == "2024-01-15T10:30:00"
        assert report.total_records == 100
        assert len(report.scan_results) == 2

    def test_qa_report_total_issues_property(self):
        """Test total issues calculation."""
        scan_results = [
            QAScanResult("check1", 100, 5, [], {}),
            QAScanResult("check2", 100, 3, [], {}),
            QAScanResult("check3", 100, 0, [], {})
        ]

        report = QAReport("2024-01-15T10:30:00", 100, scan_results)

        assert report.total_issues == 8  # 5 + 3 + 0

    def test_qa_report_issues_by_severity_property(self):
        """Test issues by severity calculation."""
        issues = [
            QAIssue("GOV1_1", "check1", "high", "field", "val", "Issue 1"),
            QAIssue("GOV1_2", "check1", "high", "field", "val", "Issue 2"),
            QAIssue("GOV1_3", "check2", "medium", "field", "val", "Issue 3"),
            QAIssue("GOV1_4", "check2", "low", "field", "val", "Issue 4"),
            QAIssue("GOV1_5", "check2", "low", "field", "val", "Issue 5")
        ]

        scan_results = [
            QAScanResult("check1", 100, 2, issues[:2], {}),
            QAScanResult("check2", 100, 3, issues[2:], {})
        ]

        report = QAReport("2024-01-15T10:30:00", 100, scan_results)

        severity_counts = report.issues_by_severity

        assert severity_counts["high"] == 2
        assert severity_counts["medium"] == 1
        assert severity_counts["low"] == 2

    def test_qa_report_to_dict(self):
        """Test converting QA report to dictionary."""
        issues = [
            QAIssue("GOV1_1", "operativity", "high", "operativity", "wrong", "Issue"),
            QAIssue("GOV1_2", "content", "medium", "content", "poor", "Content issue")
        ]

        scan_results = [
            QAScanResult("operativity", 50, 1, issues[:1], {"accuracy": "98%"}),
            QAScanResult("content", 50, 1, issues[1:], {"quality": "good"})
        ]

        report = QAReport("2024-01-15T10:30:00", 100, scan_results)

        report_dict = report.to_dict()

        assert report_dict["timestamp"] == "2024-01-15T10:30:00"
        assert report_dict["total_records"] == 100
        assert report_dict["total_issues"] == 2
        assert report_dict["issues_by_severity"]["high"] == 1
        assert report_dict["issues_by_severity"]["medium"] == 1
        assert len(report_dict["scan_results"]) == 2

    def test_qa_report_empty_scan_results(self):
        """Test QA report with no scan results."""
        report = QAReport("2024-01-15T10:30:00", 0, [])

        assert report.total_issues == 0
        assert report.issues_by_severity == {}

        report_dict = report.to_dict()
        assert report_dict["total_issues"] == 0
        assert report_dict["issues_by_severity"] == {}
        assert len(report_dict["scan_results"]) == 0


@pytest.mark.parametrize("total_scanned,issues_found,expected_rate", [
    (100, 0, "0.0%"),
    (100, 1, "1.0%"),
    (100, 25, "25.0%"),
    (100, 100, "100.0%"),
    (0, 0, "0%"),  # Special case for zero scanned
])
def test_issue_rate_calculation_parametrized(total_scanned, issues_found, expected_rate):
    """Parametrized test for issue rate calculation."""
    result = QAScanResult("test", total_scanned, issues_found, [], {})
    result_dict = result.to_dict()
    assert result_dict["issue_rate"] == expected_rate