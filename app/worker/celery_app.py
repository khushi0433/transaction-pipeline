from celery import Celery
from app.config import settings

# Create the Celery application
# First argument: name of the current module (for Celery's logging)
# broker: where tasks are sent TO (Redis)
# backend: where results are stored (also Redis)
celery_app = Celery(
    "transaction_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],  # where to find task functions
)

# Configuration
celery_app.conf.update(
    # Tasks expire from result backend after 1 hour
    result_expires=3600,

    # Use JSON for serialization (not Python pickle — safer)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # If a task has been running for 10 minutes, kill it
    # Prevents zombie tasks from blocking the queue
    task_soft_time_limit=600,
    task_time_limit=660,
)