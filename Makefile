# Israeli Government Decisions Scraper - Makefile
# Easy commands for common operations

SHELL := /bin/bash
PYTHON := python3
VENV_DIR := venv
BIN_DIR := bin
SRC_DIR := src
TEST_DIR := tests
DOCS_DIR := docs

.PHONY: help install sync overnight large-batch test test-connection clean docs lint format setup migrate-preview migrate-preview-n migrate-dry migrate-execute migrate-execute-yes migrate-all-years migrate-year monitor monitor-30 qa-scan qa-scan-check qa-fix-preview qa-fix-dry qa-fix-execute special-tags-preview special-tags-dry special-tags-year special-tags-all incremental-qa-setup incremental-qa-run incremental-qa-status incremental-qa-report incremental-qa-cleanup test-qa test-unit test-integration test-performance test-regression test-property test-all-qa test-coverage test-report install-dev setup-dev format-check security pre-commit install-hooks ci-test health-check discover discover-resume discover-test full-scrape full-scrape-test push-local push-local-qa

# Default target - show help
help:
	@echo "🏛️  Israeli Government Decisions Scraper"
	@echo "======================================"
	@echo ""
	@echo "📋 Available commands:"
	@echo "  make setup        - Initial project setup (install dependencies)"
	@echo "  make sync         - Run daily sync (unlimited, auto-approve)"
	@echo "  make overnight    - Run overnight sync for large batches"
	@echo "  make large-batch  - Run large batch sync with progress tracking"
	@echo "  make test         - Run all tests"
	@echo "  make test-conn    - Test database connection"
	@echo "  make clean        - Clean up generated files"
	@echo "  make docs         - View documentation"
	@echo "  make lint         - Run code linting (if available)"
	@echo "  make format       - Format code (if available)"
	@echo ""
	@echo "📊 Monitoring commands:"
	@echo "  make monitor      - Tag quality report (last 7 days)"
	@echo "  make monitor-30   - Tag quality report (last 30 days)"
	@echo ""
	@echo "🔍 QA commands:"
	@echo "  make qa-scan                     - Full QA scan (all checks)"
	@echo "  make qa-scan-check check=X       - Run specific check"
	@echo "  make qa-fix-preview check=X      - Preview fix (10 records)"
	@echo "  make qa-fix-dry check=X          - Dry-run fix"
	@echo "  make qa-fix-execute check=X      - Execute fix"
	@echo ""
	@echo "⚡ Enhanced QA commands:"
	@echo "  make simple-qa-run               - Run simple incremental QA (working!)"
	@echo "  make simple-qa-status            - Show incremental QA status"
	@echo "  make simple-qa-reset             - Reset change tracking"
	@echo "  make enhanced-qa-run             - Run enhanced incremental QA (optimized)"
	@echo "  make enhanced-qa-status          - Show enhanced QA status"
	@echo ""
	@echo "📋 3-Phase Pipeline commands:"
	@echo "  make discover                    - Phase 1: Discover all decision URLs"
	@echo "  make discover-resume             - Resume discovery from checkpoint"
	@echo "  make discover-test               - Test discovery (3 pages only)"
	@echo "  make full-scrape                 - Phase 2: Scrape all from manifest (local)"
	@echo "  make full-scrape-resume          - Resume scrape from checkpoint"
	@echo "  make full-scrape-test            - Test scrape (5 decisions from manifest)"
	@echo "  make full-scrape-ai-only         - Re-run AI on existing raw data (no Chrome)"
	@echo "  make push-local                  - Phase 3: Push local data to Supabase"
	@echo "  make push-local-qa               - QA check local data before pushing"
	@echo ""
	@echo "📊 Real-time Monitoring:"
	@echo "  make monitor-start               - Start real-time quality monitoring"
	@echo ""
	@echo "🚀 Deployment commands:"
	@echo "  make deploy-check                - Check current issues and prerequisites"
	@echo "  make deploy-improvements         - Deploy all algorithm improvements"
	@echo "  make deploy-auto                 - Auto-deploy without confirmations"
	@echo "  make verify-deployment           - Verify deployment success"
	@echo "  make monitor-check               - Run single monitoring check"
	@echo "  make monitor-health              - Show system health score"
	@echo "  make monitor-alerts              - Show current alerts"
	@echo ""
	@echo "📋 Quality Reports:"
	@echo "  make report-daily                - Generate daily quality report"
	@echo "  make report-weekly               - Generate weekly quality report"
	@echo "  make report-monthly              - Generate monthly quality report"
	@echo "  make report-custom format=html   - Generate report in specific format"
	@echo ""
	@echo "🏷️  Special Category Tags (AI-based):"
	@echo "  make special-tags-preview        - Preview on 10 records"
	@echo "  make special-tags-dry            - Full dry-run"
	@echo "  make special-tags-year year=2024 - Process specific year"
	@echo "  make special-tags-all            - Process all years (25K records)"
	@echo ""
	@echo "🏷️  Tag Migration commands:"
	@echo "  make migrate-preview    - Preview on 10 records"
	@echo "  make migrate-preview-n n=20  - Preview on N records"
	@echo "  make migrate-dry        - Full dry-run (no changes)"
	@echo "  make migrate-execute    - Execute migration (with confirmation)"
	@echo ""
	@echo "🗓️  Year-by-Year Migration:"
	@echo "  make migrate-all-years  - Migrate all years (2024-1993)"
	@echo "  make migrate-year year=2024  - Migrate a specific year"
	@echo ""
	@echo "🧪 QA Testing commands:"
	@echo "  make test-qa                     - Run basic QA tests (unit tests)"
	@echo "  make test-unit                   - Run unit tests"
	@echo "  make test-integration            - Run integration tests"
	@echo "  make test-performance            - Run performance tests"
	@echo "  make test-regression             - Run regression tests"
	@echo "  make test-property               - Run property-based tests"
	@echo "  make test-all-qa                 - Run all QA test suites"
	@echo "  make test-coverage               - Generate coverage report"
	@echo "  make test-report                 - Generate comprehensive test report"
	@echo ""
	@echo "🔧 Development commands:"
	@echo "  make install-dev                 - Install development dependencies"
	@echo "  make setup-dev                   - Set up development environment"
	@echo "  make format-check                - Check code formatting"
	@echo "  make security                    - Run security checks"
	@echo "  make pre-commit                  - Run pre-commit hooks"
	@echo "  make install-hooks               - Install pre-commit hooks"
	@echo "  make ci-test                     - Run CI-like test suite"
	@echo "  make health-check                - Run system health checks"
	@echo ""
	@echo "🔧 First time setup:"
	@echo "  1. Copy .env.example to .env and fill in your credentials"
	@echo "  2. Run: make setup"
	@echo "  3. Run: make test-conn"
	@echo "  4. Run: make sync"
	@echo ""

