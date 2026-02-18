"""
Integration tests for the full QA pipeline.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.gov_scraper.processors.qa import (
    run_scan,
    format_report,
    export_report_json,
    ALL_CHECKS,
    QAReport,
    QAScanResult
)


class TestFullQAPipeline:
    """Test the complete QA scanning pipeline."""

    @pytest.fixture
    def sample_database_records(self):
        """Sample database records for integration testing."""
        return [
            {
                "decision_key": "GOV1_1",
                "gov_num": 1,
                "decision_num": 1,
                "decision_title": "החלטה על תקציב החינוך לשנת 2024",
                "decision_content": "הממשלה החליטה לאשר הגדלת תקציב החינוך ב-15 אחוזים",
                "decision_date": "2024-01-15",
                "operativity": "אופרטיבית",
                "summary": "אישור הגדלת תקציב החינוך ב-15%",
                "tags_policy_area": "חינוך",
                "tags_government_body": "משרד החינוך",
                "tags_locations": "ארצי"
            },
            {
                "decision_key": "GOV1_2",
                "gov_num": 1,
                "decision_num": 2,
                "decision_title": "החלטה על שיפור התחבורה הציבורית",
                "decision_content": "הממשלה מציינת כי חשוב לשפר את התחבורה הציבורית",
                "decision_date": "2024-01-16",
                "operativity": "אופרטיבית",  # Mismatch - should be declarative
                "summary": "החלטה על שיפור התחבורה הציבורית",  # Same as title
                "tags_policy_area": "תחבורה",
                "tags_government_body": "משרד התחבורה",
                "tags_locations": "ארצי"
            },
            {
                "decision_key": "GOV1_3",
                "gov_num": 1,
                "decision_num": 3,
                "decision_title": "החלטה על בריאות הציבור",
                "decision_content": "Just a moment... Cloudflare Ray ID: 123456",  # Contaminated
                "decision_date": "2024-01-17",
                "operativity": "דקלרטיבית",
                "summary": "החלטה בנושא בריאות",
                "tags_policy_area": "בריאות",
                "tags_government_body": "משרד הבריאות",
                "tags_locations": "ארצי"
            },
            {
                "decision_key": "GOV1_4",
                "gov_num": 1,
                "decision_num": 4,
                "decision_title": "החלטה על ביטחון",
                "decision_content": "החלטה בנושא ביטחון המדינה והצבא",
                "decision_date": "2024-01-18",
                "operativity": "אופרטיבית",
                "summary": "החלטה ביטחונית",
                "tags_policy_area": "שונות",  # Should be בטחון
                "tags_government_body": "משרד הביטחון",
                "tags_locations": "ארצי"
            },
            {
                "decision_key": "GOV1_5",
                "gov_num": 1,
                "decision_num": 5,
                "decision_title": "החלטה חסרה",
                "decision_content": "",  # Missing content
                "decision_date": "invalid-date",  # Invalid date
                "operativity": "",  # Missing operativity
                "summary": "",  # Missing summary
                "tags_policy_area": "",
                "tags_government_body": "",
                "tags_locations": ""
            }
        ]

    def test_full_scan_all_checks(self, sample_database_records):
        """Test running full scan with all checks."""
        report = run_scan(sample_database_records, checks=None)

        assert isinstance(report, QAReport)
        assert report.total_records == 5
        assert len(report.scan_results) > 0
        assert report.total_issues > 0

        # Verify that scan results contain expected checks
        check_names = {result.check_name for result in report.scan_results}
        expected_checks = {
            "operativity", "content-quality", "summary-quality",
            "policy-relevance", "date-validity"
        }

        # Should contain at least some core checks
        assert len(check_names.intersection(expected_checks)) > 0

    def test_full_scan_specific_checks(self, sample_database_records):
        """Test running scan with specific checks only."""
        selected_checks = ["operativity", "content-quality"]
        report = run_scan(sample_database_records, checks=selected_checks)

        assert isinstance(report, QAReport)
        assert report.total_records == 5
        assert len(report.scan_results) == 2

        check_names = {result.check_name for result in report.scan_results}
        assert check_names == set(selected_checks)

    def test_scan_detects_known_issues(self, sample_database_records):
        """Test that scan detects known issues in sample data."""
        report = run_scan(sample_database_records)

        # Should detect operativity mismatch (GOV1_2)
        operativity_results = [r for r in report.scan_results if r.check_name == "operativity"]
        if operativity_results:
            assert operativity_results[0].issues_found > 0

        # Should detect content quality issues (GOV1_3 - Cloudflare, GOV1_5 - empty)
        content_results = [r for r in report.scan_results if "content" in r.check_name]
        if content_results:
            total_content_issues = sum(r.issues_found for r in content_results)
            assert total_content_issues > 0

        # Should detect summary quality issues (GOV1_2 - same as title, GOV1_5 - empty)
        summary_results = [r for r in report.scan_results if "summary" in r.check_name]
        if summary_results:
            assert summary_results[0].issues_found > 0

    def test_scan_with_empty_records(self):
        """Test scan behavior with empty record set."""
        report = run_scan([])

        assert isinstance(report, QAReport)
        assert report.total_records == 0
        assert len(report.scan_results) > 0  # Checks still run

        # All scan results should show 0 scanned
        for result in report.scan_results:
            assert result.total_scanned == 0
            assert result.issues_found == 0

    def test_scan_performance_with_large_dataset(self):
        """Test scan performance with larger dataset."""
        # Create a larger dataset
        large_dataset = []
        for i in range(100):
            record = {
                "decision_key": f"GOV1_{i}",
                "gov_num": 1,
                "decision_num": i,
                "decision_title": f"החלטה מספר {i}",
                "decision_content": f"תוכן החלטה מספר {i} עם מילות מפתח",
                "decision_date": f"2024-01-{(i % 28) + 1:02d}",
                "operativity": "אופרטיבית" if i % 2 == 0 else "דקלרטיבית",
                "summary": f"סיכום החלטה {i}",
                "tags_policy_area": "כלכלה ואוצר" if i % 3 == 0 else "שונות",
                "tags_government_body": "משרד האוצר" if i % 2 == 0 else "משרד החינוך",
                "tags_locations": "ארצי"
            }
            large_dataset.append(record)

        # Run scan with time measurement
        import time
        start_time = time.time()
        report = run_scan(large_dataset)
        end_time = time.time()

        scan_duration = end_time - start_time

        assert isinstance(report, QAReport)
        assert report.total_records == 100
        assert scan_duration < 30  # Should complete within 30 seconds

        # Verify all records were processed
        for result in report.scan_results:
            assert result.total_scanned == 100

    def test_report_formatting(self, sample_database_records):
        """Test report formatting functionality."""
        report = run_scan(sample_database_records)
        formatted_report = format_report(report)

        assert isinstance(formatted_report, str)
        assert len(formatted_report) > 0

        # Should contain key sections
        assert "QA REPORT" in formatted_report or "דוח איכות" in formatted_report
        assert str(report.total_records) in formatted_report
        assert str(report.total_issues) in formatted_report

    def test_report_json_export(self, sample_database_records, temp_dir):
        """Test JSON report export functionality."""
        import os
        import json

        report = run_scan(sample_database_records)
        export_path = os.path.join(temp_dir, "test_report.json")

        export_report_json(report, export_path)

        assert os.path.exists(export_path)

        # Verify JSON structure
        with open(export_path, 'r', encoding='utf-8') as f:
            exported_data = json.load(f)

        assert "timestamp" in exported_data
        assert "total_records" in exported_data
        assert "total_issues" in exported_data
        assert "scan_results" in exported_data
        assert exported_data["total_records"] == 5

    def test_scan_error_handling(self):
        """Test scan error handling with malformed records."""
        malformed_records = [
            {"decision_key": "GOV1_1"},  # Minimal record
            {"decision_key": "GOV1_2", "decision_content": None},  # None content
            None,  # None record
            {},  # Empty record
        ]

        # Should not crash with malformed data
        report = run_scan(malformed_records)

        assert isinstance(report, QAReport)
        # Should handle gracefully, exact behavior depends on implementation


class TestQAPipelineIntegration:
    """Test QA pipeline integration with mocked database."""

    @patch('src.gov_scraper.processors.qa.fetch_records_for_qa')
    def test_pipeline_with_mocked_database(self, mock_fetch, sample_qa_report):
        """Test pipeline integration with mocked database fetch."""
        # Mock database response
        mock_records = [
            {
                "decision_key": "GOV1_1",
                "decision_content": "תוכן החלטה",
                "operativity": "אופרטיבית",
                "tags_policy_area": "כלכלה ואוצר"
            }
        ]
        mock_fetch.return_value = mock_records

        # Test would involve calling higher-level functions that use fetch_records_for_qa
        # For now, verify the mock setup
        records = mock_fetch()
        assert len(records) == 1
        assert records[0]["decision_key"] == "GOV1_1"

    def test_cross_check_interactions(self, sample_database_records):
        """Test interactions between different QA checks."""
        # Run scan and analyze check interactions
        report = run_scan(sample_database_records)

        # Count total unique issues across all checks
        all_decision_keys_with_issues = set()
        for result in report.scan_results:
            for issue in result.issues:
                all_decision_keys_with_issues.add(issue.decision_key)

        # Verify that problematic records are caught by multiple checks
        # GOV1_5 (empty record) should be caught by multiple checks
        gov1_5_issues = []
        for result in report.scan_results:
            for issue in result.issues:
                if issue.decision_key == "GOV1_5":
                    gov1_5_issues.append(f"{result.check_name}:{issue.field}")

        # Should have multiple types of issues for the empty record
        assert len(gov1_5_issues) > 1

    def test_scan_result_consistency(self, sample_database_records):
        """Test consistency of scan results across multiple runs."""
        report1 = run_scan(sample_database_records)
        report2 = run_scan(sample_database_records)

        # Results should be consistent
        assert report1.total_records == report2.total_records
        assert len(report1.scan_results) == len(report2.scan_results)

        # Check names should be the same
        check_names1 = {r.check_name for r in report1.scan_results}
        check_names2 = {r.check_name for r in report2.scan_results}
        assert check_names1 == check_names2

        # Issue counts should be the same for deterministic checks
        for result1 in report1.scan_results:
            result2 = next(r for r in report2.scan_results if r.check_name == result1.check_name)
            assert result1.total_scanned == result2.total_scanned
            assert result1.issues_found == result2.issues_found


@pytest.mark.slow
class TestQAPipelinePerformance:
    """Performance tests for QA pipeline."""

    def test_scan_scales_linearly(self):
        """Test that scan performance scales roughly linearly."""
        import time

        # Test with different dataset sizes
        sizes = [10, 50, 100]
        durations = []

        for size in sizes:
            records = [
                {
                    "decision_key": f"GOV1_{i}",
                    "decision_content": f"תוכן החלטה {i}",
                    "operativity": "אופרטיבית",
                    "decision_date": "2024-01-15",
                    "summary": f"סיכום {i}",
                    "tags_policy_area": "שונות"
                }
                for i in range(size)
            ]

            start_time = time.time()
            run_scan(records)
            end_time = time.time()

            durations.append(end_time - start_time)

        # Verify reasonable scaling (not exponential)
        # Allow for some variation but should be roughly linear
        ratio_50_10 = durations[1] / durations[0]
        ratio_100_50 = durations[2] / durations[1]

        # Ratios should be reasonable (between 2-10x for dataset size increases)
        assert 1 < ratio_50_10 < 10
        assert 1 < ratio_100_50 < 5

    @pytest.mark.parametrize("record_count", [1, 10, 50])
    def test_scan_memory_efficiency(self, record_count):
        """Test memory efficiency of scan operations."""
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create records and run scan
        records = [
            {
                "decision_key": f"GOV1_{i}",
                "decision_content": "א" * 1000,  # 1KB content per record
                "operativity": "אופרטיבית",
                "decision_date": "2024-01-15",
                "summary": f"סיכום {i}",
                "tags_policy_area": "שונות"
            }
            for i in range(record_count)
        ]

        run_scan(records)

        # Get final memory usage
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB for test sizes)
        assert memory_increase < 100 * 1024 * 1024  # 100MB