#!/usr/bin/env python3
"""
QA Monitoring Dashboard for GOV2DB System

A comprehensive dashboard for monitoring data quality metrics, trends, and issues
in real-time with automated reporting and alerting capabilities.

Usage:
    python bin/qa_dashboard.py --port 5000 --debug
    python bin/qa_dashboard.py --config-file dashboard_config.json

Features:
- Real-time QA metrics display
- Issue trend visualization
- Performance monitoring
- Alert system for critical issues
- REST API endpoints
- WebSocket support for live updates
- Automated reporting (daily/weekly/monthly)
- Caching layer for performance
"""

import sys
import os
import argparse
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Third-party imports
import redis
from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import plotly
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# Import project modules
from src.gov_scraper.processors.qa import (
    fetch_records_for_qa,
    fetch_records_stratified,
    run_scan,
    ALL_CHECKS,
    QAReport,
    QAScanResult
)
from src.gov_scraper.db.dal import fetch_latest_decision
from src.gov_scraper.db.connector import get_supabase_client

# =============================================================================
# Data Models
# =============================================================================

@dataclass
class DashboardMetrics:
    """Current dashboard metrics snapshot"""
    timestamp: str
    total_records: int
    total_issues: int
    issue_rate: float
    checks_passed: int
    checks_failed: int
    critical_alerts: int
    overall_health_score: float
    recent_scans: int

@dataclass
class IssueDistribution:
    """Issue distribution by category and severity"""
    by_check: Dict[str, int]
    by_severity: Dict[str, int]
    by_date: Dict[str, int]
    heatmap_data: List[Dict[str, Any]]

@dataclass
class TrendData:
    """Historical trend data"""
    dates: List[str]
    issue_rates: List[float]
    health_scores: List[float]
    total_records: List[int]

@dataclass
class Alert:
    """System alert"""
    id: str
    timestamp: str
    severity: str
    check_name: str
    message: str
    count: int
    resolved: bool = False

# =============================================================================
# Dashboard Core
# =============================================================================

