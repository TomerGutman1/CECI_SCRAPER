import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("Supabase URL or Service Key not set in environment variables.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def fetch_latest_decision():
  client = get_supabase_client()
  response = (
    client.table("israeli_government_decisions")
    .select("*")
    .gt("decision_date", "2023-01-01")
    .neq("decision_number", None)
    .neq("decision_content", "המשך התוכן...")
    .order("decision_date", desc=True)
    .limit(1)
    .execute()
  )
  if response.data:
    return response.data[0]
  return None

if __name__ == "__main__":
    latest_decision = fetch_latest_decision()
    if latest_decision:
        print("Latest decision:")
        for k, v in latest_decision.items():
            print(f"{k}: {v}")
    else:
        print("No decisions found.")
