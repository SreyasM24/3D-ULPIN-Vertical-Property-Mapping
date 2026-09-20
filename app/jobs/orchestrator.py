"""
End-to-End Cadastral Processing Orchestrator.
Coordinates the entire lifecycle:
Source Inspection -> Preprocessing -> ML Feature Extraction ->
3D Cadastral Construction -> 3D ULPIN Generation ->
Deterministic Cadastral Validation -> Digital Twin Registration -> Completion.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import shapely.affinity
import shapely.geometry
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.jobs.manager import JobManager
from app.jobs.schemas import JobStatus, JobStage
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.schemas.parcel import ParcelCreate, GeoJSONPolygon
from app.schemas.building import BuildingCreate
from app.schemas.floor import FloorCreate
from app.schemas.unit import UnitCreate
from app.services.cadastre_service import CadastreService
from app.services.spatial_engine import (
    geojson_to_shapely,
    compute_projected_spatial_metrics,
)
from app.services.geometry_normalization import GeometryNormalizationService
from app.services.cadastral_validator import CadastralValidationService
from app.services.digital_twin_service import DigitalTwinService
from app.ml.pipelines.feature_extraction import FeatureExtractionPipeline
from app.ml.pipelines.vertical_cadastre import VerticalCadastreFeatureService
from app.services.ingestion.geojson_adapter import GeoJSONIngestionAdapter
from app.services.ingestion.metadata_adapters import (
    LiDARMetadataAdapter,
    DEMDSMMetadataAdapter,
    DroneImageryMetadataAdapter,
    FloorPlanMetadataAdapter,
)
from app.core.exceptions import CadastreException, EntityNotFoundException
from app.core.logging import logger


class CadastralProcessingOrchestrator:
    """Coordinates multi-stage asynchronous processing workflows."""

    @staticmethod
    def _create_inset_footprint(parcel_geom: Dict[str, Any], scale_factor: float = 0.65) -> Dict[str, Any]:
        """Derives a safe building footprint strictly contained inside the parent parcel."""
        poly = geojson_to_shapely(parcel_geom, auto_heal=True)
        centroid = poly.centroid
        scaled = shapely.affinity.scale(poly, xfact=scale_factor, yfact=scale_factor, origin=centroid)
        if not scaled.is_valid:
            scaled = scaled.buffer(0)
        return GeoJSONPolygon(**shapely.geometry.mapping(scaled)).model_dump()

    @staticmethod
    def _partition_footprint(bld_footprint: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
        """Partitions building footprint into non-overlapping unit polygons."""
        poly = geojson_to_shapely(bld_footprint, auto_heal=True)
        if count <= 1:
            return [GeoJSONPolygon(**shapely.geometry.mapping(poly)).model_dump()]
        minx, miny, maxx, maxy = poly.bounds
        dx = (maxx - minx) / count
        partitions = []
        for i in range(count):
            box_slice = shapely.geometry.box(minx + i * dx, miny, minx + (i + 1) * dx, maxy)
            part = poly.intersection(box_slice)
            if not part.is_empty and part.is_valid:
                partitions.append(GeoJSONPolygon(**shapely.geometry.mapping(part)).model_dump())
            else:
                partitions.append(GeoJSONPolygon(**shapely.geometry.mapping(poly)).model_dump())
        return partitions

    @classmethod
    def run_survey_ingestion_job(cls, db: Session, job_id: str, payload: Dict[str, Any]) -> None:
        """
        Asynchronously ingests, inspects, normalizes, and audits raw survey datasets.
        """
        JobManager.start_job(db, job_id)

        # 1. Source Inspection
        source_filename = payload.get("source_filename", "unnamed_survey")
        source_type = (payload.get("source_type") or "GEOJSON").upper()
        source_crs = payload.get("source_crs", "EPSG:4326")
        dataset_payload = payload.get("dataset_payload") or {}
        options = payload.get("options") or {}

        # Security check against path traversal
        if ".." in source_filename or "/" in source_filename or "\\" in source_filename:
            raise CadastreException(f"Invalid source filename containing path traversal characters: {source_filename}")

        JobManager.transition_stage(
            db, job_id,
            stage=JobStage.INSPECTION.value,
            progress_percent=20.0,
            details={"source_type": source_type, "source_filename": source_filename, "crs": source_crs}
        )

        # 2. Preprocessing & Ingestion Adapter
        JobManager.transition_stage(
            db, job_id,
            stage=JobStage.PREPROCESSING.value,
            progress_percent=50.0,
            details={"action": "executing_dataset_adapter"}
        )

        ingest_result = None
        if source_type == "GEOJSON":
            adapter = GeoJSONIngestionAdapter(source_name=source_filename)
            ingest_result = adapter.ingest(dataset_payload, options={"source_crs": source_crs})
        elif source_type == "LIDAR":
            adapter = LiDARMetadataAdapter(source_name=source_filename)
            ingest_result = adapter.ingest(dataset_payload)
        elif source_type in ("DEM_DSM", "RASTER"):
            adapter = DEMDSMMetadataAdapter(source_name=source_filename)
            ingest_result = adapter.ingest(dataset_payload)
        elif source_type == "DRONE":
            adapter = DroneImageryMetadataAdapter(source_name=source_filename)
            ingest_result = adapter.ingest(dataset_payload)
        elif source_type in ("CAD", "CAD_FLOOR_PLAN"):
            adapter = FloorPlanMetadataAdapter(source_name=source_filename)
            ingest_result = adapter.ingest(dataset_payload)
        else:
            raise CadastreException(f"Unsupported survey source type for ingestion: {source_type}")

        # 3. Cadastral Construction Check
        created_parcels = []
        if source_type == "GEOJSON" and options.get("auto_create_parcels", False):
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.CADASTRAL_CONSTRUCTION.value,
                progress_percent=75.0,
                details={"action": "auto_registering_parcels"}
            )
            # Register features if collection
            features = dataset_payload.get("features", [])
            for idx, feat in enumerate(features[:5]):  # limit batch in single job
                geom = feat.get("geometry")
                if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
                    try:
                        p_in = ParcelCreate(
                            state_code=str(options.get("state_code", "MH")),
                            district_code=str(options.get("district_code", "PUN")),
                            village_code=str(options.get("village_code", "54321")),
                            survey_number=feat.get("properties", {}).get("survey_number", f"SN-JOB-{job_id[:6]}-{idx+1}"),
                            geometry_geojson=GeoJSONPolygon(**geom)
                        )
                        parcel = CadastreService.create_parcel(db, p_in)
                        created_parcels.append(parcel.id)
                    except Exception as p_err:
                        logger.warning(f"Could not auto-create parcel from feature {idx}: {p_err}")

        # 4. Validation & Audit
        JobManager.transition_stage(
            db, job_id,
            stage=JobStage.VALIDATION.value,
            progress_percent=90.0,
            details={"validation_status": str(ingest_result.provenance.validation_status) if ingest_result else None}
        )

        # 5. Completion
        res_data = ingest_result.model_dump(mode="json") if hasattr(ingest_result, "model_dump") else (ingest_result or {})
        result_ref = {
            "source_filename": source_filename,
            "source_type": source_type,
            "ingestion_status": res_data.get("status", "SUCCESS"),
            "features_detected": res_data.get("metrics", {}).get("feature_count", 1),
            "provenance": res_data.get("provenance", {}),
            "created_parcel_ids": created_parcels
        }

        JobManager.mark_completed(db, job_id, result_reference=result_ref)

    @classmethod
    def run_end_to_end_parcel_processing(cls, db: Session, job_id: str, payload: Dict[str, Any]) -> None:
        """
        Executes the full end-to-end pipeline:
        Parcel resolution -> ML feature extraction -> 3D cadastre construction ->
        3D ULPIN generation -> Deterministic validation -> Digital twin assembly.
        """
        JobManager.start_job(db, job_id)

        # 1. Stage: INSPECTION
        JobManager.transition_stage(
            db, job_id,
            stage=JobStage.INSPECTION.value,
            progress_percent=15.0,
            details={"step": "Inspecting input geometries and metadata"}
        )

        parcel_id = payload.get("parcel_id")
        parcel = None
        newly_created_parcel = None
        newly_created_building = None
        if parcel_id:
            parcel = db.get(LandParcel, parcel_id)
            if not parcel:
                raise EntityNotFoundException("LandParcel", parcel_id)
        else:
            parcel_geojson = payload.get("parcel_geojson")
            if not parcel_geojson:
                raise CadastreException("Either existing parcel_id or parcel_geojson must be provided.")
            
            # Normalize parcel geometry
            norm_res = GeometryNormalizationService.normalize_geojson(parcel_geojson)
            if not norm_res.is_valid or not norm_res.geojson:
                raise CadastreException(f"Invalid parcel geometry: {norm_res.validation_message}")
            
            # Check if parcel with identical centroid already exists
            p_in = ParcelCreate(
                state_code=str(payload.get("state_code", "MH")),
                district_code=str(payload.get("district_code", "PUN")),
                village_code=str(payload.get("village_code", "54321")),
                survey_number=payload.get("survey_number", f"SN-JOB-{job_id[:6]}"),
                geometry_geojson=GeoJSONPolygon(**norm_res.geojson)
            )
            try:
                parcel = CadastreService.create_parcel(db, p_in)
                newly_created_parcel = parcel
            except Exception:
                # If duplicate ULPIN already exists in DB, fetch it
                metrics = compute_projected_spatial_metrics(norm_res.geojson)
                from app.services.ulpin_engine import generate_2d_ulpin
                ulpin = generate_2d_ulpin(
                    lat=metrics["centroid_lat"],
                    lon=metrics["centroid_lon"],
                    state_code=p_in.state_code,
                    survey_number=p_in.survey_number
                )
                parcel = db.execute(select(LandParcel).where(LandParcel.ulpin == ulpin)).scalar_one_or_none()
                if not parcel:
                    raise

        # Associate entity with job
        job = JobManager.get_job(db, job_id)
        if job:
            job.entity_type = "PARCEL"
            job.entity_id = parcel.id
            db.commit()

        try:
            # 2. Stage: PREPROCESSING
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.PREPROCESSING.value,
                progress_percent=30.0,
                details={"step": "Projecting coordinates and resolving footprint bounds", "parcel_ulpin": parcel.ulpin}
            )

            bld_footprint = payload.get("building_footprint_geojson")
            if not bld_footprint:
                bld_footprint = cls._create_inset_footprint(parcel.geometry_geojson, scale_factor=0.65)
            else:
                norm_bld = GeometryNormalizationService.normalize_geojson(bld_footprint)
                if norm_bld.is_valid and norm_bld.geojson:
                    bld_footprint = norm_bld.geojson

            # 3. Stage: FEATURE_EXTRACTION (ML Layer)
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.FEATURE_EXTRACTION.value,
                progress_percent=45.0,
                details={"step": "Extracting 3D heights and vertical strata via ML pipeline"}
            )

            ml_pipeline = FeatureExtractionPipeline()
            ml_inputs = {
                "footprint_geojson": bld_footprint,
                "height_m": payload.get("total_height_m"),
                "ground_elevation_m": payload.get("ground_elevation_m", 0.0),
                "floor_count": payload.get("floor_count"),
                "basement_count": payload.get("basement_count", 0),
                **(payload.get("source_evidence") or {})
            }
            ml_result = ml_pipeline.process(ml_inputs)

            estimated_height = ml_result.features.height_m if ml_result.features else (payload.get("total_height_m") or 15.0)
            strata_levels = ml_result.vertical_proposals or []
            ground_z = payload.get("ground_elevation_m", 0.0) or 0.0

            # 4. Stage: CADASTRAL_CONSTRUCTION (Deterministic 3D Cadastre)
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.CADASTRAL_CONSTRUCTION.value,
                progress_percent=65.0,
                details={
                    "step": "Constructing deterministic Building, FloorLevel strata, and Vertical Units",
                    "estimated_height_m": estimated_height,
                    "strata_count": len(strata_levels)
                }
            )

            # Check existing building or create new one
            existing_bld = db.execute(
                select(Building).where(Building.parcel_id == parcel.id)
            ).scalars().first()

            if existing_bld:
                building = existing_bld
            else:
                bld_code = f"BLD-{job_id[:6].upper()}"
                above_count = sum(1 for s in strata_levels if "B" not in s.level_code) or 3
                base_count = sum(1 for s in strata_levels if "B" in s.level_code) or 0
                height_prov = next((p for p in ml_result.provenance if "HEIGHT" in p.source_id), None)
                floor_prov = next((p for p in ml_result.provenance if "FLOOR" in p.source_id), None)
                bld_spatial_metadata = {
                    "height_source": height_prov.source_type.value if height_prov else "OBSERVED_SURVEY_METADATA",
                    "height_method": height_prov.method if height_prov else "EXPLICIT_METADATA",
                    "floor_source": floor_prov.source_type.value if floor_prov else "DETERMINISTIC_BASELINE",
                    "floor_method": floor_prov.method if floor_prov else "PARAMETRIC_STRATA_DECOMPOSITION",
                    "confidence": ml_result.confidence,
                    "uncertainty_m": ml_result.uncertainty_m,
                    "requires_review": ml_result.confidence < 0.70 or (height_prov and "AI" in height_prov.source_type.value)
                }
                bld_create = BuildingCreate(
                    parcel_id=parcel.id,
                    building_name=f"Cadastral Structure {bld_code}",
                    building_code=bld_code,
                    structure_type="COMMERCIAL_RESIDENTIAL",
                    floors_above_ground=max(1, above_count),
                    basement_floors=base_count,
                    total_height_m=estimated_height,
                    ground_elevation_m=ground_z,
                    footprint_geojson=GeoJSONPolygon(**bld_footprint),
                    spatial_metadata=bld_spatial_metadata
                )
                building = CadastreService.create_building(db, bld_create)
                newly_created_building = building

            # Create Floors and Units if auto_generate_strata is True and floors don't exist yet
            existing_floors = db.execute(
                select(FloorLevel).where(FloorLevel.building_id == building.id)
            ).scalars().all()

            created_floors: List[FloorLevel] = list(existing_floors)
            created_units: List[VerticalUnit] = []

            if not existing_floors and payload.get("auto_generate_strata", True):
                # Propose candidate cadastre
                candidate_cadastre = VerticalCadastreFeatureService.generate_candidate_cadastre(
                    footprint_geojson=bld_footprint,
                    ground_elevation_m=ground_z,
                    total_height_m=estimated_height,
                    strata_levels=strata_levels,
                    units_per_floor=payload.get("units_per_floor", 2),
                    parent_parcel_id=parcel.id,
                    building_code=building.building_code
                )

                # Persist Floor Levels
                for fl_data in candidate_cadastre["candidate_floors"]:
                    fl_in = FloorCreate(
                        building_id=building.id,
                        level_number=fl_data["level_number"],
                        level_code=fl_data["level_code"],
                        level_type="BASEMENT" if "B" in fl_data["level_code"] else ("GROUND" if fl_data["level_code"] == "G" else "TYPICAL"),
                        z_min=fl_data["z_min"],
                        z_max=fl_data["z_max"],
                        footprint_geojson=GeoJSONPolygon(**bld_footprint)
                    )
                    fl_orm = CadastreService.create_floor(db, fl_in)
                    created_floors.append(fl_orm)

                # 5. Stage: ULPIN_GENERATION (Derive 3D ULPINs for Vertical Units)
                JobManager.transition_stage(
                    db, job_id,
                    stage=JobStage.ULPIN_GENERATION.value,
                    progress_percent=75.0,
                    details={"step": "Generating 3D ULPIN identifiers for vertical property units"}
                )

                floor_map = {fl.level_code: fl for fl in created_floors}
                units_per_floor = payload.get("units_per_floor", 2)
                unit_footprints = cls._partition_footprint(bld_footprint, units_per_floor)

                floor_units_tracker: Dict[str, int] = {}
                for u_data in candidate_cadastre["candidate_units"]:
                    lvl_code = u_data["level_code"]
                    floor_obj = floor_map.get(lvl_code)
                    if floor_obj:
                        u_idx = floor_units_tracker.get(lvl_code, 0)
                        floor_units_tracker[lvl_code] = u_idx + 1
                        u_geom = unit_footprints[u_idx % len(unit_footprints)]

                        unit_num = u_data.get("unit_number", f"{lvl_code}-{u_idx+1:02d}")
                        unit_code = u_data.get("unit_code") or f"U-{unit_num.replace(' ', '')}"
                        unit_type = u_data.get("unit_type", "APARTMENT")

                        u_in = UnitCreate(
                            floor_id=floor_obj.id,
                            unit_number=unit_num,
                            unit_code=unit_code,
                            unit_type=unit_type,
                            z_min=u_data["z_min"],
                            z_max=u_data["z_max"],
                            footprint_geojson=GeoJSONPolygon(**u_geom),
                            is_multi_floor=u_data.get("is_multi_floor", False),
                            floor_span=u_data.get("floor_span"),
                            spatial_metadata={
                                "classification": u_data.get("classification"),
                                "source": u_data.get("source"),
                                "confidence": u_data.get("confidence"),
                                "uncertainty_m": u_data.get("uncertainty_m"),
                                "stage": u_data.get("stage", "ESTIMATED")
                            }
                        )
                        try:
                            u_orm = CadastreService.create_unit(db, u_in, enforce_clash_free=True)
                            created_units.append(u_orm)
                        except Exception as u_err:
                            logger.warning(f"Could not create vertical unit {unit_num}: {u_err}")

            # 6. Stage: VALIDATION (Deterministic Cadastral Rule Engine)
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.VALIDATION.value,
                progress_percent=85.0,
                details={"step": "Executing deterministic cadastral validation rules and 3D clash audit"}
            )

            validation_report = CadastralValidationService.validate_parcel_hierarchy(
                db=db,
                parcel_id=parcel.id,
                persist=True
            )

            # 7. Stage: DIGITAL_TWIN_UPDATE
            JobManager.transition_stage(
                db, job_id,
                stage=JobStage.DIGITAL_TWIN_UPDATE.value,
                progress_percent=95.0,
                details={"step": "Assembling complete 3D digital twin model"}
            )

            dt = DigitalTwinService.assemble_digital_twin(db, parcel.id)

            # 8. Stage: COMPLETED
            result_ref = {
                "parcel_id": parcel.id,
                "parcel_ulpin": parcel.ulpin,
                "building_id": building.id,
                "building_code": building.building_code,
                "floors_count": len(created_floors),
                "units_count": len(created_units) or dt.summary.total_units,
                "unit_ulpins": [u.ulpin_3d for u in created_units if u.ulpin_3d],
                "quality_score": validation_report.quality_score.total_score if hasattr(validation_report.quality_score, "total_score") else float(validation_report.quality_score),
                "quality_grade": validation_report.quality_score.grade.value if hasattr(validation_report.quality_score, "grade") else "HIGH_CONFIDENCE",
                "is_valid": validation_report.is_valid,
                "validation_run_id": validation_report.validation_run_id,
                "digital_twin_summary": {
                    "total_units": dt.summary.total_units,
                    "total_volume_cu_m": dt.summary.total_volume_cu_m,
                    "total_carpet_area_sqm": dt.summary.total_carpet_area_sqm,
                    "anomalies_detected": [a for a in dt.summary.anomalies_detected]
                },
                "anomalies": [a.model_dump() for a in ml_result.anomalies] if ml_result.anomalies else [a for a in dt.summary.anomalies_detected],
                "ml_confidence": ml_result.confidence,
                "ml_confidence_level": ml_result.confidence_level.value if hasattr(ml_result.confidence_level, "value") else str(ml_result.confidence_level),
                "ml_uncertainty_m": ml_result.uncertainty_m
            }

            JobManager.mark_completed(
                db=db,
                job_id=job_id,
                result_reference=result_ref,
                stage_details={"completed_at": datetime.now(timezone.utc).isoformat()}
            )
        except Exception as exc:
            logger.error(f"Error during orchestrator execution for job {job_id}: {exc}")
            try:
                if newly_created_parcel and db.get(LandParcel, newly_created_parcel.id):
                    db.delete(newly_created_parcel)
                    db.commit()
                elif newly_created_building and db.get(Building, newly_created_building.id):
                    db.delete(newly_created_building)
                    db.commit()
            except Exception as clean_err:
                logger.warning(f"Failed to clean up partial records for job {job_id}: {clean_err}")
                try:
                    db.rollback()
                except Exception:
                    pass
            raise
