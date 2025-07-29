import os
import logging
import pandas as pd
from db_connector import get_supabase_client
from utils import read_decisions_csv, remove_unwanted_columns, drop_incomplete_rows, filter_new_rows

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

def _insert_rows_to_db(rows):
    client = get_supabase_client()
    try:
        response = client.table("israeli_government_decisions").insert(rows).execute()
        inserted = len(rows)
        logging.info(f"Inserted {inserted} new rows.")
        print(f"Inserted {inserted} new rows.")
        return inserted
    except Exception as e:
        logging.error(f"Failed to insert rows: {e}")
        print(f"Failed to insert rows: {e}")
        return 0

def save_new_rows_from_table_to_db():
    """
    Reads decisions.csv, filters for new/valid rows, removes unwanted columns, skips incomplete rows, and inserts new rows to Supabase.
    Prints a summary and logs actions.
    """
    logging.basicConfig(filename="logs/db.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "decisions.csv"))
    df = read_decisions_csv(csv_path)
    if df is None:
        return

    latest_decision = fetch_latest_decision()
    if not latest_decision:
        logging.info("No latest decision found. Terminating script.")
        print("No latest decision found. Terminating script.")
        return

    last_date = latest_decision.get("decision_date")
    last_num = str(latest_decision.get("decision_number"))

    df = remove_unwanted_columns(df, ["id", "created_at", "updated_at", "decision_date_db"])
    df, skipped_missing = drop_incomplete_rows(df, ["decision_date", "decision_number", "decision_url"])
    df, skipped_old = filter_new_rows(df, last_date, last_num)

    # Convert any NaN values to None for DB compatibility
    df = df.where(pd.notna(df), None)
    new_rows = df.to_dict(orient="records")

    # Remove "embedding" attribute if it exists and is null in any row
    for row in new_rows:
        if "embedding" in row and pd.isna(row["embedding"]):
            del row["embedding"]

    # Convert decision_number to integer and then back to string
    for row in new_rows:
        if "decision_number" in row:
            row["decision_number"] = str(int(row["decision_number"])) if pd.notna(row["decision_number"]) else None

    skipped_total = skipped_missing + skipped_old

    if not new_rows:
        logging.info("No new rows to insert.")
        print(f"No new rows to insert. Skipped {skipped_total} rows.")
        return

    inserted = _insert_rows_to_db(new_rows)
    print(f"Inserted {inserted} new rows. Skipped {skipped_total} rows.")
    logging.info(f"Inserted {inserted} new rows. Skipped {skipped_total} rows.")

if __name__ == "__main__":
    save_new_rows_from_table_to_db()