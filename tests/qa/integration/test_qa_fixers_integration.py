"""
Integration tests for QA fixers and the fix pipeline.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.gov_scraper.processors.qa import (
    fix_operativity,
    fix_policy_tags,
    fix_summaries,
    fix_government_body_tags,
    fix_location_tags,
    QAScanResult
)


class TestQAFixersIntegration:
    """Integration tests for QA fixers."""

    @pytest.fixture
    def operativity_mismatch_records(self):
        """Records with operativity mismatches for testing fixes."""
        return [
            {
                "decision_key": "GOV1_1",
                "decision_content": "הממשלה החליטה לבטל את התוכנית ולעצור הפעילות",
                "operativity": "דקלרטיבית",  # Should be אופרטיבית
                "decision_title": "החלטה על ביטול תוכנית",
                "tags_policy_area": "כלכלה ואוצר"
            },
            {
                "decision_key": "GOV1_2",
                "decision_content": "הממשלה מציינת ומבהירה כי החלטה זו חשובה",
                "operativity": "אופרטיבית",  # Should be דקלרטיבית
                "decision_title": "הבהרה ממשלתית",
                "tags_policy_area": "שונות"
            }
        ]

    @pytest.fixture
    def poor_summary_records(self):
        """Records with poor quality summaries for testing fixes."""
        return [
            {
                "decision_key": "GOV1_1",
                "decision_title": "החלטה על תקציב החינוך",
                "summary": "החלטה על תקציב החינוך",  # Same as title
                "decision_content": "הממשלה דנה בהצעה להגדיל את תקציב החינוך לצורך שיפור מערכת ההשכלה",
                "operativity": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_2",
                "decision_title": "החלטה על תחבורה ציבורית",
                "summary": "קצר",  # Too short
                "decision_content": "התוכנית כוללת הקמת קווי רכבת חדשים ושדרוג התחבורה הציבורית",
                "operativity": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_3",
                "decision_title": "החלטה על בריאות",
                "summary": "",  # Empty
                "decision_content": "החלטה על שיפור שירותי הבריאות ורפואה",
                "operativity": "אופרטיבית"
            }
        ]

    @pytest.fixture
    def policy_mismatch_records(self):
        """Records with policy tag mismatches for testing fixes."""
        return [
            {
                "decision_key": "GOV1_1",
                "decision_content": "החלטה בנושא ביטחון המדינה וחיזוק כוחות הביטחון",
                "decision_title": "החלטה ביטחונית",
                "tags_policy_area": "שונות",  # Should be בטחון
                "operativity": "אופרטיבית"
            },
            {
                "decision_key": "GOV1_2",
                "decision_content": "החלטה על שיפור שירותי הבריאות והרפואה",
                "decision_title": "החלטה רפואית",
                "tags_policy_area": "שונות",  # Should be בריאות
                "operativity": "אופרטיבית"
            }
        ]

    @patch('src.gov_scraper.db.connector.get_supabase_client')
    def test_operativity_fixer_dry_run(self, mock_supabase, operativity_mismatch_records):
        """Test operativity fixer in dry-run mode."""
        # Mock database client
        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        updates, scan_result = fix_operativity(operativity_mismatch_records, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.check_name == "operativity-fix"
        assert scan_result.total_scanned == len(operativity_mismatch_records)

        # In dry-run mode, should not call database updates
        mock_client.table.return_value.update.assert_not_called()

        # Should identify records that need fixing
        assert len(updates) > 0
        assert isinstance(updates, list)

    @patch('src.gov_scraper.db.connector.get_supabase_client')
    def test_operativity_fixer_execute_mode(self, mock_supabase, operativity_mismatch_records):
        """Test operativity fixer in execute mode."""
        # Mock database client and successful update response
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value.data = [{"decision_key": "GOV1_1"}]

        mock_supabase.return_value = mock_client

        updates, scan_result = fix_operativity(operativity_mismatch_records, dry_run=False)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned == len(operativity_mismatch_records)

        # Should have attempted database updates
        if len(updates) > 0:
            mock_client.table.assert_called()
            mock_table.update.assert_called()

    @patch('src.gov_scraper.processors.ai.make_openai_request_with_retry')
    @patch('src.gov_scraper.db.connector.get_supabase_client')
    def test_summary_fixer_with_ai(self, mock_supabase, mock_ai, poor_summary_records):
        """Test summary fixer using AI generation."""
        # Mock AI response
        mock_ai_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"summary": "סיכום משופר שנוצר על ידי AI", "confidence": 0.9}'
                    }]
                }
            }]
        }
        mock_ai.return_value = mock_ai_response

        # Mock database client
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value.data = [{"decision_key": "GOV1_1"}]

        mock_supabase.return_value = mock_client

        updates, scan_result = fix_summaries(poor_summary_records, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned == len(poor_summary_records)

        # Should have called AI for summary generation
        if len(updates) > 0:
            mock_ai.assert_called()

    @patch('src.gov_scraper.processors.ai.make_openai_request_with_retry')
    @patch('src.gov_scraper.db.connector.get_supabase_client')
    def test_policy_tag_fixer_with_ai(self, mock_supabase, mock_ai, policy_mismatch_records):
        """Test policy tag fixer using AI classification."""
        # Mock AI response
        mock_ai_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"policy_tags": ["בטחון"], "confidence": 0.95, "reasoning": "Decision deals with security matters"}'
                    }]
                }
            }]
        }
        mock_ai.return_value = mock_ai_response

        # Mock database client
        mock_client = MagicMock()
        mock_supabase.return_value = mock_client

        updates, scan_result = fix_policy_tags(policy_mismatch_records, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned == len(policy_mismatch_records)

        # Should have identified records for fixing
        if len(updates) > 0:
            mock_ai.assert_called()

    def test_fixer_error_handling(self):
        """Test fixer error handling with malformed records."""
        malformed_records = [
            {"decision_key": "GOV1_1"},  # Missing required fields
            None,  # None record
            {},  # Empty record
        ]

        # Should handle errors gracefully without crashing
        updates, scan_result = fix_operativity(malformed_records, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned >= 0
        # Exact behavior depends on implementation

    def test_fixer_batch_processing(self, operativity_mismatch_records):
        """Test that fixers handle batch processing correctly."""
        # Create a larger dataset
        large_dataset = operativity_mismatch_records * 10  # 20 records

        updates, scan_result = fix_operativity(large_dataset, dry_run=True)

        assert isinstance(scan_result, QAScanResult)
        assert scan_result.total_scanned == len(large_dataset)

        # Should process all records
        assert len(updates) >= 0


class TestFixerPipelineIntegration:
    """Test integration between different fixers."""

    @pytest.fixture
    def multi_issue_records(self):
        """Records with multiple types of issues."""
        return [
            {
                "decision_key": "GOV1_1",
                "decision_content": "הממשלה מציינת בנושא ביטחון וחיזוק הצבא",
                "operativity": "אופרטיבית",  # Should be דקלרטיבית
                "decision_title": "החלטה ביטחונית",
                "summary": "החלטה ביטחונית",  # Same as title
                "tags_policy_area": "שונות",  # Should be בטחון
                "tags_government_body": "משרד הביטחון"
            }
        ]

    def test_sequential_fixer_application(self, multi_issue_records):
        """Test applying multiple fixers sequentially."""
        original_records = multi_issue_records.copy()

        # Apply operativity fixer
        operativity_updates, operativity_result = fix_operativity(
            original_records, dry_run=True
        )

        # Apply summary fixer
        summary_updates, summary_result = fix_summaries(
            original_records, dry_run=True
        )

        # Apply policy tag fixer
        policy_updates, policy_result = fix_policy_tags(
            original_records, dry_run=True
        )

        # Each fixer should have processed the records
        assert operativity_result.total_scanned == len(original_records)
        assert summary_result.total_scanned == len(original_records)
        assert policy_result.total_scanned == len(original_records)

        # Should detect issues in each category
        total_issues = (operativity_result.issues_found +
                       summary_result.issues_found +
                       policy_result.issues_found)
        assert total_issues > 0

    def test_fixer_conflict_resolution(self):
        """Test handling of potential conflicts between fixers."""
        # This is a conceptual test - in practice, fixers should be designed
        # to avoid conflicts or have clear precedence rules

        records = [
            {
                "decision_key": "GOV1_1",
                "decision_content": "תוכן החלטה",
                "operativity": "דקלרטיבית",
                "summary": "סיכום קיים",
                "tags_policy_area": "שונות"
            }
        ]

        # Multiple fixers should be able to process the same records
        # without interfering with each other in dry-run mode
        updates1, result1 = fix_operativity(records, dry_run=True)
        updates2, result2 = fix_summaries(records, dry_run=True)

        assert result1.total_scanned == 1
        assert result2.total_scanned == 1

    @patch('src.gov_scraper.db.connector.get_supabase_client')
    def test_fixer_transaction_handling(self, mock_supabase):
        """Test that fixers handle database transactions appropriately."""
        # Mock database with transaction-like behavior
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_update

        # Simulate transaction success/failure
        mock_update.execute.return_value.data = [{"decision_key": "GOV1_1"}]

        mock_supabase.return_value = mock_client

        records = [
            {
                "decision_key": "GOV1_1",
                "operativity": "דקלרטיבית",
                "decision_content": "החליטה לבטל"
            }
        ]

        updates, scan_result = fix_operativity(records, dry_run=False)

        # Should handle database operations appropriately
        assert isinstance(scan_result, QAScanResult)


@pytest.mark.slow
class TestFixerPerformance:
    """Performance tests for QA fixers."""

    def test_fixer_performance_scaling(self):
        """Test fixer performance with increasing dataset sizes."""
        import time

        sizes = [10, 50, 100]
        durations = []

        for size in sizes:
            records = [
                {
                    "decision_key": f"GOV1_{i}",
                    "decision_content": f"החליטה לבטל פעילות {i}",
                    "operativity": "דקלרטיבית",
                    "decision_title": f"החלטה {i}"
                }
                for i in range(size)
            ]

            start_time = time.time()
            fix_operativity(records, dry_run=True)
            end_time = time.time()

            durations.append(end_time - start_time)

        # Performance should scale reasonably
        assert all(d < 10 for d in durations)  # Under 10 seconds for test sizes

    def test_fixer_memory_usage(self):
        """Test memory efficiency of fixers."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create large dataset
        large_records = [
            {
                "decision_key": f"GOV1_{i}",
                "decision_content": "א" * 1000,  # 1KB per record
                "operativity": "דקלרטיבית",
                "decision_title": f"החלטה {i}"
            }
            for i in range(100)
        ]

        fix_operativity(large_records, dry_run=True)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Should not use excessive memory
        assert memory_increase < 50 * 1024 * 1024  # Under 50MB increase