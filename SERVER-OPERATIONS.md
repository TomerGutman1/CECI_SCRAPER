# GOV2DB Server Operations Guide

## Server Connection Details

| Field | Value |
|-------|-------|
| **IP** | 178.62.39.248 |
| **User** | root |
| **SSH Host Alias** | ceci |
| **Project Path** | /root/ceci-ai-production/ceci-ai/GOV2DB |
| **Container Name** | gov2db-scraper |
| **Docker Image** | tomerjoe/gov2db-scraper:latest |
| **Network** | compose_ceci-internal |
| **Daily Sync** | 02:00 AM (Asia/Jerusalem) |

---

## SSH Setup (One-Time)

```bash
# Create SSH key file
mkdir -p ~/.ssh
cat > ~/.ssh/ceci-ai-key << 'EOF'
# Paste your private SSH key here
EOF
chmod 600 ~/.ssh/ceci-ai-key

# Add to SSH config
cat >> ~/.ssh/config << 'EOF'

Host ceci
    HostName 178.62.39.248
    User root
    IdentityFile ~/.ssh/ceci-ai-key
    ServerAliveInterval 60
EOF
```

**Connect:** `ssh ceci`

---

## Daily Verification Checklist

### Quick Health Check (30 seconds)

```bash
ssh ceci "docker ps | grep gov2db && docker inspect --format='Health: {{.State.Health.Status}}' gov2db-scraper"
```

**Expected output:**
```
gov2db-scraper   Up X hours (healthy)   tomerjoe/gov2db-scraper:latest
Health: healthy
```

### Full Verification (2 minutes)

```bash
ssh ceci

# 1. Container running?
docker ps | grep gov2db-scraper

# 2. Health status
docker inspect --format='{{.State.Health.Status}}' gov2db-scraper

# 3. Timezone correct (IST/IDT)?
docker exec gov2db-scraper date

# 4. Cron configured for 02:00?
docker exec gov2db-scraper cat /etc/cron.d/gov2db-scraper | grep "^0 2"

# 5. Run taste tool
./GOV2DB/taste.sh

# 6. Check sync log (after 02:00 AM)
tail -20 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log
```

---

## Log Locations

| Log | Path | Description |
|-----|------|-------------|
| **Daily Sync** | `GOV2DB/logs/daily_sync.log` | Main sync output |
| **Cron** | `GOV2DB/logs/cron.log` | Cron daemon output |
| **Container** | `docker logs gov2db-scraper` | Container stdout |

### View Logs

```bash
# Live sync log
ssh ceci "tail -f /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log"

# Last 50 lines of sync log
ssh ceci "tail -50 /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log"

# Container logs
ssh ceci "docker logs --tail 100 gov2db-scraper"

# Follow container logs
ssh ceci "docker logs -f gov2db-scraper"
```

---

## Manual Operations

### Run Manual Sync

```bash
# Quick test (1 decision)
ssh ceci "docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose"

# Full sync
ssh ceci "docker exec gov2db-scraper python3 bin/sync.py --unlimited --no-approval --verbose"
```

### Restart Container

```bash
ssh ceci "docker restart gov2db-scraper"
```

### Enter Container Shell

```bash
ssh ceci "docker exec -it gov2db-scraper bash"
```

### Check Database Connection

```bash
ssh ceci "docker exec gov2db-scraper python3 -c \"
from gov_scraper.db.connector import get_supabase_client
client = get_supabase_client()
r = client.table('israeli_government_decisions').select('count').limit(1).execute()
print('DB Connection: OK')
\""
```

---

## Troubleshooting

### Container Not Running

```bash
# Check status
ssh ceci "docker ps -a | grep gov2db"

# View logs for error
ssh ceci "docker logs gov2db-scraper"

# Restart
ssh ceci "docker restart gov2db-scraper"
```

### Container Unhealthy

```bash
# Check health details
ssh ceci "docker inspect gov2db-scraper | grep -A 20 'Health'"

# Run health check manually
ssh ceci "docker exec gov2db-scraper /usr/local/bin/healthcheck.sh"
```

### Sync Not Running at 02:00

```bash
# Check cron is running
ssh ceci "docker exec gov2db-scraper ps aux | grep cron"

# Check cron configuration
ssh ceci "docker exec gov2db-scraper cat /etc/cron.d/gov2db-scraper"

# Check timezone
ssh ceci "docker exec gov2db-scraper date"
```

### Disk Space Issues

```bash
# Check disk space
ssh ceci "df -h"

# Check Docker space
ssh ceci "docker system df"

# Clean up (careful!)
ssh ceci "docker system prune -f"
```

---

## Update Container

### Pull New Image & Restart

```bash
ssh ceci "docker pull tomerjoe/gov2db-scraper:latest && \
  docker stop gov2db-scraper && \
  docker rm gov2db-scraper && \
  docker run -d \
    --name gov2db-scraper \
    --restart unless-stopped \
    --env-file /root/ceci-ai-production/ceci-ai/GOV2DB/.env \
    -v /root/ceci-ai-production/ceci-ai/GOV2DB/logs:/app/logs \
    -v /root/ceci-ai-production/ceci-ai/GOV2DB/data:/app/data \
    --network compose_ceci-internal \
    --memory 1g \
    --cpus 0.9 \
    tomerjoe/gov2db-scraper:latest"
```

### Rebuild Locally & Push

```bash
# On local machine
cd /Users/tomergutman/Downloads/GOV2DB
docker buildx build --platform linux/amd64 -t tomerjoe/gov2db-scraper:latest --push .
```

---

## Emergency Rollback

```bash
ssh ceci "docker stop gov2db-scraper && docker rm gov2db-scraper"
```

This completely removes GOV2DB without affecting other containers.

---

## Verification After Sync (Check Tomorrow Morning)

After 02:00 AM, run:

```bash
ssh ceci "./GOV2DB/taste.sh"
```

**Expected output includes:**
- 5 latest decisions from DB
- Container status: running | Health: healthy
- Last 5 lines of sync log showing completion

---

## Contact / Resources

- **Docker Hub:** https://hub.docker.com/r/tomerjoe/gov2db-scraper
- **GitHub:** https://github.com/TomerGutman1/CECI_SCRAPER
- **Supabase:** https://hthrsrekzyobmlvtquub.supabase.co

---

*Last updated: 2026-01-20*
*Deployed by: Claude Code*
