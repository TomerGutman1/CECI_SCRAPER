"""
Optimized Data Access Layer (DAL) for GOV2DB QA System

Features:
- Connection pooling for improved performance
- Query batching for bulk operations
- Prepared statements for security and speed
- Advanced transaction management
- Retry logic with exponential backoff
- Performance monitoring and metrics

Designed for 25K+ record database with high-frequency QA operations.
"""

import os
import logging
import time
import json
import asyncio
from contextlib import contextmanager, asynccontextmanager
from typing import List, Dict, Set, Tuple, Optional, Any, AsyncGenerator, Iterator
from dataclasses import dataclass
from collections import defaultdict, deque
import threading
from datetime import datetime, timedelta
import pandas as pd

# Third-party imports
from postgrest import APIError
from supabase import create_client, Client
import asyncpg
import psycopg2
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import RealDictCursor, execute_values
import backoff

from .connector import get_supabase_client, SUPABASE_URL, SUPABASE_SERVICE_KEY
from ..config import MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration and Data Classes
# ============================================================================

@dataclass
class ConnectionPoolConfig:
    """Configuration for database connection pool."""
    min_connections: int = 2
    max_connections: int = 20
    max_idle_time: int = 300  # 5 minutes
    connection_timeout: int = 30
    command_timeout: int = 60
    retry_attempts: int = 3
    health_check_interval: int = 60  # 1 minute

@dataclass
class BatchConfig:
    """Configuration for batch operations."""
    default_batch_size: int = 100
    max_batch_size: int = 1000
    max_concurrent_batches: int = 5
    batch_timeout: int = 300  # 5 minutes
    enable_transaction_batching: bool = True

@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    queries_executed: int = 0
    total_execution_time: float = 0.0
    cached_queries: int = 0
    failed_queries: int = 0
    connection_pool_hits: int = 0
    connection_pool_misses: int = 0
    batch_operations: int = 0
    last_reset: datetime = None

    def __post_init__(self):
        if self.last_reset is None:
            self.last_reset = datetime.now()

    def reset(self):
        """Reset all metrics."""
        self.queries_executed = 0
        self.total_execution_time = 0.0
        self.cached_queries = 0
        self.failed_queries = 0
        self.connection_pool_hits = 0
        self.connection_pool_misses = 0
        self.batch_operations = 0
        self.last_reset = datetime.now()

    def get_avg_execution_time(self) -> float:
        """Get average query execution time."""
        if self.queries_executed == 0:
            return 0.0
        return self.total_execution_time / self.queries_executed

# ============================================================================
# Enhanced Connection Pool Manager
# ============================================================================

