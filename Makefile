# Israeli Government Decisions Scraper - Makefile

SHELL := /bin/bash
PYTHON := python3
VENV_DIR := venv
BIN_DIR := bin
SRC_DIR := src
TEST_DIR := tests

.PHONY: help setup sync sync-chrome sync-dev sync-test test test-conn clean status qa-scan qa-scan-check qa-fix-preview qa-fix-dry qa-fix-execute simple-qa-run simple-qa-status simple-qa-reset discover discover-resume discover-test full-scrape full-scrape-resume full-scrape-test full-scrape-ai-only push-local push-local-qa health-check

# Default target - show help
help:
	@echo "Israeli Government Decisions Scraper"
	@echo "======================================"
	@echo ""
	@echo "Setup:"
	@echo "  make setup              - Initial project setup"
	@echo "  make test-conn          - Test database connection"
	@echo "  make status             - Show project status"
	@echo ""
	@echo "Daily Operations:"
	@echo "  make sync               - Daily sync via API (no Chrome, default)"
	@echo "  make sync-chrome        - Daily sync via Selenium (legacy fallback)"
	@echo "  make sync-dev           - Dev mode (5 decisions, API)"
	@echo "  make sync-test          - Quick test (1 decision, API)"
	@echo ""
	@echo "QA Commands:"
	@echo "  make qa-scan                     - Full QA scan"
	@echo "  make qa-scan-check check=X       - Run specific check"
	@echo "  make qa-fix-preview check=X      - Preview fix (10 records)"
	@echo "  make qa-fix-dry check=X          - Dry-run fix"
	@echo "  make qa-fix-execute check=X      - Execute fix"
	@echo "  make simple-qa-run               - Fast incremental QA"
	@echo "  make simple-qa-status            - Incremental QA status"
	@echo "  make simple-qa-reset             - Reset change tracking"
	@echo ""
	@echo "3-Phase Pipeline:"
	@echo "  make discover                    - Phase 1: Discover all decision URLs"
	@echo "  make discover-resume             - Resume discovery from checkpoint"
	@echo "  make discover-test               - Test discovery (3 pages only)"
	@echo "  make full-scrape                 - Phase 2: Scrape all from manifest"
	@echo "  make full-scrape-resume          - Resume scrape from checkpoint"
	@echo "  make full-scrape-test            - Test scrape (5 decisions)"
	@echo "  make full-scrape-ai-only         - Re-run AI on existing raw data"
	@echo "  make push-local                  - Phase 3: Push local data to Supabase"
	@echo "  make push-local-qa               - QA check local data before pushing"
	@echo ""
	@echo "Other:"
	@echo "  make test               - Run all tests"
	@echo "  make clean              - Clean up generated files"
	@echo "  make health-check       - Run system health checks"

# =============================================================================
# Setup & Configuration
# =============================================================================

setup:
	@echo "Setting up project..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV_DIR); \
	fi
	@echo "Installing dependencies..."
	@source $(VENV_DIR)/bin/activate && pip install -r requirements.txt
	@echo "Installing package in development mode..."
	@source $(VENV_DIR)/bin/activate && pip install -e .
	@echo "Setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Copy .env.example to .env and fill in your credentials"
	@echo "  2. Run: make test-conn"

status:
	@echo "Project Status"
	@echo "=================="
	@echo "Virtual Environment: $(shell [ -d $(VENV_DIR) ] && echo "Present" || echo "Missing")"
	@echo "Dependencies: $(shell [ -f $(VENV_DIR)/bin/activate ] && source $(VENV_DIR)/bin/activate && python -c "import supabase, selenium, google.genai; print('Installed')" 2>/dev/null || echo "Missing")"
	@echo "Environment File: $(shell [ -f .env ] && echo "Present" || echo "Create from .env.example")"
	@echo "Database Connection: $(shell source $(VENV_DIR)/bin/activate && python $(TEST_DIR)/test_connection.py >/dev/null 2>&1 && echo "Working" || echo "Check .env credentials")"

# =============================================================================
# Daily Operations
# =============================================================================

sync:
	@echo "Starting daily sync via API (no Chrome)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --unlimited --no-approval --use-api --verbose

sync-chrome:
	@echo "Starting daily sync via Selenium (legacy fallback)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --unlimited --no-approval --no-headless --verbose

sync-dev:
	@echo "Starting development sync (5 decisions, API)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 5 --use-api --verbose

