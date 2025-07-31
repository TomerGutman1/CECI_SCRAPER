#!/bin/bash
# OVERNIGHT SYNC SCRIPT - NO TIMEOUT, ROBUST FOR LARGE BATCHES
# Perfect for catching up on 350+ decisions gap
# Run this and go to sleep peacefully!

echo "🌙 OVERNIGHT SYNC - PROCESSING LARGE DECISION GAP"
echo "=================================================="
echo "✅ No timeout - will run until ALL decisions are processed"
echo "✅ Comprehensive logging - you can check progress anytime"
echo "✅ Auto-recovery - continues even if some decisions fail"
echo "✅ Progress tracking - shows exactly what's happening"
echo ""

# Get current timestamp for logging
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="logs/overnight_sync_$(date '+%Y%m%d_%H%M%S').log"

echo "🕐 Started at: $START_TIME"
echo "📝 Detailed logs: $LOG_FILE"
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the sync with maximum logging and no limits
echo "🚀 Starting unlimited sync with full logging..."
echo "📊 Processing ALL decisions until database baseline is reached"
echo "🔄 Large batch mode: Fetching 500 URLs for complete coverage"
echo "⏱️  Initial URL extraction may take 30-60 seconds"
echo ""

# For large batches, recommend running without AI first for speed
echo "⚡ RECOMMENDATION: For 350+ decisions, consider running without AI first:"
echo "   This run: ~30-60 minutes (without AI)"
echo "   Later run: Add AI analysis to existing decisions if needed"
echo ""

# Start the actual sync
nohup python bin/sync.py \
    --unlimited \
    --no-approval \
    --no-ai \
    --verbose \
    > "$LOG_FILE" 2>&1 &

# Get the process ID
SYNC_PID=$!

echo "🎯 Sync started in background with PID: $SYNC_PID"
echo "📋 To monitor progress:"
echo "   tail -f $LOG_FILE"
echo ""
echo "📊 To check if it's still running:"
echo "   ps aux | grep $SYNC_PID"
echo ""
echo "⏹️  To stop if needed (not recommended):"
echo "   kill $SYNC_PID"
echo ""

# Create a status file
STATUS_FILE="sync_status_$(date '+%Y%m%d_%H%M%S').txt"
echo "Sync started at: $START_TIME" > "$STATUS_FILE"
echo "Process ID: $SYNC_PID" >> "$STATUS_FILE"
echo "Log file: $LOG_FILE" >> "$STATUS_FILE"

echo "📄 Status file created: $STATUS_FILE"
echo ""
echo "🌙 OVERNIGHT SYNC INITIATED!"
echo "✅ You can now go to sleep peacefully"
echo "📱 Check $LOG_FILE tomorrow morning for results"
echo ""
echo "Expected completion: 30-90 minutes for 350 decisions"
echo "=================================================="