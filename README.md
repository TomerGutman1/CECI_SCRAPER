# Israeli Government Decisions Scraper 🏛️

A comprehensive web scraper that extracts and processes Israeli government decisions from the official government website (gov.il), automatically analyzing and categorizing decisions with AI-powered content processing.

## ✅ Current Status

**✅ FULLY IMPLEMENTED AND OPERATIONAL**: The scraper pipeline is complete and successfully extracts real data from the Israeli government website with high-quality output.

**🎯 Key Achievements**:
- Complete Selenium-based web scraping with JavaScript rendering
- AI-powered content analysis with GPT-3.5-turbo
- Standardized data format with 37 authorized Hebrew policy tags
- Clean date formatting (DD.MM.YYYY → YYYY-MM-DD)
- Precise committee extraction (2-3 words after "ועדות שרים:")
- UTF-8-BOM CSV export for proper Hebrew display

## 📁 Project Structure

```
gov2db/
├── 📄 README.md                    # This file - project documentation
├── 📋 requirements.txt             # Python dependencies
├── 🔧 .env                        # Environment variables (API keys)
├── 📊 data/                       # Output directory for scraped data
│   └── scraped_decisions_*.csv    # Generated CSV files with decision data
├── 🐍 src/                        # Source code directory
│   ├── 🚀 main.py                 # Main orchestrator - runs the complete pipeline
│   ├── 📃 catalog_scraper.py      # Discovers government decision URLs
│   ├── 🕷️ decision_scraper_selenium.py  # Extracts individual decision content
│   ├── 🧠 ai_processor.py         # AI-powered content analysis and tagging
│   ├── 💾 data_manager.py         # CSV data handling and storage
│   ├── 🌐 selenium_utils.py       # Selenium WebDriver utilities
│   └── ⚙️ config.py               # Configuration and constants
└── 📋 .env.example               # Template for environment variables
```

## 🧪 Testing Results

**✅ Successfully tested with real government data**:
- Scraped live decisions from gov.il
- Clean Hebrew text extraction and processing
- Perfect date format conversion (2025-07-24)
- Precise committee names (e.g., "ועדת השרים לענייני חקיקה")
- AI summaries and policy tagging working correctly

## 🎯 What This Project Does

This scraper performs a complete end-to-end pipeline:

1. **🔍 Discovery**: Finds all available government decision URLs from the catalog
2. **📝 Extraction**: Scrapes individual decision pages for detailed content
3. **🤖 AI Analysis**: Processes content with OpenAI GPT for summaries and categorization
4. **🏷️ Tagging**: Applies standardized policy area tags and government body classifications
5. **💾 Storage**: Saves structured data to CSV files for analysis

## 📋 File Descriptions

### 🚀 `src/main.py` - The Orchestrator
The main entry point that coordinates the entire scraping pipeline:
- Initializes the selenium webdriver
- Manages the workflow from URL discovery to data export
- Handles error recovery and logging
- Controls the overall execution flow

### 📃 `src/catalog_scraper.py` - URL Discovery Engine
Discovers government decision URLs from the official catalog:
- Navigates through paginated decision listings
- Extracts decision URLs and basic metadata
- Handles JavaScript-rendered content
- Returns a list of decision URLs to process

### 🕷️ `src/decision_scraper_selenium.py` - Content Extractor
Extracts detailed content from individual decision pages:
- **Date Processing**: Extracts DD.MM.YYYY dates and converts to YYYY-MM-DD format
- **Committee Extraction**: Gets 2-3 words after "ועדות שרים:" before next section
- **Title & Content**: Extracts decision titles and full Hebrew content
- **Metadata**: Pulls decision numbers, government info, and URLs
- Handles JavaScript-heavy pages with dynamic content loading

