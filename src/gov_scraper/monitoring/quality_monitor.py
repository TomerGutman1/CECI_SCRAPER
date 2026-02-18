#!/usr/bin/env python3
"""
Real-time Quality Monitor for GOV2DB
=====================================

Continuous monitoring system that tracks data quality metrics, detects anomalies,
and triggers alerts based on configurable thresholds.

Key Features:
- Real-time duplicate rate monitoring (alert >5%)
- Tag confidence tracking (alert <60% avg)
- Missing fields detection and trending
- Anomaly detection using statistical methods
- Performance metrics collection
- Automated alert generation
- Historical trend analysis

Monitoring Targets:
- Data Quality: duplicates, missing fields, invalid values
- Content Quality: tag accuracy, summary quality, operativity consistency
- Processing Performance: sync times, QA processing rates, error rates
- System Health: database connectivity, API response times, memory usage
"""

import os
import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from pathlib import Path
import time
import asyncio

from ..db.connector import get_supabase_client
from .alert_manager import AlertManager
from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)

@dataclass
class QualityMetric:
    """Individual quality metric measurement."""
    name: str
    value: float
    timestamp: str
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    trend: Optional[str] = None  # 'improving', 'degrading', 'stable'
    metadata: Dict[str, Any] = None

@dataclass
class AnomalyResult:
    """Result of anomaly detection analysis."""
    is_anomaly: bool
    confidence: float
    expected_range: Tuple[float, float]
    current_value: float
    description: str

