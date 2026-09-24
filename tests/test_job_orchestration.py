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


def test_dynamic_input_propagation_and_strata_recalculation(client, sample_parcel_geojson):
    """
    Regression Test: Proves dynamic vertical input propagation.
    Compares Test A (18m, 4 floors, 1 basement, 2 units/floor)
    against Test B (30m, 8 floors, 2 basements, 4 units/floor).
    Verifies that vertical parameters dynamically update building height,
    floor levels, strata decomposition, unit counts, and 3D ULPIN registry.
    """
    # -------------------------------------------------------------
    # 1. RUN TEST A: 18m, 4 floors above, 1 basement, 2 units/floor
    # -------------------------------------------------------------
    payload_a = {
        "survey_number": "DEMO-PROPAGATION-001",
        "state_code": 27,
        "district_code": "PUN",
        "parcel_geojson": sample_parcel_geojson,
        "total_height_m": 18.0,
        "ground_elevation_m": 500.0,
        "floor_count": 4,
        "basement_count": 1,
        "units_per_floor": 2,
        "auto_generate_strata": True,
        "source_evidence": {
            "source_type": "DRONE_PHOTOGRAMMETRY",
            "source_reference": "survey_a.geojson"
        }
    }
    resp_a = client.post("/api/v1/jobs/process-parcel", json=payload_a)
    assert resp_a.status_code == status.HTTP_202_ACCEPTED
    job_id_a = resp_a.json()["data"]["job_id"]

    res_resp_a = client.get(f"/api/v1/jobs/{job_id_a}/result")
    assert res_resp_a.status_code == status.HTTP_200_OK
    res_a = res_resp_a.json()["data"]
    assert res_a["status"] == "COMPLETED"

    created_a = res_a["created_entities"]
    parcel_id_a = created_a["parcel_id"]
    assert created_a["floors_count"] == 5   # 4 above + 1 basement
    assert created_a["units_count"] == 10   # 5 floors * 2 units/floor
    assert len(created_a["unit_ulpins"]) == 10
    ulpins_a = set(created_a["unit_ulpins"])

    # Verify Digital Twin for Test A
    dt_resp_a = client.get(f"/api/v1/parcels/{parcel_id_a}/digital-twin")
    assert dt_resp_a.status_code == status.HTTP_200_OK
    dt_data_a = dt_resp_a.json()["data"]
    assert len(dt_data_a["parcel"]["buildings"]) == 1
    bld_a = dt_data_a["parcel"]["buildings"][0]
    assert bld_a["total_height_m"] == 18.0
    assert len(bld_a["floors"]) == 5
    assert dt_data_a["summary"]["total_units"] == 10
    assert dt_data_a["summary"]["total_floors"] == 5

    # -------------------------------------------------------------
    # 2. RUN TEST B: 30m, 8 floors above, 2 basements, 4 units/floor
    # Submitting updated vertical parameters for the SAME parcel
    # -------------------------------------------------------------
    payload_b = {
        "parcel_id": parcel_id_a,
        "survey_number": "DEMO-PROPAGATION-001",
        "state_code": 27,
        "district_code": "PUN",
        "parcel_geojson": sample_parcel_geojson,
        "total_height_m": 30.0,
        "ground_elevation_m": 560.0,
        "floor_count": 8,
        "basement_count": 2,
        "units_per_floor": 4,
        "auto_generate_strata": True,
        "source_evidence": {
            "source_type": "DRONE_PHOTOGRAMMETRY",
            "source_reference": "survey_b.geojson"
        }
    }
    resp_b = client.post("/api/v1/jobs/process-parcel", json=payload_b)
    assert resp_b.status_code == status.HTTP_202_ACCEPTED
    job_id_b = resp_b.json()["data"]["job_id"]

    res_resp_b = client.get(f"/api/v1/jobs/{job_id_b}/result")
    assert res_resp_b.status_code == status.HTTP_200_OK
    res_b = res_resp_b.json()["data"]
    assert res_b["status"] == "COMPLETED"

    created_b = res_b["created_entities"]
    assert created_b["floors_count"] == 10  # 8 above + 2 basements
    assert created_b["units_count"] == 40   # 10 floors * 4 units/floor
    assert len(created_b["unit_ulpins"]) == 40
    ulpins_b = set(created_b["unit_ulpins"])

    # Verify Digital Twin for Test B
    dt_resp_b = client.get(f"/api/v1/parcels/{parcel_id_a}/digital-twin")
    assert dt_resp_b.status_code == status.HTTP_200_OK
    dt_data_b = dt_resp_b.json()["data"]
    bld_b = dt_data_b["parcel"]["buildings"][0]
    assert bld_b["total_height_m"] == 30.0
    assert bld_b["ground_elevation_m"] == 560.0
    assert len(bld_b["floors"]) == 10
    assert dt_data_b["summary"]["total_units"] == 40
    assert dt_data_b["summary"]["total_floors"] == 10

    # -------------------------------------------------------------
    # 3. VERIFY MATERIAL DIVERGENCE BETWEEN TEST A AND TEST B
    # -------------------------------------------------------------
    assert bld_b["total_height_m"] != bld_a["total_height_m"]
    assert created_b["floors_count"] != created_a["floors_count"]
    assert created_b["units_count"] != created_a["units_count"]
    # Ensure newly created 3D ULPIN set reflects the 40 stratified units
    assert ulpins_b != ulpins_a
    assert len(ulpins_b - ulpins_a) == 30  # 30 new 3D ULPINs registered across expanded strata


