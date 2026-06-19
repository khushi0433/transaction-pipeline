from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any
import uuid


# Response models used by the jobs endpoints.
# These are built from SQLAlchemy objects (not raw dicts) in the router layer.


class JobCreateResponse(BaseModel):
    """Immediate response after creating an upload job."""

    job_id: uuid.UUID
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Current state of a job as seen by the client."""

    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Included once the worker finishes successfully.
    summary: Optional[dict] = None

    # Enables `model_validate(sqlalchemy_obj)`-style construction from ORM attributes.
    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    """A transaction row returned in job results (cleaned + enriched)."""

    id: uuid.UUID
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None

    # Present when the worker attempts LLM classification.
    llm_category: Optional[str] = None
    llm_failed: bool

    model_config = {"from_attributes": True}


class JobSummaryOut(BaseModel):
    """Narrative summary generated from aggregated job stats."""

    total_spend_inr: float
    total_spend_usd: float
    top_merchants: Optional[Any] = None
    anomaly_count: int
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    model_config = {"from_attributes": True}


class JobResultsResponse(BaseModel):
    """Full results payload for a completed job."""

    job_id: uuid.UUID
    status: str
    transactions: List[TransactionOut]
    anomalies: List[TransactionOut]
    summary: Optional[JobSummaryOut] = None


class JobListItem(BaseModel):
    """Lightweight row for job listings."""

    job_id: uuid.UUID
    filename: str
    status: str
    row_count_raw: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}

