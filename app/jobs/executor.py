"""
Job Execution Abstraction Layer.
Provides pluggable worker dispatch (FastAPI BackgroundTasks, ThreadPool, Celery-ready).
Ensures safe transactional isolation with dedicated SessionLocal per execution.
"""

import sys
import traceback
from typing import Callable, Any
from fastapi import BackgroundTasks
from app.db.session import SessionLocal
from app.jobs.manager import JobManager
from app.core.logging import logger


class JobExecutor:
    """Dispatches asynchronous background tasks with database session isolation."""

    session_factory: Any = None

    @classmethod
    def get_session(cls):
        if cls.session_factory is not None:
            return cls.session_factory()
        from app.db.session import SessionLocal
        return SessionLocal()

    @classmethod
    def run_worker_task(cls, fn: Callable[..., Any], job_id: str, *args, **kwargs) -> None:
        """
        Executes a job worker within a dedicated database session.
        Catches any uncaught exceptions to ensure job status transitions to FAILED.
        """
        db = cls.get_session()
        try:
            logger.info(f"Worker execution initiated for job_id={job_id}")
            fn(db=db, job_id=job_id, *args, **kwargs)
        except Exception as exc:
            err_msg = str(exc)
            tb = traceback.format_exc()
            logger.error(f"Job {job_id} encountered unhandled exception: {err_msg}\n{tb}")
            try:
                JobManager.mark_failed(
                    db=db,
                    job_id=job_id,
                    error_message=err_msg,
                    error_details={"traceback": tb, "exception_class": exc.__class__.__name__}
                )
            except Exception as db_err:
                logger.critical(f"Failed to record failure for job {job_id}: {db_err}")
        finally:
            db.close()

    @classmethod
    def dispatch(
        cls,
        background_tasks: BackgroundTasks,
        fn: Callable[..., Any],
        job_id: str,
        *args,
        **kwargs
    ) -> None:
        """Enqueues task into FastAPI background tasks."""
        background_tasks.add_task(cls.run_worker_task, fn, job_id, *args, **kwargs)

    @classmethod
    def dispatch_sync(
        cls,
        fn: Callable[..., Any],
        job_id: str,
        *args,
        **kwargs
    ) -> None:
        """Executes task synchronously (useful in tests or CLI scripts)."""
        cls.run_worker_task(fn, job_id, *args, **kwargs)