# Initial project setup
setup:
	@echo "🔧 Setting up project..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "📦 Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV_DIR); \
	fi
	@echo "📥 Installing dependencies..."
	@source $(VENV_DIR)/bin/activate && pip install -r requirements.txt
	@echo "🔧 Installing package in development mode..."
	@source $(VENV_DIR)/bin/activate && pip install -e .
	@echo "✅ Setup complete!"
	@echo ""
	@echo "📝 Next steps:"
	@echo "  1. Copy .env.example to .env and fill in your credentials"
	@echo "  2. Run: make test-conn"

# Daily sync - unlimited processing until baseline
# Uses --no-headless to bypass Cloudflare WAF (Feb 2026)
sync:
	@echo "🚀 Starting daily sync (unlimited until baseline)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --unlimited --no-approval --no-headless --verbose

# Overnight sync for large batches
overnight:
	@echo "🌙 Starting overnight sync for large batches..."
	@bash $(BIN_DIR)/overnight_sync.sh

# Large batch sync with progress tracking
large-batch:
	@echo "📦 Starting large batch sync..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/large_batch_sync.py --with-ai

# Run all tests
test:
	@echo "🧪 Running all tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_connection.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_database.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_data_insertion.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_fixes.py

# Test database connection only
test-conn:
	@echo "🔌 Testing database connection..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_connection.py

