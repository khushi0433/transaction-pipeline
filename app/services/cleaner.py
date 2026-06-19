import pandas as pd
import re
from datetime import datetime


# CSVs can contain multiple date representations; we normalize them into ISO (YYYY-MM-DD).
DATE_FORMATS = [
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%Y-%m-%d",
]


# Indian-only merchants that should never have USD transactions
DOMESTIC_MERCHANTS = {
    "swiggy", "ola", "irctc", "zomato",
    "jio recharge", "bookmyshow",
}


def parse_date(date_str: str) -> str | None:
    """
    Convert a raw date string into ISO (YYYY-MM-DD) using the supported formats.
    Returns None when the input doesn't match any known format.
    """

    if not date_str or pd.isna(date_str):
        return None

    date_str = str(date_str).strip()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue  # try next format

    return None  # none of the formats worked


def clean_amount(amount_val) -> float | None:
    """
    Parse the amount field into a float.

    This function focuses on presentation cleanup (e.g., '$' symbols) while leaving
    numeric meaning intact. If parsing fails or the value is missing, it returns None.
    """

    if pd.isna(amount_val):
        return None

    # Convert to string, strip whitespace and $ signs
    cleaned = str(amount_val).strip().replace("$", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Master cleaning function. Takes raw DataFrame, returns clean one.
    Applies all cleaning rules in sequence.
    """

    # Data quality passes: dedupe, normalize field formats, and ensure DB-friendly nulls.
    original_count = len(df)
    df = df.drop_duplicates()
    duplicates_removed = original_count - len(df)
    print(f"  Removed {duplicates_removed} duplicate rows")

    df["date"] = df["date"].apply(parse_date)
    df["amount"] = df["amount"].apply(clean_amount)

    df["currency"] = df["currency"].str.strip().str.upper()
    df["status"] = df["status"].str.strip().str.upper()

    df["category"] = df["category"].replace("", pd.NA)
    df["category"] = df["category"].fillna("Uncategorised")

    text_columns = ["merchant", "account_id", "notes", "txn_id"]
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].str.strip()

    # Keep txn_id as NULL when missing so downstream JSON/DB writes stay consistent.
    df["txn_id"] = df["txn_id"].replace("", pd.NA)


    return df