"""
Test runner and reporting utilities for QA test suite.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class TestResult:
    """Represents the result of a test run."""
    test_name: str
    status: str  # "passed", "failed", "skipped"
    duration: float
    error_message: Optional[str] = None
    markers: List[str] = None


@dataclass
class TestSuiteResult:
    """Represents the result of a complete test suite run."""
    suite_name: str
    start_time: datetime
    end_time: datetime
    total_tests: int
    passed: int
    failed: int
    skipped: int
    error_count: int
    duration: float
    coverage_percentage: float
    tests: List[TestResult]


class QATestRunner:
    """Test runner for QA test suite with enhanced reporting."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.test_results_dir = self.project_root / "test-results"
        self.test_results_dir.mkdir(exist_ok=True)

    def run_unit_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run unit tests."""
        return self._run_test_suite(
            "Unit Tests",
            ["tests/qa/unit/"],
            markers=["unit"],
            verbose=verbose
        )

    def run_integration_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run integration tests."""
        return self._run_test_suite(
            "Integration Tests",
            ["tests/qa/integration/"],
            markers=["integration"],
            verbose=verbose
        )

    def run_performance_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run performance tests."""
        return self._run_test_suite(
            "Performance Tests",
            ["tests/qa/performance/"],
            markers=["performance"],
            verbose=verbose
        )

    def run_regression_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run regression tests."""
        return self._run_test_suite(
            "Regression Tests",
            ["tests/qa/regression/"],
            markers=["regression"],
            verbose=verbose
        )

    def run_property_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run property-based tests."""
        return self._run_test_suite(
            "Property Tests",
            ["tests/qa/property/"],
            markers=["property"],
            verbose=verbose
        )

    def run_smoke_tests(self, verbose: bool = True) -> TestSuiteResult:
        """Run quick smoke tests."""
        return self._run_test_suite(
            "Smoke Tests",
            ["tests/qa/"],
            markers=["smoke"],
            verbose=verbose
        )

    def run_all_tests(self, verbose: bool = True, include_slow: bool = False) -> List[TestSuiteResult]:
        """Run all test suites."""
        suites = []

        print("🧪 Running GOV2DB QA Test Suite")
        print("=" * 50)

        # Unit tests (fast)
        print("\n📋 Running Unit Tests...")
        suites.append(self.run_unit_tests(verbose=False))

        # Integration tests
        print("\n🔗 Running Integration Tests...")
        suites.append(self.run_integration_tests(verbose=False))

        # Regression tests
        print("\n🔄 Running Regression Tests...")
        suites.append(self.run_regression_tests(verbose=False))

        # Property tests
        print("\n🎯 Running Property Tests...")
        suites.append(self.run_property_tests(verbose=False))

        if include_slow:
            # Performance tests (slow)
            print("\n⚡ Running Performance Tests...")
            suites.append(self.run_performance_tests(verbose=False))

        # Generate combined report
        self._generate_combined_report(suites)

        return suites

    def _run_test_suite(
        self,
        suite_name: str,
        test_paths: List[str],
        markers: Optional[List[str]] = None,
        verbose: bool = True
    ) -> TestSuiteResult:
        """Run a specific test suite."""
        start_time = datetime.now()

        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short",
            "--junitxml=" + str(self.test_results_dir / f"{suite_name.lower().replace(' ', '_')}.xml"),
            "--cov=src/gov_scraper/processors/qa",
            "--cov-report=term-missing",
            "--cov-report=xml:" + str(self.test_results_dir / f"coverage_{suite_name.lower().replace(' ', '_')}.xml"),
        ]

        if verbose:
            cmd.append("-v")

        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        cmd.extend(test_paths)

        # Run tests
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300  # 5 minute timeout
            )

            output = result.stdout
            error_output = result.stderr

            if verbose:
                print(output)
                if error_output:
                    print("STDERR:", error_output)

        except subprocess.TimeoutExpired:
            return TestSuiteResult(
                suite_name=suite_name,
                start_time=start_time,
                end_time=datetime.now(),
                total_tests=0,
                passed=0,
                failed=1,
                skipped=0,
                error_count=1,
                duration=300.0,
                coverage_percentage=0.0,
                tests=[TestResult(
                    test_name="Test Suite",
                    status="failed",
                    duration=300.0,
                    error_message="Test suite timed out after 5 minutes"
                )]
            )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Parse results
        test_results = self._parse_pytest_output(output)
        coverage_percentage = self._extract_coverage_percentage(output)

        # Count results
        passed = len([t for t in test_results if t.status == "passed"])
        failed = len([t for t in test_results if t.status == "failed"])
        skipped = len([t for t in test_results if t.status == "skipped"])

        suite_result = TestSuiteResult(
            suite_name=suite_name,
            start_time=start_time,
            end_time=end_time,
            total_tests=len(test_results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            error_count=failed,
            duration=duration,
            coverage_percentage=coverage_percentage,
            tests=test_results
        )

        # Print summary
        print(f"\n{suite_name} Summary:")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⏭️  Skipped: {skipped}")
        print(f"  📊 Coverage: {coverage_percentage:.1f}%")
        print(f"  ⏱️  Duration: {duration:.2f}s")

        return suite_result

    def _parse_pytest_output(self, output: str) -> List[TestResult]:
        """Parse pytest output to extract test results."""
        results = []
        lines = output.split('\n')

        for line in lines:
            if '::' in line and any(status in line for status in ['PASSED', 'FAILED', 'SKIPPED']):
                parts = line.split(' ')
                if len(parts) >= 2:
                    test_name = parts[0]
                    status_part = [p for p in parts if p in ['PASSED', 'FAILED', 'SKIPPED']]
                    if status_part:
                        status = status_part[0].lower()

                        # Extract duration if available
                        duration = 0.0
                        for part in parts:
                            if 's' in part and part.replace('.', '').replace('s', '').isdigit():
                                try:
                                    duration = float(part.replace('s', ''))
                                except:
                                    pass

                        results.append(TestResult(
                            test_name=test_name,
                            status=status,
                            duration=duration
                        ))

        return results

    def _extract_coverage_percentage(self, output: str) -> float:
        """Extract coverage percentage from pytest output."""
        lines = output.split('\n')
        for line in lines:
            if 'TOTAL' in line and '%' in line:
                parts = line.split()
                for part in parts:
                    if '%' in part:
                        try:
                            return float(part.replace('%', ''))
                        except:
                            continue
        return 0.0

    def _generate_combined_report(self, suites: List[TestSuiteResult]):
        """Generate a combined HTML report."""
        total_tests = sum(s.total_tests for s in suites)
        total_passed = sum(s.passed for s in suites)
        total_failed = sum(s.failed for s in suites)
        total_skipped = sum(s.skipped for s in suites)
        avg_coverage = sum(s.coverage_percentage for s in suites) / len(suites) if suites else 0

        print(f"\n🎯 Overall Test Results:")
        print(f"=" * 30)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {total_passed} ({total_passed/max(total_tests,1)*100:.1f}%)")
        print(f"❌ Failed: {total_failed} ({total_failed/max(total_tests,1)*100:.1f}%)")
        print(f"⏭️  Skipped: {total_skipped} ({total_skipped/max(total_tests,1)*100:.1f}%)")
        print(f"📊 Avg Coverage: {avg_coverage:.1f}%")

        # Generate JSON report
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "skipped": total_skipped,
                "average_coverage": avg_coverage,
                "success_rate": total_passed / max(total_tests, 1) * 100
            },
            "suites": [asdict(suite) for suite in suites]
        }

        report_path = self.test_results_dir / "combined_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, default=str)

        print(f"📄 Detailed report saved to: {report_path}")

        # Generate simple HTML report
        self._generate_html_report(report_data)

    def _generate_html_report(self, report_data: Dict[str, Any]):
        """Generate a simple HTML report."""
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>GOV2DB QA Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .summary { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .suite { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }
        .passed { color: #28a745; }
        .failed { color: #dc3545; }
        .skipped { color: #ffc107; }
        .coverage { color: #17a2b8; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 8px; text-align: left; border: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
    </style>
</head>
<body>
    <h1>🧪 GOV2DB QA Test Report</h1>

    <div class="summary">
        <h2>📊 Summary</h2>
        <p><strong>Generated:</strong> {timestamp}</p>
        <p><strong>Total Tests:</strong> {total_tests}</p>
        <p><strong>✅ Passed:</strong> <span class="passed">{passed} ({success_rate:.1f}%)</span></p>
        <p><strong>❌ Failed:</strong> <span class="failed">{failed}</span></p>
        <p><strong>⏭️ Skipped:</strong> <span class="skipped">{skipped}</span></p>
        <p><strong>📊 Average Coverage:</strong> <span class="coverage">{average_coverage:.1f}%</span></p>
    </div>

    <h2>📋 Test Suites</h2>
    {suites_html}
</body>
</html>
        """.strip()

        suites_html = ""
        for suite in report_data["suites"]:
            suite_html = f"""
            <div class="suite">
                <h3>{suite['suite_name']}</h3>
                <p><strong>Duration:</strong> {suite['duration']:.2f}s</p>
                <p><strong>✅ Passed:</strong> <span class="passed">{suite['passed']}</span></p>
                <p><strong>❌ Failed:</strong> <span class="failed">{suite['failed']}</span></p>
                <p><strong>⏭️ Skipped:</strong> <span class="skipped">{suite['skipped']}</span></p>
                <p><strong>📊 Coverage:</strong> <span class="coverage">{suite['coverage_percentage']:.1f}%</span></p>
            </div>
            """
            suites_html += suite_html

        html_content = html_template.format(
            timestamp=report_data["timestamp"],
            total_tests=report_data["summary"]["total_tests"],
            passed=report_data["summary"]["passed"],
            failed=report_data["summary"]["failed"],
            skipped=report_data["summary"]["skipped"],
            success_rate=report_data["summary"]["success_rate"],
            average_coverage=report_data["summary"]["average_coverage"],
            suites_html=suites_html
        )

        html_path = self.test_results_dir / "test_report.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"🌐 HTML report saved to: {html_path}")


def main():
    """Main entry point for test runner."""
    import argparse

    parser = argparse.ArgumentParser(description="GOV2DB QA Test Runner")
    parser.add_argument("--suite", choices=["unit", "integration", "performance", "regression", "property", "all"],
                       default="all", help="Test suite to run")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--include-slow", action="store_true", help="Include slow tests")

    args = parser.parse_args()

    runner = QATestRunner()

    if args.suite == "unit":
        runner.run_unit_tests(verbose=args.verbose)
    elif args.suite == "integration":
        runner.run_integration_tests(verbose=args.verbose)
    elif args.suite == "performance":
        runner.run_performance_tests(verbose=args.verbose)
    elif args.suite == "regression":
        runner.run_regression_tests(verbose=args.verbose)
    elif args.suite == "property":
        runner.run_property_tests(verbose=args.verbose)
    elif args.suite == "all":
        runner.run_all_tests(verbose=args.verbose, include_slow=args.include_slow)


if __name__ == "__main__":
    main()