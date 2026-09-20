"""
Test Suite: Asynchronous Ingestion & End-to-End Cadastral Processing Orchestration.
Covers state transitions, idempotent queuing, background execution, error handling,
cancellation, deterministic cadastral generation, and API contract compliance.
"""

import pytest
from fastapi import status
from sqlalchemy.orm import Session

from app.jobs.manager import JobManager
from app.jobs.models import ProcessingJob
from app.jobs.schemas import JobStatus, JobStage, JobType
from app.core.exceptions import CadastreException


def test_job_state_machine_and_transitions(db_session: Session):
    """Verifies valid state transitions and stage event logging."""
    job = JobManager.create_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        entity_type="DATASET",
        source_filename="test_survey.geojson"
    )
    assert job.status == JobStatus.QUEUED.value
    assert job.progress_percent == 0.0
    assert job.current_stage == JobStage.QUEUED.value
    assert len(job.stage_details.get("events", [])) == 1

    # Transition to RUNNING / INSPECTION
    JobManager.transition_stage(db_session, job.job_id, stage=JobStage.INSPECTION.value, progress_percent=20.0)
    db_session.refresh(job)
    assert job.status == JobStatus.RUNNING.value
    assert job.current_stage == JobStage.INSPECTION.value
    assert job.progress_percent == 20.0
    assert len(job.stage_details["events"]) == 2

    # Transition to PREPROCESSING
    JobManager.transition_stage(db_session, job.job_id, stage=JobStage.PREPROCESSING.value, progress_percent=50.0)
    db_session.refresh(job)
    assert job.progress_percent == 50.0

    # Complete job
    result_data = {"test_key": "test_value"}
    JobManager.mark_completed(db_session, job.job_id, result_reference=result_data)
    db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED.value
    assert job.progress_percent == 100.0
    assert job.result_reference == result_data

    # Invalid transition attempt after COMPLETED is safely ignored
    JobManager.transition_stage(db_session, job.job_id, stage=JobStage.INSPECTION.value, progress_percent=10.0)
    db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED.value
    assert job.progress_percent == 100.0


def test_job_cancellation_and_terminal_guard(db_session: Session):
    """Verifies that queued/running jobs can be cancelled and terminal jobs reject cancellation."""
    job = JobManager.create_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename="cancel_target.geojson"
    )
    assert job.status == JobStatus.QUEUED.value

    # Cancel job
    cancelled_job = JobManager.cancel_job(db_session, job.job_id, reason="User requested abort")
    assert cancelled_job.status == JobStatus.CANCELLED.value
    assert cancelled_job.error_message == "User requested abort"

    # Attempting to cancel already cancelled job must raise CadastreException
    with pytest.raises(CadastreException):
        JobManager.cancel_job(db_session, job.job_id, reason="Abort again")


def test_job_idempotency_lookup(db_session: Session):
    """Verifies that active jobs for the same source/entity are identified to prevent duplicates."""
    job1 = JobManager.create_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename="unique_survey.geojson"
    )

    # Lookup finds active job
    active = JobManager.find_active_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename="unique_survey.geojson"
    )
    assert active is not None
    assert active.job_id == job1.job_id

    # Once completed, lookup returns None (allowing new job)
    JobManager.mark_completed(db_session, job1.job_id, result_reference={})
    active_after = JobManager.find_active_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename="unique_survey.geojson"
    )
    assert active_after is None


