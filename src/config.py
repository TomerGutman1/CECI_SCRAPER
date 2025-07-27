"""Configuration constants for the Israeli Government Decisions Scraper."""

import os
from dotenv import load_dotenv

# Load environment variables from the project root
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(current_dir)
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# URLs
BASE_CATALOG_URL = 'https://www.gov.il/he/collectors/policies'
CATALOG_PARAMS = {
    'Type': '30280ed5-306f-4f0b-a11d-cacf05d36648',
    'skip': 0,
    'limit': 5  # Start with 5 decisions
}
BASE_DECISION_URL = 'https://www.gov.il'

# HTTP Settings
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds

# Fixed values for decisions
GOVERNMENT_NUMBER = 37
PRIME_MINISTER = "בנימין נתניהו"

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = 'gpt-3.5-turbo'

# Hebrew field labels for parsing
HEBREW_LABELS = {
    'date': 'תאריך פרסום:',
    'number': 'מספר החלטה:',
    'committee': 'ועדות שרים:'
}

# Output settings
OUTPUT_DIR = 'data'
OUTPUT_FILE = 'decisions_data.csv'
LOG_DIR = 'logs'
LOG_FILE = 'scraper.log'

# CSV columns (excluding embedding, created_at, updated_at)
CSV_COLUMNS = [
    'id', 'decision_date', 'decision_number', 'committee', 'decision_title', 
    'decision_content', 'decision_url', 'summary', 'operativity', 
    'tags_policy_area', 'tags_government_body', 'tags_location', 'all_tags',
    'government_number', 'prime_minister', 'decision_key'
]