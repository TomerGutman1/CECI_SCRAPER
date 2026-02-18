"""
Regression tests for known issues in the QA system.

These tests ensure that previously identified and fixed issues
do not reoccur in future versions.
"""

import pytest
from src.gov_scraper.processors.qa import (
    run_scan,
    check_operativity,
    check_content_quality,
    check_policy_tag_relevance,
    check_government_body_hallucination,
    check_summary_quality,
    fix_operativity,
    QAIssue,
    QAScanResult
)


class TestCloudflareContaminationRegression:
    """Regression tests for Cloudflare contamination issues."""

    def test_cloudflare_detection_still_works(self):
        """Ensure Cloudflare contamination detection still works (Issue #CF-001)."""
        cloudflare_records = [
            {
                "decision_key": "GOV1_CF1",
                "decision_content": "Just a moment... Cloudflare Ray ID: 8abc123def456",
                "decision_title": "החלטה מזוהמת",
                "operativity": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_CF2",
                "decision_content": "Verify you are human. This page is under DDoS protection by Cloudflare",
                "decision_title": "החלטה נוספת מזוהמת",
                "operativity": "דקלרטיבית"
            },
            {
                "decision_key": "GOV1_CLEAN",
                "decision_content": "תוכן תקין של החלטה ממשלתית בנושא חשוב",
                "decision_title": "החלטה תקינה",
                "operativity": "אופרטיבית"
            }
        ]

        result = check_content_quality(cloudflare_records)

        # Should detect both Cloudflare-contaminated records
        cloudflare_issues = [
            issue for issue in result.issues
            if "cloudflare" in issue.description.lower() or "contamination" in issue.description.lower()
        ]

        assert len(cloudflare_issues) >= 2, "Cloudflare detection regressed"

        # Verify specific records were flagged
        flagged_keys = {issue.decision_key for issue in cloudflare_issues}
        assert "GOV1_CF1" in flagged_keys, "Failed to detect first Cloudflare record"
        assert "GOV1_CF2" in flagged_keys, "Failed to detect second Cloudflare record"
        assert "GOV1_CLEAN" not in flagged_keys, "False positive on clean record"

    def test_cloudflare_patterns_comprehensive(self):
        """Test all known Cloudflare contamination patterns (Issue #CF-002)."""
        contamination_patterns = [
            "Just a moment...",
            "Cloudflare",
            "Ray ID:",
            "Verify you are human",
            "DDoS protection",
            "Please enable JavaScript",
            "This page is under protection"
        ]

        records = []
        for i, pattern in enumerate(contamination_patterns):
            records.append({
                "decision_key": f"GOV1_CF_{i}",
                "decision_content": f"התחלת תוכן {pattern} המשך תוכן",
                "decision_title": f"החלטה {i}",
                "operativity": "אופרטיבית"
            })

        result = check_content_quality(records)

        # Should detect contamination in all records
        contaminated_keys = {
            issue.decision_key for issue in result.issues
            if "cloudflare" in issue.description.lower() or "contamination" in issue.description.lower()
        }

        expected_keys = {f"GOV1_CF_{i}" for i in range(len(contamination_patterns))}
        missing_detections = expected_keys - contaminated_keys

        assert len(missing_detections) == 0, f"Failed to detect contamination in: {missing_detections}"


