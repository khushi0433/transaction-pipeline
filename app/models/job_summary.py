# app/models/job_summary.py
import uuid
from datetime import datetime
from sqlalchemy import Text, Integer, Numeric, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class JobSummary(Base):
    __tablename__ = "job_summary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,    # enforces one-to-one: one summary per job
    )

    total_spend_inr: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    total_spend_usd: Mapped[float] = mapped_column(Numeric(15, 2), default=0)

    # JSONB stores Python dicts/lists as binary JSON in Postgres
    # Example: [{"merchant": "Amazon", "total": 45000.00, "count": 5}]
    top_merchants: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="summary_risk_level_check",
        ),
    )