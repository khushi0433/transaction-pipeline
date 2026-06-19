# app/models/job.py
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Job(Base):
    """
    Maps to the 'jobs' table in PostgreSQL.
    Each instance of this class = one row in the table.
    """

    # __tablename__ tells SQLAlchemy which table this class maps to
    __tablename__ = "jobs"

    # Mapped[type] is the modern SQLAlchemy 2.0 way to declare columns.
    # It gives you full type hints — your IDE knows the type of every field.

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,   # Python generates the UUID (not the DB)
    )

    filename: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )

    row_count_raw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_clean: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # timezone=True stores the timezone alongside the timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Table-level constraints (same as in our SQL migration)
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="jobs_status_check",
        ),
    )

    def __repr__(self) -> str:
        """Makes print(job) readable during debugging."""
        return f"<Job id={self.id} filename={self.filename} status={self.status}>"