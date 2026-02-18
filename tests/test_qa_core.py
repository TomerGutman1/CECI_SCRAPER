"""
Unit tests for QA Core module.

Tests the AbstractQACheck base class, factory pattern, and progress tracking.
"""

import pytest
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.gov_scraper.processors.qa_core import (
    AbstractQACheck, QACheckFactory, ProgressManager, CompositeQACheck,
    QAIssue, CheckSeverity, CheckStatus, CheckProgress, QAScanResult
)


class MockQACheck(AbstractQACheck):
    """Mock QA check for testing."""

    def __init__(self, issue_count=0, **kwargs):
        super().__init__(check_name="mock_check", **kwargs)
        self.issue_count = issue_count

    def _validate_record(self, record):
        """Create mock issues."""
        issues = []
        for i in range(self.issue_count):
            issues.append(self.create_issue(
                decision_key=record.get('decision_key', 'test'),
                severity=CheckSeverity.LOW,
                field='test_field',
                current_value='test_value',
                description=f'Mock issue {i}'
            ))
        return issues

    def _generate_summary(self, issues, total_scanned):
        return {
            "mock_summary": True,
            "total_issues": len(issues),
            "total_scanned": total_scanned
        }


class FailingQACheck(AbstractQACheck):
    """QA check that always fails for error testing."""

    def __init__(self, **kwargs):
        super().__init__(check_name="failing_check", **kwargs)

    def _validate_record(self, record):
        raise ValueError("Simulated failure")

    def _generate_summary(self, issues, total_scanned):
        return {}


class TestAbstractQACheck:
    """Test AbstractQACheck base functionality."""

    def test_initialization(self):
        """Test basic initialization."""
        check = MockQACheck(
            check_name="test_check",
            description="Test description",
            batch_size=500
        )

        assert check.check_name == "mock_check"  # Set in MockQACheck
        assert check.description == "Test description"
        assert check.batch_size == 500
        assert check.progress is None

    def test_create_issue(self):
        """Test issue creation."""
        check = MockQACheck()
        issue = check.create_issue(
            decision_key="test_key",
            severity=CheckSeverity.HIGH,
            field="test_field",
            current_value="current",
            description="Test issue",
            expected_value="expected",
            custom_metadata="test"
        )

        assert isinstance(issue, QAIssue)
        assert issue.decision_key == "test_key"
        assert issue.severity == CheckSeverity.HIGH
        assert issue.field == "test_field"
        assert issue.current_value == "current"
        assert issue.description == "Test issue"
        assert issue.expected_value == "expected"
        assert issue.metadata["custom_metadata"] == "test"

    def test_run_with_single_record(self):
        """Test running check on single record."""
        check = MockQACheck(issue_count=2)
        records = [{"decision_key": "test_1", "content": "test"}]

        result = check.run(records)

        assert isinstance(result, QAScanResult)
        assert result.check_name == "mock_check"
        assert result.total_scanned == 1
        assert result.issues_found == 2
        assert len(result.issues) == 2
        assert result.progress is not None
        assert result.progress.status == CheckStatus.COMPLETED

    def test_run_with_multiple_records(self):
        """Test running check on multiple records."""
        check = MockQACheck(issue_count=1, batch_size=2)
        records = [
            {"decision_key": "test_1"},
            {"decision_key": "test_2"},
            {"decision_key": "test_3"}
        ]

        result = check.run(records)

        assert result.total_scanned == 3
        assert result.issues_found == 3
        assert result.progress.processed_records == 3

    def test_run_with_errors(self):
        """Test error handling during record processing."""
        check = FailingQACheck()
        records = [{"decision_key": "test_1"}]

        result = check.run(records)

        assert result.error is not None
        assert result.progress.status == CheckStatus.FAILED

    def test_batch_processing(self):
        """Test batch processing functionality."""
        check = MockQACheck(batch_size=2)
        records = [{"decision_key": f"test_{i}"} for i in range(5)]

        batches = list(check._batch_iterator(records))

        assert len(batches) == 3  # 2, 2, 1
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    def test_progress_tracking(self):
        """Test progress tracking during execution."""
        check = MockQACheck(issue_count=1, enable_progress_tracking=True)
        records = [{"decision_key": f"test_{i}"} for i in range(3)]

        result = check.run(records)

        progress = result.progress
        assert progress is not None
        assert progress.check_name == "mock_check"
        assert progress.total_records == 3
        assert progress.processed_records == 3
        assert progress.issues_found == 3
        assert progress.status == CheckStatus.COMPLETED
        assert progress.progress_pct == 100.0

    def test_disabled_progress_tracking(self):
        """Test with disabled progress tracking."""
        check = MockQACheck(enable_progress_tracking=False)
        records = [{"decision_key": "test_1"}]

        result = check.run(records)

        assert result.progress is None


