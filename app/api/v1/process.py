"""
Unified Cadastral Processing Convenience Router.
Provides direct processing entry points for 3D cadastre workflows.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.schemas import JobRead, ParcelProcessJobRequest
from app.api.v1.jobs import submit_parcel_processing_job
from app.schemas.common import APIResponse

router = APIRouter(prefix="/process", tags=["Unified Cadastral Processing Entrypoints"])


@router.post("/parcel", response_model=APIResponse[JobRead], status_code=status.HTTP_202_ACCEPTED)
def trigger_parcel_processing(
    request: ParcelProcessJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Convenience alias endpoint to initiate asynchronous end-to-end 3D parcel processing.
    Delegates to the job orchestration engine and returns an HTTP 202 tracking response.
    """
    return submit_parcel_processing_job(request=request, background_tasks=background_tasks, db=db)