# Clean up generated files (see enhanced version in QA section)

# View documentation
docs:
	@echo "📚 Opening documentation..."
	@echo "Main documentation files:"
	@echo "  - $(DOCS_DIR)/README.md - Main project documentation"
	@echo "  - $(DOCS_DIR)/DEVELOPER_GUIDE.md - Developer guidance"
	@echo "  - $(DOCS_DIR)/INTEGRATION_GUIDE.md - Database integration"
	@echo "  - $(DOCS_DIR)/TESTING_GUIDE.md - Testing procedures"

# Code linting (if flake8 is available)
lint:
	@echo "🔍 Running code linting..."
	@if command -v flake8 >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && flake8 $(SRC_DIR) $(BIN_DIR) $(TEST_DIR) --max-line-length=120; \
	else \
		echo "⚠️  flake8 not installed. Install with: pip install flake8"; \
	fi

# Code formatting (if black is available)
format:
	@echo "🎨 Formatting code..."
	@if command -v black >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && black $(SRC_DIR) $(BIN_DIR) $(TEST_DIR) --line-length=120; \
	else \
		echo "⚠️  black not installed. Install with: pip install black"; \
	fi

# Development sync with AI processing
sync-dev:
	@echo "🔬 Starting development sync with AI..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 5 --no-headless --verbose

# Quick test with 1 decision
sync-test:
	@echo "⚡ Quick test sync (1 decision)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 1 --no-approval --no-headless --verbose

# =============================================================================
# Tag Migration Commands
# =============================================================================

# Preview migration on 10 records (default)
migrate-preview:
	@echo "🔍 Previewing tag migration on 10 records..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py preview --verbose

# Preview with custom count
migrate-preview-n:
	@echo "🔍 Previewing tag migration on $(n) records..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py preview --count $(n) --verbose

# Full dry-run (no changes)
migrate-dry:
	@echo "📋 Running full migration dry-run (no database changes)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py dry-run --verbose

# Execute migration (with confirmation)
migrate-execute:
	@echo "🚀 Executing tag migration..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py execute --verbose

# Execute migration without confirmation (careful!)
migrate-execute-yes:
	@echo "⚠️  Executing tag migration (auto-confirm)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py execute --yes --verbose

# Migrate all years from 2024 back to 1993
migrate-all-years:
	@echo "🗓️  Running migration for all years (2024-1993)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_all_years.py --verbose

# Migrate a specific year
migrate-year:
	@echo "📅 Running migration for year $(year)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/migrate_tags.py execute \
		--start-date $(year)-01-01 --end-date $(year)-12-31 --yes --verbose

# =============================================================================

# Show project status
status:
	@echo "📊 Project Status"
	@echo "=================="
	@echo "Virtual Environment: $(shell [ -d $(VENV_DIR) ] && echo "✅ Present" || echo "❌ Missing")"
	@echo "Dependencies: $(shell [ -f $(VENV_DIR)/bin/activate ] && source $(VENV_DIR)/bin/activate && python -c "import supabase, selenium, google.genai; print('✅ Installed')" 2>/dev/null || echo "❌ Missing")"
	@echo "Environment File: $(shell [ -f .env ] && echo "✅ Present" || echo "❌ Create from .env.example")"
	@echo "Database Connection: $(shell source $(VENV_DIR)/bin/activate && python $(TEST_DIR)/test_connection.py >/dev/null 2>&1 && echo "✅ Working" || echo "❌ Check .env credentials")"

