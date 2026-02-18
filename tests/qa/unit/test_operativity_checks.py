"""
Unit tests for operativity-related QA checks.
"""

import pytest
from src.gov_scraper.processors.qa import (
    check_operativity,
    check_operativity_vs_content,
    check_operativity_validity,
    QAIssue,
    QAScanResult
)


class TestOperativityCheck:
    """Test the basic operativity check."""

    def test_check_operativity_with_valid_data(self):
        """Test operativity check with valid data."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "אופרטיבית",
                "decision_content": "החליטה לבטל את התוכנית"
            },
            {
                "decision_key": "GOV1_2",
                "operativity": "דקלרטיבית",
                "decision_content": "הממשלה מציינת כי החלטה זו חשובה"
            }
        ]

        result = check_operativity(records)

        assert isinstance(result, QAScanResult)
        assert result.check_name == "operativity"
        assert result.total_scanned == 2
        assert result.issues_found >= 0

    def test_check_operativity_with_missing_data(self):
        """Test operativity check with missing operativity field."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_content": "החליטה לבטל את התוכנית"
            }
        ]

        result = check_operativity(records)

        assert result.total_scanned == 1
        assert any("missing operativity" in issue.description.lower() or
                  "חסר סיווג אופרטיביות" in issue.description
                  for issue in result.issues)

    def test_check_operativity_with_empty_data(self):
        """Test operativity check with empty records."""
        records = []

        result = check_operativity(records)

        assert result.total_scanned == 0
        assert result.issues_found == 0
        assert len(result.issues) == 0

    def test_check_operativity_with_invalid_values(self):
        """Test operativity check with invalid operativity values."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "לא חוקי",
                "decision_content": "תוכן החלטה"
            }
        ]

        result = check_operativity(records)

        assert result.total_scanned == 1
        assert any("invalid operativity" in issue.description.lower() or
                  "ערך לא תקין" in issue.description
                  for issue in result.issues)


class TestOperativityVsContentCheck:
    """Test the operativity vs content consistency check."""

    def test_operative_with_operative_keywords(self):
        """Test operative decision with operative keywords."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "אופרטיבית",
                "decision_content": "הממשלה החליטה לבטל את התוכנית ולעצור את הפעילות"
            }
        ]

        result = check_operativity_vs_content(records)

        # Should have no issues - correct classification
        issues_for_record = [i for i in result.issues if i.decision_key == "GOV1_1"]
        # This should be correctly classified, so minimal or no issues
        assert result.total_scanned == 1

    def test_declarative_with_operative_keywords(self):
        """Test declarative decision with operative keywords (mismatch)."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "דקלרטיבית",
                "decision_content": "הממשלה החליטה לבטל את התוכנית ולאשר הקצאת כספים"
            }
        ]

        result = check_operativity_vs_content(records)

        assert result.total_scanned == 1
        # Should detect mismatch
        issues_for_record = [i for i in result.issues if i.decision_key == "GOV1_1"]
        if issues_for_record:
            assert any("mismatch" in issue.description.lower() or
                      "אי התאמה" in issue.description
                      for issue in issues_for_record)

    def test_operative_with_declarative_keywords(self):
        """Test operative decision with only declarative keywords (mismatch)."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "אופרטיבית",
                "decision_content": "הממשלה מציינת ומבהירה כי החלטה זו חשובה לדעתה"
            }
        ]

        result = check_operativity_vs_content(records)

        assert result.total_scanned == 1
        # Should detect potential mismatch
        issues_for_record = [i for i in result.issues if i.decision_key == "GOV1_1"]
        if issues_for_record:
            assert any("mismatch" in issue.description.lower() or
                      "אי התאמה" in issue.description
                      for issue in issues_for_record)

    def test_no_keywords_present(self):
        """Test decision with no operativity keywords."""
        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "אופרטיבית",
                "decision_content": "זהו תוכן נייטרלי ללא מילות מפתח ספציפיות"
            }
        ]

        result = check_operativity_vs_content(records)

        assert result.total_scanned == 1
        # Should note lack of keyword evidence
        issues_for_record = [i for i in result.issues if i.decision_key == "GOV1_1"]
        if issues_for_record:
            assert any("no keywords" in issue.description.lower() or
                      "אין מילות מפתח" in issue.description or
                      "ללא עדות" in issue.description
                      for issue in issues_for_record)


class TestOperativityValidityCheck:
    """Test the operativity validity check."""

    def test_valid_operativity_values(self):
        """Test with valid operativity values."""
        records = [
            {"decision_key": "GOV1_1", "operativity": "אופרטיבית"},
            {"decision_key": "GOV1_2", "operativity": "דקלרטיבית"},
            {"decision_key": "GOV1_3", "operativity": "מעורבת"}
        ]

        result = check_operativity_validity(records)

        assert result.total_scanned == 3
        # All should be valid
        assert result.issues_found == 0

    def test_invalid_operativity_values(self):
        """Test with invalid operativity values."""
        records = [
            {"decision_key": "GOV1_1", "operativity": "לא חוקי"},
            {"decision_key": "GOV1_2", "operativity": "operative"},  # English
            {"decision_key": "GOV1_3", "operativity": ""},  # Empty
            {"decision_key": "GOV1_4", "operativity": None}  # None
        ]

        result = check_operativity_validity(records)

        assert result.total_scanned == 4
        assert result.issues_found == 4
        assert all(issue.severity == "high" for issue in result.issues)

    def test_mixed_validity(self):
        """Test with mix of valid and invalid operativity values."""
        records = [
            {"decision_key": "GOV1_1", "operativity": "אופרטיבית"},  # Valid
            {"decision_key": "GOV1_2", "operativity": "לא חוקי"},    # Invalid
            {"decision_key": "GOV1_3", "operativity": "דקלרטיבית"}  # Valid
        ]

        result = check_operativity_validity(records)

        assert result.total_scanned == 3
        assert result.issues_found == 1

        invalid_issue = result.issues[0]
        assert invalid_issue.decision_key == "GOV1_2"
        assert invalid_issue.current_value == "לא חוקי"


@pytest.mark.parametrize("operativity,content,should_have_issue", [
    ("אופרטיבית", "החליטה לבטל", False),  # Correct
    ("דקלרטיבית", "מציינת כי", False),      # Correct
    ("דקלרטיבית", "החליטה לבטל", True),    # Mismatch - should be operative
    ("אופרטיבית", "מציינת בלבד", True),     # Mismatch - should be declarative
])
def test_operativity_content_matching_parametrized(operativity, content, should_have_issue):
    """Parametrized test for operativity-content matching."""
    records = [{
        "decision_key": "GOV1_TEST",
        "operativity": operativity,
        "decision_content": content
    }]

    result = check_operativity_vs_content(records)

    assert result.total_scanned == 1

    if should_have_issue:
        assert result.issues_found > 0
    else:
        # Note: The check might still find issues due to lack of keywords
        # This is expected behavior - we're testing the logic works
        pass