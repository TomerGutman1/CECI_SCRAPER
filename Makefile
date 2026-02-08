# Israeli Government Decisions Scraper - Makefile
# Easy commands for common operations

SHELL := /bin/bash
PYTHON := python3
VENV_DIR := venv
BIN_DIR := bin
SRC_DIR := src
TEST_DIR := tests
DOCS_DIR := docs

.PHONY: help install sync overnight large-batch test test-connection clean docs lint format setup migrate-preview migrate-preview-n migrate-dry migrate-execute migrate-execute-yes migrate-all-years migrate-year monitor monitor-30 qa-scan qa-scan-check qa-fix-preview qa-fix-dry qa-fix-execute special-tags-preview special-tags-dry special-tags-year special-tags-all

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
	@echo "🏷️  Special Category Tags (AI-based):"
	@echo "  make special-tags-preview        - Preview on 10 records"
	@echo "  make special-tags-dry            - Full dry-run"
	@echo "  make special-tags-year year=2024 - Process specific year"
	@echo "  make special-tags-all            - Process all years (25K records)"
	@echo ""
	@echo "🏷️  Tag Migration commands:
	@echo "  make migrate-preview    - Preview on 10 records"
	@echo "  make migrate-preview-n n=20  - Preview on N records"
	@echo "  make migrate-dry        - Full dry-run (no changes)"
	@echo "  make migrate-execute    - Execute migration (with confirmation)"
	@echo ""
	@echo "🗓️  Year-by-Year Migration:"
	@echo "  make migrate-all-years  - Migrate all years (2024-1993)"
	@echo "  make migrate-year year=2024  - Migrate a specific year"
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

# Clean up generated files
clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name "*.pyd" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -f nohup.out 2>/dev/null || true
	@echo "✅ Cleanup complete!"

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