class TestCompositeQACheck:
    """Test CompositeQACheck functionality."""

    def test_composite_check_creation(self):
        """Test composite check creation."""
        sub_checks = [
            MockQACheck(issue_count=1),
            MockQACheck(issue_count=2)
        ]

        composite = CompositeQACheck(
            check_name="composite_test",
            sub_checks=sub_checks
        )

        assert composite.check_name == "composite_test"
        assert len(composite.sub_checks) == 2

    def test_composite_check_execution(self):
        """Test composite check execution."""
        sub_checks = [
            MockQACheck(issue_count=1),
            MockQACheck(issue_count=2)
        ]

        composite = CompositeQACheck(
            check_name="composite_test",
            sub_checks=sub_checks
        )

        records = [{"decision_key": "test_1"}]
        result = composite.run(records)

        assert result.total_scanned == 1
        assert result.issues_found == 3  # 1 + 2 from sub-checks
        assert "sub_check_results" in result.summary
        assert len(result.summary["sub_check_results"]) == 2


class TestQACheckFactory:
    """Test QACheckFactory functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear registry
        QACheckFactory._registry.clear()

    def test_register_and_create(self):
        """Test check registration and creation."""
        QACheckFactory.register("mock_check", MockQACheck)

        check = QACheckFactory.create("mock_check", issue_count=3)

        assert isinstance(check, MockQACheck)
        assert check.issue_count == 3

    def test_create_unknown_check(self):
        """Test creating unknown check."""
        with pytest.raises(ValueError, match="Unknown check"):
            QACheckFactory.create("unknown_check")

    def test_get_available_checks(self):
        """Test getting available checks."""
        QACheckFactory.register("check1", MockQACheck)
        QACheckFactory.register("check2", MockQACheck)

        available = QACheckFactory.get_available_checks()

        assert "check1" in available
        assert "check2" in available

    def test_create_composite_check(self):
        """Test creating composite check."""
        QACheckFactory.register("mock_check", MockQACheck)

        composite = QACheckFactory.create_composite_check(
            "composite_test",
            ["mock_check", "mock_check"],
            description="Test composite"
        )

        assert isinstance(composite, CompositeQACheck)
        assert len(composite.sub_checks) == 2


class TestProgressManager:
    """Test ProgressManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.checkpoint_dir = "test_checkpoints"
        self.progress_manager = ProgressManager(self.checkpoint_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        import os
        if os.path.exists(self.checkpoint_dir):
            shutil.rmtree(self.checkpoint_dir)

    def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoints."""
        progress = CheckProgress(
            check_name="test_check",
            total_records=100,
            processed_records=50,
            issues_found=10
        )

        # Save checkpoint
        checkpoint_id = self.progress_manager.save_checkpoint(progress)

        # Load checkpoint
        loaded_progress = self.progress_manager.load_checkpoint(checkpoint_id)

        assert loaded_progress is not None
        assert loaded_progress.check_name == "test_check"
        assert loaded_progress.total_records == 100
        assert loaded_progress.processed_records == 50
        assert loaded_progress.issues_found == 10

    def test_load_nonexistent_checkpoint(self):
        """Test loading non-existent checkpoint."""
        result = self.progress_manager.load_checkpoint("nonexistent")

        assert result is None

    def test_list_checkpoints(self):
        """Test listing checkpoints."""
        progress = CheckProgress(
            check_name="test_check",
            total_records=100
        )

        checkpoint_id = self.progress_manager.save_checkpoint(progress)
        checkpoints = self.progress_manager.list_checkpoints()

        assert checkpoint_id in checkpoints

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_cleanup_old_checkpoints(self, mock_listdir, mock_exists):
        """Test cleaning up old checkpoints."""
        mock_exists.return_value = True
        mock_listdir.return_value = [f"checkpoint_{i}.json" for i in range(15)]

        with patch('os.remove') as mock_remove:
            self.progress_manager.cleanup_old_checkpoints(keep_latest=10)

            # Should remove 5 old checkpoints
            assert mock_remove.call_count == 5


class TestDataClasses:
    """Test data class functionality."""

    def test_qa_issue_creation(self):
        """Test QAIssue creation and serialization."""
        issue = QAIssue(
            decision_key="test_key",
            check_name="test_check",
            severity=CheckSeverity.HIGH,
            field="test_field",
            current_value="current",
            description="Test description",
            expected_value="expected",
            metadata={"custom": "value"}
        )

        issue_dict = issue.to_dict()

        assert issue_dict["decision_key"] == "test_key"
        assert issue_dict["severity"] == "high"
        assert issue_dict["metadata"]["custom"] == "value"

    def test_check_progress_metrics(self):
        """Test CheckProgress metrics calculation."""
        progress = CheckProgress(
            check_name="test_check",
            total_records=100,
            processed_records=50,
            issues_found=10
        )

        assert progress.progress_pct == 50.0
        assert progress.elapsed_time >= 0
        assert progress.records_per_second >= 0

    def test_qa_scan_result_metrics(self):
        """Test QAScanResult metrics calculation."""
        issues = [
            QAIssue("key1", "check", CheckSeverity.HIGH, "field", "value", "desc"),
            QAIssue("key2", "check", CheckSeverity.LOW, "field", "value", "desc")
        ]

        result = QAScanResult(
            check_name="test_check",
            total_scanned=100,
            issues_found=2,
            issues=issues
        )

        assert result.issue_rate == 2.0
        result_dict = result.to_dict()
        assert result_dict["issue_rate"] == "2.0%"


if __name__ == "__main__":
    pytest.main([__file__])