### 🧠 `src/ai_processor.py` - AI Content Analyzer
AI-powered content processing using OpenAI GPT-3.5-turbo:
- **Summarization**: Creates concise Hebrew summaries of decisions
- **Operativity Analysis**: Determines if decisions are operational vs. declarative
- **Policy Tagging**: Classifies decisions using 37 authorized Hebrew policy areas:
  - ביטחון לאומי וצבא (National Security & Military)
  - כלכלה מאקרו ותקציב (Macroeconomics & Budget)
  - חינוך והשכלה גבוהה (Education & Higher Education)
  - בריאות ורפואה (Health & Medicine)
  - And 33 more standardized categories...
- **Government Body Tagging**: Identifies relevant government ministries and bodies
- **Location Tagging**: Extracts geographical references

### 💾 `src/data_manager.py` - Data Handler
Manages CSV data operations:
- Creates structured CSV files with UTF-8-BOM encoding for Hebrew support
- Handles data validation and deduplication
- Manages incremental data updates
- Generates timestamped output files

### 🌐 `src/selenium_utils.py` - Web Automation
Selenium WebDriver wrapper for robust web scraping:
- Manages Chrome browser automation with Hebrew language support
- Handles JavaScript rendering and dynamic content
- Implements wait strategies for content loading
- Provides error handling and retry mechanisms

### ⚙️ `src/config.py` - Configuration Hub
Central configuration management:
- Hebrew field labels and mappings
- Government metadata (current government number: 37, PM: בנימין נתניהו)
- Environment variable loading (.env file handling)
- OpenAI API configuration

## 📊 Output Data Format

The scraper generates CSV files with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `id` | Sequential identifier | 1, 2, 3... |
| `decision_date` | Formatted date (YYYY-MM-DD) | 2025-07-24 |
| `decision_number` | Government decision number | 3286 |
| `committee` | Committee name (2-3 words) | ועדת השרים לענייני חקיקה |
| `decision_title` | Full Hebrew title | תקנות שעת חירום... |
| `decision_content` | Complete Hebrew content | מזכירות הממשלה... |
| `decision_url` | Source URL | https://www.gov.il/he/pages/dec3286-2025 |
| `summary` | AI-generated Hebrew summary | ההחלטה הממשלתית מאפשרת... |
| `operativity` | Operational classification | אופרטיבית / הצהרתית |
| `tags_policy_area` | Policy area tags | סייבר ואבטחת מידע; שונות |
| `tags_government_body` | Government body tags | ממשלה, מזכירות הממשלה |
| `tags_location` | Location tags | רשום ריק (if none) |
| `all_tags` | Combined tags | All tags concatenated |
| `government_number` | Current government number | 37 |
| `prime_minister` | Current Prime Minister | בנימין נתניהו |
| `decision_key` | Unique identifier | 37_3286 |

## 🏷️ Policy Area Tags (37 Authorized Categories)

The system uses a strict classification with these Hebrew policy areas:

