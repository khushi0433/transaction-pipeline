import pandas as pd
from app.services.cleaner import DOMESTIC_MERCHANTS


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds two columns to the DataFrame:
    - is_anomaly: True/False
    - anomaly_reason: string explaining why (or None)

    Rules:
    1. Amount > 3x the account's median → statistical outlier
    2. Currency is USD but merchant is domestic-only → currency mismatch
    """

    # Initialize both columns with default values
    df["is_anomaly"] = False
    df["anomaly_reason"] = None

    # Outlier heuristic (per account): a transaction far above the typical amount
    # is treated as suspicious. We use the median to reduce the influence of extremes.


    account_medians = df.groupby("account_id")["amount"].transform("median")

    # Boolean mask: True for rows where amount > 3 * account median
    outlier_mask = df["amount"] > (3 * account_medians)

    df.loc[outlier_mask, "is_anomaly"] = True
    df.loc[outlier_mask, "anomaly_reason"] = (
        "Amount exceeds 3x account median (statistical outlier)"
    )

    # Currency sanity check: if a known domestic merchant appears with USD,
    # it's unlikely to be legitimate and is flagged as anomalous.


    # Normalize merchant names for comparison (lowercase, stripped)
    merchant_lower = df["merchant"].str.lower().str.strip()
    is_domestic = merchant_lower.isin(DOMESTIC_MERCHANTS)
    is_usd = df["currency"] == "USD"

    mismatch_mask = is_domestic & is_usd

    # If multiple checks trigger for the same row, we aggregate their explanations.

    already_flagged = df["is_anomaly"] & mismatch_mask
    newly_flagged = ~df["is_anomaly"] & mismatch_mask

    df.loc[already_flagged, "anomaly_reason"] += (
        "; USD currency used with domestic-only merchant"
    )
    df.loc[newly_flagged, "is_anomaly"] = True
    df.loc[newly_flagged, "anomaly_reason"] = (
        "USD currency used with domestic-only merchant"
    )

    anomaly_count = df["is_anomaly"].sum()
    print(f"  Detected {anomaly_count} anomalies")

    return df