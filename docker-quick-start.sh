#!/bin/bash
# GOV2DB Docker Quick Start Script
# Run this for a quick sanity check before integrating

set -e

echo "=========================================="
echo "GOV2DB Docker Quick Start"
echo "=========================================="
echo ""

# Step 1: Check prerequisites
echo "Step 1: Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found! Please install Docker first."
    exit 1
fi
echo "✅ Docker found: $(docker --version)"

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found! Please install Docker Compose first."
    exit 1
fi
echo "✅ Docker Compose found: $(docker-compose --version)"
echo ""

# Step 2: Check .env file
echo "Step 2: Checking .env file..."
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  IMPORTANT: Edit .env and add your API keys:"
    echo "   - OPENAI_API_KEY"
    echo "   - SUPABASE_URL"
    echo "   - SUPABASE_SERVICE_ROLE_KEY"
    echo ""
    read -p "Press Enter after you've edited .env..."
fi
echo "✅ .env file exists"

# Check if API keys are set
if ! grep -q "sk-proj" .env 2>/dev/null; then
    echo "⚠️  WARNING: OPENAI_API_KEY may not be set correctly in .env"
fi
if ! grep -q "supabase.co" .env 2>/dev/null; then
    echo "⚠️  WARNING: SUPABASE_URL may not be set correctly in .env"
fi
echo ""

# Step 3: Create directories
echo "Step 3: Creating directories..."
mkdir -p logs data
chmod 755 logs data
echo "✅ Directories created: logs/, data/"
echo ""

# Step 4: Build image
echo "Step 4: Building Docker image..."
echo "This may take 5-10 minutes on first build..."
docker build -t gov2db-scraper:latest .
echo "✅ Image built successfully"
echo ""

# Step 5: Test run (once mode)
echo "Step 5: Running test sync (once mode)..."
echo "This will run a single sync to test everything works..."
read -p "Continue with test sync? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker run --rm \
        --env-file .env \
        -v $(pwd)/logs:/app/logs \
        -v $(pwd)/data:/app/data \
        gov2db-scraper:latest \
        once

    echo ""
    echo "✅ Test sync completed!"
    echo "Check logs/: $(ls -lh logs/ 2>/dev/null | wc -l) files"
else
    echo "Skipped test sync"
fi
echo ""

# Step 6: Summary
echo "=========================================="
echo "✅ Quick Start Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "Option A: Run standalone (for development)"
echo "  docker-compose up -d"
echo "  docker logs -f gov2db-scraper"
echo ""
echo "Option B: Integrate with main docker-compose"
echo "  1. Read INTEGRATION-GUIDE.md"
echo "  2. Find your network name: docker network ls"
echo "  3. Copy from docker-compose.integration.yml"
echo "  4. Add to your main docker-compose.yml"
echo "  5. docker-compose up -d gov2db-scraper"
echo ""
echo "Useful commands:"
echo "  Health check: docker inspect --format='{{.State.Health.Status}}' gov2db-scraper"
echo "  View logs: docker logs -f gov2db-scraper"
echo "  Manual sync: docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --verbose"
echo "  Debug shell: docker exec -it gov2db-scraper bash"
echo ""
echo "Documentation:"
echo "  📖 INTEGRATION-GUIDE.md - Quick integration steps"
echo "  📚 README-DOCKER.md - Full documentation"
echo ""