class QADashboard:
    """Core QA Dashboard application"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_client = self._init_redis()
        self.alerts = []
        self.metrics_cache = {}
        self.last_scan_time = None
        self.scheduler = BackgroundScheduler()

        # Flask app setup
        self.app = Flask(__name__, template_folder='templates')
        self.app.config['SECRET_KEY'] = config.get('secret_key', 'dev-key-change-in-prod')

        # Enable CORS for API endpoints
        CORS(self.app, resources={r"/api/*": {"origins": "*"}})

        # SocketIO setup for real-time updates
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        # Setup routes
        self._setup_routes()
        self._setup_api_routes()
        self._setup_websocket_handlers()

        # Start background tasks
        self._start_background_tasks()

    def _init_redis(self) -> Optional[redis.Redis]:
        """Initialize Redis client for caching"""
        try:
            redis_host = self.config.get('redis_host', 'localhost')
            redis_port = self.config.get('redis_port', 6379)
            redis_db = self.config.get('redis_db', 0)

            client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
            client.ping()  # Test connection
            logging.info(f"Redis connected: {redis_host}:{redis_port}")
            return client
        except Exception as e:
            logging.warning(f"Redis connection failed: {e}. Using in-memory cache.")
            return None

    def _setup_routes(self):
        """Setup web routes"""

        @self.app.route('/')
        def dashboard():
            """Main dashboard page"""
            return render_template('dashboard.html')

        @self.app.route('/alerts')
        def alerts_page():
            """Alerts management page"""
            return render_template('alerts.html')

        @self.app.route('/reports')
        def reports_page():
            """Reports and analytics page"""
            return render_template('reports.html')

    def _setup_api_routes(self):
        """Setup REST API endpoints"""

        @self.app.route('/api/qa/metrics', methods=['GET'])
        def get_metrics():
            """Get current QA metrics"""
            try:
                metrics = self._get_cached_or_fetch('metrics', self._fetch_current_metrics, ttl=300)
                return jsonify(asdict(metrics))
            except Exception as e:
                logging.error(f"Error fetching metrics: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/qa/issues', methods=['GET'])
        def get_issues():
            """Get current issues with filtering"""
            try:
                check = request.args.get('check')
                severity = request.args.get('severity')
                limit = int(request.args.get('limit', 100))

                issues = self._fetch_current_issues(check, severity, limit)
                return jsonify(issues)
            except Exception as e:
                logging.error(f"Error fetching issues: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/qa/history', methods=['GET'])
        def get_history():
            """Get historical QA data"""
            try:
                days = int(request.args.get('days', 7))
                trend_data = self._get_cached_or_fetch(
                    f'history_{days}d',
                    lambda: self._fetch_historical_data(days),
                    ttl=3600
                )
                return jsonify(asdict(trend_data))
            except Exception as e:
                logging.error(f"Error fetching history: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/qa/export', methods=['POST'])
        def export_report():
            """Generate and export QA report"""
            try:
                report_type = request.json.get('type', 'current')
                format_type = request.json.get('format', 'json')

                if report_type == 'current':
                    report = self._generate_current_report()
                elif report_type == 'weekly':
                    report = self._generate_weekly_report()
                elif report_type == 'monthly':
                    report = self._generate_monthly_report()
                else:
                    return jsonify({'error': 'Invalid report type'}), 400

                if format_type == 'json':
                    return jsonify(report)
                elif format_type == 'csv':
                    return self._export_csv_report(report)
                else:
                    return jsonify({'error': 'Invalid format type'}), 400

            except Exception as e:
                logging.error(f"Error exporting report: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/qa/scan/trigger', methods=['POST'])
        def trigger_scan():
            """Trigger a new QA scan"""
            try:
                scan_config = request.json or {}
                check_name = scan_config.get('check')
                sample_size = scan_config.get('sample_size', 1000)

                # Start scan in background
                threading.Thread(
                    target=self._run_background_scan,
                    args=(check_name, sample_size),
                    daemon=True
                ).start()

                return jsonify({'message': 'Scan started', 'status': 'running'})
            except Exception as e:
                logging.error(f"Error triggering scan: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/qa/alerts', methods=['GET'])
        def get_alerts():
            """Get current alerts"""
            active_only = request.args.get('active_only', 'true').lower() == 'true'
            alerts = [alert for alert in self.alerts if not active_only or not alert.resolved]
            return jsonify([asdict(alert) for alert in alerts])

        @self.app.route('/api/qa/alerts/<alert_id>/resolve', methods=['POST'])
        def resolve_alert(alert_id):
            """Resolve an alert"""
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    self._broadcast_alert_update(alert)
                    return jsonify({'message': 'Alert resolved'})
            return jsonify({'error': 'Alert not found'}), 404

    def _setup_websocket_handlers(self):
        """Setup WebSocket event handlers"""

        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            logging.info(f"Client connected: {request.sid}")

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            logging.info(f"Client disconnected: {request.sid}")

        @self.socketio.on('subscribe_metrics')
        def handle_subscribe_metrics():
            """Handle metrics subscription"""
            # Send current metrics immediately
            try:
                metrics = self._get_cached_or_fetch('metrics', self._fetch_current_metrics, ttl=60)
                emit('metrics_update', asdict(metrics))
            except Exception as e:
                logging.error(f"Error sending metrics: {e}")
                emit('error', {'message': str(e)})

    def _start_background_tasks(self):
        """Start background monitoring tasks"""

        # Schedule periodic scans
        self.scheduler.add_job(
            self._periodic_scan,
            'interval',
            minutes=self.config.get('scan_interval_minutes', 15),
            id='periodic_scan'
        )

        # Schedule metrics updates
        self.scheduler.add_job(
            self._update_metrics,
            'interval',
            minutes=self.config.get('metrics_update_minutes', 5),
            id='metrics_update'
        )

        # Schedule daily reports
        self.scheduler.add_job(
            self._send_daily_report,
            'cron',
            hour=self.config.get('daily_report_hour', 9),
            id='daily_report'
        )

        # Schedule weekly reports
        self.scheduler.add_job(
            self._send_weekly_report,
            'cron',
            day_of_week='monday',
            hour=self.config.get('weekly_report_hour', 9),
            id='weekly_report'
        )

        # Schedule monthly reports
        self.scheduler.add_job(
            self._send_monthly_report,
            'cron',
            day=1,
            hour=self.config.get('monthly_report_hour', 9),
            id='monthly_report'
        )

        self.scheduler.start()
        logging.info("Background tasks started")

    # =============================================================================
    # Data Fetching Methods
    # =============================================================================

    def _fetch_current_metrics(self) -> DashboardMetrics:
        """Fetch current dashboard metrics"""
        try:
            # Get basic stats
            # Get record count using direct Supabase query
            client = get_supabase_client()
            result = client.table('israeli_government_decisions').select('id', count='exact').execute()
            total_records = result.count

            # Run a quick stratified scan for health metrics
            records = fetch_records_stratified(sample_size=1000, seed=42)
            report = run_scan(records, checks=None)  # All checks

            # Calculate metrics
            total_issues = report.total_issues
            issue_rate = (total_issues / len(records) * 100) if records else 0

            checks_passed = len([r for r in report.scan_results if r.issues_found == 0])
            checks_failed = len(report.scan_results) - checks_passed

            # Count critical alerts
            critical_alerts = len([a for a in self.alerts if a.severity == 'critical' and not a.resolved])

            # Calculate health score (0-100)
            health_score = max(0, 100 - issue_rate)

            # Recent scans count
            recent_scans = self._count_recent_scans()

            metrics = DashboardMetrics(
                timestamp=datetime.now().isoformat(),
                total_records=total_records,
                total_issues=total_issues,
                issue_rate=round(issue_rate, 2),
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                critical_alerts=critical_alerts,
                overall_health_score=round(health_score, 1),
                recent_scans=recent_scans
            )

            self.last_scan_time = datetime.now()
            return metrics

        except Exception as e:
            logging.error(f"Error fetching current metrics: {e}")
            raise

    def _fetch_current_issues(self, check: Optional[str] = None,
                            severity: Optional[str] = None,
                            limit: int = 100) -> Dict[str, Any]:
        """Fetch current issues with optional filtering"""
        try:
            records = fetch_records_stratified(sample_size=min(limit * 10, 5000), seed=42)

            if check and check in ALL_CHECKS:
                checks_to_run = [check]
            else:
                checks_to_run = list(ALL_CHECKS.keys())

            report = run_scan(records, checks=checks_to_run)

            all_issues = []
            for scan_result in report.scan_results:
                for issue in scan_result.issues:
                    issue_dict = {
                        'check_name': scan_result.check_name,
                        'decision_key': issue.decision_key,
                        'severity': issue.severity,
                        'message': issue.message,
                        'field': getattr(issue, 'field', ''),
                        'timestamp': report.timestamp
                    }

                    # Apply severity filter
                    if severity and issue.severity != severity:
                        continue

                    all_issues.append(issue_dict)

            # Sort by severity and limit
            severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
            all_issues.sort(key=lambda x: severity_order.get(x['severity'], 4))

            return {
                'issues': all_issues[:limit],
                'total_count': len(all_issues),
                'distribution': self._calculate_issue_distribution(report)
            }

        except Exception as e:
            logging.error(f"Error fetching current issues: {e}")
            raise

    def _fetch_historical_data(self, days: int) -> TrendData:
        """Fetch historical QA trend data"""
        try:
            # For demo purposes, generate sample trend data
            # In production, this would query historical scan results from a dedicated table

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            dates = []
            issue_rates = []
            health_scores = []
            total_records = []

            # Generate daily data points
            current_date = start_date
            while current_date <= end_date:
                dates.append(current_date.strftime('%Y-%m-%d'))

                # Simulate trend data (replace with actual historical queries)
                base_issue_rate = 15.0
                daily_variation = (hash(current_date.strftime('%Y%m%d')) % 100) / 100.0 * 10 - 5
                issue_rate = max(0, base_issue_rate + daily_variation)

                issue_rates.append(round(issue_rate, 2))
                health_scores.append(round(100 - issue_rate, 1))
                total_records.append(25000 + int(daily_variation * 100))

                current_date += timedelta(days=1)

            return TrendData(
                dates=dates,
                issue_rates=issue_rates,
                health_scores=health_scores,
                total_records=total_records
            )

        except Exception as e:
            logging.error(f"Error fetching historical data: {e}")
            raise

    def _calculate_issue_distribution(self, report: QAReport) -> IssueDistribution:
        """Calculate issue distribution for heatmap and charts"""
        by_check = {}
        by_severity = defaultdict(int)
        by_date = defaultdict(int)
        heatmap_data = []

        for scan_result in report.scan_results:
            by_check[scan_result.check_name] = scan_result.issues_found

            for issue in scan_result.issues:
                by_severity[issue.severity] += 1

                # Extract date from decision_key if possible
                try:
                    # Assuming decision_key format includes date info
                    date_key = datetime.now().strftime('%Y-%m-%d')  # Placeholder
                    by_date[date_key] += 1
                except:
                    pass

        # Prepare heatmap data (check vs severity)
        for check_name, issue_count in by_check.items():
            if issue_count > 0:
                heatmap_data.append({
                    'check': check_name,
                    'severity': 'medium',  # Simplified for demo
                    'count': issue_count
                })

        return IssueDistribution(
            by_check=by_check,
            by_severity=dict(by_severity),
            by_date=dict(by_date),
            heatmap_data=heatmap_data
        )

    # =============================================================================
    # Caching Methods
    # =============================================================================

    def _get_cached_or_fetch(self, key: str, fetch_func, ttl: int = 300):
        """Get data from cache or fetch and cache it"""
        cache_key = f"qa_dashboard:{key}"

        if self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                logging.warning(f"Redis cache read failed: {e}")

        # Fetch fresh data
        data = fetch_func()

        # Cache it
        if self.redis_client:
            try:
                self.redis_client.setex(
                    cache_key,
                    ttl,
                    json.dumps(asdict(data) if hasattr(data, '__dict__') else data)
                )
            except Exception as e:
                logging.warning(f"Redis cache write failed: {e}")
        else:
            # In-memory cache as fallback
            self.metrics_cache[key] = {
                'data': data,
                'timestamp': time.time(),
                'ttl': ttl
            }

        return data

    def _invalidate_cache(self, pattern: str = "*"):
        """Invalidate cache entries matching pattern"""
        if self.redis_client:
            try:
                keys = self.redis_client.keys(f"qa_dashboard:{pattern}")
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logging.warning(f"Cache invalidation failed: {e}")
        else:
            # Clear in-memory cache
            self.metrics_cache.clear()

    # =============================================================================
    # Background Tasks
    # =============================================================================

    def _periodic_scan(self):
        """Run periodic QA scan"""
        try:
            logging.info("Starting periodic QA scan")

            # Run scan with larger sample
            records = fetch_records_stratified(sample_size=2000, seed=None)
            report = run_scan(records, checks=None)

            # Check for new alerts
            self._process_scan_for_alerts(report)

            # Invalidate metrics cache
            self._invalidate_cache("metrics*")

            # Broadcast update to connected clients
            self.socketio.emit('scan_complete', {
                'timestamp': report.timestamp,
                'total_issues': report.total_issues,
                'total_records': report.total_records
            })

            logging.info(f"Periodic scan complete: {report.total_issues} issues in {len(records)} records")

        except Exception as e:
            logging.error(f"Periodic scan failed: {e}")

    def _update_metrics(self):
        """Update dashboard metrics"""
        try:
            # Force refresh metrics cache
            self._invalidate_cache("metrics")
            metrics = self._fetch_current_metrics()

            # Broadcast to connected clients
            self.socketio.emit('metrics_update', asdict(metrics))

        except Exception as e:
            logging.error(f"Metrics update failed: {e}")

    def _process_scan_for_alerts(self, report: QAReport):
        """Process scan results for potential alerts"""
        for scan_result in report.scan_results:
            issue_rate = (scan_result.issues_found / scan_result.total_scanned * 100) if scan_result.total_scanned > 0 else 0

            # Generate alerts based on thresholds
            if issue_rate > 50:  # Critical threshold
                alert = Alert(
                    id=f"{scan_result.check_name}_{int(time.time())}",
                    timestamp=datetime.now().isoformat(),
                    severity='critical',
                    check_name=scan_result.check_name,
                    message=f"High issue rate detected: {issue_rate:.1f}%",
                    count=scan_result.issues_found
                )
                self._add_alert(alert)
            elif issue_rate > 25:  # Warning threshold
                alert = Alert(
                    id=f"{scan_result.check_name}_{int(time.time())}",
                    timestamp=datetime.now().isoformat(),
                    severity='warning',
                    check_name=scan_result.check_name,
                    message=f"Elevated issue rate: {issue_rate:.1f}%",
                    count=scan_result.issues_found
                )
                self._add_alert(alert)

    def _add_alert(self, alert: Alert):
        """Add new alert and broadcast it"""
        # Check for duplicate alerts (same check within 1 hour)
        cutoff_time = datetime.now() - timedelta(hours=1)
        existing_alert = None

        for existing in self.alerts:
            if (existing.check_name == alert.check_name and
                not existing.resolved and
                datetime.fromisoformat(existing.timestamp) > cutoff_time):
                existing_alert = existing
                break

        if existing_alert:
            # Update existing alert
            existing_alert.count = alert.count
            existing_alert.timestamp = alert.timestamp
        else:
            # Add new alert
            self.alerts.append(alert)

            # Keep only last 100 alerts
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]

        # Broadcast alert update
        self._broadcast_alert_update(alert)

    def _broadcast_alert_update(self, alert: Alert):
        """Broadcast alert update to connected clients"""
        self.socketio.emit('alert_update', asdict(alert))

    def _run_background_scan(self, check_name: Optional[str], sample_size: int):
        """Run QA scan in background thread"""
        try:
            records = fetch_records_stratified(sample_size=sample_size, seed=None)

            if check_name and check_name in ALL_CHECKS:
                checks = [check_name]
            else:
                checks = None

            report = run_scan(records, checks=checks)

            # Process results
            self._process_scan_for_alerts(report)
            self._invalidate_cache("*")

            # Broadcast completion
            self.socketio.emit('scan_complete', {
                'timestamp': report.timestamp,
                'total_issues': report.total_issues,
                'total_records': report.total_records,
                'check_name': check_name
            })

        except Exception as e:
            logging.error(f"Background scan failed: {e}")
            self.socketio.emit('scan_error', {'error': str(e)})

    def _count_recent_scans(self) -> int:
        """Count recent scans (last 24 hours)"""
        # Placeholder - in production, query scan log table
        return len(self.alerts) if self.alerts else 5

    # =============================================================================
    # Reporting Methods
    # =============================================================================

    def _generate_current_report(self) -> Dict[str, Any]:
        """Generate current status report"""
        try:
            metrics = self._fetch_current_metrics()
            issues = self._fetch_current_issues(limit=50)

            return {
                'report_type': 'current',
                'generated_at': datetime.now().isoformat(),
                'metrics': asdict(metrics),
                'top_issues': issues['issues'][:10],
                'distribution': issues['distribution'],
                'active_alerts': [asdict(a) for a in self.alerts if not a.resolved]
            }
        except Exception as e:
            logging.error(f"Error generating current report: {e}")
            raise

    def _generate_weekly_report(self) -> Dict[str, Any]:
        """Generate weekly report"""
        try:
            trend_data = self._fetch_historical_data(7)
            current_metrics = self._fetch_current_metrics()

            # Calculate weekly averages
            avg_issue_rate = sum(trend_data.issue_rates) / len(trend_data.issue_rates) if trend_data.issue_rates else 0
            avg_health_score = sum(trend_data.health_scores) / len(trend_data.health_scores) if trend_data.health_scores else 0

            return {
                'report_type': 'weekly',
                'generated_at': datetime.now().isoformat(),
                'period': {
                    'start': trend_data.dates[0] if trend_data.dates else None,
                    'end': trend_data.dates[-1] if trend_data.dates else None
                },
                'summary': {
                    'avg_issue_rate': round(avg_issue_rate, 2),
                    'avg_health_score': round(avg_health_score, 1),
                    'current_health_score': current_metrics.overall_health_score,
                    'total_alerts': len([a for a in self.alerts if datetime.fromisoformat(a.timestamp) > datetime.now() - timedelta(days=7)])
                },
                'trends': asdict(trend_data)
            }
        except Exception as e:
            logging.error(f"Error generating weekly report: {e}")
            raise

    def _generate_monthly_report(self) -> Dict[str, Any]:
        """Generate monthly executive report"""
        try:
            trend_data = self._fetch_historical_data(30)
            current_metrics = self._fetch_current_metrics()

            # Calculate monthly statistics
            avg_issue_rate = sum(trend_data.issue_rates) / len(trend_data.issue_rates) if trend_data.issue_rates else 0
            min_issue_rate = min(trend_data.issue_rates) if trend_data.issue_rates else 0
            max_issue_rate = max(trend_data.issue_rates) if trend_data.issue_rates else 0

            return {
                'report_type': 'monthly',
                'generated_at': datetime.now().isoformat(),
                'period': {
                    'start': trend_data.dates[0] if trend_data.dates else None,
                    'end': trend_data.dates[-1] if trend_data.dates else None
                },
                'executive_summary': {
                    'total_records': current_metrics.total_records,
                    'avg_issue_rate': round(avg_issue_rate, 2),
                    'best_issue_rate': round(min_issue_rate, 2),
                    'worst_issue_rate': round(max_issue_rate, 2),
                    'current_health_score': current_metrics.overall_health_score,
                    'total_critical_alerts': len([a for a in self.alerts if a.severity == 'critical' and
                                                datetime.fromisoformat(a.timestamp) > datetime.now() - timedelta(days=30)])
                },
                'trends': asdict(trend_data),
                'recommendations': self._generate_recommendations(current_metrics, trend_data)
            }
        except Exception as e:
            logging.error(f"Error generating monthly report: {e}")
            raise

    def _generate_recommendations(self, metrics: DashboardMetrics, trends: TrendData) -> List[str]:
        """Generate recommendations based on metrics and trends"""
        recommendations = []

        if metrics.overall_health_score < 70:
            recommendations.append("Consider increasing QA scan frequency due to low health score")

        if metrics.critical_alerts > 0:
            recommendations.append(f"Address {metrics.critical_alerts} critical alerts immediately")

        if trends.issue_rates and len(trends.issue_rates) > 7:
            recent_avg = sum(trends.issue_rates[-7:]) / 7
            older_avg = sum(trends.issue_rates[:-7]) / len(trends.issue_rates[:-7])
            if recent_avg > older_avg * 1.2:
                recommendations.append("Issue rates are trending upward - investigate recent changes")

        return recommendations

    def _export_csv_report(self, report: Dict[str, Any]):
        """Export report as CSV file"""
        # Placeholder - implement CSV export logic
        return jsonify({'message': 'CSV export not implemented yet'}), 501

    def _send_daily_report(self):
        """Send daily report via email (placeholder)"""
        try:
            report = self._generate_current_report()
            logging.info(f"Daily report generated: {report['metrics']['overall_health_score']}% health score")
            # TODO: Implement email sending
        except Exception as e:
            logging.error(f"Daily report failed: {e}")

    def _send_weekly_report(self):
        """Send weekly report via email (placeholder)"""
        try:
            report = self._generate_weekly_report()
            logging.info(f"Weekly report generated: {report['summary']['avg_health_score']}% avg health score")
            # TODO: Implement email sending
        except Exception as e:
            logging.error(f"Weekly report failed: {e}")

    def _send_monthly_report(self):
        """Send monthly executive report via email (placeholder)"""
        try:
            report = self._generate_monthly_report()
            logging.info(f"Monthly report generated: {report['executive_summary']['current_health_score']}% health score")
            # TODO: Implement email sending
        except Exception as e:
            logging.error(f"Monthly report failed: {e}")

# =============================================================================
# Dashboard Components (for frontend integration)
# =============================================================================

class DashboardComponents:
    """Frontend dashboard component generators"""

    @staticmethod
    def generate_quality_scorecard_data(metrics: DashboardMetrics) -> Dict[str, Any]:
        """Generate data for QualityScoreCard component"""
        return {
            'health_score': metrics.overall_health_score,
            'total_records': metrics.total_records,
            'issue_rate': metrics.issue_rate,
            'checks_passed': metrics.checks_passed,
            'checks_failed': metrics.checks_failed,
            'status': 'excellent' if metrics.overall_health_score >= 90 else
                     'good' if metrics.overall_health_score >= 75 else
                     'warning' if metrics.overall_health_score >= 60 else 'critical'
        }

    @staticmethod
    def generate_issue_heatmap_data(distribution: IssueDistribution) -> Dict[str, Any]:
        """Generate data for IssueHeatmap component"""
        # Convert to format suitable for heatmap visualization
        checks = list(distribution.by_check.keys())
        severities = ['low', 'medium', 'high', 'critical']

        heatmap_matrix = []
        for check in checks:
            row = []
            for severity in severities:
                count = sum(1 for item in distribution.heatmap_data
                          if item['check'] == check and item.get('severity') == severity)
                row.append(count)
            heatmap_matrix.append(row)

        return {
            'checks': checks,
            'severities': severities,
            'data': heatmap_matrix,
            'total_issues': sum(distribution.by_check.values())
        }

    @staticmethod
    def generate_trend_chart_data(trends: TrendData) -> Dict[str, Any]:
        """Generate data for TrendChart component"""
        return {
            'dates': trends.dates,
            'datasets': [
                {
                    'label': 'Health Score (%)',
                    'data': trends.health_scores,
                    'borderColor': '#10B981',
                    'backgroundColor': 'rgba(16, 185, 129, 0.1)'
                },
                {
                    'label': 'Issue Rate (%)',
                    'data': trends.issue_rates,
                    'borderColor': '#EF4444',
                    'backgroundColor': 'rgba(239, 68, 68, 0.1)'
                }
            ]
        }

    @staticmethod
    def generate_alert_panel_data(alerts: List[Alert]) -> Dict[str, Any]:
        """Generate data for AlertPanel component"""
        active_alerts = [alert for alert in alerts if not alert.resolved]

        by_severity = defaultdict(int)
        for alert in active_alerts:
            by_severity[alert.severity] += 1

        return {
            'active_count': len(active_alerts),
            'by_severity': dict(by_severity),
            'recent_alerts': [asdict(alert) for alert in active_alerts[:10]]
        }

# =============================================================================
# Configuration and Startup
# =============================================================================

DEFAULT_CONFIG = {
    'port': 5000,
    'host': '0.0.0.0',
    'debug': False,
    'secret_key': 'dev-key-change-in-production',
    'redis_host': 'localhost',
    'redis_port': 6379,
    'redis_db': 0,
    'scan_interval_minutes': 15,
    'metrics_update_minutes': 5,
    'daily_report_hour': 9,
    'weekly_report_hour': 9,
    'monthly_report_hour': 9
}

def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Load dashboard configuration"""
    config = DEFAULT_CONFIG.copy()

    if config_file and os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            file_config = json.load(f)
            config.update(file_config)

    # Override with environment variables
    for key in config:
        env_key = f'QA_DASHBOARD_{key.upper()}'
        if env_key in os.environ:
            value = os.environ[env_key]
            # Convert to appropriate type
            if isinstance(config[key], int):
                config[key] = int(value)
            elif isinstance(config[key], bool):
                config[key] = value.lower() in ('true', '1', 'yes', 'on')
            else:
                config[key] = value

    return config

def setup_logging(debug: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if debug else logging.INFO
    log_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, 'qa_dashboard.log'),
                encoding='utf-8'
            )
        ]
    )

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='QA Monitoring Dashboard for GOV2DB')
    parser.add_argument('--config-file', help='Path to configuration file')
    parser.add_argument('--port', type=int, help='Port to run dashboard on')
    parser.add_argument('--host', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config_file)

    # Override with command line args
    if args.port:
        config['port'] = args.port
    if args.host:
        config['host'] = args.host
    if args.debug:
        config['debug'] = True

    # Setup logging
    setup_logging(config['debug'])

    # Create and run dashboard
    dashboard = QADashboard(config)

    logging.info(f"Starting QA Dashboard on {config['host']}:{config['port']}")
    logging.info(f"Debug mode: {config['debug']}")

    try:
        dashboard.socketio.run(
            dashboard.app,
            host=config['host'],
            port=config['port'],
            debug=config['debug']
        )
    except KeyboardInterrupt:
        logging.info("Dashboard stopped by user")
    except Exception as e:
        logging.error(f"Dashboard failed to start: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()