# =============================================================================
# QA Commands
# =============================================================================

# Full QA scan (all checks)
qa-scan:
	@echo "🔍 Running full QA scan..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py scan --verbose

# Scan specific check
qa-scan-check:
	@echo "🔍 Running QA check: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py scan --check $(check) --verbose

# Preview fix (10 records)
qa-fix-preview:
	@echo "🔍 Previewing QA fix: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) preview --verbose

# Dry-run fix
qa-fix-dry:
	@echo "📋 Running QA fix dry-run: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) dry-run --verbose

# Execute fix
qa-fix-execute:
	@echo "🚀 Executing QA fix: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) execute --verbose

# =============================================================================
# Monitoring Commands
# =============================================================================

# Monitor tag quality (last 7 days)
monitor:
	@echo "📊 Analyzing tag quality (last 7 days)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/monitor_tags.py --days 7

# Monitor tag quality (last 30 days)
monitor-30:
	@echo "📊 Analyzing tag quality (last 30 days)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/monitor_tags.py --days 30

# =============================================================================
# Special Category Tags Commands (AI-based)
# =============================================================================

# Preview special category tagging on 10 records
special-tags-preview:
	@echo "🔍 Previewing special category tags (10 records)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/add_special_tags.py --preview --verbose

# Full dry-run (no database changes)
special-tags-dry:
	@echo "📋 Running special category tags dry-run..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/add_special_tags.py --dry-run --verbose

# Process specific year
special-tags-year:
	@echo "📅 Processing special category tags for year $(year)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/add_special_tags.py --execute --year $(year) --verbose

# Process all years (~25K records)
special-tags-all:
	@echo "🚀 Processing special category tags for all years..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/add_special_tags.py --execute --verbose

# =============================================================================
# Incremental QA Commands
# =============================================================================

# Setup change tracking infrastructure
incremental-qa-setup:
	@echo "🔧 Setting up incremental QA change tracking..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/incremental_qa.py setup --verbose

# Run incremental QA processing
incremental-qa-run:
	@echo "⚡ Running incremental QA processing..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/incremental_qa.py run --verbose

# Show current processing status
incremental-qa-status:
	@echo "📊 Checking incremental QA status..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/incremental_qa.py status --verbose

# Generate differential report
incremental-qa-report:
	@echo "📈 Generating differential report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/incremental_qa.py report --verbose

# Clean up old checkpoints (7 days)
incremental-qa-cleanup:
	@echo "🗑️  Cleaning up old incremental QA data..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/incremental_qa.py cleanup --days 7 --verbose

# =============================================================================
# QA Testing Commands (Enhanced)
# =============================================================================

# Install development dependencies
install-dev:
	@echo "📦 Installing development dependencies..."
	@source $(VENV_DIR)/bin/activate && pip install -r requirements.txt
	@source $(VENV_DIR)/bin/activate && pip install pytest pytest-cov pytest-html pytest-xdist hypothesis bandit black isort flake8 pre-commit mypy

# Set up development environment
setup-dev: install-dev
	@echo "🔧 Setting up development environment..."
	mkdir -p test-results logs data/qa_reports
	@echo "✅ Development environment ready!"

# Run basic QA tests (unit tests)
test-qa:
	@echo "🧪 Running QA unit tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/unit/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--cov-report=html:htmlcov-unit \
		--junitxml=test-results/unit.xml \
		--tb=short

# Run unit tests
test-unit:
	@echo "🧪 Running unit tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/unit/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--cov-report=html:htmlcov-unit \
		--junitxml=test-results/unit.xml \
		--tb=short

# Run integration tests
test-integration:
	@echo "🔗 Running integration tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/integration/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--cov-report=html:htmlcov-integration \
		--junitxml=test-results/integration.xml \
		--tb=short

# Run performance tests
test-performance:
	@echo "⚡ Running performance tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/performance/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--junitxml=test-results/performance.xml \
		--tb=short \
		-m performance

