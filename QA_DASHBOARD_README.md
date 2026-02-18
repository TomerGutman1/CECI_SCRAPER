# QA Monitoring Dashboard for GOV2DB

A comprehensive real-time monitoring dashboard for quality assurance metrics, trends, and alerts in the GOV2DB Israeli Government Decisions database.

## 🌟 Features

### Real-time Monitoring
- **Live QA Metrics**: Health scores, issue rates, and system status
- **Interactive Dashboards**: Modern web interface with real-time updates
- **WebSocket Integration**: Live data streaming without page refreshes
- **Alert System**: Instant notifications for critical issues

### Visualization & Analytics
- **Quality Score Cards**: Overall system health metrics
- **Issue Heatmaps**: Visual distribution of issues across QA checks
- **Trend Charts**: Historical quality trends and performance analysis
- **Alert Panel**: Real-time alert management with severity filtering

### Automated Reporting
- **Daily Reports**: Automated quality summaries
- **Weekly Trends**: Week-over-week performance analysis
- **Monthly Executive Reports**: Comprehensive analytics with recommendations
- **Export Capabilities**: JSON and CSV report generation

### Performance & Scalability
- **Redis Caching**: High-performance caching layer
- **Background Tasks**: Scheduled scans and metric updates
- **REST API**: Full programmatic access to all features
- **Responsive Design**: Mobile-friendly interface

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Redis (recommended for production)
- GOV2DB environment with Supabase connection
- Required environment variables in `.env`:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`

### Installation

1. **Install Dashboard Dependencies**:
   ```bash
   pip install -r requirements_dashboard.txt
   ```

2. **Start the Dashboard**:
   ```bash
   ./start_dashboard.sh
   ```

3. **Access the Dashboard**:
   Open your browser to `http://localhost:5000`

### Development Mode

```bash
./start_dashboard.sh --dev --port 5001
```

## 📊 Dashboard Components

### 1. Main Dashboard (`/`)
- **Quality Score Cards**: Real-time health metrics
- **Trend Charts**: Historical performance visualization
- **Live Alerts**: Current system alerts and notifications
- **QA Checks Grid**: Status of all quality assurance checks
- **Issue Heatmap**: Visual distribution of issues by type and severity
- **Recent Issues Table**: Latest critical issues with details

### 2. Alerts Management (`/alerts`)
- **Alert Overview**: Summary cards by severity level
- **Alert Filtering**: Filter by severity, status, or search terms
- **Alert Details**: Detailed information for each alert
- **Bulk Operations**: Resolve multiple alerts at once
- **Alert History**: Track resolved and active alerts

### 3. Reports & Analytics (`/reports`)
- **Current Status Report**: Real-time system snapshot
- **Weekly Summary**: 7-day trend analysis with comparisons
- **Monthly Executive Report**: Comprehensive analytics with recommendations
- **Export Options**: Download reports in JSON or CSV format

## 🔧 Configuration

### Configuration File (`dashboard_config.json`)

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "redis": {
    "host": "localhost",
    "port": 6379,
    "db": 0
  },
  "monitoring": {
    "scan_interval_minutes": 15,
    "metrics_update_minutes": 5,
    "alert_threshold_critical": 50,
    "alert_threshold_warning": 25
  },
  "reporting": {
    "daily_report_hour": 9,
    "weekly_report_hour": 9,
    "monthly_report_hour": 9,
    "enable_email_reports": false
  }
}
```

### Environment Variables

```bash
# Required
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Optional Dashboard Configuration
QA_DASHBOARD_PORT=5000
QA_DASHBOARD_DEBUG=false
QA_DASHBOARD_REDIS_HOST=localhost
QA_DASHBOARD_REDIS_PORT=6379
```

## 🎯 REST API Endpoints

### Metrics
- `GET /api/qa/metrics` - Current QA metrics
- `GET /api/qa/issues` - Current issues with filtering
- `GET /api/qa/history?days=7` - Historical trend data

### Alerts
- `GET /api/qa/alerts` - Current alerts
- `POST /api/qa/alerts/{id}/resolve` - Resolve an alert

### Scanning
- `POST /api/qa/scan/trigger` - Trigger a new QA scan

### Reports
- `POST /api/qa/export` - Generate and export reports

### Example API Usage

```python
import requests

