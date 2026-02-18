# GOV2DB QA Test Suite

This comprehensive test suite ensures the quality and reliability of the GOV2DB QA system that processes Israeli government decisions.

## 🏗️ Test Architecture

### Test Categories

1. **Unit Tests** (`tests/qa/unit/`)
   - Test individual QA check functions
   - Test data classes and utilities
   - Fast execution, isolated testing
   - Target: >90% code coverage

2. **Integration Tests** (`tests/qa/integration/`)
   - Test full QA pipeline workflows
   - Test database interactions (mocked)
   - Test QA fixer operations
   - Verify end-to-end functionality

3. **Performance Tests** (`tests/qa/performance/`)
   - Benchmark QA operations
   - Test scalability with large datasets
   - Memory usage analysis
   - Performance regression detection

4. **Regression Tests** (`tests/qa/regression/`)
   - Test fixes for known issues
   - Prevent reintroduction of bugs
   - Validate specific problem scenarios
   - Historical issue preservation

5. **Property-Based Tests** (`tests/qa/property/`)
   - Test system invariants with Hypothesis
   - Generate edge cases automatically
   - Verify QA system robustness
   - Test with random inputs

## 🚀 Quick Start

### Setup
```bash
# Install development dependencies
make install-dev

# Set up development environment
make setup-dev

# Install pre-commit hooks
make install-hooks
```

### Running Tests
```bash
# Run all tests
make test-all-qa

# Run specific test categories
make test-unit           # Unit tests only
make test-integration    # Integration tests
make test-performance    # Performance tests
make test-regression     # Regression tests
make test-property       # Property-based tests

# Generate coverage report
make test-coverage

# Generate comprehensive report
make test-report
```

## 📊 Test Fixtures and Data

### Mock Data Generation
The `tests/qa/fixtures/data_generators.py` module provides:

- **MockDataGenerator**: Generate realistic government decision records
- **QATestDataset**: Pre-built datasets for common scenarios
- **Issue-specific datasets**: Records with known problems

Example usage:
```python
from tests.qa.fixtures.data_generators import MockDataGenerator

generator = MockDataGenerator()
# Generate clean records
clean_records = generator.generate_clean_batch(10)

# Generate problematic records
problematic_records = generator.generate_problematic_batch(5)

# Generate specific issue types
cloudflare_records = generator.generate_specific_issue_records("cloudflare", 3)
```

### Test Datasets Available

- **Cloudflare contamination**: Records with Cloudflare interference
- **Operativity mismatches**: Wrong operative/declarative classification
- **Policy tag errors**: Incorrect policy area assignments
- **Government body hallucinations**: Non-existent ministry references
- **Summary quality issues**: Poor or missing summaries
- **Mixed issues**: Records with multiple problems

## 🔍 Test Patterns

### Unit Test Structure
```python
class TestQACheckFunction:
    """Test a specific QA check function."""

    def test_valid_input(self):
        """Test with valid, clean input."""
        records = [generate_clean_record()]
        result = qa_check_function(records)
        assert result.issues_found == 0

    def test_problematic_input(self):
        """Test with known problematic input."""
        records = [generate_problematic_record()]
        result = qa_check_function(records)
        assert result.issues_found > 0

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty records, malformed data, etc.
```

### Property-Based Test Example
```python
@given(records=record_list(min_size=1, max_size=20))
@settings(max_examples=50, deadline=10000)
def test_scan_always_returns_valid_report(self, records):
    """Property: run_scan always returns a valid QAReport."""
    report = run_scan(records)

    assert isinstance(report, QAReport)
    assert report.total_records == len(records)
    assert report.total_issues >= 0
```

## 📈 Performance Testing

### Benchmarks
Performance tests measure:

- **Throughput**: Records processed per second
- **Memory usage**: Peak memory consumption
- **Scalability**: Performance across dataset sizes
- **Regression**: Performance changes over time

### Performance Thresholds
- Unit tests: < 100ms per test
- Integration tests: < 5 seconds per test suite
- Performance tests: Baseline tracking with regression alerts
- Full scan (1000 records): < 30 seconds

## 🔄 Regression Testing

### Known Issues Covered
1. **Cloudflare Detection**: Ensures contaminated content is flagged
2. **Operativity Keywords**: Validates keyword-based classification
3. **Policy Tag Relevance**: Checks content-tag alignment
4. **Government Body Validation**: Prevents hallucinated ministries
5. **Summary Quality**: Detects poor summaries

### Adding Regression Tests
When fixing a bug:
1. Create a test that reproduces the issue
2. Verify the test fails before the fix
3. Apply the fix
4. Verify the test passes
5. Add to regression suite

## 🛡️ Quality Gates

### Pre-commit Hooks
- Code formatting (Black, isort)
- Linting (flake8)
- Type checking (mypy)
- Security scanning (bandit)
- Unit test execution
- Coverage verification

### CI/CD Pipeline
- All test categories on pull requests
- Performance tests on schedules
- Security scans on all changes
- Deployment gates based on test results

## 📊 Coverage and Reporting

### Coverage Targets
- **Unit tests**: >90% line coverage
- **Integration tests**: >80% feature coverage
- **Combined**: >85% overall coverage

### Reports Generated
- **HTML Coverage Report**: `htmlcov/index.html`
- **JUnit XML**: For CI integration
- **Performance Reports**: Benchmark results
- **Security Reports**: Vulnerability scans

## 🔧 Configuration Files

### Key Configuration
- `pytest.ini`: Pytest settings and markers
- `.coveragerc`: Coverage configuration
- `.pre-commit-config.yaml`: Pre-commit hooks
- `requirements-test.txt`: Test dependencies

### Test Markers
```bash
# Run tests by category
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m performance   # Performance tests only
pytest -m regression    # Regression tests only
pytest -m property      # Property-based tests only
pytest -m slow          # Long-running tests
```

## 🐛 Debugging Tests

### Common Issues
1. **Mocking Problems**: Ensure proper database mocking
2. **Hebrew Text**: Handle UTF-8 encoding correctly
3. **Date Dependencies**: Use fixed dates in tests
4. **Performance Variance**: Use relative thresholds

### Debug Commands
```bash
# Run with detailed output
pytest -vvv --tb=long

# Run with pdb on failure
pytest --pdb

# Profile test performance
pytest --profile

# Run parallel tests
pytest -n auto
```

## 📋 Test Maintenance

### Regular Tasks
- Update test data when business logic changes
- Review and update performance baselines
- Clean up obsolete test cases
- Update regression tests for new issues

### Test Data Management
- Keep test datasets small and focused
- Use factories for dynamic data generation
- Avoid hardcoded values that may change
- Document test data sources and assumptions

## 🤝 Contributing to Tests

### Guidelines
1. Write tests before implementing features (TDD)
2. Use descriptive test names and docstrings
3. Follow existing patterns and conventions
4. Add regression tests for any bugs fixed
5. Update documentation when adding new test types

### Code Review Checklist
- [ ] Tests cover new functionality
- [ ] Edge cases are tested
- [ ] Performance impact is considered
- [ ] Tests are maintainable and readable
- [ ] Documentation is updated

## 📞 Support

For questions about the test suite:
1. Check existing test examples
2. Review test documentation
3. Run tests locally to understand behavior
4. Add new tests following established patterns

The test suite is designed to catch issues early and ensure the QA system maintains high quality as it processes thousands of government decisions.