# GOV2DB Docker Deployment Guide

## Overview

This guide explains how to deploy GOV2DB scraper as a Docker container that runs daily at 02:00 AM (Asia/Jerusalem timezone).

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 1.29+
- Existing docker-compose network (for integration)
- OpenAI API key
- Supabase credentials

## Quick Start (Standalone)

### 1. Build the Image

```bash
docker build -t gov2db-scraper:latest .
```

### 2. Create Environment File

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
TZ=Asia/Jerusalem
```

### 3. Run with Docker Compose

```bash
docker-compose up -d
```

### 4. Verify Health

```bash
# Check container status
docker ps

# Check health status
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# View logs
docker logs -f gov2db-scraper

# View sync logs
docker exec gov2db-scraper tail -f /app/logs/daily_sync.log
```

---

## Integration with Existing Docker Compose

### Step 1: Add Service to Your docker-compose.yml

```yaml
services:
  # ... your existing services ...

  gov2db-scraper:
    build:
      context: ./path/to/GOV2DB
      dockerfile: Dockerfile
    container_name: gov2db-scraper
    restart: unless-stopped
    env_file:
      - ./path/to/GOV2DB/.env
    volumes:
      - ./path/to/GOV2DB/logs:/app/logs
      - ./path/to/GOV2DB/data:/app/data
    networks:
      - your-network-name  # Use your existing network
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

networks:
  your-network-name:
    external: true
```

### Step 2: Start the Service

```bash
# Start only the scraper (if other services already running)
docker-compose up -d gov2db-scraper

# Or restart entire stack
docker-compose up -d
```

---

## Run Modes

### Daily Automated Mode (Default)

Container runs cron daemon and executes sync at 02:00 AM daily:

```bash
docker-compose up -d
```

### Manual One-Time Execution

```bash
# Run sync immediately
docker run --rm \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  gov2db-scraper:latest \
  once

# Or with existing container
docker exec gov2db-scraper python3 bin/sync.py --unlimited --no-approval --verbose
```

### Interactive Debug Mode

```bash
# Get a bash shell in the container
docker exec -it gov2db-scraper bash

# Then run commands manually
cd /app
python3 bin/sync.py --max-decisions 5 --verbose
```

---

## Monitoring & Maintenance

### View Logs

```bash
# Container logs (cron output)
docker logs gov2db-scraper

# Daily sync logs
docker exec gov2db-scraper tail -f /app/logs/daily_sync.log

# All logs in logs directory
docker exec gov2db-scraper ls -lh /app/logs/
```

### Health Check

```bash
# Health status
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# Detailed health check output
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' gov2db-scraper

# Manual health check
docker exec gov2db-scraper /usr/local/bin/healthcheck.sh
```

### Database Connection Test

```bash
docker exec gov2db-scraper python3 tests/test_connection.py
```

### Check Next Scheduled Run

```bash
# View cron jobs
docker exec gov2db-scraper crontab -l

# Check if cron daemon is running
docker exec gov2db-scraper ps aux | grep cron
```

### Access Data Files

```bash
# Logs are in ./logs/ (mounted volume)
ls -lh logs/

# Data exports in ./data/
ls -lh data/

# View latest log
tail -f logs/daily_sync.log
```

---

## Troubleshooting

### Container Fails to Start

```bash
# Check logs
docker logs gov2db-scraper

# Check environment variables
docker exec gov2db-scraper env | grep -E 'OPENAI|SUPABASE'

# Test in interactive mode
docker run --rm -it --env-file .env gov2db-scraper:latest bash
```

### Sync Not Running at Scheduled Time

```bash
# Verify cron is running
docker exec gov2db-scraper ps aux | grep cron

# Check cron logs
docker exec gov2db-scraper cat /app/logs/cron.log

# Verify timezone
docker exec gov2db-scraper date
# Should show Asia/Jerusalem time

# Manually trigger sync to test
docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose
```

### Database Connection Issues

```bash
# Test connection
docker exec gov2db-scraper python3 tests/test_connection.py

# Check environment variables
docker exec gov2db-scraper env | grep SUPABASE

# Verify network connectivity
docker exec gov2db-scraper curl -I https://hthrsrekzyobmlvtquub.supabase.co
```

### OpenAI API Issues

```bash
# Check API key is set
docker exec gov2db-scraper env | grep OPENAI_API_KEY

# Test API connectivity
docker exec gov2db-scraper python3 -c "
import os
from openai import OpenAI
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
response = client.chat.completions.create(
    model='gpt-3.5-turbo',
    messages=[{'role': 'user', 'content': 'test'}],
    max_tokens=5
)
print('API key works!')
"
```

### Health Check Failing

```bash
# Run health check manually
docker exec gov2db-scraper /usr/local/bin/healthcheck.sh

# Check last success timestamp
docker exec gov2db-scraper cat /app/healthcheck/last_success.txt

