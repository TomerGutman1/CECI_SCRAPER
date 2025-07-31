import os
from supabase import create_client, Client
from dotenv import load_dotenv

def find_env_file():
    """Find .env file in various locations for portability."""
    # Try multiple locations in order of preference
    locations = [
        os.path.join(os.getcwd(), '.env'),                    # Current working directory
        os.path.join(os.path.dirname(__file__), '.env'),      # Same directory as connector.py
        os.path.join(os.path.dirname(__file__), '..', '.env'), # Parent directory (gov_scraper/.env)
        os.path.join(os.path.dirname(__file__), '..', '..', '.env'), # src/.env
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'), # Project root
        os.path.join(os.path.expanduser('~'), '.env'),        # User home directory
    ]
    
    for location in locations:
        if os.path.exists(location):
            return location
    
    return None

# Load environment variables from the first found .env file
env_file = find_env_file()
if env_file:
    load_dotenv(env_file)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("Supabase URL or Service Key not set in environment variables.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
