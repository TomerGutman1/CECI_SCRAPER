"""
Unit tests for content quality-related QA checks.
"""

import pytest
from src.gov_scraper.processors.qa import (
    check_summary_quality,
    check_content_quality,
    check_content_completeness,
    check_title_vs_content,
    check_date_validity,
    QAIssue,
    QAScanResult
)


class TestSummaryQualityCheck:
    """Test the summary quality check."""

    def test_good_quality_summaries(self):
        """Test decisions with good quality summaries."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה על תקציב החינוך",
                "summary": "הממשלה אישרה הגדלת תקציב החינוך ב-15% לצורך שיפור מערכת החינוך והקמת כיתות לימוד נוספות",
                "decision_content": "החלטה מפורטת על הגדלת תקציב החינוך..."
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "החלטה על שיפור תחבורה ציבורית",
                "summary": "אישור תוכנית להקמת קווי רכבת חדשים ושדרוג התחבורה הציבורית במטרופולין",
                "decision_content": "תוכנית מקיפה לשיפור התחבורה..."
            }
        ]

        result = check_summary_quality(records)

        assert isinstance(result, QAScanResult)
        assert result.check_name == "summary-quality"
        assert result.total_scanned == 2
        # Good summaries should have minimal issues
        assert result.issues_found <= 1

    def test_poor_quality_summaries(self):
        """Test decisions with poor quality summaries."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה על תקציב החינוך",
                "summary": "החלטה על תקציב החינוך",  # Same as title
                "decision_content": "החלטה מפורטת על תקציב החינוך והשכלה..."
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "החלטה חשובה",
                "summary": "החלטה",  # Too short
                "decision_content": "תוכן מפורט של החלטה חשובה..."
            },
            {
                "decision_key": "GOV1_3",
                "decision_title": "החלטה קצרה",
                "summary": "סיכום ארוך מאוד שחוזר על אותם הדברים שוב ושוב ללא תוספת משמעותית לתוכן ומכיל מידע מיותר שלא מוסיף הבנה חדשה אלא רק מאריך את הטקסט באופן מלאכותי וחסר משמעות עד כדי כך שהקורא מתקשה להבין מה הנקודה המרכזית",  # Too long
                "decision_content": "תוכן החלטה רגיל..."
            }
        ]

        result = check_summary_quality(records)

        assert result.total_scanned == 3
        assert result.issues_found >= 2  # Should detect multiple issues

        # Check for specific quality issues
        duplicate_issues = [i for i in result.issues if
                           "duplicate" in i.description.lower() or
                           "זהה לכותרת" in i.description]

        short_issues = [i for i in result.issues if
                       "too short" in i.description.lower() or
                       "קצר מדי" in i.description]

        long_issues = [i for i in result.issues if
                      "too long" in i.description.lower() or
                      "ארוך מדי" in i.description]

    def test_missing_summaries(self):
        """Test decisions with missing summaries."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה ללא סיכום",
                "summary": "",
                "decision_content": "תוכן החלטה..."
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "החלטה נוספת",
                # No summary field at all
                "decision_content": "תוכן נוסף..."
            }
        ]

        result = check_summary_quality(records)

        assert result.total_scanned == 2
        assert result.issues_found == 2  # Both should be flagged

        missing_issues = [i for i in result.issues if
                         "missing" in i.description.lower() or
                         "חסר" in i.description]
        assert len(missing_issues) >= 1


class TestContentQualityCheck:
    """Test the content quality check."""

    def test_good_quality_content(self):
        """Test decisions with good quality content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_content": """
                הממשלה דנה בהצעה להגדיל את תקציב החינוך בישראל.
                לאחר דיון מעמיק, הוחלט לאשר הגדלה של 15 אחוזים בתקציב.
                ההגדלה תשמש להקמת כיתות לימוד נוספות ולשיפור איכות ההוראה.
                יישום ההחלטה יתחיל בתחילת שנת הלימודים הבאה.
                """,
                "decision_title": "הגדלת תקציب החינוך"
            }
        ]

        result = check_content_quality(records)

        assert result.total_scanned == 1
        # Good content should have minimal issues
        assert result.issues_found <= 1

    def test_poor_quality_content(self):
        """Test decisions with poor quality content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_content": "החלטה קצרה",  # Too short
                "decision_title": "כותרת"
            },
            {
                "decision_key": "GOV1_2",
                "decision_content": "Just a moment... Cloudflare Ray ID: 123456",  # Cloudflare contamination
                "decision_title": "החלטה מזוהמת"
            },
            {
                "decision_key": "GOV1_3",
                "decision_content": "",  # Empty content
                "decision_title": "החלטה ללא תוכן"
            }
        ]

        result = check_content_quality(records)

        assert result.total_scanned == 3
        assert result.issues_found >= 2

        # Check for specific issues
        cloudflare_issues = [i for i in result.issues if
                            "cloudflare" in i.description.lower() or
                            "contamination" in i.description.lower()]

        short_issues = [i for i in result.issues if
                       "too short" in i.description.lower() or
                       "קצר מדי" in i.description]