sync-test:
	@echo "Quick test sync (1 decision, API)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 1 --no-approval --use-api --verbose

# =============================================================================
# Testing
# =============================================================================

test:
	@echo "Running all tests..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_connection.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_database.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_data_insertion.py
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_fixes.py

test-conn:
	@echo "Testing database connection..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(TEST_DIR)/test_connection.py

# =============================================================================
# QA Commands
# =============================================================================

qa-scan:
	@echo "Running full QA scan..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py scan --verbose

qa-scan-check:
	@echo "Running QA check: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py scan --check $(check) --verbose

qa-fix-preview:
	@echo "Previewing QA fix: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) preview --verbose

qa-fix-dry:
	@echo "Running QA fix dry-run: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) dry-run --verbose

qa-fix-execute:
	@echo "Executing QA fix: $(check)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/qa.py fix $(check) execute --verbose

simple-qa-run:
	@echo "Running simple incremental QA..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py run

simple-qa-status:
	@echo "Checking simple incremental QA status..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py status

simple-qa-reset:
	@echo "Resetting simple incremental QA tracking..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) bin/simple_incremental_qa.py reset

# =============================================================================
# 3-Phase Pipeline (Discovery -> Scraping -> Push)
# =============================================================================

discover:
	@echo "Starting catalog discovery (full scan)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --no-headless

discover-resume:
	@echo "Resuming catalog discovery..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --resume --no-headless

discover-test:
	@echo "Testing discovery (3 pages only)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/discover_all.py --max-pages 3 --no-headless

full-scrape:
	@echo "Starting full scrape from manifest (local storage)..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "Manifest not found! Run 'make discover' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --verbose

full-scrape-resume:
	@echo "Resuming full scrape from checkpoint..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "Manifest not found! Run 'make discover' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --resume --verbose

full-scrape-test:
	@echo "Testing full scrape (5 decisions from manifest)..."
	@if [ ! -f "data/catalog_manifest.json" ]; then \
		echo "Manifest not found! Run 'make discover-test' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --no-headless --max-decisions 5 --verbose

full-scrape-ai-only:
	@echo "Running AI processing on existing raw data (no Chrome)..."
	@if [ ! -f "data/scraped/latest_raw.json" ]; then \
		echo "No raw data found! Run 'make full-scrape' first to scrape"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/full_local_scraper.py --manifest data/catalog_manifest.json --output data/scraped/latest.json --ai-only --verbose

push-local:
	@echo "Pushing local scraped data to Supabase..."
	@if [ ! -f "data/scraped/latest.json" ]; then \
		echo "No scraped data found! Run 'make full-scrape' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/push_local.py --file data/scraped/latest.json --push

push-local-qa:
	@echo "Running QA on local scraped data..."
	@if [ ! -f "data/scraped/latest.json" ]; then \
		echo "No scraped data found! Run 'make full-scrape' first"; \
		exit 1; \
	fi
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/push_local.py --file data/scraped/latest.json --qa-only

# =============================================================================
# Utilities
# =============================================================================

clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov*/ .pytest_cache/ test-results/ coverage.xml 2>/dev/null || true
	@echo "Cleanup complete!"

health-check:
	@echo "Running health checks..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) -c " \
	import sys; \
	try: \
	    from src.gov_scraper.processors.qa import ALL_CHECKS, ALL_FIXERS, run_scan; \
	    from src.gov_scraper.db.connector import get_supabase_client; \
	    print(f'QA module: {len(ALL_CHECKS)} checks, {len(ALL_FIXERS)} fixers'); \
	    client = get_supabase_client(); \
	    result = client.table('israeli_government_decisions').select('id', count='exact').limit(1).execute(); \
	    print(f'Database: {result.count} records'); \
	    print('Health check PASSED'); \
	except Exception as e: \
	    print(f'Health check FAILED: {e}'); \
	    sys.exit(1) \
	"

lint:
	@echo "Running code linting..."
	@if command -v flake8 >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && flake8 $(SRC_DIR) $(BIN_DIR) --max-line-length=120; \
	else \
		echo "flake8 not installed. Install with: pip install flake8"; \
	fi

format:
	@echo "Formatting code..."
	@if command -v black >/dev/null 2>&1; then \
		source $(VENV_DIR)/bin/activate && black $(SRC_DIR) $(BIN_DIR) --line-length=120; \
	else \
		echo "black not installed. Install with: pip install black"; \
	fi
