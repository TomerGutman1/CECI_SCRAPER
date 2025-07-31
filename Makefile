# Israeli Government Decisions Scraper - Makefile
# Easy commands for common operations

SHELL := /bin/bash
PYTHON := python3
VENV_DIR := venv
BIN_DIR := bin
SRC_DIR := src
TEST_DIR := tests
DOCS_DIR := docs

.PHONY: help install sync overnight large-batch test test-connection clean docs lint format setup

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
sync:
	@echo "🚀 Starting daily sync (unlimited until baseline)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --unlimited --no-approval --verbose

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
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 5 --verbose

# Quick test with 1 decision
sync-test:
	@echo "⚡ Quick test sync (1 decision)..."
	@source $(VENV_DIR)/bin/activate && $(PYTHON) $(BIN_DIR)/sync.py --max-decisions 1 --no-ai --no-approval --verbose

# Show project status
status:
	@echo "📊 Project Status"
	@echo "=================="
	@echo "Virtual Environment: $(shell [ -d $(VENV_DIR) ] && echo "✅ Present" || echo "❌ Missing")"
	@echo "Dependencies: $(shell [ -f $(VENV_DIR)/bin/activate ] && source $(VENV_DIR)/bin/activate && python -c "import supabase, selenium, openai; print('✅ Installed')" 2>/dev/null || echo "❌ Missing")"
	@echo "Environment File: $(shell [ -f .env ] && echo "✅ Present" || echo "❌ Create from .env.example")"
	@echo "Database Connection: $(shell source $(VENV_DIR)/bin/activate && python $(TEST_DIR)/test_connection.py >/dev/null 2>&1 && echo "✅ Working" || echo "❌ Check .env credentials")"