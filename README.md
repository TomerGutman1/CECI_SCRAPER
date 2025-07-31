# Israeli Government Decisions Scraper 🏛️

A professional, production-ready web scraper that extracts and processes Israeli government decisions from the official government website with comprehensive database integration.

## ✨ Features

- **🎯 Smart Scraping**: Selenium-based extraction handles JavaScript-heavy government websites
- **🗄️ Database Integration**: Seamless Supabase integration with incremental processing
- **🤖 AI Analysis**: GPT-3.5-turbo powered content analysis and policy tagging
- **📊 Unlimited Sync**: Process all decisions until database baseline with no timeout
- **🔄 URL Recovery**: Intelligent URL correction for government website inconsistencies
- **🛡️ Robust Error Handling**: Continues processing despite individual failures
- **📈 Production Ready**: Clean architecture, comprehensive logging, and professional structure

## 🚀 Quick Start

### 1. Setup
```bash
# Clone and setup
git clone <repository-url>
cd GOV2DB
make setup
```

### 2. Configure
```bash
# Copy environment template and fill in your credentials
cp .env.example .env
# Edit .env with your Supabase and OpenAI API keys
```

### 3. Test Connection
```bash
make test-conn
```

### 4. Run Daily Sync
```bash
make sync
```

## 📁 Project Structure

```
GOV2DB/
├── 📁 bin/                          # Executable Scripts
│   ├── sync.py                      # Main production sync
│   ├── overnight_sync.sh            # Overnight processing
│   └── large_batch_sync.py          # Large batch processor
│
├── 📁 src/gov_scraper/              # Core Package
│   ├── scrapers/                    # Web scraping modules
│   ├── processors/                  # Data processing & AI
│   ├── db/                          # Database integration
│   ├── utils/                       # Common utilities
│   └── config.py                    # Configuration
│
├── 📁 tests/                        # Test Suite
├── 📁 docs/                         # Documentation
├── 📁 data/                         # Output Data
├── 📁 logs/                         # Log Files
└── 📁 venv/                         # Virtual Environment
```

## 🎯 Common Commands

| Command | Description |
|---------|-------------|
| `make sync` | Daily sync (unlimited until baseline) |
| `make overnight` | Large batch processing |
| `make test` | Run all tests |
| `make test-conn` | Test database connection |
| `make clean` | Clean up generated files |
| `make help` | Show all available commands |

## 🔧 Environment Variables

Create `.env` file with:

```bash
# Required for AI processing
OPENAI_API_KEY=your_openai_api_key_here

# Required for database integration  
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_key_here
```

## 📊 Data Schema

The system extracts 19 fields per decision including:

- **Direct Extraction**: Decision date, number, committee, title, content
- **AI Generated**: Summary, operativity, policy tags, location tags
- **System Fields**: Government number, PM, decision key, URL

## 🔄 Processing Workflow

1. **📊 Database Query**: Fetch latest decision as baseline
2. **🔍 URL Extraction**: Get decision URLs from government catalog
3. **📄 Content Scraping**: Extract Hebrew text with error recovery
4. **🤖 AI Analysis**: Generate summaries and policy classifications
5. **💾 Database Sync**: Insert new decisions with duplicate prevention

## 📚 Documentation

- **[docs/README.md](docs/README.md)** - Detailed project documentation
- **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** - Developer guidance
- **[docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)** - Database setup
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** - Testing procedures

## 🛠️ Development

### Install for Development
```bash
make setup
# or manually:
pip install -e .
```

### Run Tests
```bash
make test
```

### Code Quality
```bash
make lint    # Code linting
make format  # Code formatting
```

## 🎯 Usage Examples

### Daily Operations
```bash
# Standard daily sync
make sync

# Test with limited decisions
make sync-test

# Development sync with AI
make sync-dev
```

### Large Batch Processing
```bash
# Overnight processing for 350+ decisions
make overnight

# Advanced large batch with progress tracking
make large-batch
```

## 🏗️ Architecture

- **Clean Package Structure**: Professional Python package with proper imports
- **Portable Code**: No hardcoded paths, flexible .env loading
- **Modular Design**: Separated concerns (scrapers, processors, db, utils)
- **Error Recovery**: Smart URL correction and processing continuation
- **Database Integration**: Incremental processing with baseline detection

## 📈 Performance

- **Processing Speed**: ~5-10 decisions per minute
- **Scalability**: Handles 350+ decision batches overnight
- **Resource Efficient**: Selenium with smart waiting and cleanup
- **Robust**: Continues processing despite individual URL failures

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test`
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

---

**🚀 Production Ready** - Deployed and tested with real Israeli government data

🇮🇱 **Built for Israeli Government Decision Analysis & Transparency**