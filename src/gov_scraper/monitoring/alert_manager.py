#!/usr/bin/env python3
"""
Alert Management System for GOV2DB
===================================

Handles alert generation, routing, and delivery with configurable channels,
cooldown periods, and escalation rules.

Features:
- Multiple alert channels (log, email, dashboard, webhook)
- Alert cooldown to prevent spam
- Severity-based escalation
- Alert history and acknowledgment
- Recovery notifications
"""

import os
import json
import logging
import smtplib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Individual alert with metadata."""
    id: str
    severity: str  # 'critical', 'warning', 'info'
    metric: str
    value: float
    threshold: Optional[float]
    message: str
    timestamp: str
    metadata: Dict[str, Any]
    channels_sent: List[str] = None
    acknowledged: bool = False
    resolved: bool = False

    def __post_init__(self):
        if self.channels_sent is None:
            self.channels_sent = []

class AlertManager:
    """
    Alert management system with multiple channels and smart routing.
    """

    def __init__(self, config_file: str = "config/monitoring_alerts.yaml"):
        self.config_file = Path(config_file)
        self.config = self._load_config()

        # Alert history and state
        self.alert_history = {}
        self.active_alerts = {}
        self.cooldown_cache = defaultdict(datetime)

        # Setup directories
        self.alerts_dir = Path("data/monitoring/alerts")
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

        # Email client setup
        self.smtp_client = None
        self._setup_email()

    def _load_config(self) -> Dict:
        """Load alert configuration."""
        default_config = {
            'channels': {
                'log': {'enabled': True, 'level': 'INFO'},
                'email': {
                    'enabled': False,
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': 587,
                    'username': '',
                    'password': '',
                    'recipients': [],
                    'subject_prefix': '[GOV2DB Alert]'
                },
                'dashboard': {'enabled': True},
                'webhook': {
                    'enabled': False,
                    'url': '',
                    'headers': {},
                    'timeout': 30
                }
            },
            'rules': {
                'cooldown_minutes': {
                    'critical': 30,
                    'warning': 60,
                    'info': 120
                },
                'escalation_hours': {
                    'critical': 1,
                    'warning': 4,
                    'info': 24
                },
                'auto_resolve_hours': 24,
                'batch_similar_alerts': True
            },
            'templates': {
                'email': {
                    'critical': "🚨 CRITICAL: {message}\n\nMetric: {metric}\nValue: {value}\nThreshold: {threshold}\nTime: {timestamp}",
                    'warning': "⚠️ WARNING: {message}\n\nMetric: {metric}\nValue: {value}\nThreshold: {threshold}\nTime: {timestamp}",
                    'info': "ℹ️ INFO: {message}\n\nMetric: {metric}\nValue: {value}\nTime: {timestamp}"
                },
                'log': {
                    'critical': "CRITICAL ALERT: {message} | Metric: {metric} | Value: {value}",
                    'warning': "WARNING ALERT: {message} | Metric: {metric} | Value: {value}",
                    'info': "INFO ALERT: {message} | Metric: {metric} | Value: {value}"
                }
            }
        }

        if self.config_file.exists():
            try:
                import yaml
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                    # Deep merge configuration
                    self._deep_merge(default_config, user_config)
            except Exception as e:
                logger.warning(f"Failed to load alert config, using defaults: {e}")

        return default_config

    def _deep_merge(self, base: Dict, update: Dict):
        """Recursively merge configuration dictionaries."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _setup_email(self):
        """Setup email client if configured."""
        email_config = self.config['channels']['email']
        if not email_config['enabled'] or not email_config['username']:
            return

        try:
            # Note: In production, use OAuth2 or app-specific passwords
            # This is a basic setup for demonstration
            logger.info("Email alerts configured")
        except Exception as e:
            logger.error(f"Failed to setup email: {e}")

    def _generate_alert_id(self, alert_data: Dict) -> str:
        """Generate unique but consistent ID for alert."""
        key_data = f"{alert_data['metric']}_{alert_data['severity']}_{alert_data.get('threshold', '')}"
        return hashlib.md5(key_data.encode()).hexdigest()[:12]

    def _should_send_alert(self, alert: Alert) -> bool:
        """Check if alert should be sent based on cooldown rules."""
        cooldown_key = f"{alert.metric}_{alert.severity}"
        cooldown_minutes = self.config['rules']['cooldown_minutes'].get(alert.severity, 60)

        last_sent = self.cooldown_cache.get(cooldown_key, datetime.min)
        cooldown_expires = last_sent + timedelta(minutes=cooldown_minutes)

        if datetime.now() < cooldown_expires:
            logger.debug(f"Alert in cooldown: {cooldown_key} (expires in {cooldown_expires - datetime.now()})")
            return False

        return True

    async def send_alert(self, alert_data: Dict) -> str:
        """Send alert through configured channels."""
        # Create alert object
        alert_id = self._generate_alert_id(alert_data)
        alert = Alert(
            id=alert_id,
            severity=alert_data.get('severity', 'warning'),
            metric=alert_data.get('metric', 'unknown'),
            value=alert_data.get('value', 0),
            threshold=alert_data.get('threshold'),
            message=alert_data.get('message', 'Unknown alert'),
            timestamp=datetime.now().isoformat(),
            metadata=alert_data.get('metadata', {})
        )

        # Check cooldown
        if not self._should_send_alert(alert):
            logger.debug(f"Alert {alert_id} skipped due to cooldown")
            return alert_id

        # Send through channels
        channels_sent = []

        # Log channel
        if self.config['channels']['log']['enabled']:
            await self._send_log_alert(alert)
            channels_sent.append('log')

        # Email channel
        if self.config['channels']['email']['enabled']:
            await self._send_email_alert(alert)
            channels_sent.append('email')

        # Dashboard channel
        if self.config['channels']['dashboard']['enabled']:
            await self._send_dashboard_alert(alert)
            channels_sent.append('dashboard')

        # Webhook channel
        if self.config['channels']['webhook']['enabled']:
            await self._send_webhook_alert(alert)
            channels_sent.append('webhook')

        # Update alert state
        alert.channels_sent = channels_sent
        self.active_alerts[alert_id] = alert
        self.alert_history[alert_id] = alert

        # Update cooldown
        cooldown_key = f"{alert.metric}_{alert.severity}"
        self.cooldown_cache[cooldown_key] = datetime.now()

        # Save to file
        await self._save_alert(alert)

        logger.info(f"Alert {alert_id} sent via channels: {channels_sent}")
        return alert_id

    async def _send_log_alert(self, alert: Alert):
        """Send alert to logging system."""
        template = self.config['templates']['log'].get(alert.severity, self.config['templates']['log']['info'])

        message = template.format(
            message=alert.message,
            metric=alert.metric,
            value=alert.value,
            threshold=alert.threshold or 'N/A',
            timestamp=alert.timestamp
        )

        if alert.severity == 'critical':
            logger.critical(message)
        elif alert.severity == 'warning':
            logger.warning(message)
        else:
            logger.info(message)

    async def _send_email_alert(self, alert: Alert):
        """Send alert via email."""
        try:
            email_config = self.config['channels']['email']
            if not email_config['recipients']:
                logger.warning("No email recipients configured")
                return

            template = self.config['templates']['email'].get(alert.severity, self.config['templates']['email']['info'])

            # Format message
            body = template.format(
                message=alert.message,
                metric=alert.metric,
                value=alert.value,
                threshold=alert.threshold or 'N/A',
                timestamp=alert.timestamp
            )

            # Add metadata if present
            if alert.metadata:
                body += f"\n\nAdditional Details:\n{json.dumps(alert.metadata, indent=2)}"

            # Create message
            msg = MIMEMultipart()
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = f"{email_config['subject_prefix']} {alert.severity.upper()} - {alert.metric}"

            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            # Send email
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)

            logger.info(f"Email alert sent to {len(email_config['recipients'])} recipients")

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    async def _send_dashboard_alert(self, alert: Alert):
        """Send alert to dashboard system."""
        try:
            # Save alert for dashboard consumption
            dashboard_alert = {
                'id': alert.id,
                'severity': alert.severity,
                'metric': alert.metric,
                'value': alert.value,
                'threshold': alert.threshold,
                'message': alert.message,
                'timestamp': alert.timestamp,
                'metadata': alert.metadata,
                'acknowledged': alert.acknowledged,
                'resolved': alert.resolved
            }

            dashboard_file = self.alerts_dir / "dashboard_alerts.json"

            # Load existing alerts
            existing_alerts = []
            if dashboard_file.exists():
                try:
                    with open(dashboard_file, 'r', encoding='utf-8') as f:
                        existing_alerts = json.load(f)
                except Exception:
                    pass

            # Add new alert and keep last 100
            existing_alerts.append(dashboard_alert)
            existing_alerts = existing_alerts[-100:]

            # Save updated alerts
            with open(dashboard_file, 'w', encoding='utf-8') as f:
                json.dump(existing_alerts, f, indent=2, ensure_ascii=False)

            logger.debug("Alert saved for dashboard")

        except Exception as e:
            logger.error(f"Failed to send dashboard alert: {e}")

    async def _send_webhook_alert(self, alert: Alert):
        """Send alert via webhook."""
        try:
            import aiohttp

            webhook_config = self.config['channels']['webhook']
            if not webhook_config['url']:
                logger.warning("Webhook URL not configured")
                return

            payload = {
                'alert_id': alert.id,
                'severity': alert.severity,
                'metric': alert.metric,
                'value': alert.value,
                'threshold': alert.threshold,
                'message': alert.message,
                'timestamp': alert.timestamp,
                'metadata': alert.metadata
            }

            timeout = aiohttp.ClientTimeout(total=webhook_config.get('timeout', 30))

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    webhook_config['url'],
                    json=payload,
                    headers=webhook_config.get('headers', {})
                ) as response:
                    if response.status == 200:
                        logger.info(f"Webhook alert sent successfully")
                    else:
                        logger.warning(f"Webhook returned status {response.status}")

        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")

    async def _save_alert(self, alert: Alert):
        """Save alert to persistent storage."""
        try:
            alert_file = self.alerts_dir / f"{alert.id}.json"
            with open(alert_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(alert), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save alert: {e}")

    async def acknowledge_alert(self, alert_id: str, user: str = "system") -> bool:
        """Acknowledge an alert."""
        if alert_id not in self.active_alerts:
            return False

        alert = self.active_alerts[alert_id]
        alert.acknowledged = True
        alert.metadata['acknowledged_by'] = user
        alert.metadata['acknowledged_at'] = datetime.now().isoformat()

        await self._save_alert(alert)
        logger.info(f"Alert {alert_id} acknowledged by {user}")
        return True

    async def resolve_alert(self, alert_id: str, user: str = "system") -> bool:
        """Resolve an alert."""
        if alert_id not in self.active_alerts:
            return False

        alert = self.active_alerts[alert_id]
        alert.resolved = True
        alert.metadata['resolved_by'] = user
        alert.metadata['resolved_at'] = datetime.now().isoformat()

        # Send recovery notification
        recovery_message = f"Alert resolved: {alert.message}"
        await self.send_alert({
            'severity': 'info',
            'metric': alert.metric,
            'value': alert.value,
            'message': recovery_message,
            'metadata': {'original_alert_id': alert_id, 'recovery': True}
        })

        # Remove from active alerts
        del self.active_alerts[alert_id]

        await self._save_alert(alert)
        logger.info(f"Alert {alert_id} resolved by {user}")
        return True

    def get_active_alerts(self, severity: Optional[str] = None) -> List[Alert]:
        """Get currently active alerts."""
        alerts = list(self.active_alerts.values())

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for specified time period."""
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_iso = cutoff.isoformat()

        return [
            alert for alert in self.alert_history.values()
            if alert.timestamp >= cutoff_iso
        ]

    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        active_alerts = list(self.active_alerts.values())
        recent_alerts = self.get_alert_history(24)

        stats = {
            'active_alerts': len(active_alerts),
            'active_by_severity': defaultdict(int),
            'recent_alerts_24h': len(recent_alerts),
            'recent_by_severity': defaultdict(int),
            'top_metrics': defaultdict(int)
        }

        for alert in active_alerts:
            stats['active_by_severity'][alert.severity] += 1

        for alert in recent_alerts:
            stats['recent_by_severity'][alert.severity] += 1
            stats['top_metrics'][alert.metric] += 1

        return dict(stats)

    async def cleanup_old_alerts(self, days: int = 30):
        """Clean up old alert files."""
        cutoff = datetime.now() - timedelta(days=days)
        cleaned = 0

        for alert_file in self.alerts_dir.glob("*.json"):
            if alert_file.name == "dashboard_alerts.json":
                continue

            try:
                file_time = datetime.fromtimestamp(alert_file.stat().st_mtime)
                if file_time < cutoff:
                    alert_file.unlink()
                    cleaned += 1
            except Exception:
                continue

        logger.info(f"Cleaned up {cleaned} old alert files")
        return cleaned


async def main():
    """CLI interface for alert management."""
    import argparse

    parser = argparse.ArgumentParser(description="Alert Management System")
    parser.add_argument('command', choices=['test', 'status', 'ack', 'resolve', 'cleanup'],
                       help='Command to execute')
    parser.add_argument('--alert-id', help='Alert ID for ack/resolve commands')
    parser.add_argument('--severity', choices=['critical', 'warning', 'info'],
                       help='Alert severity for test command')
    parser.add_argument('--cleanup-days', type=int, default=30,
                       help='Days to keep alert files')
    parser.add_argument('--config', help='Configuration file path')

    args = parser.parse_args()

    alert_manager = AlertManager(
        config_file=args.config or "config/monitoring_alerts.yaml"
    )

    if args.command == 'test':
        # Send test alert
        severity = args.severity or 'info'
        test_alert = {
            'severity': severity,
            'metric': 'test_metric',
            'value': 42.0,
            'threshold': 50.0,
            'message': f'Test {severity} alert from CLI',
            'metadata': {'test': True}
        }

        alert_id = await alert_manager.send_alert(test_alert)
        print(f"Test alert sent: {alert_id}")

    elif args.command == 'status':
        stats = alert_manager.get_alert_statistics()
        print(f"Alert Statistics:")
        print(f"  Active alerts: {stats['active_alerts']}")
        print(f"  Recent alerts (24h): {stats['recent_alerts_24h']}")
        print(f"  By severity: {dict(stats['recent_by_severity'])}")

        if stats['active_alerts'] > 0:
            print("\nActive Alerts:")
            for alert in alert_manager.get_active_alerts()[:5]:
                print(f"  {alert.id}: {alert.severity} - {alert.message}")

    elif args.command == 'ack':
        if not args.alert_id:
            print("--alert-id required for ack command")
            return

        success = await alert_manager.acknowledge_alert(args.alert_id, "cli_user")
        if success:
            print(f"Alert {args.alert_id} acknowledged")
        else:
            print(f"Alert {args.alert_id} not found or already acknowledged")

    elif args.command == 'resolve':
        if not args.alert_id:
            print("--alert-id required for resolve command")
            return

        success = await alert_manager.resolve_alert(args.alert_id, "cli_user")
        if success:
            print(f"Alert {args.alert_id} resolved")
        else:
            print(f"Alert {args.alert_id} not found")

    elif args.command == 'cleanup':
        cleaned = await alert_manager.cleanup_old_alerts(args.cleanup_days)
        print(f"Cleaned up {cleaned} old alert files")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())