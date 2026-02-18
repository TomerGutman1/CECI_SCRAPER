#!/usr/bin/env python3
"""
Database Migration Script for GOV2DB QA System Optimization

This script orchestrates the database optimization process by:
1. Running index optimization migrations
2. Creating QA views and materialized views
3. Installing stored procedures
4. Validating performance improvements
5. Generating optimization report

Usage:
    python database/migrate.py --apply-all
    python database/migrate.py --dry-run
    python database/migrate.py --rollback
    python database/migrate.py --benchmark
"""

import os
import sys
import time
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
from psycopg2.extras import RealDictCursor
from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.db.optimized_dal import get_optimized_dal, ConnectionPoolConfig, BatchConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / 'logs' / 'migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration and Data Classes
# ============================================================================

@dataclass
class MigrationResult:
    """Result of a migration operation."""
    migration_name: str
    success: bool
    execution_time: float
    affected_objects: int
    error_message: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

@dataclass
class BenchmarkResult:
    """Performance benchmark result."""
    operation: str
    before_time: float
    after_time: float
    improvement_percentage: float
    records_tested: int

# ============================================================================
# Migration Manager
# ============================================================================

class DatabaseMigrationManager:
    """Manages database migrations and optimizations."""

    def __init__(self, connection_string: Optional[str] = None):
        self.migrations_dir = Path(__file__).parent / 'migrations'
        self.results: List[MigrationResult] = []

        # Initialize connections
        try:
            self.supabase = get_supabase_client()
            self.optimized_dal = get_optimized_dal(
                pool_config=ConnectionPoolConfig(min_connections=2, max_connections=10),
                batch_config=BatchConfig(default_batch_size=100)
            )
            logger.info("Database connections initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            raise

    def get_direct_connection(self):
        """Get direct PostgreSQL connection for DDL operations."""
        try:
            # Extract connection details from Supabase (simplified)
            # In production, this would parse the actual connection string
            return psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                database=os.getenv('DB_NAME', 'postgres'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', ''),
                sslmode='prefer'
            )
        except Exception as e:
            logger.error(f"Failed to create direct connection: {e}")
            raise

    def execute_sql_file(self, sql_file_path: Path, dry_run: bool = False) -> MigrationResult:
        """Execute a SQL migration file."""
        start_time = time.time()
        migration_name = sql_file_path.stem

        try:
            # Read SQL file
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            if dry_run:
                logger.info(f"DRY RUN: Would execute {migration_name}")
                # Parse SQL to count potential changes
                affected_objects = sql_content.count('CREATE') + sql_content.count('ALTER')
                return MigrationResult(
                    migration_name=migration_name,
                    success=True,
                    execution_time=0.0,
                    affected_objects=affected_objects,
                    warnings=["Dry run - no changes applied"]
                )

            # Execute SQL
            with self.get_direct_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Split and execute statements
                    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
                    affected_objects = 0

                    for statement in statements:
                        if statement.upper().startswith(('CREATE', 'ALTER', 'DROP', 'INSERT')):
                            cursor.execute(statement)
                            affected_objects += 1
                        elif statement.upper().startswith(('SELECT', 'WITH')):
                            # View definitions or queries
                            cursor.execute(statement)

                    conn.commit()

            execution_time = time.time() - start_time
            logger.info(f"Successfully executed {migration_name} in {execution_time:.2f}s")

            return MigrationResult(
                migration_name=migration_name,
                success=True,
                execution_time=execution_time,
                affected_objects=affected_objects
            )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Migration {migration_name} failed: {error_msg}")

            return MigrationResult(
                migration_name=migration_name,
                success=False,
                execution_time=execution_time,
                affected_objects=0,
                error_message=error_msg
            )

    def run_migrations(self, dry_run: bool = False) -> List[MigrationResult]:
        """Run all migration files in order."""
        results = []

        # Migration files in execution order
        migration_files = [
            '001_optimize_indexes.sql',
            '002_qa_views.sql',
            '003_stored_procedures.sql'
        ]

        logger.info(f"Starting migrations {'(DRY RUN)' if dry_run else ''}")

        for migration_file in migration_files:
            migration_path = self.migrations_dir / migration_file

            if not migration_path.exists():
                logger.warning(f"Migration file not found: {migration_file}")
                continue

            logger.info(f"Executing migration: {migration_file}")
            result = self.execute_sql_file(migration_path, dry_run)
            results.append(result)

            if not result.success and not dry_run:
                logger.error(f"Migration {migration_file} failed, stopping")
                break

        self.results.extend(results)
        return results

    def validate_optimizations(self) -> Dict[str, bool]:
        """Validate that optimizations were applied successfully."""
        validations = {}

        try:
            with self.get_direct_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:

                    # Check indexes
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM pg_indexes
                        WHERE tablename = 'israeli_government_decisions'
                          AND indexname LIKE 'idx_%'
                    """)
                    index_count = cursor.fetchone()['count']
                    validations['indexes_created'] = index_count >= 15

                    # Check views
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM information_schema.views
                        WHERE table_schema = 'public'
                          AND table_name IN (
                              'qa_issues_summary',
                              'content_quality_metrics',
                              'suspicious_records',
                              'qa_dashboard',
                              'government_analysis'
                          )
                    """)
                    view_count = cursor.fetchone()['count']
                    validations['views_created'] = view_count == 5

                    # Check stored procedures
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM information_schema.routines
                        WHERE routine_schema = 'public'
                          AND routine_type = 'FUNCTION'
                          AND routine_name IN (
                              'batch_update_decisions',
                              'detect_and_fix_qa_issues',
                              'collect_performance_metrics',
                              'validate_and_update_tags',
                              'database_health_check'
                          )
                    """)
                    function_count = cursor.fetchone()['count']
                    validations['procedures_created'] = function_count == 5

                    # Check optimization log table
                    cursor.execute("""
                        SELECT COUNT(*) as count
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'qa_optimization_log'
                    """)
                    log_table_exists = cursor.fetchone()['count'] == 1
                    validations['log_table_created'] = log_table_exists

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            for key in ['indexes_created', 'views_created', 'procedures_created', 'log_table_created']:
                validations[key] = False

        return validations

    def run_benchmarks(self, sample_size: int = 1000) -> List[BenchmarkResult]:
        """Run performance benchmarks to measure improvements."""
        benchmarks = []

        logger.info(f"Running performance benchmarks with {sample_size} records")

        try:
            # Benchmark 1: QA date range queries
            before_time = time.time()
            old_results = self.supabase.table("israeli_government_decisions").select(
                "decision_key,decision_date,summary,operativity"
            ).gte("decision_date", "2024-01-01").limit(sample_size).execute()
            before_time = time.time() - before_time

            after_time = time.time()
            new_results = self.optimized_dal.fetch_decisions_optimized(
                fields=["decision_key", "decision_date", "summary", "operativity"],
                filters={"decision_date": {"gte": "2024-01-01"}},
                limit=sample_size
            )
            after_time = time.time() - after_time

            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0

            benchmarks.append(BenchmarkResult(
                operation="qa_date_range_query",
                before_time=before_time,
                after_time=after_time,
                improvement_percentage=improvement,
                records_tested=len(new_results)
            ))

            # Benchmark 2: Bulk key checking
            decision_keys = [row['decision_key'] for row in (old_results.data or [])[:100]]

            before_time = time.time()
            old_existing = self.supabase.table("israeli_government_decisions").select(
                "decision_key"
            ).in_("decision_key", decision_keys).execute()
            before_time = time.time() - before_time

            after_time = time.time()
            new_existing = self.optimized_dal.check_decision_keys_optimized(decision_keys)
            after_time = time.time() - after_time

            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0

            benchmarks.append(BenchmarkResult(
                operation="bulk_key_checking",
                before_time=before_time,
                after_time=after_time,
                improvement_percentage=improvement,
                records_tested=len(decision_keys)
            ))

            # Benchmark 3: QA scan simulation
            before_time = time.time()
            # Simulate old QA scan logic
            old_scan = self.supabase.table("israeli_government_decisions").select(
                "decision_key,decision_content,summary,tags_policy_area"
            ).gte("decision_date", "2024-12-01").execute()
            before_time = time.time() - before_time

            after_time = time.time()
            new_scan = self.optimized_dal.execute_qa_scan(
                scan_type="content_quality",
                filters={"start_date": "2024-12-01", "end_date": "2024-12-31"}
            )
            after_time = time.time() - after_time

            improvement = ((before_time - after_time) / before_time * 100) if before_time > 0 else 0

            benchmarks.append(BenchmarkResult(
                operation="qa_content_scan",
                before_time=before_time,
                after_time=after_time,
                improvement_percentage=improvement,
                records_tested=new_scan.get('total_scanned', 0)
            ))

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")

        return benchmarks

    def generate_optimization_report(self,
                                   migrations: List[MigrationResult],
                                   validations: Dict[str, bool],
                                   benchmarks: List[BenchmarkResult]) -> Dict:
        """Generate comprehensive optimization report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_migrations": len(migrations),
                "successful_migrations": sum(1 for m in migrations if m.success),
                "total_execution_time": sum(m.execution_time for m in migrations),
                "validation_passed": all(validations.values()),
                "average_performance_improvement": 0.0
            },
            "migrations": [
                {
                    "name": m.migration_name,
                    "success": m.success,
                    "execution_time": m.execution_time,
                    "affected_objects": m.affected_objects,
                    "error": m.error_message,
                    "warnings": m.warnings
                }
                for m in migrations
            ],
            "validations": validations,
            "benchmarks": [
                {
                    "operation": b.operation,
                    "before_time_ms": round(b.before_time * 1000, 2),
                    "after_time_ms": round(b.after_time * 1000, 2),
                    "improvement_percentage": round(b.improvement_percentage, 1),
                    "records_tested": b.records_tested
                }
                for b in benchmarks
            ],
            "recommendations": self._generate_recommendations(migrations, validations, benchmarks)
        }

        # Calculate average improvement
        if benchmarks:
            avg_improvement = sum(b.improvement_percentage for b in benchmarks) / len(benchmarks)
            report["summary"]["average_performance_improvement"] = round(avg_improvement, 1)

        return report

    def _generate_recommendations(self,
                                migrations: List[MigrationResult],
                                validations: Dict[str, bool],
                                benchmarks: List[BenchmarkResult]) -> List[str]:
        """Generate optimization recommendations."""
        recommendations = []

        # Migration-based recommendations
        failed_migrations = [m for m in migrations if not m.success]
        if failed_migrations:
            recommendations.append(
                f"Fix {len(failed_migrations)} failed migrations before proceeding with production deployment"
            )

        # Validation-based recommendations
        if not validations.get('indexes_created', True):
            recommendations.append("Index creation incomplete - verify database permissions and retry")

        if not validations.get('views_created', True):
            recommendations.append("QA views missing - dashboard functionality will be limited")

        # Performance-based recommendations
        if benchmarks:
            low_improvement = [b for b in benchmarks if b.improvement_percentage < 20]
            if low_improvement:
                recommendations.append(
                    f"Consider additional optimization for operations with <20% improvement: "
                    f"{', '.join(b.operation for b in low_improvement)}"
                )

            high_improvement = [b for b in benchmarks if b.improvement_percentage > 70]
            if high_improvement:
                recommendations.append(
                    f"Excellent performance gains achieved in: "
                    f"{', '.join(b.operation for b in high_improvement)}"
                )

        if not recommendations:
            recommendations.append("All optimizations applied successfully - ready for production use")

        return recommendations

    def rollback_optimizations(self) -> List[MigrationResult]:
        """Rollback database optimizations (DROP statements)."""
        rollback_results = []

        logger.warning("Starting rollback of database optimizations")

        # Rollback operations in reverse order
        rollback_operations = [
            ("stored_procedures", "DROP FUNCTION IF EXISTS batch_update_decisions CASCADE"),
            ("stored_procedures", "DROP FUNCTION IF EXISTS detect_and_fix_qa_issues CASCADE"),
            ("stored_procedures", "DROP FUNCTION IF EXISTS collect_performance_metrics CASCADE"),
            ("stored_procedures", "DROP FUNCTION IF EXISTS validate_and_update_tags CASCADE"),
            ("stored_procedures", "DROP FUNCTION IF EXISTS database_health_check CASCADE"),

            ("qa_views", "DROP VIEW IF EXISTS qa_issues_summary CASCADE"),
            ("qa_views", "DROP VIEW IF EXISTS content_quality_metrics CASCADE"),
            ("qa_views", "DROP VIEW IF EXISTS suspicious_records CASCADE"),
            ("qa_views", "DROP VIEW IF EXISTS qa_dashboard CASCADE"),
            ("qa_views", "DROP VIEW IF EXISTS government_analysis CASCADE"),

            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_date_range"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_operativity_date"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_govt_date_key"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_decision_key_prefix"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_missing_summary"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_truncated_content"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_missing_tags"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_qa_url_issues"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_gin_policy_tags"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_gin_body_tags"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_gin_title_search"),
            ("optimization_indexes", "DROP INDEX IF EXISTS idx_gin_content_search"),

            ("optimization_log", "DROP TABLE IF EXISTS qa_optimization_log")
        ]

        try:
            with self.get_direct_connection() as conn:
                with conn.cursor() as cursor:
                    for operation_name, sql in rollback_operations:
                        try:
                            start_time = time.time()
                            cursor.execute(sql)
                            execution_time = time.time() - start_time

                            rollback_results.append(MigrationResult(
                                migration_name=f"rollback_{operation_name}",
                                success=True,
                                execution_time=execution_time,
                                affected_objects=1
                            ))

                            logger.info(f"Rolled back: {operation_name}")

                        except Exception as e:
                            rollback_results.append(MigrationResult(
                                migration_name=f"rollback_{operation_name}",
                                success=False,
                                execution_time=0.0,
                                affected_objects=0,
                                error_message=str(e)
                            ))

                    conn.commit()

        except Exception as e:
            logger.error(f"Rollback failed: {e}")

        return rollback_results

    def close(self):
        """Close database connections."""
        try:
            if hasattr(self, 'optimized_dal'):
                self.optimized_dal.close()
        except Exception as e:
            logger.error(f"Error closing connections: {e}")

