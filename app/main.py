# app/main.py
from fastapi import FastAPI
from app.routers import jobs
from app.database import engine
from app.models import Job, Transaction, JobSummary  # noqa: F401 - needed for Base
from app.database import Base

# Bootstrap the DB schema for this assignment.
# In production, schema changes should be managed via migrations (e.g., Alembic).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Transaction Processing Pipeline",
    description="AI-powered async transaction processing API",
    version="1.0.0",
)

# API routing: expose the job endpoints under the /jobs namespace.
app.include_router(jobs.router)



@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Transaction Pipeline API is running"}