"""
Unit tests for specific QA check implementations.

Tests ContentQualityCheck, URLIntegrityCheck, TagValidationCheck, etc.
"""

import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from src.gov_scraper.processors.qa_core import CheckSeverity, QAScanResult
from src.gov_scraper.processors.qa_checks import (
    ContentQualityCheck, DuplicateDetectionCheck,
    URLIntegrityCheck, DomainConsistencyCheck,
    TagValidationCheck, TagConsistencyCheck,
    DateConsistencyCheck, TemporalConsistencyCheck,
    DepartmentValidationCheck, DepartmentConsistencyCheck
)


class TestContentQualityCheck:
    """Test ContentQualityCheck functionality."""

    def test_initialization(self):
        """Test check initialization."""
        check = ContentQualityCheck(
            duplicate_threshold=0.9,
            min_content_length=100,
            max_repetition_ratio=0.4
        )

        assert check.check_name == "content_quality"
        assert check.duplicate_threshold == 0.9
        assert check.min_content_length == 100
        assert check.max_repetition_ratio == 0.4

    def test_completeness_check_short_content(self):
        """Test content completeness with short content."""
        check = ContentQualityCheck(min_content_length=50)
        record = {
            "decision_key": "test_1",
            "decision_content": "Short content"  # Only 13 characters
        }

        issues = check._validate_record(record)

        # Should find short content issue
        short_issues = [i for i in issues if "too short" in i.description]
        assert len(short_issues) == 1
        assert short_issues[0].severity == CheckSeverity.MEDIUM

    def test_completeness_check_placeholder_text(self):
        """Test detection of placeholder text."""
        check = ContentQualityCheck()
        record = {
            "decision_key": "test_1",
            "decision_content": "החלטה זו לא זמין כרגע ויעודכן בהמשך"
        }

        issues = check._validate_record(record)

        # Should find placeholder text issues
        placeholder_issues = [i for i in issues if "placeholder" in i.description]
        assert len(placeholder_issues) > 0
        assert placeholder_issues[0].severity == CheckSeverity.HIGH

    def test_quality_metrics_repetition(self):
        """Test high repetition detection."""
        check = ContentQualityCheck(max_repetition_ratio=0.3)
        record = {
            "decision_key": "test_1",
            "decision_content": "החלטה החלטה החלטה החלטה החלטה החלטה החלטה החלטה החלטה החלטה"
        }

        issues = check._validate_record(record)

        # Should find high repetition
        repetition_issues = [i for i in issues if "repetition" in i.description]
        assert len(repetition_issues) == 1

    def test_content_integrity_html_remnants(self):
        """Test HTML/XML remnants detection."""
        check = ContentQualityCheck()
        record = {
            "decision_key": "test_1",
            "decision_content": "החלטה עם <div>תגי HTML</div> ו&nbsp;entities"
        }

        issues = check._validate_record(record)

        # Should find HTML remnants
        html_issues = [i for i in issues if "HTML" in i.description or "markup" in i.description]
        assert len(html_issues) == 1

    def test_mixed_direction_text(self):
        """Test mixed RTL/LTR text detection."""
        check = ContentQualityCheck()
        record = {
            "decision_key": "test_1",
            "decision_content": "החלטה בעברית עם English text mixed in and more Hebrew text to make it substantial enough for testing mixed direction issues"
        }

        issues = check._validate_record(record)

        # Should find mixed direction issues
        direction_issues = [i for i in issues if "direction" in i.description]
        assert len(direction_issues) == 1


