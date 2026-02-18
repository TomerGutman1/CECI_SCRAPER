"""
Performance tests for batch operations in the QA system.
"""

import pytest
import time
import psutil
import os
from concurrent.futures import ThreadPoolExecutor
from src.gov_scraper.processors.qa import (
    run_scan,
    fix_operativity,
    check_operativity,
    check_content_quality,
    ALL_CHECKS
)


class TestBatchPerformance:
    """Test performance of batch operations."""

    @pytest.fixture
    def performance_records(self):
        """Generate records for performance testing."""
        def generate_record(i):
            return {
                "decision_key": f"PERF_{i}",
                "gov_num": i // 1000 + 1,
                "decision_num": i,
                "decision_title": f"החלטה מספר {i} עם כותרת ארוכה יותר לבדיקת ביצועים",
                "decision_content": f"תוכן החלטה מספר {i} " * 10,  # Longer content
                "decision_date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "operativity": "אופרטיבית" if i % 2 == 0 else "דקלרטיבית",
                "summary": f"סיכום החלטה מספר {i} עם תוכן מפורט יותר",
                "tags_policy_area": ["כלכלה ואוצר", "חינוך", "בריאות", "שונות"][i % 4],
                "tags_government_body": ["משרד האוצר", "משרד החינוך", "משרד הבריאות"][i % 3],
                "tags_locations": "ארצי"
            }
        return generate_record

    @pytest.mark.performance
    @pytest.mark.parametrize("record_count", [100, 500, 1000])
    def test_scan_performance_scaling(self, performance_records, record_count, test_config):
        """Test scan performance scaling with different dataset sizes."""
        records = [performance_records(i) for i in range(record_count)]

        start_time = time.time()
        report = run_scan(records)
        end_time = time.time()

        duration = end_time - start_time
        threshold = test_config["performance_threshold_ms"] / 1000.0  # Convert to seconds

        print(f"\nScan Performance - {record_count} records:")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Records/second: {record_count / duration:.1f}")
        print(f"  Total issues: {report.total_issues}")

        # Performance assertions
        assert duration < threshold * (record_count / 100)  # Scale with size
        assert report.total_records == record_count

        # Verify all records were processed
        for result in report.scan_results:
            assert result.total_scanned == record_count

    @pytest.mark.performance
    def test_individual_check_performance(self, performance_records):
        """Test performance of individual QA checks."""
        records = [performance_records(i) for i in range(1000)]

        performance_results = {}

        # Test key checks individually
        checks_to_test = [
            ("operativity", check_operativity),
            ("content-quality", check_content_quality),
        ]

        for check_name, check_function in checks_to_test:
            start_time = time.time()
            result = check_function(records)
            end_time = time.time()

            duration = end_time - start_time
            performance_results[check_name] = {
                "duration": duration,
                "records_per_second": len(records) / duration,
                "issues_found": result.issues_found
            }

        # Print performance summary
        print("\nIndividual Check Performance (1000 records):")
        for check_name, perf in performance_results.items():
            print(f"  {check_name}: {perf['duration']:.2f}s ({perf['records_per_second']:.0f} rec/s)")

        # All checks should complete within reasonable time
        for check_name, perf in performance_results.items():
            assert perf["duration"] < 5.0, f"{check_name} took too long: {perf['duration']:.2f}s"

    @pytest.mark.performance
    def test_memory_efficiency(self, performance_records):
        """Test memory efficiency of QA operations."""
        # Get initial memory baseline
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        record_counts = [100, 500, 1000]
        memory_usage = []

        for count in record_counts:
            records = [performance_records(i) for i in range(count)]

            # Run scan and measure memory
            run_scan(records)

            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - initial_memory
            memory_usage.append(memory_increase)

            print(f"\nMemory usage with {count} records: {memory_increase:.1f} MB")

        # Memory usage should scale reasonably (not exponentially)
        memory_per_1k_records = memory_usage[2]  # 1000 records
        assert memory_per_1k_records < 100, f"Memory usage too high: {memory_per_1k_records:.1f} MB"

        # Check that memory scales roughly linearly
        if len(memory_usage) >= 2:
            ratio = memory_usage[1] / max(memory_usage[0], 0.1)  # Avoid division by zero
            assert ratio < 10, f"Memory scaling too aggressive: {ratio:.1f}x"

    @pytest.mark.performance
    def test_batch_fixer_performance(self, performance_records):
        """Test performance of batch fix operations."""
        # Create records that need fixing
        records = []
        for i in range(500):
            record = performance_records(i)
            # Introduce operativity mismatch
            if i % 2 == 0:
                record["operativity"] = "דקלרטיבית"
                record["decision_content"] = f"החליטה לבטל פעילות {i}"
            records.append(record)

        start_time = time.time()
        updates, scan_result = fix_operativity(records, dry_run=True)
        end_time = time.time()

        duration = end_time - start_time

        print(f"\nBatch Fixer Performance (500 records):")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Records/second: {500 / duration:.1f}")
        print(f"  Updates needed: {len(updates)}")
        print(f"  Issues found: {scan_result.issues_found}")

        # Should complete within reasonable time
        assert duration < 10.0, f"Batch fixer too slow: {duration:.2f}s"
        assert scan_result.total_scanned == 500

    @pytest.mark.performance
    @pytest.mark.slow
    def test_large_dataset_performance(self, performance_records):
        """Test performance with large datasets (stress test)."""
        large_count = 5000
        records = [performance_records(i) for i in range(large_count)]

        # Test with limited checks to avoid timeout
        limited_checks = ["operativity", "content-quality", "summary-quality"]

        start_time = time.time()
        report = run_scan(records, checks=limited_checks)
        end_time = time.time()

        duration = end_time - start_time

        print(f"\nLarge Dataset Performance ({large_count} records):")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Records/second: {large_count / duration:.1f}")
        print(f"  Total issues: {report.total_issues}")
        print(f"  Checks run: {len(report.scan_results)}")

        # Should complete within reasonable time (allowing for large dataset)
        assert duration < 60.0, f"Large dataset scan too slow: {duration:.2f}s"
        assert report.total_records == large_count

        # Performance should be reasonable
        records_per_second = large_count / duration
        assert records_per_second > 50, f"Too slow: {records_per_second:.1f} records/second"

    @pytest.mark.performance
    def test_concurrent_scan_performance(self, performance_records):
        """Test performance of concurrent scan operations."""
        records = [performance_records(i) for i in range(200)]

        # Split into batches for concurrent processing
        batch_size = 50
        batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]

        def scan_batch(batch):
            return run_scan(batch, checks=["operativity", "content-quality"])

        start_time = time.time()

        # Run concurrent scans
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(scan_batch, batch) for batch in batches]
            results = [future.result() for future in futures]

        end_time = time.time()

        duration = end_time - start_time

        print(f"\nConcurrent Scan Performance:")
        print(f"  Total records: {len(records)}")
        print(f"  Batches: {len(batches)}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Records/second: {len(records) / duration:.1f}")

        # Verify all batches were processed
        assert len(results) == len(batches)
        total_processed = sum(report.total_records for report in results)
        assert total_processed == len(records)

        # Concurrent processing should be reasonably fast
        assert duration < 10.0, f"Concurrent processing too slow: {duration:.2f}s"