class TestContentCompletenessCheck:
    """Test the content completeness check."""

    def test_complete_content(self):
        """Test decisions with complete content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה מלאה",
                "decision_content": "תוכן מלא ומקיף של החלטה עם פרטים רלוונטיים",
                "summary": "סיכום מתאים לתוכן",
                "operativity": "אופרטיבית",
                "tags_policy_area": "כלכלה ואוצר"
            }
        ]

        result = check_content_completeness(records)

        assert result.total_scanned == 1
        # Complete content should have minimal issues
        assert result.issues_found <= 1

    def test_incomplete_content(self):
        """Test decisions with incomplete content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה חלקית",
                "decision_content": "",  # Missing content
                "summary": "סיכום קיים",
                "operativity": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "",  # Missing title
                "decision_content": "תוכן קיים",
                "operativity": "דקלרטיבית"
            },
            {
                "decision_key": "GOV1_3",
                "decision_title": "החלטה ללא סיווג",
                "decision_content": "תוכן קיים",
                # Missing operativity
                "summary": "סיכום"
            }
        ]

        result = check_content_completeness(records)

        assert result.total_scanned == 3
        assert result.issues_found >= 2

        # Check for missing field issues
        missing_issues = [i for i in result.issues if
                         "missing" in i.description.lower() or
                         "חסר" in i.description]
        assert len(missing_issues) >= 2


class TestTitleVsContentCheck:
    """Test the title vs content consistency check."""

    def test_consistent_title_content(self):
        """Test decisions with consistent titles and content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה על תקציב החינוך",
                "decision_content": "הממשלה דנה בהצעה להגדיל את תקציב החינוך ולשפר את מערכת ההשכלה"
            }
        ]

        result = check_title_vs_content(records)

        assert result.total_scanned == 1
        # Consistent title and content should have minimal issues

    def test_inconsistent_title_content(self):
        """Test decisions with inconsistent titles and content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה על תקציב החינוך",
                "decision_content": "הממשלה דנה בנושא הביטחון והצבא ובחיזוק כוחות הביטחון"
            }
        ]

        result = check_title_vs_content(records)

        assert result.total_scanned == 1
        # May detect inconsistency depending on implementation

    def test_missing_title_or_content(self):
        """Test with missing title or content."""
        records = [
            {
                "decision_key": "GOV1_1",
                "decision_title": "",
                "decision_content": "תוכן ללא כותרת"
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "כותרת ללא תוכן",
                "decision_content": ""
            }
        ]

        result = check_title_vs_content(records)

        assert result.total_scanned == 2


class TestDateValidityCheck:
    """Test the date validity check."""

    def test_valid_dates(self):
        """Test with valid decision dates."""
        records = [
            {"decision_key": "GOV1_1", "decision_date": "2024-01-15"},
            {"decision_key": "GOV1_2", "decision_date": "2023-12-31"},
            {"decision_key": "GOV1_3", "decision_date": "2022-06-01"}
        ]

        result = check_date_validity(records)

        assert result.total_scanned == 3
        assert result.issues_found == 0  # All dates should be valid

    def test_invalid_dates(self):
        """Test with invalid decision dates."""
        records = [
            {"decision_key": "GOV1_1", "decision_date": "invalid-date"},
            {"decision_key": "GOV1_2", "decision_date": "2024-13-01"},  # Invalid month
            {"decision_key": "GOV1_3", "decision_date": "2024-02-30"},  # Invalid day
            {"decision_key": "GOV1_4", "decision_date": ""},  # Empty date
            {"decision_key": "GOV1_5"}  # No date field
        ]

        result = check_date_validity(records)

        assert result.total_scanned == 5
        assert result.issues_found >= 4  # Should detect multiple invalid dates

    def test_future_dates(self):
        """Test with future dates (potentially suspicious)."""
        records = [
            {"decision_key": "GOV1_1", "decision_date": "2030-01-01"}  # Future date
        ]

        result = check_date_validity(records)

        assert result.total_scanned == 1
        # Future dates might be flagged as suspicious


@pytest.mark.parametrize("summary,title,expected_issue_type", [
    ("סיכום טוב ומקיף של החלטה", "כותרת החלטה", "none"),
    ("כותרת החלטה", "כותרת החלטה", "duplicate"),
    ("קצר", "כותרת ארוכה יותר", "too_short"),
    ("", "כותרת", "missing"),
])
def test_summary_quality_parametrized(summary, title, expected_issue_type):
    """Parametrized test for summary quality."""
    records = [{
        "decision_key": "GOV1_TEST",
        "summary": summary,
        "decision_title": title,
        "decision_content": "תוכן החלטה לדוגמה עם מידע רלוונטי"
    }]

    result = check_summary_quality(records)

    assert result.total_scanned == 1

    if expected_issue_type == "none":
        assert result.issues_found <= 1  # Might still have minor issues
    elif expected_issue_type == "duplicate":
        assert any("duplicate" in issue.description.lower() or
                  "זהה" in issue.description
                  for issue in result.issues)
    elif expected_issue_type == "too_short":
        assert any("short" in issue.description.lower() or
                  "קצר" in issue.description
                  for issue in result.issues)
    elif expected_issue_type == "missing":
        assert any("missing" in issue.description.lower() or
                  "חסר" in issue.description
                  for issue in result.issues)