# Force update health check (after successful manual sync)
docker exec gov2db-scraper sh -c 'echo "$(date -Iseconds)" > /app/healthcheck/last_success.txt'
```

---

## Configuration

### Change Sync Schedule

Edit `docker/crontab` before building:

```cron
# Example: Run at 03:30 AM instead
30 3 * * * cd /app && python3 bin/sync.py ...
```

Rebuild image:
```bash
docker-compose build
docker-compose up -d
```

### Change Safety Mode

Edit `docker/crontab` to use `--safety-mode extra-safe`:

```cron
0 2 * * * cd /app && python3 bin/sync.py --unlimited --no-approval --verbose --safety-mode extra-safe >> /app/logs/daily_sync.log 2>&1 ...
```

### Change Timezone

Update `docker-compose.yml`:

```yaml
environment:
  - TZ=America/New_York  # or any valid timezone
```

---

## Updating the Container

### Update Code

```bash
# Pull latest code
cd /path/to/GOV2DB
git pull

# Rebuild image
docker-compose build gov2db-scraper

# Restart container
docker-compose up -d gov2db-scraper
```

### Update Tag Lists

Since `new_tags.md` and `new_departments.md` are mounted as volumes (read-only), you can update them without rebuilding:

```bash
# Edit files on host
vim new_tags.md

# Changes take effect immediately (no restart needed for next sync)
```

---

## Resource Management

### Disk Space

```bash
# Check container disk usage
docker exec gov2db-scraper du -sh /app/logs /app/data

# Check log rotation status
docker exec gov2db-scraper ls -lh /app/logs/

# Manual log cleanup (if needed)
docker exec gov2db-scraper find /app/logs -name "*.log.*" -mtime +30 -delete
```

### Memory Usage

```bash
# Monitor resource usage
docker stats gov2db-scraper

# Check current memory
docker inspect --format='{{.HostConfig.Memory}}' gov2db-scraper
```

---

## Backup & Recovery

### Backup Data

```bash
# Logs and data are in mounted volumes
tar -czf gov2db-backup-$(date +%Y%m%d).tar.gz logs/ data/
```

### Restore from Backup

```bash
tar -xzf gov2db-backup-YYYYMMDD.tar.gz
docker-compose up -d
```

---

## Security Best Practices

1. **Never commit .env file** - Always use `.env.example` as template
2. **Use secrets management** - Consider Docker secrets for production:
   ```yaml
   secrets:
     - openai_api_key
     - supabase_key
   ```
3. **Rotate API keys regularly** - Update `.env` and restart container
4. **Limit network access** - Use custom networks, not bridge
5. **Review logs** - Check for suspicious activity in logs

---

## Production Deployment Checklist

- [ ] `.env` file created with valid credentials
- [ ] Logs directory exists and is writable
- [ ] Data directory exists and is writable
- [ ] Database connection tested (`make test-conn`)
- [ ] Container health check passing
- [ ] Cron schedule verified (check timezone)
- [ ] Log rotation configured
- [ ] Resource limits set (CPU, memory)
- [ ] Backup strategy in place
- [ ] Monitoring alerts configured
- [ ] API key rotation schedule established

---

## Advanced Topics

### Running Multiple Instances

If you need to run multiple scrapers (e.g., for different government numbers):

```yaml
services:
  gov2db-scraper-37:
    # ... configuration for government 37 ...

  gov2db-scraper-36:
    # ... configuration for government 36 ...
```

### Custom Cron Schedule

For more complex schedules, edit `docker/crontab`:

```cron
# Run twice daily (02:00 and 14:00)
0 2,14 * * * cd /app && python3 bin/sync.py ...

# Run on weekdays only
0 2 * * 1-5 cd /app && python3 bin/sync.py ...
```

### External Monitoring

Integrate with monitoring systems like Prometheus, Grafana, or Datadog:

```yaml
# Example: Adding labels for monitoring
services:
  gov2db-scraper:
    labels:
      - "prometheus.scrape=true"
      - "prometheus.port=8080"
```

---

## Support

For issues or questions:
1. Check logs: `docker logs gov2db-scraper`
2. Run health check: `docker exec gov2db-scraper /usr/local/bin/healthcheck.sh`
3. Review CLAUDE.md for project documentation
4. Check GitHub issues

---

## Appendix: File Structure

```
GOV2DB/
├── Dockerfile                      # Main container definition
├── docker-compose.yml              # Compose template
├── .dockerignore                   # Build optimization
├── README-DOCKER.md               # This file
├── docker/
│   ├── docker-entrypoint.sh       # Entry point script
│   ├── healthcheck.sh             # Health monitoring
│   ├── crontab                    # Cron schedule
│   └── logrotate.conf             # Log rotation config
├── logs/                          # Mounted volume (persistent)
├── data/                          # Mounted volume (persistent)
└── [existing project files...]
```

---

## Quick Reference Commands

```bash
# Build
docker build -t gov2db-scraper:latest .

# Run standalone
docker-compose up -d

# Run once (manual)
docker exec gov2db-scraper python3 bin/sync.py --unlimited --no-approval --verbose

# View logs
docker logs -f gov2db-scraper
tail -f logs/daily_sync.log

# Health check
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# Debug shell
docker exec -it gov2db-scraper bash

# Stop
docker-compose down

# Rebuild after code changes
docker-compose build && docker-compose up -d
```
