# Israeli Government Decisions Scraper 🏛️

A professional, production-ready system that automatically extracts and processes Israeli government decisions from the official government website (gov.il) with comprehensive database integration and AI-powered analysis.

## 🎯 What This System Does

This system monitors the Israeli government's official decisions website and:
1. **Finds new decisions** that haven't been processed yet
2. **Extracts the Hebrew text** from each decision page
3. **Analyzes the content** using AI to generate summaries and policy tags
4. **Stores everything** in a Supabase database for analysis and research

**Perfect for**: Researchers, journalists, policy analysts, and anyone tracking Israeli government activities.

## ✨ Key Features

- **🎯 Smart Web Scraping**: Uses Selenium to handle complex JavaScript-heavy government websites
- **🗄️ Database Integration**: Seamless Supabase integration with automatic duplicate prevention
- **🤖 AI Content Analysis**: GPT-3.5-turbo generates summaries, policy areas, and governmental body tags
- **📊 Incremental Processing**: Only processes new decisions, never duplicates work
- **🔄 Error Recovery**: Intelligent URL correction handles government website inconsistencies
- **🛡️ Robust Operation**: Continues processing even if individual decisions fail
- **📈 Production Ready**: Professional architecture with comprehensive logging

## 🚀 Quick Start (For Everyone)

### Step 1: Get the Code
```bash
# Download the project
git clone <repository-url>
cd GOV2DB
```

### Step 2: Set Up the System
```bash
# This installs all the required software
make setup
```

### Step 3: Add Your API Keys
```bash
# Copy the template file
cp .env.example .env

# Edit .env file with your credentials:
# - Get Supabase keys from your Supabase project dashboard
# - Get OpenAI API key from platform.openai.com
```

### Step 4: Test Everything Works
```bash
# Test database connection
make test-conn

# Test the system with 1 decision
make sync-test
```

### Step 5: Run Your First Sync
```bash
# Process all new decisions (this is the main command you'll use)
make sync
```

## 📋 Main Commands (What Each Does)

| Command | What It Does | Which File Runs |
|---------|-------------|-----------------|
| `make sync` | **Main daily operation** - Processes all new decisions until database is up-to-date | `bin/sync.py` |
| `make sync-test` | **Quick test** - Processes just 1 decision to test the system | `bin/sync.py` (with `--max-decisions 1`) |
| `make overnight` | **Large batch processing** - For processing 350+ decisions (runs overnight) | `bin/overnight_sync.sh` → `bin/large_batch_sync.py` |
| `make test-conn` | **Check database** - Tests if your database credentials work | `tests/test_connection.py` |
| `make test` | **Run all tests** - Comprehensive system testing | All files in `tests/` folder |
| `make setup` | **Install everything** - First-time setup of the system | Uses `requirements.txt` and `setup.py` |
| `make status` | **System health** - Shows if everything is properly installed | Checks all system components |
| `make clean` | **Cleanup** - Removes temporary files and cache | Built-in cleanup operations |

## 🏗️ How It Works (Technical Overview)

The system follows this workflow:

1. **📊 Check Database**: Finds the most recent decision already in your database
2. **🔍 Scan Government Website**: Gets list of all available decisions from gov.il
3. **📄 Process New Decisions**: For each new decision:
   - Downloads the Hebrew text from the decision page
   - Uses AI to generate summary and policy tags
   - Saves to database (avoiding duplicates)
4. **📈 Continue Until Current**: Stops when it reaches decisions already in database

## 📁 Project Structure (For Developers)

```
GOV2DB/
├── 📁 bin/                          # Main executable scripts
│   ├── sync.py                      # 🎯 Primary sync script (what "make sync" runs)
│   ├── large_batch_sync.py          # 📦 Large batch processor (350+ decisions)
│   └── overnight_sync.sh            # 🌙 Shell script for overnight operations
│
├── 📁 src/gov_scraper/              # Core Python package
│   ├── scrapers/                    # 🕷️ Web scraping (Selenium-based)
│   │   ├── catalog.py               # Gets decision URLs from government catalog
│   │   └── decision.py              # Extracts content from individual decisions
│   ├── processors/                  # 🧠 Data processing and AI
│   │   ├── ai.py                    # OpenAI GPT integration
│   │   ├── incremental.py           # Smart baseline processing
│   │   └── approval.py              # User confirmation workflows
│   ├── db/                          # 🗄️ Database operations
│   │   ├── dal.py                   # Data access layer (Supabase)
│   │   └── utils.py                 # Database utilities
│   └── config.py                    # ⚙️ Configuration and environment
│
├── 📁 tests/                        # 🧪 Test suite
├── 📁 docs/                         # 📚 Documentation
├── 📁 data/                         # 📄 Output files (CSV exports)
├── 📁 logs/                         # 📝 Log files
└── 📁 venv/                         # 🐍 Python virtual environment
```