- **ביטחון לאומי וצבא** - National Security & Military
- **ביטחון פנים וחירום אזרחי** - Internal Security & Civil Emergency
- **דיפלומטיה ויחסים בינלאומיים** - Diplomacy & International Relations
- **הגירה וקליטת עלייה** - Immigration & Immigrant Absorption
- **תעסוקה ושוק העבודה** - Employment & Labor Market
- **כלכלה מאקרו ותקציב** - Macroeconomics & Budget
- **מס ומכס** - Tax & Customs
- **תחבורה ותשתיות** - Transportation & Infrastructure
- **אנרגיה ומשאבי טבע** - Energy & Natural Resources
- **איכות הסביבה ופיתוח בר קיימא** - Environment & Sustainable Development
- **חקלאות ופיתוח כפרי** - Agriculture & Rural Development
- **תיירות** - Tourism
- **מדע וטכנולוגיה** - Science & Technology
- **סייבר ואבטחת מידע** - Cyber & Information Security
- **חדשנות ויזמות** - Innovation & Entrepreneurship
- **חינוך והשכלה גבוהה** - Education & Higher Education
- **בריאות ורפואה** - Health & Medicine
- **רווחה וביטחון סוציאלי** - Welfare & Social Security
- **דיור ופיתוח עירוני** - Housing & Urban Development
- **תרבות ואמנות** - Culture & Arts
- **ספורט** - Sports
- **דת ושירותי דת** - Religion & Religious Services
- **עלייה וקליטה** - Immigration & Absorption
- **קהילות יהודיות בתפוצות** - Jewish Diaspora Communities
- **מיעוטים וחברה ערבית** - Minorities & Arab Society
- **נשים ושוויון מגדרי** - Women & Gender Equality
- **מוגבלויות ונגישות** - Disabilities & Accessibility
- **נוער וצעירים** - Youth & Young Adults
- **קשישים** - Elderly
- **משפט וחקיקה** - Law & Legislation
- **מינהל ושירות המדינה** - Administration & Civil Service
- **שלטון מקומי** - Local Government
- **ממשל דיגיטלי** - Digital Government
- **שקיפות ואתיקה** - Transparency & Ethics
- **מילואים ותמיכה בלוחמים** - Reserve Duty & Support for Combat Veterans
- **שונות** - Miscellaneous

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8+
- Chrome browser
- OpenAI API key

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Install ChromeDriver
The scraper uses Selenium with Chrome. ChromeDriver is automatically managed by the selenium-manager.

## 📊 Usage

### Run Complete Pipeline
```bash
cd src
python main.py
```

This will:
1. Discover all available government decision URLs
2. Scrape each decision page for content
3. Process content with AI for analysis
4. Generate a timestamped CSV file in the `data/` directory

### Run Individual Components

**Discover URLs only:**
```bash
python catalog_scraper.py
```

**Test decision scraping:**
```bash
python decision_scraper_selenium.py
```

**Test AI processing:**
```bash
python ai_processor.py
```

## 🔧 Technical Architecture

### Data Flow
```
📋 Catalog Scraper → 🔗 Decision URLs → 🕷️ Content Scraper → 🧠 AI Processor → 💾 CSV Export
```

### AI Processing Pipeline
1. **Content Analysis**: GPT-3.5-turbo analyzes Hebrew decision content
2. **Classification**: Strict mapping to authorized policy tags
3. **Fuzzy Matching**: Handles Hebrew text variations and synonyms
4. **Validation**: Ensures output meets quality standards

### Data Quality Features
- **Date Standardization**: DD.MM.YYYY → YYYY-MM-DD conversion
- **Committee Extraction**: Precise 2-3 word extraction after "ועדות שרים:"
- **Tag Deduplication**: Removes duplicate policy tags
- **Hebrew Text Cleaning**: Removes artifacts and normalizes text
- **UTF-8-BOM Encoding**: Proper Hebrew character support in CSV

## 🐛 Troubleshooting

### Common Issues

**API Key Error:**
```
Ensure your .env file contains: OPENAI_API_KEY=your_key_here
```

**ChromeDriver Issues:**
```
The project uses selenium-manager for automatic ChromeDriver management.
If issues persist, install Chrome browser manually.
```

**Hebrew Encoding Problems:**
```
CSV files use UTF-8-BOM encoding. Open with Excel or import correctly.
```

**Empty Results:**
```
Check government website availability and network connection.
Some decisions may be temporarily unavailable.
```

## 📈 Performance & Scaling

- **Processing Speed**: ~5-10 decisions per minute (limited by AI processing)
- **Resource Usage**: Moderate CPU and memory usage
- **API Limits**: Respects OpenAI rate limits with retry logic
- **Error Handling**: Robust error recovery and logging

## 🤝 Contributing

To contribute to this project:
1. Understand the Hebrew language requirements
2. Familiarize yourself with Israeli government structure
3. Test changes with real government decision data
4. Ensure data quality standards are maintained

## 📝 License

This project is designed for research and analysis of public government decisions. Please respect the government website's terms of use and rate limiting.

---

**Created for analyzing Israeli Government Decision transparency and accessibility** 🇮🇱