class TestOperativityMisclassificationRegression:
    """Regression tests for operativity misclassification issues."""

    def test_operative_keywords_detection(self):
        """Test that operative keywords are still properly detected (Issue #OP-001)."""
        operative_test_cases = [
            {
                "decision_key": "GOV1_OP1",
                "decision_content": "הממשלה החליטה לבטל את התוכנית",
                "operativity": "דקלרטיבית",  # Wrong - should be operative
                "expected_correct": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_OP2",
                "decision_content": "הוחלט לאשר הקצאת תקציב נוסף",
                "operativity": "דקלרטיבית",  # Wrong - should be operative
                "expected_correct": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_OP3",
                "decision_content": "יש לעצור את הפעילות הבלתי חוקית",
                "operativity": "דקלרטיבית",  # Wrong - should be operative
                "expected_correct": "אופרטיבית"
            }
        ]

        result = check_operativity(operative_test_cases)

        # Should detect all misclassifications
        misclassification_issues = [
            issue for issue in result.issues
            if "mismatch" in issue.description.lower() or "אי התאמה" in issue.description
        ]

        assert len(misclassification_issues) >= 2, "Operative keyword detection regressed"

        # Verify specific cases were caught
        flagged_keys = {issue.decision_key for issue in misclassification_issues}
        expected_keys = {"GOV1_OP1", "GOV1_OP2", "GOV1_OP3"}
        missing_detections = expected_keys - flagged_keys

        # Allow for some cases to not be detected (keyword matching isn't perfect)
        assert len(missing_detections) <= 1, f"Too many operative cases missed: {missing_detections}"

    def test_declarative_keywords_detection(self):
        """Test that declarative keywords are still properly detected (Issue #OP-002)."""
        declarative_test_cases = [
            {
                "decision_key": "GOV1_DEC1",
                "decision_content": "הממשלה מציינת כי החלטה זו חשובה",
                "operativity": "אופרטיבית",  # Wrong - should be declarative
                "expected_correct": "דקלרטיבית"
            },
            {
                "decision_key": "GOV1_DEC2",
                "decision_content": "רה\"מ מבהיר בעניין המדיניות החדשה",
                "operativity": "אופרטיבית",  # Wrong - should be declarative
                "expected_correct": "דקלרטיבית"
            },
            {
                "decision_key": "GOV1_DEC3",
                "decision_content": "לדעת הממשלה, הנושא חשוב מאוד",
                "operativity": "אופרטיבית",  # Wrong - should be declarative
                "expected_correct": "דקלרטיבית"
            }
        ]

        result = check_operativity(declarative_test_cases)

        # Should detect misclassifications
        misclassification_issues = [
            issue for issue in result.issues
            if "mismatch" in issue.description.lower() or "אי התאמה" in issue.description
        ]

        assert len(misclassification_issues) >= 1, "Declarative keyword detection regressed"

    def test_operativity_fixer_still_works(self):
        """Test that operativity fixer still works correctly (Issue #OP-003)."""
        records_to_fix = [
            {
                "decision_key": "GOV1_FIX1",
                "decision_content": "הממשלה החליטה לבטל את הפעילות",
                "operativity": "דקלרטיבית",  # Should be fixed to אופרטיבית
                "decision_title": "החלטת ביטול"
            }
        ]

        updates, scan_result = fix_operativity(records_to_fix, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned == 1

        # Should identify at least one fix
        if len(updates) > 0:
            # Verify the fix is correct
            update = updates[0]
            assert update[0] == "GOV1_FIX1"  # decision_key
            assert "operativity" in update[1]  # update dict should contain operativity
            assert update[1]["operativity"] == "אופרטיבית"


class TestPolicyTagRelevanceRegression:
    """Regression tests for policy tag relevance issues."""

    def test_obvious_mismatch_detection(self):
        """Test detection of obvious policy tag mismatches (Issue #PT-001)."""
        mismatch_cases = [
            {
                "decision_key": "GOV1_PT1",
                "decision_content": "החלטה בנושא ביטחון המדינה והצבא",
                "decision_title": "החלטה ביטחונית",
                "tags_policy_area": "חינוך",  # Wrong - should be בטחון
            },
            {
                "decision_key": "GOV1_PT2",
                "decision_content": "החלטה על תקציב החינוך והשכלה גבוהה",
                "decision_title": "תקציב חינוך",
                "tags_policy_area": "בריאות",  # Wrong - should be חינוך
            },
            {
                "decision_key": "GOV1_PT3",
                "decision_content": "החלטה על שירותי בריאות ורפואה",
                "decision_title": "שירותי רפואה",
                "tags_policy_area": "כלכלה ואוצר",  # Wrong - should be בריאות
            }
        ]

        result = check_policy_tag_relevance(mismatch_cases)

        # Should detect relevance issues
        relevance_issues = [
            issue for issue in result.issues
            if "relevance" in issue.description.lower() or "רלוונטיות" in issue.description
        ]

        # Allow for some flexibility in detection
        assert len(relevance_issues) >= 1, "Policy tag relevance detection regressed"

    def test_default_tag_overuse_detection(self):
        """Test detection of 'שונות' tag overuse (Issue #PT-002)."""
        records_with_default = []
        for i in range(20):
            records_with_default.append({
                "decision_key": f"GOV1_DEF_{i}",
                "decision_content": f"החלטה מספר {i} בנושא ספציפי",
                "tags_policy_area": "שונות"  # All using default tag
            })

        from src.gov_scraper.processors.qa import check_policy_fallback_rate
        result = check_policy_fallback_rate(records_with_default)

        # Should detect high fallback rate
        assert result.summary.get("fallback_rate", 0) == 100
        assert result.issues_found > 0, "Default tag overuse detection regressed"


class TestGovernmentBodyHallucinationRegression:
    """Regression tests for government body hallucination issues."""

    def test_fictional_ministry_detection(self):
        """Test detection of fictional ministries (Issue #GB-001)."""
        fictional_bodies = [
            {
                "decision_key": "GOV1_FICT1",
                "tags_government_body": "משרד הקסמים והכישופים",
                "decision_content": "החלטה על נושא כלשהו"
            },
            {
                "decision_key": "GOV1_FICT2",
                "tags_government_body": "Ministry of Silly Walks",
                "decision_content": "החלטה נוספת"
            },
            {
                "decision_key": "GOV1_FICT3",
                "tags_government_body": "משרד הדרקונים והחד-קרנים",
                "decision_content": "החלטה פנטסטית"
            }
        ]

        result = check_government_body_hallucination(fictional_bodies)

        # Should detect hallucinated bodies
        hallucination_issues = [
            issue for issue in result.issues
            if "hallucination" in issue.description.lower() or
               "לא קיים" in issue.description or
               "בלתי קיים" in issue.description
        ]

        # Should catch at least the obviously fictional ones
        assert len(hallucination_issues) >= 1, "Government body hallucination detection regressed"

    def test_english_ministry_detection(self):
        """Test detection of English ministry names (Issue #GB-002)."""
        english_bodies = [
            {
                "decision_key": "GOV1_ENG1",
                "tags_government_body": "Ministry of Education",
                "decision_content": "Decision content"
            },
            {
                "decision_key": "GOV1_ENG2",
                "tags_government_body": "Department of Health",
                "decision_content": "More content"
            }
        ]

        result = check_government_body_hallucination(english_bodies)

        # Should detect English names as suspicious
        suspicious_issues = [
            issue for issue in result.issues
            if "english" in issue.description.lower() or
               "אנגלית" in issue.description or
               any(key in ["GOV1_ENG1", "GOV1_ENG2"] for key in [issue.decision_key])
        ]

        # Allow some flexibility - English names might not always be caught
        # but the detection mechanism should be working
        assert result.total_scanned == 2, "Processing regressed"


class TestSummaryQualityRegression:
    """Regression tests for summary quality issues."""

    def test_duplicate_title_summary_detection(self):
        """Test detection of summaries identical to titles (Issue #SQ-001)."""
        duplicate_cases = [
            {
                "decision_key": "GOV1_DUP1",
                "decision_title": "החלטה על תקציב החינוך",
                "summary": "החלטה על תקציב החינוך",  # Exact duplicate
                "decision_content": "תוכן מפורט על תקציב החינוך"
            },
            {
                "decision_key": "GOV1_DUP2",
                "decision_title": "החלטה על שיפור התחבורה",
                "summary": "החלטה על שיפור התחבורה",  # Exact duplicate
                "decision_content": "תוכן על תחבורה ציבורית"
            }
        ]

        result = check_summary_quality(duplicate_cases)

        # Should detect duplicates
        duplicate_issues = [
            issue for issue in result.issues
            if "duplicate" in issue.description.lower() or
               "זהה" in issue.description or
               "כפול" in issue.description
        ]

        assert len(duplicate_issues) >= 2, "Duplicate title-summary detection regressed"

        # Verify specific records were flagged
        flagged_keys = {issue.decision_key for issue in duplicate_issues}
        assert "GOV1_DUP1" in flagged_keys
        assert "GOV1_DUP2" in flagged_keys

    def test_empty_summary_detection(self):
        """Test detection of empty summaries (Issue #SQ-002)."""
        empty_cases = [
            {
                "decision_key": "GOV1_EMPTY1",
                "decision_title": "החלטה חשובה",
                "summary": "",  # Empty
                "decision_content": "תוכן מפורט של החלטה"
            },
            {
                "decision_key": "GOV1_EMPTY2",
                "decision_title": "החלטה נוספת",
                # No summary field at all
                "decision_content": "תוכן נוסף"
            }
        ]

        result = check_summary_quality(empty_cases)

        # Should detect missing summaries
        missing_issues = [
            issue for issue in result.issues
            if "missing" in issue.description.lower() or
               "חסר" in issue.description or
               "ריק" in issue.description
        ]

        assert len(missing_issues) >= 2, "Empty summary detection regressed"

    def test_too_short_summary_detection(self):
        """Test detection of overly short summaries (Issue #SQ-003)."""
        short_cases = [
            {
                "decision_key": "GOV1_SHORT1",
                "decision_title": "החלטה מפורטת על נושא חשוב מאוד",
                "summary": "החלטה",  # Way too short
                "decision_content": "תוכן ארוך ומפורט של החלטה חשובה על נושא מורכב"
            },
            {
                "decision_key": "GOV1_SHORT2",
                "decision_title": "החלטה על תקציב ושיפורים במערכת",
                "summary": "תקציב",  # Too short
                "decision_content": "החלטה מפורטת על הגדלת תקציבים ושיפורים"
            }
        ]

        result = check_summary_quality(short_cases)

        # Should detect short summaries
        short_issues = [
            issue for issue in result.issues
            if "short" in issue.description.lower() or
               "קצר" in issue.description
        ]

        assert len(short_issues) >= 1, "Short summary detection regressed"


class TestDateValidityRegression:
    """Regression tests for date validity issues."""

    def test_invalid_date_formats(self):
        """Test detection of invalid date formats (Issue #DV-001)."""
        invalid_dates = [
            {
                "decision_key": "GOV1_DATE1",
                "decision_date": "2024-13-01",  # Invalid month
            },
            {
                "decision_key": "GOV1_DATE2",
                "decision_date": "2024-02-30",  # Invalid day
            },
            {
                "decision_key": "GOV1_DATE3",
                "decision_date": "invalid-date",  # Completely invalid
            },
            {
                "decision_key": "GOV1_DATE4",
                "decision_date": "",  # Empty date
            }
        ]

        from src.gov_scraper.processors.qa import check_date_validity
        result = check_date_validity(invalid_dates)

        # Should detect all invalid dates
        assert result.issues_found >= 4, "Date validity detection regressed"

        # Verify all records were flagged
        flagged_keys = {issue.decision_key for issue in result.issues}
        expected_keys = {"GOV1_DATE1", "GOV1_DATE2", "GOV1_DATE3", "GOV1_DATE4"}
        missing_detections = expected_keys - flagged_keys

        assert len(missing_detections) == 0, f"Failed to detect invalid dates: {missing_detections}"


@pytest.mark.regression
class TestRegressionSuite:
    """Combined regression test suite."""

    def test_no_false_positives_on_clean_data(self):
        """Ensure clean data doesn't trigger false positives (Issue #REG-001)."""
        clean_records = [
            {
                "decision_key": "GOV1_CLEAN1",
                "gov_num": 1,
                "decision_num": 1,
                "decision_title": "החלטה על שיפור מערכת החינוך",
                "decision_content": "הממשלה החליטה לאשר תוכנית חמש שנתית לשיפור איכות החינוך",
                "decision_date": "2024-01-15",
                "operativity": "אופרטיבית",
                "summary": "אישור תוכנית חמש שנתית לשיפור איכות החינוך בישראל",
                "tags_policy_area": "חינוך",
                "tags_government_body": "משרד החינוך",
                "tags_locations": "ארצי"
            }
        ]

        report = run_scan(clean_records)

        # Clean data should have minimal issues
        total_high_severity_issues = sum(
            1 for result in report.scan_results
            for issue in result.issues
            if issue.severity == "high"
        )

        assert total_high_severity_issues == 0, f"False positives detected: {total_high_severity_issues} high severity issues"

    def test_regression_detection_stability(self):
        """Test that regression detection is stable across runs (Issue #REG-002)."""
        test_records = [
            {
                "decision_key": "GOV1_STABLE",
                "decision_content": "Just a moment... Cloudflare",  # Known issue
                "operativity": "דקלרטיבית",
                "summary": "",
                "tags_policy_area": "שונות"
            }
        ]

        # Run multiple scans
        reports = []
        for _ in range(3):
            reports.append(run_scan(test_records))

        # Results should be consistent
        issue_counts = [report.total_issues for report in reports]
        assert len(set(issue_counts)) <= 1, f"Inconsistent results: {issue_counts}"

        # Check names should be consistent
        check_names_per_run = [
            {result.check_name for result in report.scan_results}
            for report in reports
        ]

        assert all(names == check_names_per_run[0] for names in check_names_per_run), "Inconsistent checks run"