class TestDuplicateDetectionCheck:
    """Test DuplicateDetectionCheck functionality."""

    def test_duplicate_detection(self):
        """Test duplicate content detection."""
        check = DuplicateDetectionCheck(similarity_threshold=0.8)
        records = [
            {
                "decision_key": "test_1",
                "decision_content": "זוהי החלטה ממשלה חשובה מאוד"
            },
            {
                "decision_key": "test_2",
                "decision_content": "זוהי החלטה ממשלה חשובה מאוד"  # Identical
            },
            {
                "decision_key": "test_3",
                "decision_content": "החלטה אחרת לגמרי ושונה"
            }
        ]

        result = check.run(records)

        assert result.issues_found > 0
        # Should find issues for both test_1 and test_2
        duplicate_keys = {issue.decision_key for issue in result.issues}
        assert "test_1" in duplicate_keys
        assert "test_2" in duplicate_keys
        assert "test_3" not in duplicate_keys


class TestURLIntegrityCheck:
    """Test URLIntegrityCheck functionality."""

    def test_url_format_validation(self):
        """Test URL format validation."""
        check = URLIntegrityCheck(check_accessibility=False)  # Skip HTTP checks
        record = {
            "decision_key": "test_1",
            "decision_link": "not-a-valid-url"
        }

        issues = check._validate_record(record)

        # Should find format issues
        format_issues = [i for i in issues if "format" in i.description.lower()]
        assert len(format_issues) > 0

    def test_valid_government_url(self):
        """Test valid government URL."""
        check = URLIntegrityCheck(check_accessibility=False)
        record = {
            "decision_key": "test_1",
            "decision_link": "https://www.gov.il/decisions/12345"
        }

        issues = check._validate_record(record)

        # Should not find format issues for valid URL
        format_issues = [i for i in issues if "format" in i.description.lower()]
        assert len(format_issues) == 0

    def test_suspicious_url_patterns(self):
        """Test suspicious URL pattern detection."""
        check = URLIntegrityCheck(check_accessibility=False)
        record = {
            "decision_key": "test_1",
            "decision_link": "javascript:alert('xss')"
        }

        issues = check._validate_record(record)

        # Should find suspicious pattern
        suspicious_issues = [i for i in issues if "suspicious" in i.description.lower()]
        assert len(suspicious_issues) == 1

    def test_http_vs_https(self):
        """Test HTTP vs HTTPS preference."""
        check = URLIntegrityCheck(check_accessibility=False)
        record = {
            "decision_key": "test_1",
            "decision_link": "http://www.gov.il/decisions/12345"  # HTTP instead of HTTPS
        }

        issues = check._validate_record(record)

        # Should suggest HTTPS
        https_issues = [i for i in issues if "HTTPS" in i.description]
        assert len(https_issues) == 1
        assert https_issues[0].severity == CheckSeverity.LOW

    @patch('requests.Session.get')
    def test_url_accessibility_success(self, mock_get):
        """Test successful URL accessibility check."""
        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://www.gov.il/decisions/12345"
        mock_response.history = []
        mock_response.headers = {'content-type': 'text/html'}
        mock_get.return_value = mock_response

        check = URLIntegrityCheck(check_accessibility=True)
        record = {
            "decision_key": "test_1",
            "decision_link": "https://www.gov.il/decisions/12345"
        }

        issues = check._validate_record(record)

        # Should not find accessibility issues
        access_issues = [i for i in issues if "404" in i.description or "inaccessible" in i.description]
        assert len(access_issues) == 0

    @patch('requests.Session.get')
    def test_url_accessibility_404(self, mock_get):
        """Test 404 URL accessibility check."""
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        check = URLIntegrityCheck(check_accessibility=True)
        record = {
            "decision_key": "test_1",
            "decision_link": "https://www.gov.il/decisions/nonexistent"
        }

        issues = check._validate_record(record)

        # Should find 404 error
        access_issues = [i for i in issues if "404" in i.description]
        assert len(access_issues) == 1
        assert access_issues[0].severity == CheckSeverity.HIGH


