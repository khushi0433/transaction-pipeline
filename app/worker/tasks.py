# app/worker/tasks.py
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models.job import Job
from app.models.transaction import Transaction
from app.models.job_summary import JobSummary
from app.services.cleaner import clean_dataframe
from app.services.anomaly import detect_anomalies
from app.services import llm


@celery_app.task(bind=True, max_retries=0)
def process_csv_job(self, job_id: str, file_path: str):
    """End-to-end transaction processing for a single uploaded CSV.

    This runs fully inside the Celery worker so the API can stay responsive:
    - update job state early (pollable status)
    - clean and enrich transactions
    - call the LLM only for records that still lack a category
    - persist both transaction rows and the narrative summary
    """

    db: Session = SessionLocal()

    try:
        # Load the job row first so we can mark progress (and safely no-op if deleted).
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        job.status = "processing"
        db.commit()
        print(f"[Job {job_id}] Starting processing...")

        # Keep ingestion tolerant: treat fields as strings, then let the cleaner normalize them.
        df = pd.read_csv(file_path, dtype=str)
        row_count_raw = len(df)
        job.row_count_raw = row_count_raw
        db.commit()
        print(f"[Job {job_id}] Loaded {row_count_raw} raw rows")

        print(f"[Job {job_id}] Cleaning data...")
        df = clean_dataframe(df)
        row_count_clean = len(df)
        job.row_count_clean = row_count_clean
        db.commit()
        print(f"[Job {job_id}] Clean rows: {row_count_clean}")

        # Apply deterministic anomaly rules before any external (LLM) calls.
        print(f"[Job {job_id}] Detecting anomalies...")
        df = detect_anomalies(df)

        # Only delegate uncategorised rows to the LLM to reduce cost and latency.
        print(f"[Job {job_id}] Running LLM classification...")
        uncategorised_mask = df["category"] == "Uncategorised"
        uncategorised_df = df[uncategorised_mask]

        llm_results = {}
        llm_failed_ids = set()

        if not uncategorised_df.empty:
            batch = uncategorised_df[["txn_id", "merchant", "amount", "currency", "notes"]].to_dict(
                orient="records"
            )
            llm_results = llm.classify_transactions_batch(batch)

            if not llm_results:
                # If the model call fails entirely, keep a traceable flag per transaction.
                llm_failed_ids = set(uncategorised_df["txn_id"].dropna().tolist())
                print(f"[Job {job_id}] LLM classification failed for all batches")

        # Merge LLM outcomes back into the working DataFrame.
        for idx, row in df.iterrows():
            txn_id = row.get("txn_id")
            if txn_id in llm_results:
                df.at[idx, "llm_category"] = llm_results[txn_id]
                df.at[idx, "category"] = llm_results[txn_id]
            elif txn_id in llm_failed_ids:
                df.at[idx, "llm_failed"] = True

        # Ensure schema-stable columns for downstream persistence.
        if "llm_failed" not in df.columns:
            df["llm_failed"] = False
        if "llm_category" not in df.columns:
            df["llm_category"] = None

        print(f"[Job {job_id}] Saving transactions to database...")
        transactions_to_insert = []

        for _, row in df.iterrows():
            txn = Transaction(
                job_id=job_id,
                txn_id=row.get("txn_id") if pd.notna(row.get("txn_id")) else None,
                date=row.get("date") if pd.notna(row.get("date")) else None,
                merchant=row.get("merchant"),
                amount=float(row["amount"]) if pd.notna(row.get("amount")) else None,
                currency=row.get("currency"),
                status=row.get("status"),
                category=row.get("category"),
                account_id=row.get("account_id"),
                notes=row.get("notes") if pd.notna(row.get("notes")) else None,
                is_anomaly=bool(row.get("is_anomaly", False)),
                anomaly_reason=row.get("anomaly_reason") if pd.notna(row.get("anomaly_reason")) else None,
                llm_category=row.get("llm_category") if pd.notna(row.get("llm_category")) else None,
                llm_failed=bool(row.get("llm_failed", False)),
            )
            transactions_to_insert.append(txn)

        # Bulk insert is critical here—this path can involve many rows.
        db.bulk_save_objects(transactions_to_insert)
        db.commit()

        # Build a small, structured stats object to guide the narrative generation.
        print(f"[Job {job_id}] Generating narrative summary...")
        inr_df = df[df["currency"] == "INR"]
        usd_df = df[df["currency"] == "USD"]

        total_inr = float(inr_df["amount"].sum()) if not inr_df.empty else 0
        total_usd = float(usd_df["amount"].sum()) if not usd_df.empty else 0

        top_merchants = (
            df.groupby("merchant")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
            .reset_index()
            .rename(columns={"amount": "total"})
            .to_dict(orient="records")
        )

        category_breakdown = df.groupby("category")["amount"].sum().to_dict()
        anomaly_count = int(df["is_anomaly"].sum())

        stats = {
            "total_inr": total_inr,
            "total_usd": total_usd,
            "total_count": len(df),
            "anomaly_count": anomaly_count,
            "top_merchants": top_merchants,
            "category_breakdown": {k: float(v) for k, v in category_breakdown.items()},
        }

        narrative_result = llm.generate_narrative_summary(stats)

        summary = JobSummary(
            job_id=job_id,
            total_spend_inr=total_inr,
            total_spend_usd=total_usd,
            top_merchants=top_merchants,
            anomaly_count=anomaly_count,
            narrative=narrative_result.get("narrative") if narrative_result else None,
            risk_level=narrative_result.get("risk_level") if narrative_result else None,
        )
        db.add(summary)

        # Mark job as complete only after all persistence steps succeed.
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[Job {job_id}] ✓ Completed successfully")

    except Exception as e:
        # If anything fails, capture the error on the job row for easier debugging.
        print(f"[Job {job_id}] ✗ Failed: {e}")
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()

