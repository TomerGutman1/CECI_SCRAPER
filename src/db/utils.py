import pandas as pd
import logging

def read_decisions_csv(csv_path):
  try:
      df = pd.read_csv(csv_path, encoding="utf-8")
      return df
  except Exception as e:
      logging.error(f"Failed to read CSV: {e}")
      print(f"Failed to read CSV: {e}")
      return None

def remove_unwanted_columns(df, columns):
  for col in columns:
      if col in df.columns:
          df = df.drop(columns=[col])
  return df

def drop_incomplete_rows(df, required):
  before_drop = len(df)

  df = df.dropna(subset=required)

  after_drop = len(df)
  skipped_missing = before_drop - after_drop
  return df, skipped_missing

def filter_new_rows(df, last_date, last_num):
  skipped_old = 0
  before_filter = len(df)
  
  df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
  last_date_dt = pd.to_datetime(last_date, errors="coerce")
  df = df[df["decision_date"] >= last_date_dt]
  mask_old = (df["decision_date"] == last_date_dt) & (df["decision_number"].astype(int).astype(str) == last_num)
  df = df[~mask_old]
  df["decision_date"] = df["decision_date"].dt.strftime("%Y-%m-%d")
  
  skipped_old = before_filter - len(df)
  return df, skipped_old