# Get current metrics
response = requests.get('http://localhost:5000/api/qa/metrics')
metrics = response.json()
print(f"Health Score: {metrics['overall_health_score']}%")

# Get issues with filtering
response = requests.get('http://localhost:5000/api/qa/issues?severity=critical&limit=10')
issues = response.json()

# Export weekly report
response = requests.post('http://localhost:5000/api/qa/export', json={
    'type': 'weekly',
    'format': 'json'
})
report = response.json()
```

## 🔍 QA Checks Integration

The dashboard monitors all 19 QA checks from the GOV2DB system:

### Phase 1 Checks
- **operativity**: Decision operativity classification
- **policy-relevance**: Policy tag relevance analysis
- **policy-fallback**: Policy fallback rate monitoring

### Phase 2 Checks
- **operativity-vs-content**: Content consistency validation
- **tag-body**: Tag and government body consistency
- **committee-tag**: Committee tag validation
- **location-hallucination**: Location accuracy verification
- **government-body-hallucination**: Government body accuracy
- **summary-quality**: Summary quality assessment

### Cross-field Validation Checks
- **summary-vs-tags**: Summary and tags alignment
- **location-vs-body**: Location and body consistency
- **date-vs-government**: Date and government alignment
- **title-vs-content**: Title and content correlation

### Data Quality Checks
- **date-validity**: Date format and validity
- **content-quality**: Content completeness and quality
- **tag-consistency**: Tag consistency across records
- **content-completeness**: Missing or incomplete data detection

## 🚨 Alert System

### Alert Severity Levels
- **Critical**: Issue rate > 50% (requires immediate attention)
- **Warning**: Issue rate > 25% (elevated monitoring needed)
- **Info**: General notifications and status updates

### Alert Types
- **Quality Degradation**: Significant increase in issue rates
- **Check Failures**: Specific QA checks reporting high failure rates
- **System Anomalies**: Unusual patterns or data inconsistencies
- **Performance Issues**: Slow response times or processing delays

### Alert Management
- **Real-time Notifications**: Instant WebSocket alerts
- **Alert History**: Track all alerts over time
- **Bulk Operations**: Resolve multiple alerts simultaneously
- **Auto-Resolution**: Configurable auto-resolution rules

## 📈 Performance Monitoring

### Caching Strategy
- **Metrics Cache**: 5-minute TTL for dashboard metrics
- **Historical Data Cache**: 1-hour TTL for trend data
- **Report Cache**: 30-minute TTL for generated reports
- **Fallback Caching**: In-memory cache when Redis unavailable

### Background Tasks
- **Periodic Scans**: Automated QA scans every 15 minutes
- **Metrics Updates**: Real-time metric refreshes every 5 minutes
- **Report Generation**: Scheduled daily/weekly/monthly reports
- **Cache Cleanup**: Automatic cache invalidation and cleanup

### Scalability Considerations
- **Stratified Sampling**: Efficient sampling for large datasets
- **Async Processing**: Non-blocking background operations
- **WebSocket Management**: Efficient real-time communication
- **Database Connection Pooling**: Optimized database access

## 🛠️ Deployment

### Development Deployment
```bash
./start_dashboard.sh --dev --port 5001
```

### Production Deployment

1. **Configure Production Settings**:
   ```json
   {
     "server": {
       "host": "0.0.0.0",
       "port": 5000,
       "debug": false,
       "secret_key": "your-secure-production-key"
     },
     "redis": {
       "host": "your-redis-host",
       "port": 6379,
       "password": "your-redis-password"
     }
   }
   ```

2. **Start with Production Config**:
   ```bash
   ./start_dashboard.sh --config production_config.json
   ```

3. **Use Process Manager** (recommended):
   ```bash
   # Using PM2
   pm2 start bin/qa_dashboard.py --name qa-dashboard

   # Using systemd
   sudo systemctl enable qa-dashboard
   sudo systemctl start qa-dashboard
   ```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements_dashboard.txt
EXPOSE 5000

CMD ["python", "bin/qa_dashboard.py", "--host", "0.0.0.0", "--port", "5000"]
```