def test_regression_case_a_new_parcel_registration(client):
    """
    TEST A — NEW PARCEL
    Given target_parcel_id is null/omitted and valid survey input,
    verify that:
    - job is accepted
    - no 'LandParcel not found' error occurs
    - new LandParcel is registered anew
    - 3D cadastral hierarchy, 3D ULPIN generation, and validation succeed
    """
    payload = {
        "parcel_id": None,
        "survey_number": "DEMO-26011-001",
        "state_code": 27,
        "district_code": "PUN",
        "total_height_m": 18.0,
        "floor_count": 4,
        "basement_count": 1,
        "units_per_floor": 2,
        "auto_generate_strata": True,
        "source_evidence": {
            "source_type": "DRONE_PHOTOGRAMMETRY",
            "source_reference": "demo_26011_drone_survey.geojson"
        }
    }
    resp = client.post("/api/v1/jobs/process-parcel", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    job_id = resp.json()["data"]["job_id"]

    res_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert res_resp.status_code == status.HTTP_200_OK
    res = res_resp.json()["data"]
    assert res["status"] == "COMPLETED"
    assert res["quality_score"] is not None

    created = res["created_entities"]
    assert created["parcel_id"] is not None
    assert created["floors_count"] == 5
    assert created["units_count"] == 10
    assert len(created["unit_ulpins"]) == 10


def test_regression_case_b_existing_parcel_processing(client, sample_parcel_geojson):
    """
    TEST B — EXISTING PARCEL
    Given target_parcel_id is an ACTUAL existing LandParcel UUID,
    verify that existing parcel is processed and no duplicate LandParcel is created.
    """
    # 1. Create parcel first
    p_create = client.post("/api/v1/parcels/", json={
        "state_code": "27",
        "district_code": "PUN",
        "village_code": "54321",
        "survey_number": "SN-EXISTING-999",
        "geometry_geojson": sample_parcel_geojson
    })
    assert p_create.status_code == status.HTTP_201_CREATED
    existing_parcel_id = p_create.json()["data"]["id"]

    # 2. Process using existing parcel UUID
    payload = {
        "parcel_id": existing_parcel_id,
        "survey_number": "SN-EXISTING-999",
        "state_code": 27,
        "district_code": "PUN",
        "total_height_m": 24.0,
        "floor_count": 6,
        "basement_count": 1,
        "units_per_floor": 2,
    }
    resp = client.post("/api/v1/jobs/process-parcel", json=payload)
    assert resp.status_code == status.HTTP_202_ACCEPTED
    job_id = resp.json()["data"]["job_id"]

    res_resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert res_resp.status_code == status.HTTP_200_OK
    res = res_resp.json()["data"]
    assert res["status"] == "COMPLETED"
    assert res["created_entities"]["parcel_id"] == existing_parcel_id


def test_regression_case_c_invalid_existing_parcel_clean_rejection(client):
    """
    TEST C — INVALID EXISTING PARCEL
    Given target_parcel_id is a random nonexistent UUID,
    verify that a clean 404/validation error is returned and no fake parcel is created.
    """
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    payload = {
        "parcel_id": fake_uuid,
        "survey_number": "SN-NONEXISTENT",
        "state_code": 27,
        "district_code": "PUN",
        "total_height_m": 15.0,
        "floor_count": 3
    }
    resp = client.post("/api/v1/jobs/process-parcel", json=payload)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    err = resp.json()["error"]
    assert err["code"] == "ENTITY_NOT_FOUND"
    assert fake_uuid in err["message"]


def test_regression_case_d_and_e_repeated_new_surveys_no_leakage(client):
    """
    TEST D & E — REPEATED NEW SURVEYS
    Run two consecutive NEW survey submissions with parcel_id=None.
    Verify that the second survey does not inherit the first survey's parcel UUID
    and both create independent, isolated 3D cadastral hierarchies.
    """
    # First new survey
    payload_1 = {
        "parcel_id": None,
        "survey_number": "SN-NEW-RUN-1",
        "state_code": 27,
        "district_code": "PUN",
        "total_height_m": 12.0,
        "floor_count": 3,
        "units_per_floor": 2
    }
    resp_1 = client.post("/api/v1/jobs/process-parcel", json=payload_1)
    assert resp_1.status_code == status.HTTP_202_ACCEPTED
    job_1_id = resp_1.json()["data"]["job_id"]

    res_1 = client.get(f"/api/v1/jobs/{job_1_id}/result").json()["data"]
    assert res_1["status"] == "COMPLETED"
    parcel_id_1 = res_1["created_entities"]["parcel_id"]

    # Second new survey with parcel_id=None
    payload_2 = {
        "parcel_id": None,
        "survey_number": "SN-NEW-RUN-2",
        "state_code": 27,
        "district_code": "PUN",
        "total_height_m": 18.0,
        "floor_count": 4,
        "units_per_floor": 3
    }
    resp_2 = client.post("/api/v1/jobs/process-parcel", json=payload_2)
    assert resp_2.status_code == status.HTTP_202_ACCEPTED
    job_2_id = resp_2.json()["data"]["job_id"]

    res_2 = client.get(f"/api/v1/jobs/{job_2_id}/result").json()["data"]
    assert res_2["status"] == "COMPLETED"
    parcel_id_2 = res_2["created_entities"]["parcel_id"]

    # Assert independence: second survey created its own distinct parcel
    assert parcel_id_1 != parcel_id_2
    assert res_2["created_entities"]["units_count"] == 12  # 4 floors * 3 units/floor

