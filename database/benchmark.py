#!/usr/bin/env python3
"""
Performance Benchmark Suite for GOV2DB Database Optimization

Comprehensive benchmarking tool that measures:
1. Query performance improvements
2. Index effectiveness
3. Connection pool efficiency
4. Batch operation throughput
5. Memory usage optimization
6. Concurrent load handling

Usage:
    python database/benchmark.py --comprehensive
    python database/benchmark.py --quick --sample-size 500
    python database/benchmark.py --compare-implementations
    python database/benchmark.py --load-test --concurrent-users 10
"""

import os
import sys
import time
import json
import threading
import statistics
import argparse
import psutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib.pyplot as plt
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.db.optimized_dal import get_optimized_dal, ConnectionPoolConfig, BatchConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# Data Classes for Benchmark Results
# ============================================================================

@dataclass
class BenchmarkMetrics:
    """Individual benchmark measurement."""
    operation: str
    implementation: str  # 'supabase', 'optimized_dal', 'direct_sql'
    execution_time: float
    memory_usage_mb: float
    records_processed: int
    cpu_usage_percent: float
    success: bool = True
    error_message: Optional[str] = None

@dataclass
class LoadTestResult:
    """Load test results for concurrent operations."""
    concurrent_users: int
    operation: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput_ops_per_second: float
    peak_memory_mb: float
    peak_cpu_percent: float

@dataclass
class ComparisonResult:
    """Comparison between implementations."""
    operation: str
    baseline_time: float
    optimized_time: float
    improvement_percentage: float
    baseline_memory: float
    optimized_memory: float
    memory_reduction_percentage: float
    records_tested: int

# ============================================================================
# Performance Monitoring Utilities
# ============================================================================

