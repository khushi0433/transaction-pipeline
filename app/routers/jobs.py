import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.job import Job
from app.models.transaction import Transaction
from app.models.job_summary import JobSummary
from app.schemas.job import (
    JobCreateResponse,
    JobStatusResponse,
    JobResultsResponse,
    JobListItem,
    TransactionOut,
    JobSummaryOut,
)
from app.worker.tasks import process_csv_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload", response_model=JobCreateResponse, status_code=202)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept CSV upload, create job record, enqueue processing task.
    Returns job_id immediately — does NOT wait for processing.
    Status 202 = "Accepted" (not yet done, but will be processed).
    """

    # Input contract: only CSV uploads are accepted.
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are accepted",
        )

    # Persistence + async processing: create the job record first, then hand off the
    # actual work to the Celery worker (202 Accepted semantics).
    job = Job(filename=file.filename)
    db.add(job)
    db.commit()
    db.refresh(job)  # ensure we have the generated UUID

    # Store the raw upload on disk; the worker will load it from this location.
    file_path = os.path.join(UPLOAD_DIR, f"{job.id}.csv")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Enqueue worker execution (returns immediately).
    process_csv_job.delay(str(job.id), file_path)


    return JobCreateResponse(
        job_id=job.id,
        status="pending",
        message="Job accepted. Poll /jobs/{job_id}/status for updates.",
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return current job status. If completed, include summary stats."""

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response_data = {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
    }

    # When completed, include the derived summary to avoid forcing clients to call
    # /results just for high-level stats.
    if job.status == "completed":
        summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()
        if summary:
            response_data["summary"] = {
                "total_spend_inr": float(summary.total_spend_inr or 0),
                "total_spend_usd": float(summary.total_spend_usd or 0),
                "anomaly_count": summary.anomaly_count,
                "risk_level": summary.risk_level,
            }


    return response_data


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return full results: all transactions, anomalies, and LLM summary."""

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job.status}"
        )

    # Materialize results for this job.
    transactions = (
        db.query(Transaction)
        .filter(Transaction.job_id == job_id)
        .all()
    )

    # Split out anomalies for convenience while still returning the full transaction list.
    anomalies = [t for t in transactions if t.is_anomaly]

    summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()

    # Serialization: dates are stored as date objects in the ORM, but the API returns strings.

    def txn_to_out(t):
        return TransactionOut(
            id=t.id,
            txn_id=t.txn_id,
            date=str(t.date) if t.date else None,
            merchant=t.merchant,
            amount=float(t.amount) if t.amount else None,
            currency=t.currency,
            status=t.status,
            category=t.category,
            account_id=t.account_id,
            is_anomaly=t.is_anomaly,
            anomaly_reason=t.anomaly_reason,
            llm_category=t.llm_category,
            llm_failed=t.llm_failed,
        )

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        transactions=[txn_to_out(t) for t in transactions],
        anomalies=[txn_to_out(t) for t in anomalies],
        summary=JobSummaryOut.model_validate(summary) if summary else None,
    )


@router.get("", response_model=list[JobListItem])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """List all jobs. Optionally filter by ?status=pending|processing|completed|failed"""

    query = db.query(Job).order_by(Job.created_at.desc())

    if status:
        query = query.filter(Job.status == status)

    jobs = query.all()

    return [
        JobListItem(
            job_id=j.id,
            filename=j.filename,
            status=j.status,
            row_count_raw=j.row_count_raw,
            created_at=j.created_at,
        )
        for j in jobs
    ]