# GOV2DB Israeli Government Decisions Scraper
# Production-ready Docker image with Selenium, Python, and automated daily sync

FROM selenium/standalone-chrome:latest

# Switch to root for setup
USER root

# Install Python 3.11 and required system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3-venv \
    cron \
    tzdata \
    logrotate \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running scraper (security best practice)
RUN useradd -m -u 1000 -s /bin/bash scraper

# Set working directory
WORKDIR /app

# Copy requirements first (layer caching optimization)
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY bin/ ./bin/
COPY src/ ./src/
COPY setup.py .
COPY new_tags.md new_departments.md ./

# Install package in editable mode
RUN pip3 install -e .

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/healthcheck \
    && chown -R scraper:scraper /app

# Copy entrypoint and health check scripts
COPY docker/docker-entrypoint.sh /usr/local/bin/
COPY docker/healthcheck.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/healthcheck.sh

# Setup cron job for daily sync at 02:00 AM
COPY docker/crontab /etc/cron.d/gov2db-scraper
RUN chmod 0644 /etc/cron.d/gov2db-scraper \
    && crontab -u scraper /etc/cron.d/gov2db-scraper

# Setup logrotate
COPY docker/logrotate.conf /etc/logrotate.d/gov2db
RUN chmod 0644 /etc/logrotate.d/gov2db

# Switch to non-root user
USER scraper

# Expose health check port (optional, for HTTP health endpoint)
EXPOSE 8080

# Environment defaults (override via docker-compose)
ENV TZ=Asia/Jerusalem \
    PYTHONUNBUFFERED=1 \
    SYNC_MODE=daily

# Health check
HEALTHCHECK --interval=1h --timeout=30s --start-period=5m --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

# Entry point
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["cron"]
