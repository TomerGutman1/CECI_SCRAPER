#!/usr/bin/env python3
"""
Metrics Collection System for GOV2DB
=====================================

Collects, stores, and aggregates quality metrics for monitoring and reporting.

Features:
- Time-series metrics storage
- Metric aggregation and rollups
- Historical data retention
- Export to multiple formats
- Dashboard integration
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict, deque
import statistics
import sqlite3

logger = logging.getLogger(__name__)

@dataclass
class MetricDataPoint:
    """Single metric data point."""
    name: str
    value: float
    timestamp: str
    metadata: Dict[str, Any] = None
    tags: Dict[str, str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.tags is None:
            self.tags = {}

@dataclass
class AggregatedMetric:
    """Aggregated metric over time period."""
    name: str
    period: str  # 'hour', 'day', 'week'
    start_time: str
    end_time: str
    count: int
    min_value: float
    max_value: float
    avg_value: float
    median_value: float
    std_dev: float

class MetricsCollector:
    """
    Metrics collection and storage system with time-series capabilities.
    """

    def __init__(
        self,
        storage_dir: str = "data/monitoring/metrics",
        retention_days: int = 90
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days

        # Initialize SQLite database for time-series storage
        self.db_path = self.storage_dir / "metrics.db"
        self._init_database()

        # In-memory cache for fast access
        self.recent_metrics = defaultdict(lambda: deque(maxlen=1000))

    def _init_database(self):
        """Initialize SQLite database for metrics storage."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        value REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT,
                        tags TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes for performance
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_metrics_name_timestamp
                    ON metrics(name, timestamp)
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
                    ON metrics(timestamp)
                """)

                # Create aggregated metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aggregated_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        period TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL,
                        count INTEGER NOT NULL,
                        min_value REAL NOT NULL,
                        max_value REAL NOT NULL,
                        avg_value REAL NOT NULL,
                        median_value REAL,
                        std_dev REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_aggregated_unique
                    ON aggregated_metrics(name, period, start_time)
                """)

                conn.commit()

        except Exception as e:
            logger.error(f"Failed to initialize metrics database: {e}")

    async def save_metrics(self, metrics: List[Any]):
        """Save multiple metrics to storage."""
        if not metrics:
            return

        data_points = []

        for metric in metrics:
            # Handle both QualityMetric and dict formats
            if hasattr(metric, 'name'):
                data_point = MetricDataPoint(
                    name=metric.name,
                    value=metric.value,
                    timestamp=metric.timestamp,
                    metadata=metric.metadata if hasattr(metric, 'metadata') else {},
                    tags={'trend': getattr(metric, 'trend', 'stable')}
                )
            elif isinstance(metric, dict):
                data_point = MetricDataPoint(
                    name=metric.get('name', 'unknown'),
                    value=metric.get('value', 0),
                    timestamp=metric.get('timestamp', datetime.now().isoformat()),
                    metadata=metric.get('metadata', {}),
                    tags=metric.get('tags', {})
                )
            else:
                continue

            data_points.append(data_point)

        # Save to database
        await self._save_to_database(data_points)

        # Update in-memory cache
        for point in data_points:
            self.recent_metrics[point.name].append(point)

        logger.info(f"Saved {len(data_points)} metric data points")

    async def _save_to_database(self, data_points: List[MetricDataPoint]):
        """Save data points to SQLite database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                for point in data_points:
                    conn.execute("""
                        INSERT INTO metrics (name, value, timestamp, metadata, tags)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        point.name,
                        point.value,
                        point.timestamp,
                        json.dumps(point.metadata) if point.metadata else None,
                        json.dumps(point.tags) if point.tags else None
                    ))
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to save metrics to database: {e}")

    def get_metric_history(
        self,
        metric_name: str,
        hours: int = 24,
        limit: Optional[int] = None
    ) -> List[MetricDataPoint]:
        """Get historical data for a specific metric."""
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT name, value, timestamp, metadata, tags
                    FROM metrics
                    WHERE name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                """
                params = [metric_name, cutoff]

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                data_points = []
                for row in rows:
                    metadata = json.loads(row[3]) if row[3] else {}
                    tags = json.loads(row[4]) if row[4] else {}

                    data_points.append(MetricDataPoint(
                        name=row[0],
                        value=row[1],
                        timestamp=row[2],
                        metadata=metadata,
                        tags=tags
                    ))

                return data_points

        except Exception as e:
            logger.error(f"Failed to get metric history: {e}")
            return []

    def get_recent_metrics(self, metric_name: Optional[str] = None) -> Dict[str, List[MetricDataPoint]]:
        """Get recently cached metrics."""
        if metric_name:
            return {metric_name: list(self.recent_metrics.get(metric_name, []))}
        else:
            return {name: list(points) for name, points in self.recent_metrics.items()}

    async def aggregate_metrics(self, period: str = 'hour') -> Dict[str, List[AggregatedMetric]]:
        """Aggregate metrics by time period."""
        try:
            # Calculate time boundaries based on period
            now = datetime.now()
            if period == 'hour':
                start_time = now - timedelta(hours=24)
                time_format = '%Y-%m-%d %H:00:00'
                delta = timedelta(hours=1)
            elif period == 'day':
                start_time = now - timedelta(days=30)
                time_format = '%Y-%m-%d 00:00:00'
                delta = timedelta(days=1)
            elif period == 'week':
                start_time = now - timedelta(weeks=12)
                time_format = '%Y-%W'
                delta = timedelta(weeks=1)
            else:
                raise ValueError(f"Unsupported period: {period}")

            start_iso = start_time.isoformat()

            with sqlite3.connect(self.db_path) as conn:
                # Get all metric names
                cursor = conn.execute("""
                    SELECT DISTINCT name FROM metrics WHERE timestamp >= ?
                """, (start_iso,))
                metric_names = [row[0] for row in cursor.fetchall()]

                aggregated = {}

                for metric_name in metric_names:
                    # Get raw data for aggregation
                    cursor = conn.execute("""
                        SELECT value, timestamp FROM metrics
                        WHERE name = ? AND timestamp >= ?
                        ORDER BY timestamp
                    """, (metric_name, start_iso))

                    raw_data = [(row[0], datetime.fromisoformat(row[1])) for row in cursor.fetchall()]

                    if not raw_data:
                        continue

                    # Group data by time period
                    periods = defaultdict(list)
                    for value, timestamp in raw_data:
                        if period == 'week':
                            period_key = timestamp.strftime('%Y-W%U')
                        else:
                            period_key = timestamp.strftime(time_format)
                        periods[period_key].append(value)

                    # Calculate aggregations
                    aggregations = []
                    for period_key, values in periods.items():
                        if not values:
                            continue

                        # Parse period key back to datetime
                        if period == 'week':
                            year, week = period_key.split('-W')
                            period_start = datetime.strptime(f"{year}-W{week}-1", "%Y-W%U-%w")
                            period_end = period_start + timedelta(weeks=1)
                        else:
                            period_start = datetime.strptime(period_key, time_format)
                            period_end = period_start + delta

                        agg = AggregatedMetric(
                            name=metric_name,
                            period=period,
                            start_time=period_start.isoformat(),
                            end_time=period_end.isoformat(),
                            count=len(values),
                            min_value=min(values),
                            max_value=max(values),
                            avg_value=statistics.mean(values),
                            median_value=statistics.median(values),
                            std_dev=statistics.stdev(values) if len(values) > 1 else 0
                        )
                        aggregations.append(agg)

                    # Save aggregations to database
                    await self._save_aggregations(aggregations)
                    aggregated[metric_name] = aggregations

                return aggregated

        except Exception as e:
            logger.error(f"Failed to aggregate metrics: {e}")
            return {}

    async def _save_aggregations(self, aggregations: List[AggregatedMetric]):
        """Save aggregated metrics to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                for agg in aggregations:
                    conn.execute("""
                        INSERT OR REPLACE INTO aggregated_metrics
                        (name, period, start_time, end_time, count, min_value, max_value,
                         avg_value, median_value, std_dev)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        agg.name, agg.period, agg.start_time, agg.end_time,
                        agg.count, agg.min_value, agg.max_value,
                        agg.avg_value, agg.median_value, agg.std_dev
                    ))
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to save aggregated metrics: {e}")

    def get_metric_summary(self, metric_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get statistical summary for a metric."""
        history = self.get_metric_history(metric_name, hours)

        if not history:
            return {'error': 'No data available'}

        values = [point.value for point in history if point.value >= 0]  # Exclude error values

        if not values:
            return {'error': 'No valid data points'}

        return {
            'metric_name': metric_name,
            'time_period_hours': hours,
            'data_points': len(values),
            'latest_value': values[0] if values else None,
            'min_value': min(values),
            'max_value': max(values),
            'avg_value': statistics.mean(values),
            'median_value': statistics.median(values),
            'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
            'percentiles': {
                'p25': self._percentile(values, 25),
                'p75': self._percentile(values, 75),
                'p90': self._percentile(values, 90),
                'p95': self._percentile(values, 95)
            }
        }

    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile value."""
        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    async def export_metrics(
        self,
        format: str = 'json',
        metric_names: Optional[List[str]] = None,
        hours: int = 24
    ) -> str:
        """Export metrics data in specified format."""
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

            with sqlite3.connect(self.db_path) as conn:
                if metric_names:
                    placeholders = ','.join('?' * len(metric_names))
                    query = f"""
                        SELECT name, value, timestamp, metadata, tags
                        FROM metrics
                        WHERE name IN ({placeholders}) AND timestamp >= ?
                        ORDER BY timestamp DESC
                    """
                    params = metric_names + [cutoff]
                else:
                    query = """
                        SELECT name, value, timestamp, metadata, tags
                        FROM metrics
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC
                    """
                    params = [cutoff]

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                # Convert to data points
                data_points = []
                for row in rows:
                    metadata = json.loads(row[3]) if row[3] else {}
                    tags = json.loads(row[4]) if row[4] else {}

                    data_points.append({
                        'name': row[0],
                        'value': row[1],
                        'timestamp': row[2],
                        'metadata': metadata,
                        'tags': tags
                    })

                # Format output
                if format.lower() == 'json':
                    return json.dumps(data_points, indent=2, ensure_ascii=False)

                elif format.lower() == 'csv':
                    import csv
                    import io

                    output = io.StringIO()
                    if data_points:
                        writer = csv.DictWriter(output, fieldnames=[
                            'name', 'value', 'timestamp', 'metadata', 'tags'
                        ])
                        writer.writeheader()
                        for point in data_points:
                            # Flatten complex fields
                            row = point.copy()
                            row['metadata'] = json.dumps(row['metadata']) if row['metadata'] else ''
                            row['tags'] = json.dumps(row['tags']) if row['tags'] else ''
                            writer.writerow(row)

                    return output.getvalue()

                else:
                    raise ValueError(f"Unsupported format: {format}")

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return f"Export failed: {e}"

    async def cleanup_old_data(self):
        """Clean up old metrics data based on retention policy."""
        try:
            cutoff = (datetime.now() - timedelta(days=self.retention_days)).isoformat()

            with sqlite3.connect(self.db_path) as conn:
                # Clean raw metrics
                cursor = conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
                deleted_raw = cursor.rowcount

                # Clean aggregated metrics (keep longer)
                agg_cutoff = (datetime.now() - timedelta(days=self.retention_days * 2)).isoformat()
                cursor = conn.execute("DELETE FROM aggregated_metrics WHERE start_time < ?", (agg_cutoff,))
                deleted_agg = cursor.rowcount

                conn.commit()

            logger.info(f"Cleaned up {deleted_raw} raw metrics and {deleted_agg} aggregated metrics")
            return {'raw_deleted': deleted_raw, 'aggregated_deleted': deleted_agg}

        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return {'error': str(e)}

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get metrics data formatted for dashboard consumption."""
        try:
            # Get recent metrics for all known metric types
            dashboard_metrics = {
                'duplicate_rate': self.get_metric_summary('duplicate_rate', 24),
                'tag_confidence': self.get_metric_summary('tag_confidence', 24),
                'missing_fields_rate': self.get_metric_summary('missing_fields_rate', 24),
                'processing_performance': self.get_metric_summary('processing_performance', 24)
            }

            # Add time-series data for charts
            time_series = {}
            for metric_name in dashboard_metrics.keys():
                history = self.get_metric_history(metric_name, hours=168)  # Last week
                time_series[metric_name] = [
                    {'timestamp': point.timestamp, 'value': point.value}
                    for point in reversed(history[-50:])  # Last 50 points
                ]

            return {
                'summary': dashboard_metrics,
                'time_series': time_series,
                'last_updated': datetime.now().isoformat(),
                'data_retention_days': self.retention_days
            }

        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            return {'error': str(e)}


async def main():
    """CLI interface for metrics collection."""
    import argparse

    parser = argparse.ArgumentParser(description="Metrics Collection System")
    parser.add_argument('command', choices=['summary', 'export', 'aggregate', 'cleanup', 'dashboard'],
                       help='Command to execute')
    parser.add_argument('--metric', help='Specific metric name')
    parser.add_argument('--hours', type=int, default=24, help='Time period in hours')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Export format')
    parser.add_argument('--period', choices=['hour', 'day', 'week'], default='hour', help='Aggregation period')
    parser.add_argument('--output', help='Output file path')

    args = parser.parse_args()

    collector = MetricsCollector()

    if args.command == 'summary':
        if args.metric:
            summary = collector.get_metric_summary(args.metric, args.hours)
            print(json.dumps(summary, indent=2))
        else:
            # Show all available metrics
            recent = collector.get_recent_metrics()
            for name in recent.keys():
                summary = collector.get_metric_summary(name, args.hours)
                print(f"\n{name}:")
                print(json.dumps(summary, indent=2))

    elif args.command == 'export':
        metric_names = [args.metric] if args.metric else None
        data = await collector.export_metrics(args.format, metric_names, args.hours)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(data)
            print(f"Data exported to {args.output}")
        else:
            print(data)

    elif args.command == 'aggregate':
        aggregated = await collector.aggregate_metrics(args.period)
        print(f"Aggregated {sum(len(metrics) for metrics in aggregated.values())} metric periods")

        if args.metric and args.metric in aggregated:
            for agg in aggregated[args.metric][-5:]:  # Last 5 periods
                print(f"{agg.start_time}: avg={agg.avg_value:.2f}, min={agg.min_value:.2f}, max={agg.max_value:.2f}")

    elif args.command == 'cleanup':
        result = await collector.cleanup_old_data()
        print(f"Cleanup result: {result}")

    elif args.command == 'dashboard':
        data = collector.get_dashboard_data()
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())