# Run regression tests
test-regression:
	@echo "🔄 Running regression tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/regression/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--junitxml=test-results/regression.xml \
		--tb=short \
		-m regression

# Run property-based tests
test-property:
	@echo "🎯 Running property-based tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/property/ \
		--verbose \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=term-missing \
		--junitxml=test-results/property.xml \
		--tb=short \
		-m property

# Run all QA test suites
test-all-qa:
	@echo "🚀 Running all QA test suites..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) tests/qa/test_runner.py --suite all --verbose

# Generate detailed coverage report
test-coverage:
	@echo "📊 Generating coverage report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m pytest tests/qa/unit/ tests/qa/integration/ \
		--cov=src/gov_scraper/processors/qa \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml \
		--cov-report=term \
		--cov-fail-under=80

# Generate comprehensive test report
test-report:
	@echo "📋 Generating comprehensive test report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) tests/qa/test_runner.py --suite all --include-slow
	@echo "📄 Reports generated in test-results/ directory"

# Check code formatting without making changes
format-check:
	@echo "🎨 Checking code formatting..."
	@if command -v black >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && black --check --diff src/gov_scraper/processors/qa.py tests/qa/ --line-length=120; \
	else \
		echo "⚠️  black not installed. Install with: make install-dev"; \
	fi
	@if command -v isort >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && isort --check-only --diff src/gov_scraper/processors/qa.py tests/qa/ --profile=black --line-length=120; \
	else \
		echo "⚠️  isort not installed. Install with: make install-dev"; \
	fi

# Run security checks
security:
	@echo "🔒 Running security checks..."
	@if command -v bandit >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && bandit -r src/gov_scraper/processors/qa.py -f text; \
	else \
		echo "⚠️  bandit not installed. Install with: make install-dev"; \
	fi

# Install pre-commit hooks
install-hooks:
	@echo "🪝 Installing pre-commit hooks..."
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit install; \
		pre-commit install --hook-type pre-push; \
		echo "✅ Pre-commit hooks installed"; \
	else \
		echo "⚠️  pre-commit not installed. Install with: make install-dev"; \
	fi

# Run pre-commit hooks on all files
pre-commit:
	@echo "🔍 Running pre-commit hooks..."
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files; \
	else \
		echo "⚠️  pre-commit not installed. Install with: make install-dev"; \
	fi

# Run CI-like test suite
ci-test:
	@echo "🤖 Running CI-like test suite..."
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) security
	$(MAKE) test-unit

# =============================================================================
# Enhanced QA Commands
# =============================================================================

# Run enhanced incremental QA
enhanced-qa-run:
	@echo "⚡ Running enhanced incremental QA (optimized)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.processors.incremental_qa run --verbose

# Show enhanced QA status
enhanced-qa-status:
	@echo "📊 Checking enhanced QA status..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.processors.incremental_qa status

# Clean up enhanced QA cache
enhanced-qa-cleanup:
	@echo "🗑️  Cleaning up enhanced QA cache..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.processors.incremental_qa cleanup

# =============================================================================
# Real-time Monitoring Commands
# =============================================================================

# Start continuous monitoring
monitor-start:
	@echo "📊 Starting real-time quality monitoring..."
	@echo "Press Ctrl+C to stop monitoring"
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.quality_monitor monitor --interval 15

# Run single monitoring check
monitor-check:
	@echo "🔍 Running single monitoring check..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.quality_monitor run

# Show system health score
monitor-health:
	@echo "💚 Checking system health score..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.quality_monitor health

# Show current alerts
monitor-alerts:
	@echo "🚨 Showing current alerts..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.alert_manager status

# Test alert system
monitor-test-alert:
	@echo "🧪 Testing alert system..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.alert_manager test --severity warning

# =============================================================================
# Quality Reports Commands
# =============================================================================

