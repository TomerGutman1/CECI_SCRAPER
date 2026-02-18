#!/bin/bash

# QA Dashboard Startup Script
# Usage: ./start_dashboard.sh [--dev] [--port PORT] [--config CONFIG_FILE]

set -e

# Default values
PORT=5000
DEBUG=false
CONFIG_FILE="dashboard_config.json"
VENV_PATH="venv"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEBUG=true
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--dev] [--port PORT] [--config CONFIG_FILE] [--venv VENV_PATH]"
            echo ""
            echo "Options:"
            echo "  --dev              Enable development mode with debug logging"
            echo "  --port PORT        Port to run the dashboard on (default: 5000)"
            echo "  --config FILE      Configuration file path (default: dashboard_config.json)"
            echo "  --venv PATH        Virtual environment path (default: venv)"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting GOV2DB QA Dashboard${NC}"
echo "=================================="

# Check if we're in the project root
if [[ ! -f "bin/qa_dashboard.py" ]]; then
    echo -e "${RED}❌ Error: Please run this script from the GOV2DB project root directory${NC}"
    echo "Expected to find: bin/qa_dashboard.py"
    exit 1
fi

# Check if virtual environment exists
if [[ ! -d "$VENV_PATH" ]]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found at: $VENV_PATH${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}📦 Activating virtual environment...${NC}"
source "$VENV_PATH/bin/activate"

# Install/upgrade dependencies
echo -e "${BLUE}📦 Installing dashboard dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements_dashboard.txt

# Check if main project dependencies are installed
if ! python -c "import supabase" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Main project dependencies not found. Installing...${NC}"
    pip install -r requirements.txt
fi

# Check environment variables
echo -e "${BLUE}🔧 Checking environment configuration...${NC}"

if [[ ! -f ".env" ]]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    echo "Please create a .env file with the following variables:"
    echo "  SUPABASE_URL=your_supabase_url"
    echo "  SUPABASE_SERVICE_ROLE_KEY=your_service_key"
    echo "  GEMINI_API_KEY=your_gemini_key (optional for dashboard-only mode)"
    exit 1
fi

# Source environment variables
source .env

if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_SERVICE_ROLE_KEY" ]]; then
    echo -e "${RED}❌ Error: Required environment variables not set${NC}"
    echo "Please ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in .env"
    exit 1
fi

echo -e "${GREEN}✅ Environment configuration OK${NC}"

# Check Redis connection (optional)
echo -e "${BLUE}🔗 Checking Redis connection...${NC}"
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Redis is running${NC}"
    else
        echo -e "${YELLOW}⚠️  Redis not running. Dashboard will use in-memory cache.${NC}"
        echo "To enable Redis caching:"
        echo "  - Install Redis: brew install redis (macOS) or apt install redis (Ubuntu)"
        echo "  - Start Redis: redis-server"
    fi
else
    echo -e "${YELLOW}⚠️  Redis not installed. Dashboard will use in-memory cache.${NC}"
fi

# Create logs directory
mkdir -p logs

# Check configuration file
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${YELLOW}⚠️  Configuration file not found: $CONFIG_FILE${NC}"
    echo "Using default configuration..."
    CONFIG_FILE=""
fi

# Pre-flight check: Test database connection
echo -e "${BLUE}🔍 Testing database connection...${NC}"
if python -c "
import sys
import os
sys.path.insert(0, '.')
from src.gov_scraper.db.connector import get_supabase_client
try:
    client = get_supabase_client()
    # Test query
    result = client.table('israeli_government_decisions').select('decision_key').limit(1).execute()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    sys.exit(1)
"; then
    echo -e "${GREEN}✅ Database connection verified${NC}"
else
    echo -e "${RED}❌ Database connection failed${NC}"
    exit 1
fi

# Build command
PYTHON_CMD="python bin/qa_dashboard.py"

if [[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]]; then
    PYTHON_CMD="$PYTHON_CMD --config-file $CONFIG_FILE"
fi

PYTHON_CMD="$PYTHON_CMD --port $PORT"

if [[ "$DEBUG" == "true" ]]; then
    PYTHON_CMD="$PYTHON_CMD --debug"
fi

# Show startup info
echo ""
echo -e "${GREEN}🎯 Dashboard Configuration:${NC}"
echo "  Port: $PORT"
echo "  Debug Mode: $DEBUG"
echo "  Config File: ${CONFIG_FILE:-'default'}"
echo "  Virtual Environment: $VENV_PATH"
echo ""
echo -e "${BLUE}🌐 Dashboard will be available at:${NC}"
echo "  http://localhost:$PORT"
echo "  http://127.0.0.1:$PORT"
echo ""
echo -e "${YELLOW}📊 Dashboard Features:${NC}"
echo "  • Real-time QA metrics and health scores"
echo "  • Interactive issue distribution heatmaps"
echo "  • Historical trend analysis"
echo "  • Live alerting system"
echo "  • Automated report generation"
echo "  • REST API endpoints"
echo "  • WebSocket real-time updates"
echo ""

# Trap SIGINT to cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down dashboard...${NC}"
    exit 0
}
trap cleanup SIGINT

# Start the dashboard
echo -e "${GREEN}🚀 Starting dashboard server...${NC}"
echo "Press Ctrl+C to stop"
echo ""

# Run the dashboard
exec $PYTHON_CMD