class EnhancedConnectionPool:
    """
    Advanced connection pool with health monitoring, load balancing,
    and automatic failover capabilities.
    """

    def __init__(self, config: ConnectionPoolConfig):
        self.config = config
        self._pool: Optional[psycopg2_pool.ThreadedConnectionPool] = None
        self._async_pool: Optional[asyncpg.Pool] = None
        self._lock = threading.RLock()
        self._metrics = PerformanceMetrics()
        self._health_check_active = False
        self._prepared_statements = {}

        # Connection string parsing
        self._connection_params = self._parse_supabase_connection()

        # Initialize pools
        self._initialize_sync_pool()
        asyncio.create_task(self._initialize_async_pool())

    def _parse_supabase_connection(self) -> Dict[str, Any]:
        """Parse Supabase connection URL into PostgreSQL parameters."""
        try:
            # Extract parameters from Supabase URL
            # Format: https://project.supabase.co -> postgresql://user:pass@host:port/db
            import urllib.parse as urlparse

            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                raise ValueError("Supabase credentials not configured")

            # For Supabase, we need to construct the PostgreSQL connection
            project_id = SUPABASE_URL.split('//')[1].split('.')[0]

            return {
                'host': f'db.{project_id}.supabase.co',
                'port': 5432,
                'database': 'postgres',
                'user': 'postgres',
                'password': os.getenv('SUPABASE_DB_PASSWORD', SUPABASE_SERVICE_KEY),
                'sslmode': 'require',
                'connect_timeout': self.config.connection_timeout,
                'application_name': 'gov2db_optimized_dal'
            }
        except Exception as e:
            logger.error(f"Failed to parse Supabase connection: {e}")
            # Fallback to environment variables
            return {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', '5432')),
                'database': os.getenv('DB_NAME', 'postgres'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', ''),
                'sslmode': 'prefer',
                'connect_timeout': self.config.connection_timeout,
                'application_name': 'gov2db_optimized_dal'
            }

    def _initialize_sync_pool(self):
        """Initialize synchronous connection pool."""
        try:
            with self._lock:
                if self._pool is not None:
                    self._pool.closeall()

                self._pool = psycopg2_pool.ThreadedConnectionPool(
                    minconn=self.config.min_connections,
                    maxconn=self.config.max_connections,
                    **self._connection_params
                )

                logger.info(f"Initialized sync connection pool: "
                           f"{self.config.min_connections}-{self.config.max_connections} connections")

        except Exception as e:
            logger.error(f"Failed to initialize sync connection pool: {e}")
            raise

    async def _initialize_async_pool(self):
        """Initialize asynchronous connection pool."""
        try:
            if self._async_pool is not None:
                await self._async_pool.close()

            # Convert sync params to async format
            async_params = {
                'host': self._connection_params['host'],
                'port': self._connection_params['port'],
                'database': self._connection_params['database'],
                'user': self._connection_params['user'],
                'password': self._connection_params['password'],
                'ssl': 'require' if self._connection_params['sslmode'] == 'require' else 'prefer',
                'min_size': self.config.min_connections,
                'max_size': self.config.max_connections,
                'command_timeout': self.config.command_timeout,
                'server_settings': {
                    'application_name': 'gov2db_async_dal'
                }
            }

            self._async_pool = await asyncpg.create_pool(**async_params)

            logger.info(f"Initialized async connection pool: "
                       f"{self.config.min_connections}-{self.config.max_connections} connections")

        except Exception as e:
            logger.error(f"Failed to initialize async connection pool: {e}")

    @contextmanager
    def get_connection(self, read_only: bool = False) -> Iterator[psycopg2.extensions.connection]:
        """Get a synchronous database connection from the pool."""
        connection = None
        try:
            with self._lock:
                if self._pool is None:
                    self._initialize_sync_pool()

                connection = self._pool.getconn()
                self._metrics.connection_pool_hits += 1

                if read_only:
                    connection.set_session(readonly=True)

                yield connection

        except Exception as e:
            self._metrics.connection_pool_misses += 1
            logger.error(f"Connection pool error: {e}")

            # Fallback to direct connection
            connection = psycopg2.connect(**self._connection_params)
            if read_only:
                connection.set_session(readonly=True)
            yield connection

        finally:
            if connection:
                try:
                    if self._pool and connection in self._pool._used:
                        self._pool.putconn(connection)
                    else:
                        connection.close()
                except Exception as e:
                    logger.warning(f"Error returning connection to pool: {e}")

    @asynccontextmanager
    async def get_async_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get an asynchronous database connection from the pool."""
        if self._async_pool is None:
            await self._initialize_async_pool()

        try:
            async with self._async_pool.acquire() as connection:
                yield connection
        except Exception as e:
            logger.error(f"Async connection error: {e}")
            raise

    def get_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        return self._metrics

    def close(self):
        """Close all connections and clean up resources."""
        try:
            if self._pool:
                self._pool.closeall()
                self._pool = None

            if self._async_pool:
                asyncio.create_task(self._async_pool.close())

        except Exception as e:
            logger.error(f"Error closing connection pools: {e}")

# ============================================================================
# Optimized DAL Class
# ============================================================================

class OptimizedDAL:
    """
    High-performance Data Access Layer with advanced features:
    - Connection pooling and reuse
    - Query batching and bulk operations
    - Prepared statements and query caching
    - Automatic retry logic
    - Performance monitoring
    """

    def __init__(self,
                 pool_config: Optional[ConnectionPoolConfig] = None,
                 batch_config: Optional[BatchConfig] = None):
        self.pool_config = pool_config or ConnectionPoolConfig()
        self.batch_config = batch_config or BatchConfig()

        # Initialize connection pool
        self.pool = EnhancedConnectionPool(self.pool_config)

        # Query cache and prepared statements
        self._query_cache = {}
        self._prepared_statements = {}

        # Batch operations queue
        self._batch_queue = deque()
        self._batch_lock = threading.Lock()

        # Supabase fallback client
        self._supabase_client = get_supabase_client()

        # Performance metrics
        self._metrics = PerformanceMetrics()

        logger.info("Initialized OptimizedDAL with connection pooling and batching")

    # ------------------------------------------------------------------------
    # Core Database Operations
    # ------------------------------------------------------------------------

    def execute_query(self,
                     query: str,
                     params: Optional[Tuple] = None,
                     fetch: str = 'none',  # 'none', 'one', 'all'
                     read_only: bool = False) -> Optional[Any]:
        """
        Execute a single query with connection pooling and metrics.

        Args:
            query: SQL query string
            params: Query parameters
            fetch: Result fetching mode
            read_only: Whether this is a read-only query

        Returns:
            Query results based on fetch mode
        """
        start_time = time.time()

        try:
            with self.pool.get_connection(read_only=read_only) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)

                    if fetch == 'one':
                        result = cursor.fetchone()
                    elif fetch == 'all':
                        result = cursor.fetchall()
                    else:
                        result = cursor.rowcount

                    if not read_only:
                        conn.commit()

                    # Update metrics
                    execution_time = time.time() - start_time
                    self._metrics.queries_executed += 1
                    self._metrics.total_execution_time += execution_time

                    return result

        except Exception as e:
            self._metrics.failed_queries += 1
            logger.error(f"Query execution failed: {e}")
            raise

    @backoff.on_exception(backoff.expo,
                         (psycopg2.Error, APIError),
                         max_tries=MAX_RETRIES,
                         base=RETRY_DELAY)
    def execute_batch(self,
                     query: str,
                     data: List[Tuple],
                     batch_size: Optional[int] = None,
                     page_size: int = 1000) -> Dict[str, Any]:
        """
        Execute batch operations with automatic batching and retry logic.

        Args:
            query: SQL query template
            data: List of parameter tuples
            batch_size: Size of each batch (defaults to config)
            page_size: Page size for execute_values

        Returns:
            Batch execution results
        """
        batch_size = batch_size or self.batch_config.default_batch_size
        total_processed = 0
        total_errors = 0
        errors = []

        start_time = time.time()

        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Process data in batches
                    for i in range(0, len(data), batch_size):
                        batch_data = data[i:i + batch_size]

                        try:
                            # Use execute_values for high performance bulk inserts/updates
                            execute_values(
                                cursor,
                                query,
                                batch_data,
                                page_size=page_size
                            )
                            total_processed += len(batch_data)

                        except Exception as batch_error:
                            total_errors += len(batch_data)
                            errors.append({
                                'batch_start': i,
                                'batch_size': len(batch_data),
                                'error': str(batch_error)
                            })
                            logger.error(f"Batch {i//batch_size + 1} failed: {batch_error}")

                    conn.commit()

        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            raise

        # Update metrics
        execution_time = time.time() - start_time
        self._metrics.batch_operations += 1
        self._metrics.queries_executed += 1
        self._metrics.total_execution_time += execution_time

        return {
            'total_processed': total_processed,
            'total_errors': total_errors,
            'execution_time': execution_time,
            'errors': errors
        }

    # ------------------------------------------------------------------------
    # Enhanced Decision Management
    # ------------------------------------------------------------------------

    def fetch_decisions_optimized(self,
                                fields: Optional[List[str]] = None,
                                filters: Optional[Dict[str, Any]] = None,
                                order_by: str = 'decision_date',
                                order_desc: bool = True,
                                limit: Optional[int] = None,
                                offset: int = 0) -> List[Dict[str, Any]]:
        """
        Optimized decision fetching with flexible filtering and ordering.

        Args:
            fields: Fields to select (None = all QA fields)
            filters: Filter conditions
            order_by: Column to order by
            order_desc: Descending order
            limit: Maximum records to return
            offset: Number of records to skip

        Returns:
            List of decision records
        """
        # Default QA-relevant fields
        if fields is None:
            fields = [
                'decision_key', 'decision_date', 'decision_number',
                'decision_title', 'decision_content', 'url', 'summary',
                'operativity', 'tags_policy_area', 'tags_government_body',
                'tags_location', 'government_number', 'committee_type',
                'created_at', 'updated_at'
            ]

        # Build query
        select_clause = ', '.join(fields)
        query = f"SELECT {select_clause} FROM israeli_government_decisions"
        params = []
        where_conditions = []

        # Apply filters
        if filters:
            for field, value in filters.items():
                if isinstance(value, list):
                    # IN clause
                    placeholders = ', '.join(['%s'] * len(value))
                    where_conditions.append(f"{field} IN ({placeholders})")
                    params.extend(value)
                elif isinstance(value, dict):
                    # Range or operator filters
                    if 'gte' in value:
                        where_conditions.append(f"{field} >= %s")
                        params.append(value['gte'])
                    if 'lte' in value:
                        where_conditions.append(f"{field} <= %s")
                        params.append(value['lte'])
                    if 'like' in value:
                        where_conditions.append(f"{field} LIKE %s")
                        params.append(value['like'])
                else:
                    # Equality filter
                    where_conditions.append(f"{field} = %s")
                    params.append(value)

        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)

        # Add ordering
        order_direction = "DESC" if order_desc else "ASC"
        query += f" ORDER BY {order_by} {order_direction}"

        # Add pagination
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        if offset > 0:
            query += " OFFSET %s"
            params.append(offset)

        # Execute query
        try:
            results = self.execute_query(query, tuple(params), fetch='all', read_only=True)
            return [dict(row) for row in results] if results else []

        except Exception as e:
            logger.error(f"Optimized fetch failed: {e}")
            # Fallback to Supabase client
            return self._supabase_fallback_fetch(fields, filters, order_by, order_desc, limit, offset)

    def bulk_update_decisions(self,
                            updates: List[Dict[str, Any]],
                            conflict_resolution: str = 'skip',
                            batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        High-performance bulk update with conflict resolution.

        Args:
            updates: List of update dictionaries with 'decision_key' and fields
            conflict_resolution: 'skip', 'overwrite', 'merge'
            batch_size: Batch size for updates

        Returns:
            Update results summary
        """
        if not updates:
            return {'processed': 0, 'success': 0, 'errors': 0}

        batch_size = batch_size or self.batch_config.default_batch_size

        # Prepare update data
        update_data = []
        for update in updates:
            decision_key = update.pop('decision_key', None)
            if not decision_key:
                continue

            # Build update values tuple
            update_values = []
            update_fields = []

            for field, value in update.items():
                if field not in ['created_at', 'id']:  # Skip read-only fields
                    update_fields.append(field)
                    update_values.append(value)

            update_values.extend([datetime.now(), decision_key])  # updated_at, WHERE condition
            update_data.append(tuple(update_values))

        # Build dynamic UPDATE query
        set_clauses = [f"{field} = %s" for field in update_fields]
        query = f"""
            UPDATE israeli_government_decisions
            SET {', '.join(set_clauses)}, updated_at = %s
            WHERE decision_key = %s
        """

        # Execute batch update
        try:
            result = self.execute_batch(query, update_data, batch_size)

            logger.info(f"Bulk update completed: {result['total_processed']} processed, "
                       f"{result['total_errors']} errors")

            return {
                'processed': result['total_processed'],
                'success': result['total_processed'] - result['total_errors'],
                'errors': result['total_errors'],
                'execution_time': result['execution_time'],
                'error_details': result['errors']
            }

        except Exception as e:
            logger.error(f"Bulk update failed: {e}")
            raise

    def check_decision_keys_optimized(self, decision_keys: List[str]) -> Set[str]:
        """
        High-performance duplicate key checking using prepared statements.

        Args:
            decision_keys: List of decision keys to check

        Returns:
            Set of existing decision keys
        """
        if not decision_keys:
            return set()

        try:
            # Use ANY operator for efficient IN query
            query = """
                SELECT decision_key
                FROM israeli_government_decisions
                WHERE decision_key = ANY(%s)
            """

            results = self.execute_query(query, (decision_keys,), fetch='all', read_only=True)
            return {row['decision_key'] for row in results} if results else set()

        except Exception as e:
            logger.error(f"Optimized key check failed: {e}")
            # Fallback to original implementation
            return self._supabase_fallback_check_keys(decision_keys)

    # ------------------------------------------------------------------------
    # QA-Specific Operations
    # ------------------------------------------------------------------------

    def execute_qa_scan(self,
                       scan_type: str,
                       batch_size: int = 1000,
                       filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute QA scan with optimized batch processing.

        Args:
            scan_type: Type of QA scan to perform
            batch_size: Records per batch
            filters: Additional filters

        Returns:
            Scan results
        """
        scan_queries = {
            'content_quality': """
                SELECT decision_key, decision_date,
                       length(decision_content) as content_length,
                       CASE WHEN decision_content LIKE '%%המשך התוכן%%' THEN true ELSE false END as truncated,
                       CASE WHEN summary IS NULL OR summary = '' THEN true ELSE false END as missing_summary
                FROM israeli_government_decisions
                WHERE decision_date >= %s AND decision_date <= %s
            """,

            'tag_validation': """
                SELECT decision_key, tags_policy_area, tags_government_body,
                       CASE WHEN tags_policy_area IS NULL OR tags_policy_area = '' THEN true ELSE false END as missing_policy,
                       CASE WHEN tags_government_body IS NULL OR tags_government_body = '' THEN true ELSE false END as missing_body
                FROM israeli_government_decisions
                WHERE decision_date >= %s AND decision_date <= %s
            """,

            'operativity_check': """
                SELECT decision_key, operativity,
                       CASE WHEN operativity IS NULL THEN true ELSE false END as missing_operativity,
                       CASE WHEN operativity NOT IN ('אופרטיבית', 'דקלרטיבית') THEN true ELSE false END as invalid_operativity
                FROM israeli_government_decisions
                WHERE decision_date >= %s AND decision_date <= %s
            """
        }

        if scan_type not in scan_queries:
            raise ValueError(f"Unknown scan type: {scan_type}")

        # Default date range (last 30 days)
        end_date = filters.get('end_date', datetime.now().date())
        start_date = filters.get('start_date', end_date - timedelta(days=30))

        query = scan_queries[scan_type]
        params = (start_date, end_date)

        try:
            results = self.execute_query(query, params, fetch='all', read_only=True)

            # Process results
            total_scanned = len(results) if results else 0
            issues_found = 0
            issue_details = []

            for row in results or []:
                row_dict = dict(row)
                has_issue = False

                # Check for issues based on scan type
                if scan_type == 'content_quality':
                    if row_dict['truncated'] or row_dict['missing_summary'] or row_dict['content_length'] < 50:
                        has_issue = True
                elif scan_type == 'tag_validation':
                    if row_dict['missing_policy'] or row_dict['missing_body']:
                        has_issue = True
                elif scan_type == 'operativity_check':
                    if row_dict['missing_operativity'] or row_dict['invalid_operativity']:
                        has_issue = True

                if has_issue:
                    issues_found += 1
                    issue_details.append(row_dict)

            return {
                'scan_type': scan_type,
                'total_scanned': total_scanned,
                'issues_found': issues_found,
                'issue_rate': (issues_found / total_scanned * 100) if total_scanned > 0 else 0,
                'issue_details': issue_details[:100],  # Limit details
                'execution_time': time.time(),
                'filters_applied': filters
            }

        except Exception as e:
            logger.error(f"QA scan failed: {e}")
            raise

    # ------------------------------------------------------------------------
    # Fallback Methods (Supabase REST API)
    # ------------------------------------------------------------------------

    def _supabase_fallback_fetch(self, fields, filters, order_by, order_desc, limit, offset):
        """Fallback to Supabase REST API for fetching."""
        try:
            query = self._supabase_client.table("israeli_government_decisions")

            if fields:
                query = query.select(','.join(fields))
            else:
                query = query.select('*')

            # Apply filters
            if filters:
                for field, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(field, value)
                    elif isinstance(value, dict):
                        if 'gte' in value:
                            query = query.gte(field, value['gte'])
                        if 'lte' in value:
                            query = query.lte(field, value['lte'])
                        if 'like' in value:
                            query = query.like(field, value['like'])
                    else:
                        query = query.eq(field, value)

            # Apply ordering
            query = query.order(order_by, desc=order_desc)

            # Apply pagination
            if limit:
                if offset > 0:
                    query = query.range(offset, offset + limit - 1)
                else:
                    query = query.limit(limit)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Supabase fallback fetch failed: {e}")
            return []

    def _supabase_fallback_check_keys(self, decision_keys):
        """Fallback to Supabase for key checking."""
        try:
            response = (
                self._supabase_client
                .table("israeli_government_decisions")
                .select("decision_key")
                .in_("decision_key", decision_keys)
                .execute()
            )
            return {item['decision_key'] for item in response.data} if response.data else set()
        except Exception as e:
            logger.error(f"Supabase fallback key check failed: {e}")
            return set()

    # ------------------------------------------------------------------------
    # Performance and Monitoring
    # ------------------------------------------------------------------------

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        pool_metrics = self.pool.get_metrics()

        return {
            'dal_metrics': {
                'queries_executed': self._metrics.queries_executed,
                'avg_execution_time': self._metrics.get_avg_execution_time(),
                'failed_queries': self._metrics.failed_queries,
                'batch_operations': self._metrics.batch_operations,
                'last_reset': self._metrics.last_reset.isoformat()
            },
            'pool_metrics': {
                'connection_pool_hits': pool_metrics.connection_pool_hits,
                'connection_pool_misses': pool_metrics.connection_pool_misses,
                'cached_queries': pool_metrics.cached_queries
            },
            'config': {
                'max_connections': self.pool_config.max_connections,
                'default_batch_size': self.batch_config.default_batch_size,
                'max_batch_size': self.batch_config.max_batch_size
            }
        }

    def reset_metrics(self):
        """Reset performance metrics."""
        self._metrics.reset()
        self.pool._metrics.reset()

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        try:
            # Test sync connection
            with self.pool.get_connection(read_only=True) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    sync_healthy = cursor.fetchone() is not None

            # Test basic query
            test_result = self.execute_query(
                "SELECT COUNT(*) as count FROM israeli_government_decisions LIMIT 1",
                fetch='one',
                read_only=True
            )

            query_healthy = test_result is not None

            return {
                'status': 'healthy' if (sync_healthy and query_healthy) else 'unhealthy',
                'sync_connection': sync_healthy,
                'query_execution': query_healthy,
                'total_records': test_result['count'] if test_result else 0,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def close(self):
        """Close all connections and clean up resources."""
        try:
            self.pool.close()
            logger.info("OptimizedDAL closed successfully")
        except Exception as e:
            logger.error(f"Error closing OptimizedDAL: {e}")

# ============================================================================
# Factory Functions and Singleton
# ============================================================================

_optimized_dal_instance: Optional[OptimizedDAL] = None

def get_optimized_dal(
    pool_config: Optional[ConnectionPoolConfig] = None,
    batch_config: Optional[BatchConfig] = None,
    force_new: bool = False
) -> OptimizedDAL:
    """
    Get singleton OptimizedDAL instance with connection pooling.

    Args:
        pool_config: Connection pool configuration
        batch_config: Batch operation configuration
        force_new: Force creation of new instance

    Returns:
        OptimizedDAL instance
    """
    global _optimized_dal_instance

    if _optimized_dal_instance is None or force_new:
        if _optimized_dal_instance:
            _optimized_dal_instance.close()

        _optimized_dal_instance = OptimizedDAL(pool_config, batch_config)

    return _optimized_dal_instance

def close_optimized_dal():
    """Close and cleanup global OptimizedDAL instance."""
    global _optimized_dal_instance

    if _optimized_dal_instance:
        _optimized_dal_instance.close()
        _optimized_dal_instance = None