class QualityMonitor:
    """
    Real-time quality monitoring system with anomaly detection and alerting.

    Monitors key quality indicators and triggers alerts when thresholds are exceeded
    or anomalies are detected in data patterns.
    """

    def __init__(
        self,
        config_file: str = "config/monitoring_alerts.yaml",
        metrics_history_days: int = 30,
        anomaly_window_hours: int = 24
    ):
        self.config_file = Path(config_file)
        self.metrics_history_days = metrics_history_days
        self.anomaly_window_hours = anomaly_window_hours

        # Initialize components
        self.client = get_supabase_client()
        self.alert_manager = AlertManager()
        self.metrics_collector = MetricsCollector()

        # Load configuration
        self.config = self._load_config()

        # In-memory metrics cache for fast access
        self.metrics_cache = {}
        self.historical_metrics = defaultdict(lambda: deque(maxlen=1000))

        # Monitoring state
        self.monitoring_active = False
        self.last_full_scan = None

    def _load_config(self) -> Dict:
        """Load monitoring configuration from YAML file."""
        default_config = {
            'thresholds': {
                'duplicate_rate_warning': 3.0,
                'duplicate_rate_critical': 5.0,
                'tag_confidence_warning': 65.0,
                'tag_confidence_critical': 60.0,
                'missing_fields_warning': 5.0,
                'missing_fields_critical': 10.0,
                'processing_time_warning': 300,  # seconds
                'processing_time_critical': 600,
                'error_rate_warning': 2.0,
                'error_rate_critical': 5.0
            },
            'anomaly_detection': {
                'enabled': True,
                'sensitivity': 2.0,  # Standard deviations
                'min_samples': 10
            },
            'monitoring_intervals': {
                'quality_check_minutes': 15,
                'performance_check_minutes': 5,
                'anomaly_check_minutes': 30
            },
            'alerts': {
                'channels': ['log', 'dashboard'],
                'cooldown_minutes': 60,
                'escalation_hours': 4
            }
        }

        if self.config_file.exists():
            try:
                import yaml
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                    # Merge with defaults
                    for key, value in user_config.items():
                        if isinstance(value, dict) and key in default_config:
                            default_config[key].update(value)
                        else:
                            default_config[key] = value
            except Exception as e:
                logger.warning(f"Failed to load config file, using defaults: {e}")

        return default_config

    async def check_duplicate_rate(self) -> QualityMetric:
        """Monitor duplicate decision rates in real-time."""
        try:
            # Get recent decisions (last 7 days)
            recent_cutoff = (datetime.now() - timedelta(days=7)).isoformat()

            # Count total recent decisions
            total_query = self.client.table('israeli_government_decisions')\
                .select('decision_key', count='exact')\
                .gte('decision_date', recent_cutoff)
            total_result = total_query.execute()
            total_count = total_result.count

            # Find potential duplicates by title similarity and date proximity
            decisions_query = self.client.table('israeli_government_decisions')\
                .select('decision_key,title,decision_date,gov_num,decision_num')\
                .gte('decision_date', recent_cutoff)\
                .order('decision_date', desc=True)

            decisions = decisions_query.execute().data

            # Detect duplicates using title similarity and date proximity
            potential_duplicates = []
            seen_titles = {}

            for decision in decisions:
                title = decision.get('title', '').strip()
                date = decision.get('decision_date', '')

                if not title or len(title) < 10:
                    continue

                # Check for similar titles within 30 days
                for existing_date, existing_decisions in seen_titles.items():
                    if abs((datetime.fromisoformat(date) - datetime.fromisoformat(existing_date)).days) <= 30:
                        for existing_title, existing_key in existing_decisions:
                            # Simple similarity check (can be enhanced)
                            if self._calculate_similarity(title, existing_title) > 0.85:
                                potential_duplicates.append({
                                    'decision1': decision['decision_key'],
                                    'decision2': existing_key,
                                    'similarity': self._calculate_similarity(title, existing_title)
                                })

                if date not in seen_titles:
                    seen_titles[date] = []
                seen_titles[date].append((title, decision['decision_key']))

            duplicate_count = len(potential_duplicates)
            duplicate_rate = (duplicate_count / total_count * 100) if total_count > 0 else 0

            # Determine trend
            trend = await self._calculate_trend('duplicate_rate', duplicate_rate)

            return QualityMetric(
                name='duplicate_rate',
                value=duplicate_rate,
                timestamp=datetime.now().isoformat(),
                threshold_warning=self.config['thresholds']['duplicate_rate_warning'],
                threshold_critical=self.config['thresholds']['duplicate_rate_critical'],
                trend=trend,
                metadata={
                    'total_recent_decisions': total_count,
                    'potential_duplicates_found': duplicate_count,
                    'detection_method': 'title_similarity_date_proximity',
                    'similarity_threshold': 0.85,
                    'date_window_days': 30
                }
            )

        except Exception as e:
            logger.error(f"Error checking duplicate rate: {e}")
            return QualityMetric(
                name='duplicate_rate',
                value=-1,
                timestamp=datetime.now().isoformat(),
                metadata={'error': str(e)}
            )

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using Jaccard similarity of word sets."""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    async def check_tag_confidence(self) -> QualityMetric:
        """Monitor average tag confidence scores."""
        try:
            # Get recent decisions with tag confidence data
            recent_cutoff = (datetime.now() - timedelta(days=7)).isoformat()

            query = self.client.table('israeli_government_decisions')\
                .select('decision_key,tags_policy_area,tags_government_body,ai_confidence')\
                .gte('updated_at', recent_cutoff)\
                .not_.is_('ai_confidence', 'null')

            result = query.execute()
            decisions = result.data

            if not decisions:
                return QualityMetric(
                    name='tag_confidence',
                    value=-1,
                    timestamp=datetime.now().isoformat(),
                    metadata={'error': 'No recent decisions with confidence data'}
                )

            # Calculate tag confidence metrics
            policy_confidences = []
            body_confidences = []
            overall_confidences = []

            for decision in decisions:
                ai_conf = decision.get('ai_confidence')
                if ai_conf and isinstance(ai_conf, dict):
                    # Extract confidence values
                    policy_conf = ai_conf.get('policy_area_confidence', 0)
                    body_conf = ai_conf.get('government_body_confidence', 0)

                    if policy_conf > 0:
                        policy_confidences.append(policy_conf)
                    if body_conf > 0:
                        body_confidences.append(body_conf)

                    # Overall confidence as average
                    if policy_conf > 0 or body_conf > 0:
                        overall_conf = (policy_conf + body_conf) / 2 if policy_conf > 0 and body_conf > 0 else max(policy_conf, body_conf)
                        overall_confidences.append(overall_conf)

            # Calculate averages
            avg_policy_conf = statistics.mean(policy_confidences) if policy_confidences else 0
            avg_body_conf = statistics.mean(body_confidences) if body_confidences else 0
            avg_overall_conf = statistics.mean(overall_confidences) if overall_confidences else 0

            # Use overall confidence as primary metric
            primary_confidence = avg_overall_conf * 100  # Convert to percentage

            # Determine trend
            trend = await self._calculate_trend('tag_confidence', primary_confidence)

            return QualityMetric(
                name='tag_confidence',
                value=primary_confidence,
                timestamp=datetime.now().isoformat(),
                threshold_warning=self.config['thresholds']['tag_confidence_warning'],
                threshold_critical=self.config['thresholds']['tag_confidence_critical'],
                trend=trend,
                metadata={
                    'decisions_analyzed': len(decisions),
                    'avg_policy_confidence': avg_policy_conf * 100,
                    'avg_body_confidence': avg_body_conf * 100,
                    'policy_samples': len(policy_confidences),
                    'body_samples': len(body_confidences),
                    'overall_samples': len(overall_confidences)
                }
            )

        except Exception as e:
            logger.error(f"Error checking tag confidence: {e}")
            return QualityMetric(
                name='tag_confidence',
                value=-1,
                timestamp=datetime.now().isoformat(),
                metadata={'error': str(e)}
            )

    async def check_missing_fields(self) -> QualityMetric:
        """Monitor rates of missing critical fields."""
        try:
            # Get recent decisions
            recent_cutoff = (datetime.now() - timedelta(days=7)).isoformat()

            query = self.client.table('israeli_government_decisions')\
                .select('decision_key,title,summary,operativity,tags_policy_area,tags_government_body,decision_content')\
                .gte('updated_at', recent_cutoff)

            result = query.execute()
            decisions = result.data

            if not decisions:
                return QualityMetric(
                    name='missing_fields_rate',
                    value=-1,
                    timestamp=datetime.now().isoformat(),
                    metadata={'error': 'No recent decisions found'}
                )

            # Check for missing critical fields
            critical_fields = ['title', 'summary', 'operativity', 'tags_policy_area', 'decision_content']
            field_missing_counts = defaultdict(int)
            total_missing_any = 0

            for decision in decisions:
                missing_fields = []
                for field in critical_fields:
                    value = decision.get(field)

                    # Check if field is missing or empty
                    is_missing = (
                        value is None or
                        value == '' or
                        (isinstance(value, list) and len(value) == 0) or
                        (isinstance(value, str) and value.strip() == '')
                    )

                    if is_missing:
                        field_missing_counts[field] += 1
                        missing_fields.append(field)

                if missing_fields:
                    total_missing_any += 1

            # Calculate missing rate
            missing_rate = (total_missing_any / len(decisions) * 100) if decisions else 0

            # Determine trend
            trend = await self._calculate_trend('missing_fields_rate', missing_rate)

            return QualityMetric(
                name='missing_fields_rate',
                value=missing_rate,
                timestamp=datetime.now().isoformat(),
                threshold_warning=self.config['thresholds']['missing_fields_warning'],
                threshold_critical=self.config['thresholds']['missing_fields_critical'],
                trend=trend,
                metadata={
                    'decisions_analyzed': len(decisions),
                    'records_missing_any_field': total_missing_any,
                    'missing_by_field': dict(field_missing_counts),
                    'field_missing_rates': {
                        field: (count / len(decisions) * 100)
                        for field, count in field_missing_counts.items()
                    }
                }
            )

        except Exception as e:
            logger.error(f"Error checking missing fields: {e}")
            return QualityMetric(
                name='missing_fields_rate',
                value=-1,
                timestamp=datetime.now().isoformat(),
                metadata={'error': str(e)}
            )

    async def check_processing_performance(self) -> QualityMetric:
        """Monitor processing performance metrics."""
        try:
            # Check recent incremental QA performance
            tracking_dir = Path("data/incremental_tracking/reports")
            if not tracking_dir.exists():
                return QualityMetric(
                    name='processing_performance',
                    value=-1,
                    timestamp=datetime.now().isoformat(),
                    metadata={'error': 'No tracking directory found'}
                )

            # Find most recent report
            recent_reports = sorted(
                [f for f in tracking_dir.glob("*.json") if f.is_file()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            if not recent_reports:
                return QualityMetric(
                    name='processing_performance',
                    value=-1,
                    timestamp=datetime.now().isoformat(),
                    metadata={'error': 'No recent performance reports found'}
                )

            # Load most recent report
            with open(recent_reports[0], 'r', encoding='utf-8') as f:
                report = json.load(f)

            # Extract performance metrics
            performance_summary = report.get('performance_summary', {})
            processing_time = performance_summary.get('total_time_seconds', 0)
            processing_rate = performance_summary.get('average_processing_rate', 0)
            records_processed = performance_summary.get('records_processed', 0)

            # Use processing time as primary metric (lower is better)
            primary_metric = processing_time

            # Determine trend
            trend = await self._calculate_trend('processing_performance', primary_metric, lower_is_better=True)

            return QualityMetric(
                name='processing_performance',
                value=primary_metric,
                timestamp=datetime.now().isoformat(),
                threshold_warning=self.config['thresholds']['processing_time_warning'],
                threshold_critical=self.config['thresholds']['processing_time_critical'],
                trend=trend,
                metadata={
                    'processing_time_seconds': processing_time,
                    'processing_rate_per_sec': processing_rate,
                    'records_processed': records_processed,
                    'report_timestamp': report.get('timestamp'),
                    'report_file': str(recent_reports[0])
                }
            )

        except Exception as e:
            logger.error(f"Error checking processing performance: {e}")
            return QualityMetric(
                name='processing_performance',
                value=-1,
                timestamp=datetime.now().isoformat(),
                metadata={'error': str(e)}
            )

    async def _calculate_trend(self, metric_name: str, current_value: float, lower_is_better: bool = False) -> str:
        """Calculate trend for a metric based on historical data."""
        if metric_name not in self.historical_metrics:
            return 'stable'

        history = list(self.historical_metrics[metric_name])
        if len(history) < 3:
            return 'stable'

        # Get recent values for trend calculation
        recent_values = history[-5:]  # Last 5 measurements
        older_values = history[-10:-5] if len(history) >= 10 else history[:-5]

        if not older_values:
            return 'stable'

        recent_avg = statistics.mean(recent_values)
        older_avg = statistics.mean(older_values)

        # Calculate percentage change
        if older_avg != 0:
            change_percent = ((recent_avg - older_avg) / older_avg) * 100
        else:
            change_percent = 0

        # Determine trend (accounting for whether lower is better)
        threshold = 5.0  # 5% change threshold

        if abs(change_percent) < threshold:
            return 'stable'
        elif change_percent > threshold:
            return 'degrading' if not lower_is_better else 'improving'
        else:
            return 'improving' if not lower_is_better else 'degrading'

    def detect_anomalies(self, metric: QualityMetric) -> AnomalyResult:
        """Detect anomalies using statistical methods."""
        if not self.config['anomaly_detection']['enabled']:
            return AnomalyResult(
                is_anomaly=False,
                confidence=0.0,
                expected_range=(metric.value, metric.value),
                current_value=metric.value,
                description="Anomaly detection disabled"
            )

        history = list(self.historical_metrics[metric.name])
        min_samples = self.config['anomaly_detection']['min_samples']

        if len(history) < min_samples:
            return AnomalyResult(
                is_anomaly=False,
                confidence=0.0,
                expected_range=(metric.value, metric.value),
                current_value=metric.value,
                description=f"Insufficient historical data ({len(history)}/{min_samples})"
            )

        try:
            # Calculate statistical bounds
            mean_val = statistics.mean(history)
            stdev_val = statistics.stdev(history) if len(history) > 1 else 0

            sensitivity = self.config['anomaly_detection']['sensitivity']
            lower_bound = mean_val - (sensitivity * stdev_val)
            upper_bound = mean_val + (sensitivity * stdev_val)

            # Check if current value is anomalous
            is_anomaly = metric.value < lower_bound or metric.value > upper_bound

            if is_anomaly:
                # Calculate confidence based on how far outside bounds
                if metric.value < lower_bound:
                    distance = lower_bound - metric.value
                else:
                    distance = metric.value - upper_bound

                confidence = min(distance / stdev_val if stdev_val > 0 else 1.0, 1.0)
            else:
                confidence = 0.0

            return AnomalyResult(
                is_anomaly=is_anomaly,
                confidence=confidence,
                expected_range=(lower_bound, upper_bound),
                current_value=metric.value,
                description=f"Statistical anomaly detection (±{sensitivity}σ)"
            )

        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
            return AnomalyResult(
                is_anomaly=False,
                confidence=0.0,
                expected_range=(metric.value, metric.value),
                current_value=metric.value,
                description=f"Anomaly detection error: {e}"
            )

    async def run_quality_checks(self) -> List[QualityMetric]:
        """Run all quality monitoring checks."""
        logger.info("Running quality monitoring checks...")

        checks = [
            self.check_duplicate_rate(),
            self.check_tag_confidence(),
            self.check_missing_fields(),
            self.check_processing_performance()
        ]

        # Run checks concurrently
        results = await asyncio.gather(*checks, return_exceptions=True)

        metrics = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Check {i} failed: {result}")
                continue
            metrics.append(result)

        # Update historical data and check for anomalies
        for metric in metrics:
            # Add to historical data
            self.historical_metrics[metric.name].append(metric.value)

            # Detect anomalies
            if metric.value >= 0:  # Only for valid metrics
                anomaly = self.detect_anomalies(metric)

                # Check thresholds and generate alerts
                await self._process_metric_alerts(metric, anomaly)

        logger.info(f"Quality checks complete: {len(metrics)} metrics collected")
        return metrics

    async def _process_metric_alerts(self, metric: QualityMetric, anomaly: AnomalyResult):
        """Process metric for alert generation."""
        alerts_generated = []

        # Check critical threshold
        if (metric.threshold_critical is not None and
            ((metric.name in ['tag_confidence'] and metric.value < metric.threshold_critical) or
             (metric.name not in ['tag_confidence'] and metric.value > metric.threshold_critical))):

            alert = {
                'severity': 'critical',
                'metric': metric.name,
                'value': metric.value,
                'threshold': metric.threshold_critical,
                'message': f"Critical threshold exceeded for {metric.name}: {metric.value:.2f}",
                'metadata': metric.metadata
            }
            await self.alert_manager.send_alert(alert)
            alerts_generated.append('critical')

        # Check warning threshold
        elif (metric.threshold_warning is not None and
              ((metric.name in ['tag_confidence'] and metric.value < metric.threshold_warning) or
               (metric.name not in ['tag_confidence'] and metric.value > metric.threshold_warning))):

            alert = {
                'severity': 'warning',
                'metric': metric.name,
                'value': metric.value,
                'threshold': metric.threshold_warning,
                'message': f"Warning threshold exceeded for {metric.name}: {metric.value:.2f}",
                'metadata': metric.metadata
            }
            await self.alert_manager.send_alert(alert)
            alerts_generated.append('warning')

        # Check anomalies
        if anomaly.is_anomaly and anomaly.confidence > 0.7:
            alert = {
                'severity': 'warning',
                'metric': metric.name,
                'value': metric.value,
                'message': f"Anomaly detected in {metric.name}: {metric.value:.2f} (confidence: {anomaly.confidence:.2f})",
                'metadata': {
                    'expected_range': anomaly.expected_range,
                    'confidence': anomaly.confidence,
                    'description': anomaly.description
                }
            }
            await self.alert_manager.send_alert(alert)
            alerts_generated.append('anomaly')

        # Log trends
        if metric.trend and metric.trend != 'stable':
            logger.info(f"Trend detected for {metric.name}: {metric.trend}")

    async def start_monitoring(self, interval_minutes: int = 15):
        """Start continuous monitoring loop."""
        logger.info(f"Starting quality monitoring with {interval_minutes} minute intervals")
        self.monitoring_active = True

        try:
            while self.monitoring_active:
                start_time = time.time()

                # Run quality checks
                metrics = await self.run_quality_checks()

                # Save metrics
                await self.metrics_collector.save_metrics(metrics)

                # Update cache
                self.metrics_cache.update({m.name: m for m in metrics})

                processing_time = time.time() - start_time
                logger.info(f"Monitoring cycle complete in {processing_time:.2f}s")

                # Wait for next interval
                sleep_time = max(0, (interval_minutes * 60) - processing_time)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
            self.monitoring_active = False

    def stop_monitoring(self):
        """Stop continuous monitoring."""
        logger.info("Stopping quality monitoring")
        self.monitoring_active = False

    def get_current_metrics(self) -> Dict[str, QualityMetric]:
        """Get current cached metrics."""
        return self.metrics_cache.copy()

    def get_health_score(self) -> float:
        """Calculate overall system health score (0-100)."""
        if not self.metrics_cache:
            return -1  # No data

        scores = []

        for metric in self.metrics_cache.values():
            if metric.value < 0:  # Error condition
                continue

            # Calculate score based on thresholds
            if metric.name == 'tag_confidence':
                # Higher is better
                if metric.threshold_critical:
                    score = min(100, max(0, (metric.value / metric.threshold_critical) * 100))
                else:
                    score = metric.value
            else:
                # Lower is better for most metrics
                if metric.threshold_critical:
                    score = max(0, 100 - (metric.value / metric.threshold_critical * 100))
                else:
                    score = max(0, 100 - metric.value)

            scores.append(score)

        return statistics.mean(scores) if scores else 0


async def main():
    """CLI interface for quality monitoring."""
    import argparse

    parser = argparse.ArgumentParser(description="Quality Monitoring System")
    parser.add_argument('command', choices=['run', 'monitor', 'status', 'health'],
                       help='Command to execute')
    parser.add_argument('--interval', type=int, default=15,
                       help='Monitoring interval in minutes')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    monitor = QualityMonitor(
        config_file=args.config or "config/monitoring_alerts.yaml"
    )

    if args.command == 'run':
        metrics = await monitor.run_quality_checks()
        for metric in metrics:
            print(f"{metric.name}: {metric.value:.2f} ({metric.trend})")
            if metric.metadata:
                print(f"  Metadata: {json.dumps(metric.metadata, indent=2)}")

    elif args.command == 'monitor':
        print(f"Starting continuous monitoring (interval: {args.interval} minutes)")
        print("Press Ctrl+C to stop")
        try:
            await monitor.start_monitoring(args.interval)
        except KeyboardInterrupt:
            monitor.stop_monitoring()

    elif args.command == 'status':
        metrics = monitor.get_current_metrics()
        if metrics:
            for name, metric in metrics.items():
                print(f"{name}: {metric.value:.2f} (trend: {metric.trend})")
        else:
            print("No current metrics available - run monitoring first")

    elif args.command == 'health':
        health_score = monitor.get_health_score()
        if health_score >= 0:
            print(f"System Health Score: {health_score:.1f}/100")
        else:
            print("Health score not available - no metrics data")


if __name__ == "__main__":
    asyncio.run(main())