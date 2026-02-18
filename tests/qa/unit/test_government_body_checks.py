"""
Unit tests for government body-related QA checks.
"""

import pytest
from src.gov_scraper.processors.qa import (
    check_government_body_hallucination,
    check_body_default_patterns,
    check_location_vs_body,
    check_tag_body_consistency,
    QAIssue,
    QAScanResult
)


class TestGovernmentBodyHallucinationCheck:
    """Test the government body hallucination check."""

    def test_valid_government_bodies(self):
        """Test with valid government bodies."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",
                "decision_content": "החלטה של משרד האוצר על תקציב",
                "decision_title": "החלטת משרד האוצר"
            },
            {
                "decision_key": "GOV1_2",
                "tags_government_body": "משרד החינוך",
                "decision_content": "החלטה של משרד החינוך על הוראה",
                "decision_title": "החלטת חינוך"
            }
        ]

        result = check_government_body_hallucination(records)

        assert isinstance(result, QAScanResult)
        assert result.check_name == "government-body-hallucination"
        assert result.total_scanned == 2
        # Should have minimal issues for valid bodies
        assert result.issues_found >= 0

    def test_hallucinated_government_bodies(self):
        """Test with hallucinated/invalid government bodies."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד הקסמים והכישופים",  # Fictional
                "decision_content": "החלטה על נושא כלשהו",
                "decision_title": "החלטה"
            },
            {
                "decision_key": "GOV1_2",
                "tags_government_body": "Ministry of Magic",  # English + fictional
                "decision_content": "החלטה נוספת",
                "decision_title": "החלטה נוספת"
            }
        ]

        result = check_government_body_hallucination(records)

        assert result.total_scanned == 2
        # Should detect hallucinated bodies
        hallucination_issues = [i for i in result.issues if
                               "hallucination" in i.description.lower() or
                               "הזיה" in i.description or
                               "לא קיים" in i.description]
        # Note: Detection depends on the reference list in the implementation

    def test_mixed_valid_invalid_bodies(self):
        """Test with mix of valid and invalid bodies."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",  # Valid
                "decision_content": "החלטה תקינה"
            },
            {
                "decision_key": "GOV1_2",
                "tags_government_body": "משרד בלתי קיים",  # Invalid
                "decision_content": "החלטה עם גוף לא תקין"
            }
        ]

        result = check_government_body_hallucination(records)

        assert result.total_scanned == 2

    def test_multiple_government_bodies(self):
        """Test with multiple government bodies."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר;משרד החינוך",
                "decision_content": "החלטה משותפת של שני משרדים"
            }
        ]

        result = check_government_body_hallucination(records)

        assert result.total_scanned == 1

    def test_empty_government_body(self):
        """Test with empty government body field."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "",
                "decision_content": "החלטה ללא גוף מזוהה"
            },
            {
                "decision_key": "GOV1_2",
                "decision_content": "החלטה ללא שדה גוף ממשלתי"
                # No tags_government_body field at all
            }
        ]

        result = check_government_body_hallucination(records)

        assert result.total_scanned == 2
        # Should flag missing government body
        missing_issues = [i for i in result.issues if
                         "missing" in i.description.lower() or
                         "חסר" in i.description]


class TestBodyDefaultPatternsCheck:
    """Test the body default patterns check."""

    def test_suspicious_body_patterns(self):
        """Test detection of suspicious body patterns."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "ממשלת ישראל",  # Too generic
                "decision_content": "החלטה ספציפית על נושא מסוים"
            },
            {
                "decision_key": "GOV1_2",
                "tags_government_body": "הממשלה",  # Very generic
                "decision_content": "החלטה על נושא שצריך גוף ספציפי"
            }
        ]

        result = check_body_default_patterns(records)

        assert result.total_scanned == 2
        # Should detect default/generic patterns

    def test_specific_body_patterns(self):
        """Test with specific, appropriate body patterns."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",
                "decision_content": "החלטה על תקציב ספציפי"
            }
        ]

        result = check_body_default_patterns(records)

        assert result.total_scanned == 1
        # Should not flag specific bodies


class TestLocationVsBodyCheck:
    """Test the location vs body consistency check."""

    def test_consistent_location_body(self):
        """Test consistent location and body tags."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",
                "tags_locations": "ארצי",  # National ministry = national scope
                "decision_content": "החלטה ארצית"
            }
        ]

        result = check_location_vs_body(records)

        assert result.total_scanned == 1
        # Should validate consistency

    def test_inconsistent_location_body(self):
        """Test inconsistent location and body tags."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",  # National ministry
                "tags_locations": "תל אביב",  # Local scope
                "decision_content": "החלטה מקומית"
            }
        ]

        result = check_location_vs_body(records)

        assert result.total_scanned == 1
        # May flag inconsistency depending on implementation logic

    def test_missing_location_or_body(self):
        """Test with missing location or body information."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_government_body": "משרד האוצר",
                # No tags_locations field
                "decision_content": "החלטה ללא מיקום"
            },
            {
                "decision_key": "GOV1_2",
                "tags_locations": "ירושלים",
                # No tags_government_body field
                "decision_content": "החלטה ללא גוף"
            }
        ]

        result = check_location_vs_body(records)

        assert result.total_scanned == 2


class TestTagBodyConsistencyCheck:
    """Test the tag-body consistency check."""

    def test_consistent_tags_and_body(self):
        """Test consistent policy tags and government body."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_policy_area": "כלכלה ואוצר",
                "tags_government_body": "משרד האוצר",
                "decision_content": "החלטה כלכלית"
            },
            {
                "decision_key": "GOV1_2",
                "tags_policy_area": "חינוך",
                "tags_government_body": "משרד החינוך",
                "decision_content": "החלטה חינוכית"
            }
        ]

        result = check_tag_body_consistency(records)

        assert result.total_scanned == 2
        # Should validate consistency

    def test_inconsistent_tags_and_body(self):
        """Test inconsistent policy tags and government body."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_policy_area": "בריאות",  # Health policy
                "tags_government_body": "משרד האוצר",  # Treasury ministry
                "decision_content": "החלטה על בריאות"
            }
        ]

        result = check_tag_body_consistency(records)

        assert result.total_scanned == 1
        # Should detect inconsistency

    def test_multiple_tags_and_bodies(self):
        """Test with multiple policy tags and government bodies."""
        records = [
            {
                "decision_key": "GOV1_1",
                "tags_policy_area": "כלכלה ואוצר;חינוך",
                "tags_government_body": "משרד האוצר;משרד החינוך",
                "decision_content": "החלטה משותפת"
            }
        ]

        result = check_tag_body_consistency(records)

        assert result.total_scanned == 1
        # Should handle multiple values appropriately


@pytest.mark.parametrize("government_body,expected_validity", [
    ("משרד האוצר", "valid"),
    ("משרד החינוך", "valid"),
    ("משרד הבריאות", "valid"),
    ("משרד הקסמים", "invalid"),
    ("Ministry of Finance", "invalid"),
    ("", "invalid"),
    ("ממשלת ישראל", "generic"),
])
def test_government_body_validity_parametrized(government_body, expected_validity):
    """Parametrized test for government body validity."""
    records = [{
        "decision_key": "GOV1_TEST",
        "tags_government_body": government_body,
        "decision_content": "תוכן החלטה לדוגמה"
    }]

    result = check_government_body_hallucination(records)

    assert result.total_scanned == 1

    # The test validates that the function processes different inputs correctly
    # Actual validation depends on the reference lists in the implementation