## 🎯 Daily Usage (For Regular Users)

**Most common workflow:**
```bash
# Check if system is healthy
make status

# Run daily sync (processes all new decisions)
make sync

# Check logs if needed
tail -f logs/scraper.log
```

**For testing or development:**
```bash
# Test with just 1 decision
make sync-test

# Test database connection
make test-conn

# Run full test suite
make test
```

## 🔧 Setting Up Your API Keys

You need two services to run this system:

### 1. Supabase (Database)
- Go to [supabase.com](https://supabase.com) and create a free account
- Create a new project
- Go to Settings → API → Project URL and Service Role Key
- Copy these values to your `.env` file

### 2. OpenAI (AI Processing)
- Go to [platform.openai.com](https://platform.openai.com)
- Sign up and add a payment method (usage is typically $1-5/month)
- Go to API Keys section and create a new key
- Copy this value to your `.env` file

### Your `.env` file should look like:
```bash
# Copy from your Supabase project settings
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ0eXAiOiJKV1Q...your-long-key-here

# Copy from your OpenAI account
OPENAI_API_KEY=sk-proj-...your-openai-key-here

# Optional: Change AI model (default is gpt-3.5-turbo)
OPENAI_MODEL=gpt-3.5-turbo
```

## 📊 What Data Gets Extracted

For each government decision, the system extracts:

### 🔍 Direct from Government Website:
- **Decision Date** (תאריך פרסום) - When it was published
- **Decision Number** (מספר החלטה) - Official decision ID
- **Committee** (ועדות שרים) - Which government committee made it
- **Title** - Decision headline
- **Full Content** - Complete Hebrew text
- **URL** - Direct link to government page

### 🤖 AI-Generated Analysis:
- **Summary** - Concise description of what the decision does
- **Operativity** - Whether it's operational or declarative
- **Policy Area Tags** - Which government areas it affects (economy, security, etc.)
- **Government Body Tags** - Which ministries or agencies are involved
- **Location Tags** - Geographic areas affected
- **All Tags** - Combined tags for easy searching

### 🏛️ System Fields:
- **Government Number** - Current government (37 for current Netanyahu government)
- **Prime Minister** - Who was PM when decision was made
- **Decision Key** - Unique identifier combining government + decision number

## 🚨 Troubleshooting

### Common Issues and Solutions:

**"Database connection failed"**
```bash
# Check your .env file exists and has correct credentials
make status
# Fix: Copy .env.example to .env and add your real API keys
```

**"No decisions found" or "URLs not working"**
```bash
# The government website sometimes changes - this is normal
# The system has built-in URL recovery, just wait and try again
make sync
```

**"AI processing failed"**
```bash
# Check OpenAI API key and account has credits
# Fix: Add credits to your OpenAI account or use --no-ai flag
make sync-test --no-ai
```

**"Virtual environment issues"**
```bash
# Clean and reinstall
make clean
rm -rf venv/
make setup
```

## 📚 More Documentation

- **[docs/README.md](docs/README.md)** - Detailed technical documentation
- **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** - For developers working on the code
- **[docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)** - Database setup details
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** - Testing procedures

## 🛠️ For Developers

```bash
# Install for development
make setup

# Run all tests
make test

# Code quality (if you have flake8/black installed)
make lint
make format
```

## 📈 Performance & Scale

- **Speed**: Processes 5-10 government decisions per minute
- **Scale**: Can handle 350+ decisions in overnight batch processing
- **Reliability**: Continues working even if individual decisions fail
- **Efficiency**: Only processes new decisions, never duplicates work

## 🎯 Real-World Usage

This system is production-ready and processes real Israeli government decisions. Typical usage patterns:

- **Daily sync**: Run `make sync` once per day to stay current
- **Research projects**: Use overnight batch processing for historical analysis
- **Development**: Use `make sync-test` for safe testing with just 1 decision

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes
4. Test: `make test`
5. Submit a pull request

## 📄 License

MIT License - Free to use for research, journalism, and transparency projects.

---

**🚀 Production Ready** | **🇮🇱 Israeli Government Transparency** | **🔍 Built for Research & Analysis**