# Generate daily quality report
report-daily:
	@echo "📋 Generating daily quality report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/generate_quality_report.py daily --format json

# Generate weekly quality report
report-weekly:
	@echo "📋 Generating weekly quality report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/generate_quality_report.py weekly --format html

# Generate monthly quality report
report-monthly:
	@echo "📋 Generating monthly quality report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/generate_quality_report.py monthly --format html

# Generate custom format report
report-custom:
	@echo "📋 Generating custom quality report..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/generate_quality_report.py weekly --format $(format)

# Generate all reports
report-all:
	@echo "📋 Generating all quality reports..."
	$(MAKE) report-daily
	$(MAKE) report-weekly
	$(MAKE) report-monthly

# =============================================================================
# Metrics and Analytics Commands
# =============================================================================

# Export metrics data
metrics-export:
	@echo "📊 Exporting metrics data..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.metrics_collector export --format json --hours 168

# Show metrics summary
metrics-summary:
	@echo "📈 Showing metrics summary..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.metrics_collector summary --hours 24

# Aggregate metrics
metrics-aggregate:
	@echo "📊 Aggregating metrics..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.metrics_collector aggregate --period day

# Clean up old metrics
metrics-cleanup:
	@echo "🗑️  Cleaning up old metrics data..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -m src.gov_scraper.monitoring.metrics_collector cleanup
	$(MAKE) test-integration
	$(MAKE) test-regression
	@echo "✅ CI simulation completed"

# Run system health checks
health-check:
	@echo "🏥 Running health checks..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -c "
	import sys
	try:
	    from src.gov_scraper.processors.qa import ALL_CHECKS, ALL_FIXERS, run_scan
	    from src.gov_scraper.db.connector import get_supabase_client
	    print(f'✅ QA module: {len(ALL_CHECKS)} checks, {len(ALL_FIXERS)} fixers')
	    client = get_supabase_client()
	    print('✅ Database connection: OK')
	    print('✅ All systems operational')
	except Exception as e:
	    print(f'❌ Health check failed: {e}')
	    sys.exit(1)
	"

# Enhanced cleanup with QA test artifacts
clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name "*.pyd" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -f nohup.out 2>/dev/null || true
	@rm -rf htmlcov*/ .pytest_cache/ test-results/ coverage.xml 2>/dev/null || true
	@echo "✅ Cleanup complete!"

# Simple Incremental QA commands (working with existing DB)
simple-qa-run:
	@echo "⚡ Running simple incremental QA..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py run

simple-qa-status:
	@echo "📊 Checking simple incremental QA status..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py status

simple-qa-reset:
	@echo "🔄 Resetting simple incremental QA tracking..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py reset

# =============================================================================
# 📋 3-Phase Pipeline Commands (Discovery → Scraping → Push)
# =============================================================================

# Phase 1: Discovery - Find all decision URLs from gov.il catalog
discover:
	@echo "🔍 Starting catalog discovery (full scan)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --no-headless

# Resume discovery from where it left off
discover-resume:
	@echo "🔄 Resuming catalog discovery..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --resume --no-headless

# Test discovery with limited pages
discover-test:
	@echo "🧪 Testing discovery (3 pages only)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --max-pages 3 --no-headless

# Phase 2: Full Scrape - Process all URLs from manifest (local storage)
full-scrape:
	@echo "📦 Starting full scrape from manifest (local storage)..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "❌ Manifest not found! Run 'make discover' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --verbose

# Resume full scrape from checkpoint
full-scrape-resume:
	@echo "🔄 Resuming full scrape from checkpoint..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "❌ Manifest not found! Run 'make discover' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --resume --verbose

# Test full scrape with limited decisions
full-scrape-test:
	@echo "🧪 Testing full scrape (5 decisions from manifest)..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "❌ Manifest not found! Run 'make discover-test' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --max-decisions 5 --verbose

