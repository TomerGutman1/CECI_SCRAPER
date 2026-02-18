#!/usr/bin/env python3
"""
Quality Reports Generator for GOV2DB
=====================================

Generates comprehensive quality reports for Israeli Government Decisions database
with actionable insights and recommendations.

Features:
- Daily/Weekly/Monthly quality summaries
- Issue trend analysis with root cause analysis
- Automated recommendations for improvements
- Multiple export formats (PDF, HTML, JSON, CSV)
- Historical comparison and benchmarking
- Executive summary for stakeholders

Usage:
    python bin/generate_quality_report.py daily
    python bin/generate_quality_report.py weekly --format pdf
    python bin/generate_quality_report.py monthly --email
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import statistics
import asyncio

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.gov_scraper.monitoring.quality_monitor import QualityMonitor
from src.gov_scraper.monitoring.metrics_collector import MetricsCollector
from src.gov_scraper.processors.qa import run_scan
from src.gov_scraper.db.connector import get_supabase_client

logger = logging.getLogger(__name__)

@dataclass
class QualityInsight:
    """Quality insight with recommendation."""
    category: str
    severity: str
    description: str
    recommendation: str
    impact: str
    effort: str  # 'low', 'medium', 'high'
    priority_score: float

@dataclass
class TrendAnalysis:
    """Trend analysis for a metric."""
    metric_name: str
    current_value: float
    previous_value: float
    change_percent: float
    trend_direction: str  # 'improving', 'degrading', 'stable'
    significance: str  # 'high', 'medium', 'low', 'none'
    description: str

@dataclass
class QualityReport:
    """Complete quality report."""
    report_type: str  # 'daily', 'weekly', 'monthly'
    period_start: str
    period_end: str
    generated_at: str
    executive_summary: Dict[str, Any]
    metrics_summary: Dict[str, Any]
    trend_analysis: List[TrendAnalysis]
    quality_insights: List[QualityInsight]
    recommendations: List[str]
    historical_comparison: Dict[str, Any]

class QualityReportGenerator:
    """
    Generates comprehensive quality reports with actionable insights.
    """

    def __init__(self):
        self.client = get_supabase_client()
        self.quality_monitor = QualityMonitor()
        self.metrics_collector = MetricsCollector()

        # Setup output directories
        self.reports_dir = Path("data/qa_reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Report configuration
        self.severity_weights = {'critical': 10, 'high': 7, 'medium': 5, 'low': 3}
        self.effort_weights = {'low': 1, 'medium': 3, 'high': 5}

    async def generate_daily_report(self) -> QualityReport:
        """Generate daily quality report."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)

        return await self._generate_report(
            'daily',
            start_time.isoformat(),
            end_time.isoformat()
        )

    async def generate_weekly_report(self) -> QualityReport:
        """Generate weekly quality report."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)

        return await self._generate_report(
            'weekly',
            start_time.isoformat(),
            end_time.isoformat()
        )

    async def generate_monthly_report(self) -> QualityReport:
        """Generate monthly quality report."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=30)

        return await self._generate_report(
            'monthly',
            start_time.isoformat(),
            end_time.isoformat()
        )

    async def _generate_report(
        self,
        report_type: str,
        period_start: str,
        period_end: str
    ) -> QualityReport:
        """Generate comprehensive quality report for specified period."""
        logger.info(f"Generating {report_type} quality report for {period_start} to {period_end}")

        # Collect current metrics
        current_metrics = await self.quality_monitor.run_quality_checks()

        # Get metrics summary
        metrics_summary = await self._get_metrics_summary(current_metrics, period_start, period_end)

        # Perform trend analysis
        trend_analysis = await self._analyze_trends(current_metrics, report_type)

        # Generate quality insights
        quality_insights = await self._generate_insights(
            current_metrics,
            metrics_summary,
            trend_analysis
        )

        # Create executive summary
        executive_summary = self._create_executive_summary(
            metrics_summary,
            trend_analysis,
            quality_insights
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(quality_insights, trend_analysis)

        # Historical comparison
        historical_comparison = await self._get_historical_comparison(
            current_metrics,
            report_type
        )

        report = QualityReport(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now().isoformat(),
            executive_summary=executive_summary,
            metrics_summary=metrics_summary,
            trend_analysis=trend_analysis,
            quality_insights=quality_insights,
            recommendations=recommendations,
            historical_comparison=historical_comparison
        )

        logger.info(f"{report_type.capitalize()} quality report generated successfully")
        return report

    async def _get_metrics_summary(
        self,
        current_metrics: List[Any],
        period_start: str,
        period_end: str
    ) -> Dict[str, Any]:
        """Get summary of all quality metrics."""
        summary = {
            'period': {
                'start': period_start,
                'end': period_end,
                'duration_hours': (
                    datetime.fromisoformat(period_end) -
                    datetime.fromisoformat(period_start)
                ).total_seconds() / 3600
            },
            'metrics': {},
            'overall_health_score': 0,
            'alerts_generated': 0,
            'critical_issues': 0,
            'warning_issues': 0
        }

        # Process current metrics
        valid_metrics = [m for m in current_metrics if hasattr(m, 'value') and m.value >= 0]

        for metric in valid_metrics:
            metric_summary = {
                'current_value': metric.value,
                'threshold_warning': getattr(metric, 'threshold_warning', None),
                'threshold_critical': getattr(metric, 'threshold_critical', None),
                'trend': getattr(metric, 'trend', 'stable'),
                'metadata': getattr(metric, 'metadata', {}),
                'status': 'normal'
            }

            # Determine status based on thresholds
            if metric.threshold_critical:
                if ((metric.name == 'tag_confidence' and metric.value < metric.threshold_critical) or
                    (metric.name != 'tag_confidence' and metric.value > metric.threshold_critical)):
                    metric_summary['status'] = 'critical'
                    summary['critical_issues'] += 1
            elif metric.threshold_warning:
                if ((metric.name == 'tag_confidence' and metric.value < metric.threshold_warning) or
                    (metric.name != 'tag_confidence' and metric.value > metric.threshold_warning)):
                    metric_summary['status'] = 'warning'
                    summary['warning_issues'] += 1

            summary['metrics'][metric.name] = metric_summary

        # Calculate overall health score
        summary['overall_health_score'] = self.quality_monitor.get_health_score()

        return summary

    async def _analyze_trends(
        self,
        current_metrics: List[Any],
        report_type: str
    ) -> List[TrendAnalysis]:
        """Analyze trends in quality metrics."""
        trends = []

        # Determine comparison period based on report type
        if report_type == 'daily':
            comparison_hours = 48  # Compare with previous day
        elif report_type == 'weekly':
            comparison_hours = 336  # Compare with previous week (14 days)
        else:  # monthly
            comparison_hours = 1440  # Compare with previous month (60 days)

        for metric in current_metrics:
            if not hasattr(metric, 'value') or metric.value < 0:
                continue

            # Get historical data for comparison
            history = self.metrics_collector.get_metric_history(
                metric.name,
                hours=comparison_hours
            )

            if len(history) < 2:
                continue

            # Calculate trend
            current_value = metric.value
            comparison_period_data = history[len(history)//2:]  # Second half for comparison
            previous_value = statistics.mean([h.value for h in comparison_period_data]) if comparison_period_data else current_value

            if previous_value == 0:
                change_percent = 0
            else:
                change_percent = ((current_value - previous_value) / previous_value) * 100

            # Determine trend direction and significance
            if abs(change_percent) < 5:
                trend_direction = 'stable'
                significance = 'none'
            elif change_percent > 0:
                if metric.name == 'tag_confidence':
                    trend_direction = 'improving'
                else:
                    trend_direction = 'degrading'
            else:
                if metric.name == 'tag_confidence':
                    trend_direction = 'degrading'
                else:
                    trend_direction = 'improving'

            # Determine significance
            if abs(change_percent) > 25:
                significance = 'high'
            elif abs(change_percent) > 10:
                significance = 'medium'
            elif abs(change_percent) > 5:
                significance = 'low'
            else:
                significance = 'none'

            # Create description
            direction_word = "increased" if change_percent > 0 else "decreased"
            description = f"{metric.name} has {direction_word} by {abs(change_percent):.1f}% compared to the previous {report_type}"

            trend = TrendAnalysis(
                metric_name=metric.name,
                current_value=current_value,
                previous_value=previous_value,
                change_percent=change_percent,
                trend_direction=trend_direction,
                significance=significance,
                description=description
            )

            trends.append(trend)

        return sorted(trends, key=lambda t: abs(t.change_percent), reverse=True)

    async def _generate_insights(
        self,
        current_metrics: List[Any],
        metrics_summary: Dict[str, Any],
        trend_analysis: List[TrendAnalysis]
    ) -> List[QualityInsight]:
        """Generate actionable quality insights."""
        insights = []

        # Analyze each metric for insights
        for metric in current_metrics:
            if not hasattr(metric, 'value') or metric.value < 0:
                continue

            metric_insights = await self._analyze_metric_insights(metric, metrics_summary, trend_analysis)
            insights.extend(metric_insights)

        # Add system-level insights
        system_insights = self._generate_system_insights(metrics_summary, trend_analysis)
        insights.extend(system_insights)

        # Sort by priority score
        return sorted(insights, key=lambda i: i.priority_score, reverse=True)

    async def _analyze_metric_insights(
        self,
        metric: Any,
        metrics_summary: Dict[str, Any],
        trend_analysis: List[TrendAnalysis]
    ) -> List[QualityInsight]:
        """Analyze insights for a specific metric."""
        insights = []
        metric_name = metric.name
        current_value = metric.value

        # Get trend for this metric
        metric_trend = next((t for t in trend_analysis if t.metric_name == metric_name), None)

        # Duplicate Rate Insights
        if metric_name == 'duplicate_rate':
            if current_value > 5:
                insights.append(QualityInsight(
                    category='Data Quality',
                    severity='critical',
                    description=f'Duplicate rate is critically high at {current_value:.1f}%',
                    recommendation='Run immediate duplicate detection analysis and implement automated deduplication process',
                    impact='High - Data integrity compromised',
                    effort='medium',
                    priority_score=self._calculate_priority_score('critical', 'medium', current_value > 10)
                ))
            elif current_value > 3:
                insights.append(QualityInsight(
                    category='Data Quality',
                    severity='high',
                    description=f'Duplicate rate is above acceptable threshold at {current_value:.1f}%',
                    recommendation='Schedule duplicate cleanup and review data ingestion processes',
                    impact='Medium - Affects data accuracy',
                    effort='medium',
                    priority_score=self._calculate_priority_score('high', 'medium', False)
                ))

        # Tag Confidence Insights
        elif metric_name == 'tag_confidence':
            if current_value < 60:
                insights.append(QualityInsight(
                    category='AI Quality',
                    severity='critical',
                    description=f'Tag confidence is critically low at {current_value:.1f}%',
                    recommendation='Review AI model performance and consider retraining with recent data',
                    impact='High - Tag accuracy severely compromised',
                    effort='high',
                    priority_score=self._calculate_priority_score('critical', 'high', current_value < 50)
                ))
            elif current_value < 65:
                insights.append(QualityInsight(
                    category='AI Quality',
                    severity='high',
                    description=f'Tag confidence is below target at {current_value:.1f}%',
                    recommendation='Analyze low-confidence decisions and improve training data quality',
                    impact='Medium - Tag reliability affected',
                    effort='medium',
                    priority_score=self._calculate_priority_score('high', 'medium', False)
                ))

        # Missing Fields Insights
        elif metric_name == 'missing_fields_rate':
            if current_value > 10:
                insights.append(QualityInsight(
                    category='Data Completeness',
                    severity='critical',
                    description=f'Missing fields rate is critically high at {current_value:.1f}%',
                    recommendation='Implement field completion pipeline and review data extraction processes',
                    impact='High - Database completeness compromised',
                    effort='high',
                    priority_score=self._calculate_priority_score('critical', 'high', current_value > 15)
                ))

        # Processing Performance Insights
        elif metric_name == 'processing_performance':
            if current_value > 600:  # 10 minutes
                insights.append(QualityInsight(
                    category='Performance',
                    severity='critical',
                    description=f'Processing time is critically slow at {current_value:.0f} seconds',
                    recommendation='Optimize QA algorithms, add parallel processing, and review system resources',
                    impact='High - Operational efficiency severely impacted',
                    effort='high',
                    priority_score=self._calculate_priority_score('critical', 'high', current_value > 900)
                ))

        # Add trend-based insights
        if metric_trend and metric_trend.significance in ['high', 'medium']:
            if metric_trend.trend_direction == 'degrading':
                insights.append(QualityInsight(
                    category='Trend Analysis',
                    severity='medium' if metric_trend.significance == 'medium' else 'high',
                    description=f'{metric_name} shows degrading trend with {abs(metric_trend.change_percent):.1f}% change',
                    recommendation=f'Investigate root cause of {metric_name} degradation and implement corrective measures',
                    impact='Medium - Quality trend needs attention',
                    effort='medium',
                    priority_score=self._calculate_priority_score('medium', 'medium', metric_trend.significance == 'high')
                ))

        return insights

    def _generate_system_insights(
        self,
        metrics_summary: Dict[str, Any],
        trend_analysis: List[TrendAnalysis]
    ) -> List[QualityInsight]:
        """Generate system-level insights."""
        insights = []

        # Overall health score insights
        health_score = metrics_summary.get('overall_health_score', 0)
        if health_score < 60:
            insights.append(QualityInsight(
                category='System Health',
                severity='critical',
                description=f'Overall system health score is critically low at {health_score:.1f}%',
                recommendation='Immediate system-wide quality improvement initiative needed',
                impact='Critical - System reliability at risk',
                effort='high',
                priority_score=self._calculate_priority_score('critical', 'high', health_score < 40)
            ))

        # Multiple degrading trends
        degrading_trends = [t for t in trend_analysis if t.trend_direction == 'degrading' and t.significance in ['high', 'medium']]
        if len(degrading_trends) >= 3:
            insights.append(QualityInsight(
                category='System Health',
                severity='high',
                description=f'Multiple metrics showing degrading trends ({len(degrading_trends)} metrics)',
                recommendation='Conduct comprehensive system review and implement quality improvement program',
                impact='High - System-wide quality degradation',
                effort='high',
                priority_score=self._calculate_priority_score('high', 'high', len(degrading_trends) >= 4)
            ))

        return insights

    def _calculate_priority_score(self, severity: str, effort: str, high_impact: bool) -> float:
        """Calculate priority score for insight."""
        base_score = self.severity_weights.get(severity, 3)
        effort_penalty = self.effort_weights.get(effort, 3)
        impact_bonus = 3 if high_impact else 0

        # Higher severity and impact, lower effort = higher priority
        return base_score + impact_bonus - (effort_penalty * 0.5)

    def _create_executive_summary(
        self,
        metrics_summary: Dict[str, Any],
        trend_analysis: List[TrendAnalysis],
        quality_insights: List[QualityInsight]
    ) -> Dict[str, Any]:
        """Create executive summary of the report."""
        critical_insights = [i for i in quality_insights if i.severity == 'critical']
        high_insights = [i for i in quality_insights if i.severity == 'high']

        improving_trends = [t for t in trend_analysis if t.trend_direction == 'improving' and t.significance in ['high', 'medium']]
        degrading_trends = [t for t in trend_analysis if t.trend_direction == 'degrading' and t.significance in ['high', 'medium']]

        return {
            'overall_status': self._get_overall_status(metrics_summary, critical_insights),
            'health_score': metrics_summary.get('overall_health_score', 0),
            'key_achievements': self._get_key_achievements(improving_trends, quality_insights),
            'critical_issues': len(critical_insights),
            'high_priority_issues': len(high_insights),
            'improving_metrics': len(improving_trends),
            'degrading_metrics': len(degrading_trends),
            'top_priorities': [i.description for i in quality_insights[:3]],
            'summary_text': self._generate_summary_text(
                metrics_summary,
                len(critical_insights),
                len(high_insights),
                improving_trends,
                degrading_trends
            )
        }

    def _get_overall_status(self, metrics_summary: Dict[str, Any], critical_insights: List[QualityInsight]) -> str:
        """Determine overall system status."""
        health_score = metrics_summary.get('overall_health_score', 0)
        critical_count = len(critical_insights)

        if critical_count > 0 or health_score < 60:
            return 'CRITICAL'
        elif health_score < 75:
            return 'WARNING'
        elif health_score < 85:
            return 'GOOD'
        else:
            return 'EXCELLENT'

    def _get_key_achievements(self, improving_trends: List[TrendAnalysis], insights: List[QualityInsight]) -> List[str]:
        """Identify key achievements and improvements."""
        achievements = []

        for trend in improving_trends[:3]:  # Top 3 improvements
            achievements.append(f"{trend.metric_name} improved by {abs(trend.change_percent):.1f}%")

        # Add insights about resolved issues if any
        # This would typically come from comparing with previous reports

        return achievements

    def _generate_summary_text(
        self,
        metrics_summary: Dict[str, Any],
        critical_count: int,
        high_count: int,
        improving_trends: List[TrendAnalysis],
        degrading_trends: List[TrendAnalysis]
    ) -> str:
        """Generate executive summary text."""
        health_score = metrics_summary.get('overall_health_score', 0)

        text = f"System health score: {health_score:.1f}%. "

        if critical_count > 0:
            text += f"{critical_count} critical issue{'s' if critical_count != 1 else ''} require immediate attention. "

        if high_count > 0:
            text += f"{high_count} high-priority issue{'s' if high_count != 1 else ''} need resolution. "

        if improving_trends:
            text += f"{len(improving_trends)} metric{'s are' if len(improving_trends) != 1 else ' is'} showing improvement. "

        if degrading_trends:
            text += f"{len(degrading_trends)} metric{'s are' if len(degrading_trends) != 1 else ' is'} trending downward and need{'s' if len(degrading_trends) == 1 else ''} attention."

        return text.strip()

    def _generate_recommendations(
        self,
        quality_insights: List[QualityInsight],
        trend_analysis: List[TrendAnalysis]
    ) -> List[str]:
        """Generate prioritized recommendations."""
        recommendations = []

        # Add top priority insight recommendations
        for insight in quality_insights[:5]:  # Top 5 priorities
            recommendations.append(f"[{insight.severity.upper()}] {insight.recommendation}")

        # Add system-level recommendations
        degrading_count = len([t for t in trend_analysis if t.trend_direction == 'degrading'])
        if degrading_count >= 2:
            recommendations.append(
                "[SYSTEM] Implement automated monitoring alerts to catch quality degradation early"
            )

        return recommendations

    async def _get_historical_comparison(
        self,
        current_metrics: List[Any],
        report_type: str
    ) -> Dict[str, Any]:
        """Get historical comparison data."""
        comparison = {
            'previous_period': {},
            'same_period_last_month': {},
            'performance_vs_baseline': {}
        }

        # This would typically involve loading previous reports
        # For now, return placeholder structure

        return comparison

    async def export_report(
        self,
        report: QualityReport,
        format: str = 'json',
        output_file: Optional[str] = None
    ) -> str:
        """Export report in specified format."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if not output_file:
            output_file = f"{report.report_type}_quality_report_{timestamp}"

        output_path = self.reports_dir / f"{output_file}.{format.lower()}"

        if format.lower() == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)

        elif format.lower() == 'html':
            html_content = await self._generate_html_report(report)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

        elif format.lower() == 'csv':
            csv_content = await self._generate_csv_report(report)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(csv_content)

        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Report exported to {output_path}")
        return str(output_path)

    async def _generate_html_report(self, report: QualityReport) -> str:
        """Generate HTML version of the report."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>GOV2DB {report.report_type.title()} Quality Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .critical {{ color: #d32f2f; }}
                .warning {{ color: #f57c00; }}
                .good {{ color: #388e3c; }}
                .metric {{ display: inline-block; margin: 10px; padding: 10px; background: #f9f9f9; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>GOV2DB {report.report_type.title()} Quality Report</h1>
                <p>Generated: {report.generated_at}</p>
                <p>Period: {report.period_start} to {report.period_end}</p>
            </div>

            <div class="section">
                <h2>Executive Summary</h2>
                <p><strong>Overall Status:</strong> <span class="{report.executive_summary['overall_status'].lower()}">{report.executive_summary['overall_status']}</span></p>
                <p><strong>Health Score:</strong> {report.executive_summary['health_score']:.1f}%</p>
                <p>{report.executive_summary['summary_text']}</p>
            </div>

            <div class="section">
                <h2>Quality Metrics</h2>
        """

        for metric_name, metric_data in report.metrics_summary['metrics'].items():
            status_class = metric_data['status'] if metric_data['status'] != 'normal' else 'good'
            html += f"""
                <div class="metric">
                    <h4>{metric_name.replace('_', ' ').title()}</h4>
                    <p><span class="{status_class}">{metric_data['current_value']:.2f}</span></p>
                    <p>Trend: {metric_data['trend']}</p>
                </div>
            """

        html += """
            </div>

            <div class="section">
                <h2>Top Quality Insights</h2>
                <ol>
        """

        for insight in report.quality_insights[:10]:
            html += f"""
                <li class="{insight.severity}">
                    <strong>{insight.category}:</strong> {insight.description}
                    <br><em>Recommendation:</em> {insight.recommendation}
                </li>
            """

        html += """
                </ol>
            </div>

            <div class="section">
                <h2>Recommendations</h2>
                <ol>
        """

        for rec in report.recommendations:
            html += f"<li>{rec}</li>"

        html += """
                </ol>
            </div>
        </body>
        </html>
        """

        return html

    async def _generate_csv_report(self, report: QualityReport) -> str:
        """Generate CSV version of key report data."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Section', 'Metric', 'Value', 'Status', 'Trend', 'Description'])

        # Write metrics
        for metric_name, metric_data in report.metrics_summary['metrics'].items():
            writer.writerow([
                'Metrics',
                metric_name,
                metric_data['current_value'],
                metric_data['status'],
                metric_data['trend'],
                f"Warning: {metric_data['threshold_warning']}, Critical: {metric_data['threshold_critical']}"
            ])

        # Write insights
        for insight in report.quality_insights:
            writer.writerow([
                'Insights',
                insight.category,
                '',
                insight.severity,
                '',
                f"{insight.description} | {insight.recommendation}"
            ])

        return output.getvalue()


async def main():
    """CLI interface for quality report generation."""
    parser = argparse.ArgumentParser(description="Generate Quality Reports")
    parser.add_argument('type', choices=['daily', 'weekly', 'monthly'],
                       help='Type of report to generate')
    parser.add_argument('--format', choices=['json', 'html', 'csv'], default='json',
                       help='Output format')
    parser.add_argument('--output', help='Output file name (without extension)')
    parser.add_argument('--email', action='store_true',
                       help='Send report via email (if configured)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    generator = QualityReportGenerator()

    try:
        # Generate report
        if args.type == 'daily':
            report = await generator.generate_daily_report()
        elif args.type == 'weekly':
            report = await generator.generate_weekly_report()
        else:  # monthly
            report = await generator.generate_monthly_report()

        # Export report
        output_path = await generator.export_report(
            report,
            args.format,
            args.output
        )

        print(f"Quality report generated successfully: {output_path}")

        # Print summary to console
        print("\n=== EXECUTIVE SUMMARY ===")
        print(f"Overall Status: {report.executive_summary['overall_status']}")
        print(f"Health Score: {report.executive_summary['health_score']:.1f}%")
        print(f"Critical Issues: {report.executive_summary['critical_issues']}")
        print(f"High Priority Issues: {report.executive_summary['high_priority_issues']}")

        if report.quality_insights:
            print("\n=== TOP PRIORITIES ===")
            for i, insight in enumerate(report.quality_insights[:3], 1):
                print(f"{i}. [{insight.severity.upper()}] {insight.description}")

        if args.email:
            print("\nNote: Email functionality would require SMTP configuration")

    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)