class PerformanceMonitor:
    """Monitor system resources during benchmark execution."""

    def __init__(self):
        self.monitoring = False
        self.measurements = []
        self.monitor_thread = None

    def start(self):
        """Start monitoring system resources."""
        self.monitoring = True
        self.measurements = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.start()

    def stop(self):
        """Stop monitoring and return measurements."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        return self.measurements

    def _monitor_loop(self):
        """Monitor system resources in a loop."""
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_info = psutil.virtual_memory()
                process = psutil.Process(os.getpid())
                process_memory = process.memory_info().rss / 1024 / 1024  # MB

                self.measurements.append({
                    'timestamp': time.time(),
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory_info.percent,
                    'process_memory_mb': process_memory,
                    'available_memory_mb': memory_info.available / 1024 / 1024
                })

                time.sleep(0.5)  # Sample every 500ms
            except Exception as e:
                logger.warning(f"Monitoring error: {e}")

# ============================================================================
# Benchmark Suite
# ============================================================================

class DatabaseBenchmarkSuite:
    """Comprehensive database performance benchmark suite."""

    def __init__(self, sample_size: int = 1000):
        self.sample_size = sample_size
        self.results: List[BenchmarkMetrics] = []
        self.monitor = PerformanceMonitor()

        # Initialize database connections
        self.supabase = get_supabase_client()
        self.optimized_dal = get_optimized_dal(
            pool_config=ConnectionPoolConfig(
                min_connections=5,
                max_connections=20,
                connection_timeout=30
            ),
            batch_config=BatchConfig(default_batch_size=100)
        )

        logger.info(f"Initialized benchmark suite with sample size: {sample_size}")

    def _measure_performance(self, func, operation: str, implementation: str) -> BenchmarkMetrics:
        """Measure performance of a single operation."""
        # Start monitoring
        self.monitor.start()
        initial_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

        start_time = time.time()
        success = True
        error_message = None
        records_processed = 0

        try:
            result = func()
            if isinstance(result, (list, tuple)):
                records_processed = len(result)
            elif isinstance(result, dict) and 'total_processed' in result:
                records_processed = result['total_processed']
            elif isinstance(result, dict) and 'total_scanned' in result:
                records_processed = result['total_scanned']
            else:
                records_processed = 1

        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Benchmark failed for {operation} ({implementation}): {e}")

        execution_time = time.time() - start_time

        # Stop monitoring and get peak values
        measurements = self.monitor.stop()
        peak_memory = max([m['process_memory_mb'] for m in measurements], default=initial_memory)
        avg_cpu = statistics.mean([m['cpu_percent'] for m in measurements]) if measurements else 0

        return BenchmarkMetrics(
            operation=operation,
            implementation=implementation,
            execution_time=execution_time,
            memory_usage_mb=peak_memory,
            records_processed=records_processed,
            cpu_usage_percent=avg_cpu,
            success=success,
            error_message=error_message
        )

    def benchmark_qa_date_range_queries(self) -> List[BenchmarkMetrics]:
        """Benchmark QA date range queries across implementations."""
        results = []

        # Date range for testing
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        fields = ["decision_key", "decision_date", "summary", "operativity", "tags_policy_area"]

        # Supabase implementation
        def supabase_query():
            return (self.supabase.table("israeli_government_decisions")
                   .select(','.join(fields))
                   .gte("decision_date", start_date)
                   .lte("decision_date", end_date)
                   .limit(self.sample_size)
                   .execute().data)

        results.append(self._measure_performance(
            supabase_query, "qa_date_range_query", "supabase"
        ))

        # Optimized DAL implementation
        def optimized_query():
            return self.optimized_dal.fetch_decisions_optimized(
                fields=fields,
                filters={
                    'decision_date': {'gte': start_date, 'lte': end_date}
                },
                limit=self.sample_size
            )

        results.append(self._measure_performance(
            optimized_query, "qa_date_range_query", "optimized_dal"
        ))

        return results

    def benchmark_tag_filtering(self) -> List[BenchmarkMetrics]:
        """Benchmark tag-based filtering operations."""
        results = []

        # Supabase tag filtering
        def supabase_tag_filter():
            return (self.supabase.table("israeli_government_decisions")
                   .select("decision_key,tags_policy_area,tags_government_body")
                   .neq("tags_policy_area", None)
                   .neq("tags_policy_area", "")
                   .limit(self.sample_size)
                   .execute().data)

        results.append(self._measure_performance(
            supabase_tag_filter, "tag_filtering", "supabase"
        ))

        # Optimized DAL tag filtering
        def optimized_tag_filter():
            return self.optimized_dal.fetch_decisions_optimized(
                fields=["decision_key", "tags_policy_area", "tags_government_body"],
                filters={
                    'tags_policy_area': {'ne': ''},
                },
                limit=self.sample_size
            )

        results.append(self._measure_performance(
            optimized_tag_filter, "tag_filtering", "optimized_dal"
        ))

        return results

    def benchmark_bulk_operations(self) -> List[BenchmarkMetrics]:
        """Benchmark bulk key checking and update operations."""
        results = []

        # Generate test decision keys
        sample_keys = [f"37_{i}" for i in range(1000, 1000 + min(self.sample_size, 500))]

        # Supabase bulk key check
        def supabase_key_check():
            return (self.supabase.table("israeli_government_decisions")
                   .select("decision_key")
                   .in_("decision_key", sample_keys)
                   .execute().data)

        results.append(self._measure_performance(
            supabase_key_check, "bulk_key_check", "supabase"
        ))

        # Optimized DAL bulk key check
        def optimized_key_check():
            return list(self.optimized_dal.check_decision_keys_optimized(sample_keys))

        results.append(self._measure_performance(
            optimized_key_check, "bulk_key_check", "optimized_dal"
        ))

        return results

    def benchmark_qa_scans(self) -> List[BenchmarkMetrics]:
        """Benchmark QA scanning operations."""
        results = []

        # Simulate traditional QA scan (Supabase)
        def supabase_qa_scan():
            return (self.supabase.table("israeli_government_decisions")
                   .select("decision_key,decision_content,summary,tags_policy_area,operativity")
                   .gte("decision_date", "2024-11-01")
                   .limit(self.sample_size)
                   .execute().data)

        results.append(self._measure_performance(
            supabase_qa_scan, "qa_scan_simulation", "supabase"
        ))

        # Optimized QA scan
        def optimized_qa_scan():
            return self.optimized_dal.execute_qa_scan(
                scan_type="content_quality",
                filters={
                    'start_date': '2024-11-01',
                    'end_date': '2024-12-31'
                }
            )

        results.append(self._measure_performance(
            optimized_qa_scan, "qa_scan_optimized", "optimized_dal"
        ))

        return results

    def benchmark_concurrent_load(self, concurrent_users: int = 5, operations_per_user: int = 10) -> LoadTestResult:
        """Benchmark concurrent load handling."""
        logger.info(f"Starting load test: {concurrent_users} concurrent users, {operations_per_user} ops each")

        # Start monitoring
        self.monitor.start()

        start_time = time.time()
        response_times = []
        successful_ops = 0
        failed_ops = 0

        def user_simulation():
            """Simulate a single user's operations."""
            user_times = []
            user_success = 0
            user_failures = 0

            for _ in range(operations_per_user):
                op_start = time.time()
                try:
                    # Mix of different operations
                    operations = [
                        lambda: self.optimized_dal.fetch_decisions_optimized(
                            fields=['decision_key', 'decision_date'],
                            limit=50
                        ),
                        lambda: list(self.optimized_dal.check_decision_keys_optimized([f"37_{i}" for i in range(10)])),
                        lambda: self.optimized_dal.execute_qa_scan('content_quality', filters={'start_date': '2024-12-01'})
                    ]

                    # Random operation selection
                    import random
                    operation = random.choice(operations)
                    operation()

                    user_success += 1
                except Exception as e:
                    logger.warning(f"User operation failed: {e}")
                    user_failures += 1

                op_time = time.time() - op_start
                user_times.append(op_time)

            return user_times, user_success, user_failures

        # Execute concurrent users
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(user_simulation) for _ in range(concurrent_users)]

            for future in as_completed(futures):
                try:
                    user_times, user_success, user_failures = future.result()
                    response_times.extend(user_times)
                    successful_ops += user_success
                    failed_ops += user_failures
                except Exception as e:
                    logger.error(f"User thread failed: {e}")
                    failed_ops += operations_per_user

        total_time = time.time() - start_time

        # Stop monitoring and calculate metrics
        measurements = self.monitor.stop()
        peak_memory = max([m['process_memory_mb'] for m in measurements], default=0)
        peak_cpu = max([m['cpu_percent'] for m in measurements], default=0)

        # Calculate percentiles
        response_times.sort()
        p95_index = int(0.95 * len(response_times))
        p99_index = int(0.99 * len(response_times))

        return LoadTestResult(
            concurrent_users=concurrent_users,
            operation="mixed_qa_operations",
            total_operations=concurrent_users * operations_per_user,
            successful_operations=successful_ops,
            failed_operations=failed_ops,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            p95_response_time=response_times[p95_index] if response_times else 0,
            p99_response_time=response_times[p99_index] if response_times else 0,
            throughput_ops_per_second=successful_ops / total_time if total_time > 0 else 0,
            peak_memory_mb=peak_memory,
            peak_cpu_percent=peak_cpu
        )

    def run_comprehensive_benchmark(self) -> Dict:
        """Run all benchmarks and return comprehensive results."""
        logger.info("Starting comprehensive benchmark suite")

        all_results = []

        # Individual benchmarks
        benchmarks = [
            ("QA Date Range Queries", self.benchmark_qa_date_range_queries),
            ("Tag Filtering", self.benchmark_tag_filtering),
            ("Bulk Operations", self.benchmark_bulk_operations),
            ("QA Scans", self.benchmark_qa_scans)
        ]

        for name, benchmark_func in benchmarks:
            logger.info(f"Running: {name}")
            try:
                results = benchmark_func()
                all_results.extend(results)
                logger.info(f"Completed: {name} ({len(results)} measurements)")
            except Exception as e:
                logger.error(f"Benchmark {name} failed: {e}")

        # Load test
        logger.info("Running concurrent load test")
        try:
            load_test_result = self.benchmark_concurrent_load(concurrent_users=5, operations_per_user=10)
        except Exception as e:
            logger.error(f"Load test failed: {e}")
            load_test_result = None

        # Calculate comparisons
        comparisons = self._calculate_comparisons(all_results)

        return {
            'timestamp': datetime.now().isoformat(),
            'configuration': {
                'sample_size': self.sample_size,
                'connection_pool_config': asdict(self.optimized_dal.pool_config),
                'batch_config': asdict(self.optimized_dal.batch_config)
            },
            'individual_results': [asdict(r) for r in all_results],
            'load_test_result': asdict(load_test_result) if load_test_result else None,
            'comparisons': [asdict(c) for c in comparisons],
            'summary': self._generate_summary(all_results, comparisons, load_test_result)
        }

    def _calculate_comparisons(self, results: List[BenchmarkMetrics]) -> List[ComparisonResult]:
        """Calculate performance comparisons between implementations."""
        comparisons = []

        # Group results by operation
        operations = {}
        for result in results:
            if result.operation not in operations:
                operations[result.operation] = {}
            operations[result.operation][result.implementation] = result

        # Generate comparisons
        for operation, implementations in operations.items():
            if 'supabase' in implementations and 'optimized_dal' in implementations:
                baseline = implementations['supabase']
                optimized = implementations['optimized_dal']

                if baseline.success and optimized.success:
                    improvement = ((baseline.execution_time - optimized.execution_time) /
                                 baseline.execution_time * 100)

                    memory_reduction = ((baseline.memory_usage_mb - optimized.memory_usage_mb) /
                                      baseline.memory_usage_mb * 100)

                    comparisons.append(ComparisonResult(
                        operation=operation,
                        baseline_time=baseline.execution_time,
                        optimized_time=optimized.execution_time,
                        improvement_percentage=improvement,
                        baseline_memory=baseline.memory_usage_mb,
                        optimized_memory=optimized.memory_usage_mb,
                        memory_reduction_percentage=memory_reduction,
                        records_tested=optimized.records_processed
                    ))

        return comparisons

    def _generate_summary(self,
                         results: List[BenchmarkMetrics],
                         comparisons: List[ComparisonResult],
                         load_test: Optional[LoadTestResult]) -> Dict:
        """Generate benchmark summary statistics."""
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        summary = {
            'total_benchmarks': len(results),
            'successful_benchmarks': len(successful_results),
            'failed_benchmarks': len(failed_results),
            'avg_improvement_percentage': 0.0,
            'best_improvement': None,
            'worst_improvement': None,
            'total_records_tested': sum(r.records_processed for r in successful_results),
        }

        if comparisons:
            improvements = [c.improvement_percentage for c in comparisons]
            summary['avg_improvement_percentage'] = statistics.mean(improvements)

            best_comparison = max(comparisons, key=lambda c: c.improvement_percentage)
            worst_comparison = min(comparisons, key=lambda c: c.improvement_percentage)

            summary['best_improvement'] = {
                'operation': best_comparison.operation,
                'improvement': best_comparison.improvement_percentage
            }
            summary['worst_improvement'] = {
                'operation': worst_comparison.operation,
                'improvement': worst_comparison.improvement_percentage
            }

        if load_test:
            summary['load_test_summary'] = {
                'success_rate': (load_test.successful_operations /
                               load_test.total_operations * 100) if load_test.total_operations > 0 else 0,
                'throughput_ops_per_second': load_test.throughput_ops_per_second,
                'avg_response_time_ms': load_test.avg_response_time * 1000
            }

        return summary

    def generate_report(self, results: Dict, output_file: str = "benchmark_report.json"):
        """Generate detailed benchmark report."""
        # Save JSON report
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Benchmark report saved to: {output_file}")

        # Print summary to console
        self._print_console_summary(results)

        # Generate visualizations if matplotlib is available
        try:
            self._generate_visualizations(results)
        except ImportError:
            logger.info("Matplotlib not available - skipping visualizations")

    def _print_console_summary(self, results: Dict):
        """Print benchmark summary to console."""
        print("\n" + "="*70)
        print("DATABASE OPTIMIZATION BENCHMARK RESULTS")
        print("="*70)

        summary = results['summary']
        print(f"Total benchmarks: {summary['total_benchmarks']}")
        print(f"Successful: {summary['successful_benchmarks']}")
        print(f"Failed: {summary['failed_benchmarks']}")
        print(f"Records tested: {summary['total_records_tested']:,}")

        if 'avg_improvement_percentage' in summary:
            print(f"\nPerformance Improvements:")
            print(f"Average improvement: {summary['avg_improvement_percentage']:.1f}%")

            if summary.get('best_improvement'):
                best = summary['best_improvement']
                print(f"Best: {best['operation']} - {best['improvement']:.1f}% faster")

            if summary.get('worst_improvement'):
                worst = summary['worst_improvement']
                print(f"Worst: {worst['operation']} - {worst['improvement']:.1f}% faster")

        # Individual comparisons
        if results.get('comparisons'):
            print(f"\nDetailed Performance Comparisons:")
            for comp in results['comparisons']:
                print(f"  {comp['operation']}:")
                print(f"    Time: {comp['baseline_time']:.3f}s → {comp['optimized_time']:.3f}s "
                      f"({comp['improvement_percentage']:.1f}% faster)")
                print(f"    Memory: {comp['baseline_memory']:.1f}MB → {comp['optimized_memory']:.1f}MB "
                      f"({comp['memory_reduction_percentage']:.1f}% reduction)")

        # Load test results
        if results.get('load_test_result'):
            load = results['load_test_result']
            print(f"\nConcurrent Load Test ({load['concurrent_users']} users):")
            print(f"  Success rate: {summary['load_test_summary']['success_rate']:.1f}%")
            print(f"  Throughput: {load['throughput_ops_per_second']:.1f} ops/sec")
            print(f"  Avg response: {summary['load_test_summary']['avg_response_time_ms']:.1f}ms")
            print(f"  P95 response: {load['p95_response_time']*1000:.1f}ms")
            print(f"  Peak memory: {load['peak_memory_mb']:.1f}MB")

        print("="*70 + "\n")

    def _generate_visualizations(self, results: Dict):
        """Generate performance visualization charts."""
        try:
            import matplotlib.pyplot as plt
            import pandas as pd

            # Performance comparison chart
            if results.get('comparisons'):
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

                # Execution time comparison
                operations = [c['operation'] for c in results['comparisons']]
                baseline_times = [c['baseline_time'] for c in results['comparisons']]
                optimized_times = [c['optimized_time'] for c in results['comparisons']]

                x = range(len(operations))
                width = 0.35

                ax1.bar([i - width/2 for i in x], baseline_times, width, label='Baseline (Supabase)', alpha=0.7)
                ax1.bar([i + width/2 for i in x], optimized_times, width, label='Optimized DAL', alpha=0.7)
                ax1.set_ylabel('Execution Time (seconds)')
                ax1.set_title('Query Performance Comparison')
                ax1.set_xticks(x)
                ax1.set_xticklabels(operations, rotation=45, ha='right')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Improvement percentages
                improvements = [c['improvement_percentage'] for c in results['comparisons']]
                colors = ['green' if imp > 0 else 'red' for imp in improvements]

                ax2.bar(operations, improvements, color=colors, alpha=0.7)
                ax2.set_ylabel('Performance Improvement (%)')
                ax2.set_title('Performance Improvement by Operation')
                ax2.set_xticklabels(operations, rotation=45, ha='right')
                ax2.grid(True, alpha=0.3)
                ax2.axhline(y=0, color='black', linestyle='-', alpha=0.3)

                plt.tight_layout()
                plt.savefig('benchmark_performance_comparison.png', dpi=300, bbox_inches='tight')
                plt.close()

                logger.info("Performance visualization saved to: benchmark_performance_comparison.png")

        except Exception as e:
            logger.warning(f"Visualization generation failed: {e}")

    def close(self):
        """Cleanup resources."""
        try:
            self.optimized_dal.close()
        except Exception as e:
            logger.error(f"Error closing benchmark suite: {e}")

# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="GOV2DB Database Performance Benchmark")
    parser.add_argument('--comprehensive', action='store_true',
                       help='Run comprehensive benchmark suite')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick benchmark with smaller sample size')
    parser.add_argument('--load-test', action='store_true',
                       help='Run concurrent load test only')
    parser.add_argument('--compare-implementations', action='store_true',
                       help='Compare Supabase vs Optimized DAL implementations')
    parser.add_argument('--sample-size', type=int, default=1000,
                       help='Sample size for benchmarks')
    parser.add_argument('--concurrent-users', type=int, default=5,
                       help='Number of concurrent users for load test')
    parser.add_argument('--operations-per-user', type=int, default=10,
                       help='Operations per user in load test')
    parser.add_argument('--output-file', default='benchmark_report.json',
                       help='Output file for benchmark report')

    args = parser.parse_args()

    if not any([args.comprehensive, args.quick, args.load_test, args.compare_implementations]):
        parser.print_help()
        return 1

    # Adjust sample size for quick tests
    sample_size = 200 if args.quick else args.sample_size

    benchmark_suite = DatabaseBenchmarkSuite(sample_size=sample_size)

    try:
        if args.load_test:
            # Load test only
            result = benchmark_suite.benchmark_concurrent_load(
                concurrent_users=args.concurrent_users,
                operations_per_user=args.operations_per_user
            )
            print(f"\nLoad Test Results:")
            print(f"Success rate: {result.successful_operations/result.total_operations*100:.1f}%")
            print(f"Throughput: {result.throughput_ops_per_second:.1f} ops/sec")
            print(f"Avg response: {result.avg_response_time*1000:.1f}ms")

        else:
            # Full benchmark suite
            results = benchmark_suite.run_comprehensive_benchmark()
            benchmark_suite.generate_report(results, args.output_file)

        return 0

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        return 1

    finally:
        benchmark_suite.close()

if __name__ == '__main__':
    exit(main())