# AI-only mode: skip scraping, run AI on existing raw data
full-scrape-ai-only:
	@echo "🤖 Running AI processing on existing raw data (no Chrome)..."
	@if [ ! -f "data/scraped/latest_raw.json" ]; then \
		echo "❌ No raw data found! Run 'make full-scrape' first to scrape"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --ai-only --verbose

# Phase 3: Push Local Data - Upload scraped data to Supabase
push-local:
	@echo "📤 Pushing local scraped data to Supabase..."
	@if [ ! -f "data/scraped/latest.json" ]; then \
		echo "❌ No scraped data found! Run 'make full-scrape' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/push_local.py --file data/scraped/latest.json --push

# QA check local data before pushing
push-local-qa:
	@echo "🔍 Running QA on local scraped data..."
	@if [ ! -f "data/scraped/latest.json" ]; then \
		echo "❌ No scraped data found! Run 'make full-scrape' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/push_local.py --file data/scraped/latest.json --qa-only

# =============================================================================
# 🚀 Algorithm Improvement Deployment Commands
# =============================================================================

# Check current issues and prerequisites
deploy-check:
	@echo "🔍 Checking current issues and prerequisites..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/deploy_improvements.py --check-only

# Deploy all improvements with confirmations
deploy-improvements:
	@echo "🚀 Starting algorithm improvements deployment..."
	@echo "This will:"
	@echo "  - Backup the database"
	@echo "  - Deploy detection profiles"
	@echo "  - Enable unified AI processor"
	@echo "  - Setup monitoring system"
	@echo ""
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/deploy_improvements.py

# Auto-deploy without confirmations (use with caution!)
deploy-auto:
	@echo "🚀 Auto-deploying improvements (no confirmations)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/deploy_improvements.py --auto-confirm

# Verify deployment success
verify-deployment:
	@echo "✅ Verifying deployment..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/verify_db_integrity.py --check-all

# Run database migration (manual step)
deploy-db-migration:
	@echo "💾 Database migration instructions:"
	@echo "1. Open Supabase SQL Editor"
	@echo "2. Run: database/migrations/004_fix_duplicates_and_constraints.sql"
	@echo "3. Verify with: make verify-deployment"

# Test unified AI processor
test-unified-ai:
	@echo "🤖 Testing unified AI processor..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/test_unified_ai.py --test-count 5

# Monitor AI performance
monitor-ai-performance:
	@echo "📊 Monitoring AI performance..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/ai_performance_monitor.py --last-hour

# Quick deployment validation
deploy-validate:
	@echo "🧪 Running quick deployment validation..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -c "\
import sys; \
try: \
    from config.tag_detection_profiles import TAG_DETECTION_PROFILES; \
    print(f'✅ Tag profiles loaded: {len(TAG_DETECTION_PROFILES)} tags'); \
    from config.ministry_detection_rules import MINISTRY_DETECTION_RULES; \
    print(f'✅ Ministry rules loaded: {len(MINISTRY_DETECTION_RULES)} ministries'); \
    import os; \
    print('✅ Unified AI processor found' if os.path.exists('src/gov_scraper/processors/unified_ai.py') else '⚠️ Unified AI not found'); \
    print('✅ Quality monitor found' if os.path.exists('src/gov_scraper/monitoring/quality_monitor.py') else '⚠️ Quality monitor not found'); \
    print('✅ All components ready for deployment!'); \
except Exception as e: \
    print(f'❌ Validation failed: {e}'); \
    sys.exit(1) \
"

# Full deployment workflow
deploy-full:
	@echo "🎯 Running full deployment workflow..."
	$(MAKE) deploy-check
	@echo ""
	@read -p "Continue with deployment? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	$(MAKE) deploy-improvements
	$(MAKE) deploy-validate
	@echo ""
	@echo "✅ Deployment complete! Next steps:"
	@echo "1. Run database migration: make deploy-db-migration"
	@echo "2. Test with: make sync-test"
	@echo "3. Monitor with: make monitor-start"