def test_survey_ingestion_api_flow(client, sample_parcel_geojson):
    """Tests asynchronous survey ingestion API endpoint and result retrieval."""
    payload = {
        "source_type": "GEOJSON",
        "source_filename": "Survey_Village_Haveli.geojson",
        "source_crs": "EPSG:4326",
        "dataset_payload": sample_parcel_geojson,
        "metadata": {"notes": "SIH local test"}
    }

    # 1. Submit async ingestion job (202 Accepted)
    resp = client.post("/api/v1/jobs/ingestion", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    data = resp.json()["data"]
    job_id = data["job_id"]
    assert data["job_type"] == "SURVEY_INGESTION"
    assert data["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert data["tracking_url"] == f"/api/v1/jobs/{job_id}"

    # 2. Query status
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == status.HTTP_200_OK
    status_data = status_resp.json()["data"]
    assert status_data["status"] == "COMPLETED"
    assert status_data["progress_percent"] == 100.0

    # 3. Retrieve results
    result_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert result_resp.status_code == status.HTTP_200_OK
    res_data = result_resp.json()["data"]
    assert res_data["status"] == "COMPLETED"
    assert res_data["job_type"] == "SURVEY_INGESTION"


def test_survey_ingestion_path_traversal_blocked(client):
    """Verifies that malicious path traversal filenames are intercepted."""
    payload = {
        "source_type": "GEOJSON",
        "source_filename": "../../etc/shadow",
        "source_crs": "EPSG:4326",
        "dataset_payload": {}
    }
    resp = client.post("/api/v1/jobs/ingestion", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    job_id = resp.json()["data"]["job_id"]

    # Background task caught path traversal and marked job as FAILED
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == status.HTTP_200_OK
    assert status_resp.json()["data"]["status"] == "FAILED"
    assert "traversal" in status_resp.json()["data"]["error_message"].lower()


def test_end_to_end_parcel_processing_api_flow(client, sample_parcel_geojson):
    """
    Tests complete end-to-end processing pipeline:
    Parcel -> ML Feature Extraction -> 3D Building & Floors ->
    3D ULPIN -> Deterministic Validation -> Digital Twin.
    """
    payload = {
        "state_code": 27,
        "district_code": "PUN",
        "survey_number": "SN-ORCHESTRATOR-411",
        "parcel_geojson": sample_parcel_geojson,
        "total_height_m": 16.5,
        "ground_elevation_m": 550.0,
        "floor_count": 4,
        "basement_count": 1,
        "units_per_floor": 2,
        "auto_generate_strata": True
    }

    # 1. Trigger processing
    resp = client.post("/api/v1/jobs/process-parcel", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    job_data = resp.json()["data"]
    job_id = job_data["job_id"]
    assert job_data["job_type"] == "END_TO_END_PARCEL_PROCESS"

    # 2. Check completed job status
    poll_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert poll_resp.status_code == status.HTTP_200_OK
    poll_data = poll_resp.json()["data"]
    assert poll_data["status"] == "COMPLETED"
    assert poll_data["progress_percent"] == 100.0
    assert poll_data["current_stage"] == "COMPLETED"

    # Verify stage progression in events
    events = poll_data["stage_details"].get("events", [])
    stages_recorded = [e["stage"] for e in events]
    assert "INSPECTION" in stages_recorded
    assert "PREPROCESSING" in stages_recorded
    assert "FEATURE_EXTRACTION" in stages_recorded
    assert "CADASTRAL_CONSTRUCTION" in stages_recorded
    assert "VALIDATION" in stages_recorded
    assert "COMPLETED" in stages_recorded

    # 3. Retrieve final result
    res_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert res_resp.status_code == status.HTTP_200_OK
    res = res_resp.json()["data"]
    assert res["status"] == "COMPLETED"
    assert res["quality_score"] is not None
    assert res["quality_grade"] is not None
    assert res["digital_twin_url"] is not None
    assert "anomalies" in res
    assert isinstance(res["anomalies"], list)

    created = res["created_entities"]
    assert created["parcel_ulpin"] is not None
    assert created["building_code"] is not None
    assert created["floors_count"] >= 4
    assert len(created["unit_ulpins"]) >= 2
    # Verify 3D ULPIN format (e.g. 643C09C1D5CFDG-L01-UL0101-MQ)
    assert any("L01" in u or "G00" in u for u in created["unit_ulpins"])


def test_convenience_process_parcel_endpoint(client, sample_parcel_geojson):
    """Tests /api/v1/process/parcel convenience alias."""
    payload = {
        "state_code": 27,
        "district_code": "PUN",
        "survey_number": "SN-CONVENIENCE-01",
        "parcel_geojson": sample_parcel_geojson,
        "total_height_m": 12.0,
        "floor_count": 3,
        "units_per_floor": 2
    }
    resp = client.post("/api/v1/process/parcel", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    data = resp.json()["data"]
    assert data["job_type"] == "END_TO_END_PARCEL_PROCESS"
    assert data["tracking_url"].startswith("/api/v1/jobs/")


def test_list_jobs_and_filtering(client):
    """Tests GET /api/v1/jobs with pagination and status filters."""
    # Enqueue a dummy job
    client.post("/api/v1/jobs/ingestion", json={
        "source_type": "GEOJSON",
        "source_filename": "list_filter_test.geojson",
        "dataset_payload": {}
    })

    resp = client.get("/api/v1/jobs?limit=10&offset=0")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert "jobs" in data
    assert data["total"] >= 1
    assert len(data["jobs"]) >= 1

    # Filter by completed status
    comp_resp = client.get("/api/v1/jobs?status=COMPLETED")
    assert comp_resp.status_code == status.HTTP_200_OK
    assert all(j["status"] == "COMPLETED" for j in comp_resp.json()["data"]["jobs"])


def test_cancel_job_via_api(client, db_session: Session):
    """Tests POST /api/v1/jobs/{job_id}/cancel."""
    # Manually create a QUEUED job that hasn't executed
    job = JobManager.create_job(
        db=db_session,
        job_type=JobType.SURVEY_INGESTION.value,
        source_filename="manual_cancel_queue.geojson"
    )

    resp = client.post(f"/api/v1/jobs/{job.job_id}/cancel?reason=OperatorAborted")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert data["status"] == "CANCELLED"
    assert data["error_message"] == "OperatorAborted"
