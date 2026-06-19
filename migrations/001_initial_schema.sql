-- migrations/001_initial_schema.sql
-- Enable the UUID extension so we can generate UUIDs in PostgreSQL
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────
-- TABLE: jobs
-- Represents one uploaded CSV file and its processing state
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    -- gen_random_uuid() generates a UUID automatically on insert
    -- We never need to supply this value manually
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Original filename of the uploaded CSV
    filename          TEXT NOT NULL,
    
    -- NOT NULL ensures we always know the state
    status            TEXT NOT NULL DEFAULT 'pending',

    -- How many rows were in the raw CSV (including duplicates, blanks)
    row_count_raw     INTEGER,

    -- How many rows remain after cleaning (duplicates removed, etc.)
    row_count_clean   INTEGER,

    -- Automatically set to current time when the row is inserted
    -- TIMESTAMPTZ = timestamp WITH timezone (always store timezone!)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Set when job finishes (success or failure)
    completed_at      TIMESTAMPTZ,

    -- If processing fails, store the error message here for debugging
    error_message     TEXT,

    -- Constraint: status must be one of these four values only
    -- This is a database-level guard, not just application-level
    CONSTRAINT jobs_status_check CHECK (
        status IN ('pending', 'processing', 'completed', 'failed')
    )
);

-- Index on status: we'll frequently query "give me all pending jobs"
-- Without this index, Postgres scans ALL rows every time
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- Index on created_at: for sorting jobs by newest first
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);


-- ─────────────────────────────────────────────
-- TABLE: transactions
-- Each cleaned row from the CSV, linked to its parent job
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key: links each transaction to its job
    -- ON DELETE CASCADE: if the job is deleted, its transactions are too
    -- This prevents orphaned records with no parent
    job_id            UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

    -- Original transaction ID from the CSV (may be null if blank in CSV)
    txn_id            TEXT,

    -- Cleaned date, stored as DATE type (YYYY-MM-DD)
    date              DATE,

    merchant          TEXT,

    -- NUMERIC(12, 2) = up to 12 digits total, 2 decimal places
    -- Exact precision - never use FLOAT for money
    amount            NUMERIC(12, 2),

    -- Always stored uppercase after cleaning: INR or USD
    currency          TEXT,

    -- Always stored uppercase after cleaning: SUCCESS, FAILED, PENDING
    status            TEXT,

    -- Spending category: Food, Shopping, Travel, etc.
    -- May be 'Uncategorised' if LLM also failed
    category          TEXT,

    account_id        TEXT,

    -- Free text notes from original CSV
    notes             TEXT,

    -- ── Anomaly detection fields ──────────────
    -- TRUE if this transaction was flagged as suspicious
    is_anomaly        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Human-readable explanation of WHY it was flagged
    -- e.g. "Amount exceeds 3x account median" or "USD with domestic merchant"
    anomaly_reason    TEXT,

    -- ── LLM classification fields ─────────────
    -- Category assigned by the LLM (may differ from original category)
    llm_category      TEXT,

    -- Raw response from the LLM for this transaction (for debugging)
    llm_raw_response  TEXT,

    -- TRUE if all LLM retries failed for this transaction's batch
    llm_failed        BOOLEAN NOT NULL DEFAULT FALSE,

    -- When this record was created
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Most important index: we'll constantly query "all transactions for job X"
CREATE INDEX IF NOT EXISTS idx_transactions_job_id
    ON transactions(job_id);

-- For filtering anomalies: "show me all flagged transactions for job X"
CREATE INDEX IF NOT EXISTS idx_transactions_anomaly
    ON transactions(job_id, is_anomaly);

-- For filtering by account
CREATE INDEX IF NOT EXISTS idx_transactions_account_id
    ON transactions(account_id);


-- ─────────────────────────────────────────────
-- TABLE: job_summary
-- The LLM-generated report for a completed job
-- One-to-one relationship with jobs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_summary (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- One summary per job. UNIQUE enforces the one-to-one relationship.
    -- If you try to insert a second summary for the same job, Postgres rejects it.
    job_id            UUID NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,

    -- Total money spent per currency
    total_spend_inr   NUMERIC(15, 2) DEFAULT 0,
    total_spend_usd   NUMERIC(15, 2) DEFAULT 0,

    -- JSONB = binary JSON. Queryable, indexable, efficient.
    -- Stores: [{"merchant": "Amazon", "total": 45000.00, "count": 5}, ...]
    top_merchants     JSONB,

    -- How many transactions were flagged as anomalies
    anomaly_count     INTEGER DEFAULT 0,

    -- The 2-3 sentence LLM-written spending narrative
    narrative         TEXT,

    -- Overall risk assessment from LLM
    risk_level        TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraint: risk_level must be one of three values
    CONSTRAINT summary_risk_level_check CHECK (
        risk_level IN ('low', 'medium', 'high')
    )
);