"""
Pytest configuration and shared fixtures for GOV2DB test suite.
"""

import os
import sys
import json
import pytest
import tempfile
from datetime import datetime, date
from typing import Dict, List, Optional
from unittest.mock import Mock, MagicMock, patch

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# Import project modules
from src.gov_scraper.processors.qa import QAIssue, QAScanResult, QAReport
from src.gov_scraper.db.connector import get_supabase_client


@pytest.fixture
def project_root():
    """Get project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for testing."""
    mock_client = MagicMock()

    # Mock table operations
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    # Mock select operations
    mock_select = MagicMock()
    mock_table.select.return_value = mock_select
    mock_select.execute.return_value.data = []

    # Mock update operations
    mock_update = MagicMock()
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_update
    mock_update.execute.return_value.data = []

    with patch('src.gov_scraper.db.connector.get_supabase_client', return_value=mock_client):
        yield mock_client


@pytest.fixture
def sample_decision_data():
    """Generate sample decision data for testing."""
    return {
        "decision_key": "GOV1_1",
        "gov_num": 1,
        "decision_num": 1,
        "decision_title": "החלטה לדוגמה על נושא חשוב",
        "decision_content": """
        החלטה חשובה זו עוסקת בנושא משמעותי לכלכלת המדינה.
        ממשלת ישראל החליטה לאשר תוכנית פעולה חדשה.
        התוכנית תיושם במהלך השנה הקרובה.
        """,
        "decision_date": "2024-01-15",
        "operativity": "אופרטיבית",
        "summary": "החלטה על תוכנית פעולה חדשה בתחום הכלכלה",
        "tags_policy_area": "כלכלה ואוצר",
        "tags_government_body": "משרד האוצר",
        "tags_locations": "ארצי",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


@pytest.fixture
def sample_qa_issue():
    """Generate sample QA issue for testing."""
    return QAIssue(
        decision_key="GOV1_1",
        check_name="operativity",
        severity="high",
        field="operativity",
        current_value="דקלרטיבית",
        description="Decision classified as declarative but contains operative keywords",
        expected_value="אופרטיבית"
    )


@pytest.fixture
def sample_qa_scan_result():
    """Generate sample QA scan result."""
    issue = QAIssue(
        decision_key="GOV1_1",
        check_name="operativity",
        severity="high",
        field="operativity",
        current_value="דקלרטיבית",
        description="Operativity mismatch",
        expected_value="אופרטיבית"
    )

    return QAScanResult(
        check_name="operativity",
        total_scanned=100,
        issues_found=5,
        issues=[issue],
        summary={"misclassified": 5, "accuracy": "95%"}
    )


@pytest.fixture
def sample_qa_report(sample_qa_scan_result):
    """Generate sample QA report."""
    return QAReport(
        timestamp=datetime.now().isoformat(),
        total_records=100,
        scan_results=[sample_qa_scan_result]
    )


@pytest.fixture
def mock_gemini_api():
    """Mock Gemini API responses."""
    mock_response = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps({
                        "operativity": "אופרטיבית",
                        "confidence": 0.9,
                        "reasoning": "Decision contains operative keywords"
                    })
                }]
            }
        }]
    }

    with patch('src.gov_scraper.processors.ai.make_openai_request_with_retry', return_value=mock_response):
        yield mock_response


@pytest.fixture
def database_records_sample():
    """Generate sample database records for testing."""
    return [
        {
            "decision_key": f"GOV1_{i}",
            "gov_num": 1,
            "decision_num": i,
            "decision_title": f"החלטה מספר {i}",
            "decision_content": f"תוכן החלטה מספר {i} עם מילות מפתח שונות",
            "decision_date": f"2024-01-{i:02d}",
            "operativity": "אופרטיבית" if i % 2 == 0 else "דקלרטיבית",
            "summary": f"סיכום החלטה מספר {i}",
            "tags_policy_area": "כלכלה ואוצר" if i % 3 == 0 else "שונות",
            "tags_government_body": "משרד האוצר" if i % 2 == 0 else "משרד החינוך",
            "tags_locations": "ארצי",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        for i in range(1, 21)
    ]


@pytest.fixture
def problematic_records():
    """Generate records with known issues for testing."""
    return [
        # Operativity mismatch
        {
            "decision_key": "GOV1_PROB1",
            "decision_content": "הממשלה החליטה לבטל את התוכנית ולעצור את הפעילות",
            "operativity": "דקלרטיבית",  # Should be אופרטיבית
            "tags_policy_area": "כלכלה ואוצר",
        },
        # Policy tag mismatch
        {
            "decision_key": "GOV1_PROB2",
            "decision_content": "החלטה בנושא בטחון פנים וביטחון המדינה",
            "operativity": "אופרטיבית",
            "tags_policy_area": "שונות",  # Should be בטחון
        },
        # Government body hallucination
        {
            "decision_key": "GOV1_PROB3",
            "decision_content": "החלטה של משרד הבריאות בנושא רפואה",
            "operativity": "אופרטיבית",
            "tags_policy_area": "בריאות",
            "tags_government_body": "משרד בלתי קיים",  # Hallucinated ministry
        },
        # Poor summary quality
        {
            "decision_key": "GOV1_PROB4",
            "decision_title": "החלטה על תקציב חינוך",
            "decision_content": "החלטה חשובה על הקצאת תקציב לחינוך בישראל",
            "operativity": "אופרטיבית",
            "summary": "החלטה על תקציב חינוך",  # Same as title
            "tags_policy_area": "חינוך",
        },
        # Cloudflare contamination
        {
            "decision_key": "GOV1_PROB5",
            "decision_content": "Just a moment... Cloudflare security check. Ray ID: 123456",
            "operativity": "אופרטיבית",
            "tags_policy_area": "שונות",
        }
    ]


@pytest.fixture(scope="session")
def test_config():
    """Test configuration settings."""
    return {
        "batch_size": 5,
        "max_test_records": 20,
        "performance_threshold_ms": 1000,
        "accuracy_threshold": 0.8,
        "test_timeout": 30
    }


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for full pipeline"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and benchmark tests"
    )
    config.addinivalue_line(
        "markers", "regression: Regression tests for known issues"
    )
    config.addinivalue_line(
        "markers", "property: Property-based tests"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file paths."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        elif "regression" in str(item.fspath):
            item.add_marker(pytest.mark.regression)

        # Mark slow tests
        if any(keyword in item.name.lower() for keyword in ["performance", "batch", "large"]):
            item.add_marker(pytest.mark.slow)