```bash
docker build -t qa-dashboard .
docker run -p 5000:5000 --env-file .env qa-dashboard
```

## 🔐 Security Considerations

### Authentication (Future Enhancement)
- Currently runs without authentication (internal tool)
- Can be extended with OAuth, LDAP, or custom authentication
- Role-based access control for different user types

### Network Security
- **CORS Configuration**: Configurable allowed origins
- **Rate Limiting**: Optional API rate limiting
- **HTTPS Support**: SSL/TLS termination (via reverse proxy)

### Data Security
- **Environment Variables**: Secure credential management
- **Database Access**: Read-only service role recommended
- **Audit Logging**: Comprehensive activity logging

## 🧪 Testing

### Unit Tests (Future)
```bash
pytest tests/test_dashboard.py
```

### Integration Tests (Future)
```bash
pytest tests/integration/
```

### Load Testing (Future)
```bash
locust -f tests/load_test.py --host=http://localhost:5000
```

## 📝 Maintenance

### Log Management
- **Log Rotation**: Automatic log file rotation
- **Log Levels**: Configurable logging verbosity
- **Error Tracking**: Comprehensive error logging and tracking

### Database Maintenance
- **Connection Monitoring**: Automatic connection health checks
- **Query Optimization**: Efficient database queries
- **Data Archival**: Historical data management strategies

### Cache Management
- **Cache Monitoring**: Redis performance monitoring
- **Cache Invalidation**: Intelligent cache refresh strategies
- **Memory Management**: Efficient memory usage patterns

## 🤝 Contributing

### Code Standards
- **Python Style**: PEP 8 compliance
- **Type Hints**: Full type annotation coverage
- **Documentation**: Comprehensive docstrings
- **Error Handling**: Explicit error handling

### Development Workflow
1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Update documentation
5. Submit pull request

## 📋 Troubleshooting

### Common Issues

**Dashboard won't start**:
```bash
# Check environment variables
source .env && python -c "import os; print('SUPABASE_URL:', os.getenv('SUPABASE_URL'))"

# Check database connection
python -c "from src.gov_scraper.db.connector import get_supabase_client; print(get_supabase_client())"
```

**Redis connection errors**:
```bash
# Check Redis status
redis-cli ping

# Start Redis if not running
redis-server
```

**Performance issues**:
- Reduce scan frequency in configuration
- Increase cache TTL values
- Use smaller sample sizes for testing

**WebSocket disconnections**:
- Check firewall settings
- Verify proxy configuration
- Monitor network connectivity

## 📚 Additional Resources

- [GOV2DB Main Documentation](README.md)
- [QA System Documentation](QA-LESSONS.md)
- [Server Operations Guide](SERVER-OPERATIONS.md)
- [API Documentation](API_DOCS.md) (when available)

## 🎉 Success Metrics

The QA Dashboard enables:
- **Proactive Monitoring**: Early detection of data quality issues
- **Performance Tracking**: Historical trend analysis and reporting
- **Operational Efficiency**: Automated alerting and reporting
- **Data Confidence**: Comprehensive quality assurance oversight
- **Stakeholder Communication**: Executive reports and metrics visualization

## 📞 Support

For issues, questions, or feature requests:
1. Check the troubleshooting section above
2. Review the GOV2DB main documentation
3. Create an issue in the project repository
4. Contact the development team

---

**Dashboard Version**: 1.0.0
**Last Updated**: February 2026
**Compatible with**: GOV2DB v1.8.0+