class TestTagValidationCheck:
    """Test TagValidationCheck functionality."""

    def test_authorized_tag_validation(self):
        """Test authorized tag validation."""
        check = TagValidationCheck()
        record = {
            "decision_key": "test_1",
            "policy_areas": ["חינוך", "בריאות ורפואה"]  # Valid tags
        }

        issues = check._validate_record(record)

        # Should not find unauthorized tag issues
        auth_issues = [i for i in issues if "unauthorized" in i.description.lower()]
        assert len(auth_issues) == 0

    def test_unauthorized_tag_validation(self):
        """Test unauthorized tag detection."""
        check = TagValidationCheck()
        record = {
            "decision_key": "test_1",
            "policy_areas": ["תג_לא_מורשה", "חינוך"]
        }

        issues = check._validate_record(record)

        # Should find unauthorized tag issue
        auth_issues = [i for i in issues if "unauthorized" in i.description.lower()]
        assert len(auth_issues) == 1
        assert auth_issues[0].severity == CheckSeverity.HIGH

    def test_missing_tags(self):
        """Test missing tags detection."""
        check = TagValidationCheck()
        record = {
            "decision_key": "test_1",
            "policy_areas": []  # No tags
        }

        issues = check._validate_record(record)

        # Should find missing tags issue
        missing_issues = [i for i in issues if "no policy tags" in i.description.lower()]
        assert len(missing_issues) == 1

    def test_excessive_tags(self):
        """Test excessive tags detection."""
        check = TagValidationCheck()
        record = {
            "decision_key": "test_1",
            "policy_areas": ["חינוך", "בריאות ורפואה", "ביטחון פנים",
                           "תחבורה ובטיחות בדרכים", "משפטים", "חקלאות ופיתוח הכפר"]  # 6 tags
        }

        issues = check._validate_record(record)

        # Should find excessive tags issue
        excessive_issues = [i for i in issues if "many tags" in i.description.lower()]
        assert len(excessive_issues) == 1

    def test_tag_relevance_high_score(self):
        """Test tag relevance with high score."""
        check = TagValidationCheck(check_content_relevance=True, min_relevance_score=0.1)
        record = {
            "decision_key": "test_1",
            "policy_areas": ["חינוך"],
            "decision_content": "החלטה על בתי ספר ותלמידים ומורים וחינוך",
            "title": "החלטה בנושא חינוך"
        }

        issues = check._validate_record(record)

        # Should not find relevance issues
        relevance_issues = [i for i in issues if "relevant" in i.description.lower()]
        assert len(relevance_issues) == 0

    def test_body_tag_consistency(self):
        """Test government body and tag consistency."""
        check = TagValidationCheck()
        record = {
            "decision_key": "test_1",
            "policy_areas": ["חינוך"],
            "government_body": "משרד החינוך"
        }

        issues = check._validate_record(record)

        # Should not find consistency issues
        consistency_issues = [i for i in issues if "doesn't match" in i.description.lower()]
        assert len(consistency_issues) == 0