# ============================================================================
# Main CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="GOV2DB Database Optimization Migration")
    parser.add_argument('--apply-all', action='store_true',
                       help='Apply all optimizations (indexes, views, procedures)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simulate migration without making changes')
    parser.add_argument('--rollback', action='store_true',
                       help='Rollback all optimizations')
    parser.add_argument('--benchmark', action='store_true',
                       help='Run performance benchmarks only')
    parser.add_argument('--validate', action='store_true',
                       help='Validate optimizations only')
    parser.add_argument('--report-file', default='optimization_report.json',
                       help='Output file for optimization report')
    parser.add_argument('--sample-size', type=int, default=1000,
                       help='Sample size for benchmarks')

    args = parser.parse_args()

    if not any([args.apply_all, args.dry_run, args.rollback, args.benchmark, args.validate]):
        parser.print_help()
        return 1

    migration_manager = DatabaseMigrationManager()

    try:
        migrations = []
        validations = {}
        benchmarks = []

        # Apply migrations
        if args.apply_all or args.dry_run:
            migrations = migration_manager.run_migrations(dry_run=args.dry_run)

        # Rollback
        elif args.rollback:
            migrations = migration_manager.rollback_optimizations()

        # Validate optimizations
        if args.validate or args.apply_all:
            validations = migration_manager.validate_optimizations()

        # Run benchmarks
        if args.benchmark or args.apply_all:
            benchmarks = migration_manager.run_benchmarks(args.sample_size)

        # Generate report
        if migrations or validations or benchmarks:
            report = migration_manager.generate_optimization_report(
                migrations, validations, benchmarks
            )

            # Save report
            report_file = Path(args.report_file)
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)

            logger.info(f"Optimization report saved to: {report_file}")

            # Print summary
            print(f"\n{'='*60}")
            print("DATABASE OPTIMIZATION SUMMARY")
            print(f"{'='*60}")
            print(f"Migrations: {report['summary']['successful_migrations']}/{report['summary']['total_migrations']} successful")
            print(f"Execution time: {report['summary']['total_execution_time']:.2f}s")
            print(f"Validation: {'PASSED' if report['summary']['validation_passed'] else 'FAILED'}")

            if benchmarks:
                print(f"Avg performance improvement: {report['summary']['average_performance_improvement']:.1f}%")

                print(f"\nPerformance Improvements:")
                for benchmark in report['benchmarks']:
                    print(f"  {benchmark['operation']}: {benchmark['improvement_percentage']:.1f}% faster")

            print(f"\nRecommendations:")
            for rec in report['recommendations']:
                print(f"  • {rec}")

            print(f"{'='*60}")

        return 0

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1

    finally:
        migration_manager.close()

if __name__ == '__main__':
    exit(main())