class TestPerformanceRegression:
    """Test for performance regressions."""

    @pytest.mark.performance
    def test_performance_baseline(self, performance_records, test_config):
        """Test performance against baseline metrics."""
        records = [performance_records(i) for i in range(100)]

        # Run multiple iterations to get stable measurement
        durations = []
        for _ in range(3):
            start_time = time.time()
            run_scan(records, checks=["operativity", "content-quality"])
            end_time = time.time()
            durations.append(end_time - start_time)

        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        print(f"\nPerformance Baseline (100 records):")
        print(f"  Average: {avg_duration:.3f}s")
        print(f"  Min: {min_duration:.3f}s")
        print(f"  Max: {max_duration:.3f}s")
        print(f"  Variance: {max_duration - min_duration:.3f}s")

        # Performance assertions
        baseline_threshold = 2.0  # 2 seconds for 100 records
        assert avg_duration < baseline_threshold, f"Performance regression: {avg_duration:.2f}s"

        # Variance should be reasonable (consistent performance)
        variance = max_duration - min_duration
        assert variance < avg_duration * 0.5, f"High performance variance: {variance:.3f}s"

    @pytest.mark.performance
    def test_check_complexity_analysis(self, performance_records):
        """Analyze performance characteristics of different checks."""
        records_small = [performance_records(i) for i in range(50)]
        records_large = [performance_records(i) for i in range(200)]

        check_performance = {}

        for check_name, check_function in [
            ("operativity", check_operativity),
            ("content-quality", check_content_quality),
        ]:
            # Test small dataset
            start_time = time.time()
            check_function(records_small)
            small_duration = time.time() - start_time

            # Test large dataset
            start_time = time.time()
            check_function(records_large)
            large_duration = time.time() - start_time

            scaling_factor = large_duration / max(small_duration, 0.001)
            theoretical_scaling = len(records_large) / len(records_small)

            check_performance[check_name] = {
                "small_duration": small_duration,
                "large_duration": large_duration,
                "scaling_factor": scaling_factor,
                "theoretical_scaling": theoretical_scaling,
                "complexity": scaling_factor / theoretical_scaling
            }

        print(f"\nCheck Complexity Analysis:")
        for check_name, perf in check_performance.items():
            print(f"  {check_name}:")
            print(f"    Small (50): {perf['small_duration']:.3f}s")
            print(f"    Large (200): {perf['large_duration']:.3f}s")
            print(f"    Scaling: {perf['scaling_factor']:.1f}x (theoretical: {perf['theoretical_scaling']:.1f}x)")
            print(f"    Complexity factor: {perf['complexity']:.2f}")

            # Complexity should be close to linear (factor near 1.0)
            assert perf["complexity"] < 2.0, f"{check_name} has poor scaling: {perf['complexity']:.2f}"

    @pytest.mark.performance
    def test_memory_leak_detection(self, performance_records):
        """Test for memory leaks in repeated operations."""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        records = [performance_records(i) for i in range(100)]

        memory_measurements = []

        # Run multiple iterations
        for iteration in range(5):
            run_scan(records, checks=["operativity"])

            current_memory = process.memory_info().rss
            memory_increase = current_memory - initial_memory
            memory_measurements.append(memory_increase)

            print(f"Iteration {iteration + 1}: {memory_increase / 1024 / 1024:.1f} MB increase")

        # Memory should not continuously increase (indicating leak)
        if len(memory_measurements) >= 3:
            # Check if memory is continuously increasing
            increasing_trend = all(
                memory_measurements[i] < memory_measurements[i + 1]
                for i in range(len(memory_measurements) - 1)
            )

            if increasing_trend:
                total_increase = memory_measurements[-1] - memory_measurements[0]
                # Allow some increase but not excessive
                assert total_increase < 10 * 1024 * 1024, f"Potential memory leak: {total_increase / 1024 / 1024:.1f} MB"


@pytest.mark.performance
@pytest.mark.parametrize("optimization_level", ["basic", "optimized"])
def test_optimization_impact(performance_records, optimization_level):
    """Test impact of different optimization levels."""
    records = [performance_records(i) for i in range(200)]

    if optimization_level == "basic":
        # Run with all checks
        checks = None
    else:
        # Run with optimized subset of checks
        checks = ["operativity", "content-quality"]

    start_time = time.time()
    report = run_scan(records, checks=checks)
    duration = time.time() - start_time

    print(f"\nOptimization Level: {optimization_level}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Checks run: {len(report.scan_results)}")
    print(f"  Records/second: {len(records) / duration:.1f}")

    if optimization_level == "optimized":
        # Optimized should be faster
        assert duration < 5.0, f"Optimized version too slow: {duration:.2f}s"