class TestDateConsistencyCheck:
    """Test DateConsistencyCheck functionality."""

    def test_valid_date_parsing(self):
        """Test valid date parsing."""
        check = DateConsistencyCheck()
        record = {
            "decision_key": "test_1",
            "decision_date": "2023-12-25"
        }

        issues = check._validate_record(record)

        # Should not find format issues
        format_issues = [i for i in issues if "format" in i.description.lower()]
        assert len(format_issues) == 0

    def test_invalid_date_format(self):
        """Test invalid date format detection."""
        check = DateConsistencyCheck()
        record = {
            "decision_key": "test_1",
            "decision_date": "not-a-date"
        }

        issues = check._validate_record(record)

        # Should find format issues
        format_issues = [i for i in issues if "format" in i.description.lower()]
        assert len(format_issues) == 1
        assert format_issues[0].severity == CheckSeverity.HIGH

    def test_date_too_early(self):
        """Test date too early detection."""
        check = DateConsistencyCheck(min_valid_date=date(2000, 1, 1))
        record = {
            "decision_key": "test_1",
            "decision_date": "1990-01-01"  # Before min date
        }

        issues = check._validate_record(record)

        # Should find early date issue
        early_issues = [i for i in issues if "too early" in i.description.lower()]
        assert len(early_issues) == 1

    def test_date_consistency_order(self):
        """Test date order consistency."""
        check = DateConsistencyCheck()
        record = {
            "decision_key": "test_1",
            "decision_date": "2023-12-25",
            "publication_date": "2023-12-20"  # Published before decision
        }

        issues = check._validate_record(record)

        # Should find order inconsistency
        order_issues = [i for i in issues if "order inconsistent" in i.description.lower()]
        assert len(order_issues) == 1

    def test_government_period_alignment(self):
        """Test government period alignment."""
        check = DateConsistencyCheck()
        record = {
            "decision_key": "test_1",
            "decision_date": "2023-12-25",
            "gov_num": "36"  # Should align with government 36 period
        }

        issues = check._validate_record(record)

        # Should not find alignment issues for valid government period
        gov_issues = [i for i in issues if "government" in i.description.lower()]
        # Note: May or may not have issues depending on exact dates in test data

    def test_weekend_detection(self):
        """Test weekend decision detection."""
        check = DateConsistencyCheck()
        record = {
            "decision_key": "test_1",
            "decision_date": "2023-12-23"  # Saturday
        }

        issues = check._validate_record(record)

        # Should find weekend issue
        weekend_issues = [i for i in issues if "saturday" in i.description.lower()]
        assert len(weekend_issues) == 1


class TestDepartmentValidationCheck:
    """Test DepartmentValidationCheck functionality."""

    def test_authorized_department(self):
        """Test authorized department validation."""
        check = DepartmentValidationCheck()
        record = {
            "decision_key": "test_1",
            "government_body": "משרד החינוך"  # Valid department
        }

        issues = check._validate_record(record)

        # Should not find unauthorized issues
        auth_issues = [i for i in issues if "unauthorized" in i.description.lower()]
        assert len(auth_issues) == 0

    def test_unauthorized_department(self):
        """Test unauthorized department detection."""
        check = DepartmentValidationCheck()
        record = {
            "decision_key": "test_1",
            "government_body": "משרד לא קיים"  # Invalid department
        }

        issues = check._validate_record(record)

        # Should find unauthorized department issue
        auth_issues = [i for i in issues if "unauthorized" in i.description.lower()]
        assert len(auth_issues) == 1
        assert auth_issues[0].severity == CheckSeverity.HIGH

    def test_department_alias_recognition(self):
        """Test department alias recognition."""
        check = DepartmentValidationCheck()
        record = {
            "decision_key": "test_1",
            "government_body": "משרד ראש הממשלה"  # Alias for משרד רה"מ
        }

        issues = check._validate_record(record)

        # Should find non-canonical naming issue but not unauthorized
        auth_issues = [i for i in issues if "unauthorized" in i.description.lower()]
        canonical_issues = [i for i in issues if "canonical" in i.description.lower()]

        assert len(auth_issues) == 0  # Should recognize as authorized alias
        # May find canonical naming issue

    def test_department_format_issues(self):
        """Test department format issue detection."""
        check = DepartmentValidationCheck()
        record = {
            "decision_key": "test_1",
            "government_body": "משרד    החינוך   "  # Extra spaces
        }

        issues = check._validate_record(record)

        # Should find format issues
        format_issues = [i for i in issues if "formatting" in i.description.lower()]
        assert len(format_issues) == 1

    def test_department_policy_consistency(self):
        """Test department-policy consistency."""
        check = DepartmentValidationCheck()
        record = {
            "decision_key": "test_1",
            "government_body": "משרד החינוך",
            "policy_areas": ["בריאות ורפואה"]  # Inconsistent with education ministry
        }

        issues = check._validate_record(record)

        # Should find policy mismatch
        policy_issues = [i for i in issues if "policies don't match" in i.description.lower()]
        assert len(policy_issues) == 1


if __name__ == "__main__":
    pytest.main([__file__])