from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


# The engine is the actual connection to PostgreSQL.
# pool_pre_ping=True: before using a connection from the pool,
# ping the DB to make sure it's still alive. Prevents "connection
# dropped" errors after the DB restarts.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,        # keep 5 connections open and ready
    max_overflow=10,    # allow up to 10 extra connections under load
)

# SessionLocal is a factory that creates database sessions.
# Each request gets its own session — they don't share state.
# autocommit=False: we control when to commit (explicit is better)
# autoflush=False: don't write to DB until we explicitly call flush/commit
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """
    All our SQLAlchemy models will inherit from this class.
    It's the shared foundation that lets SQLAlchemy know which
    classes represent database tables.
    """
    pass


def get_db():
    """
    Dependency function for FastAPI routes.
    Creates a session, yields it to the route handler,
    then ALWAYS closes it — even if an exception occurs.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db        # hand the session to the route
    finally:
        db.close()      # always runs, even on error