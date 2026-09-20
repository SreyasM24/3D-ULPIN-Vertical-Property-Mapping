"""
Cadastral Validation Orchestration Service.
Executes the comprehensive validation rule engine, advanced 3D clash analysis,
quality scoring, and audit history persistence.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.floor import FloorLevel
from app.models.unit import VerticalUnit
from app.models.validation import ValidationRunRecord
from app.core.exceptions import EntityNotFoundException
from app.core.validation_rules import (
    ValidationRuleRegistry,
    RuleCategory,
    RuleSeverity,
)
from app.schemas.validation import (
    ValidationIssue,
    QualityScoreBreakdown,
    DigitalTwinValidationReport,
    EntityValidationReport,
    DetailedClashFinding,
    QualityGrade,
)
from app.services.clash_analysis_engine import AdvancedClashEngine
from app.services.cadastral_quality_scorer import CadastralQualityScorer
from app.services.ml_anomaly_hook import DeterministicDefaultAnomalyHook


class CadastralValidationService:
    """Orchestrates comprehensive cadastral validation across 2D boundaries and 3D volumetric strata."""

    ENGINE_VERSION = "1.0.0-cadastral-validator"
    ml_hook = DeterministicDefaultAnomalyHook()

    @classmethod
    def validate_parcel_hierarchy(
        cls,
        db: Session,
        parcel_id: str,
        persist: bool = True,
        tolerance_sqm: float = 0.05,
        tolerance_z_m: float = 0.05,
    ) -> DigitalTwinValidationReport:
        parcel = db.get(LandParcel, parcel_id)
        if not parcel:
            raise EntityNotFoundException("LandParcel", parcel_id)

        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        all_issues: List[ValidationIssue] = []
        rules_executed_count = 0

        # Collect entities
        buildings = db.execute(
            select(Building).where(Building.parcel_id == parcel.id)
        ).scalars().all()

        all_units_dicts: List[Dict[str, Any]] = []
        all_ulpins: List[str] = []

        total_floors = 0
        total_units = 0

        # 1. Validate Parcel Geometry
        parcel_ctx = {
            "id": str(parcel.id),
            "entity_type": "PARCEL",
            "identifier": parcel.ulpin,
            "geometry_geojson": parcel.geometry_geojson,
        }
        for r in [
            ValidationRuleRegistry.get_rule("RULE-GEO-001"),
            ValidationRuleRegistry.get_rule("RULE-GEO-002"),
            ValidationRuleRegistry.get_rule("RULE-GEO-003"),
            ValidationRuleRegistry.get_rule("RULE-GEO-004"),
            ValidationRuleRegistry.get_rule("RULE-GEO-005"),
        ]:
            if r:
                rules_executed_count += 1
                iss = r.evaluate(parcel_ctx)
                if iss:
                    all_issues.append(iss)

        # 2. Validate Buildings & Children
        for b in buildings:
            bld_id = str(b.id)
            floors = db.execute(
                select(FloorLevel).where(FloorLevel.building_id == b.id).order_by(FloorLevel.level_number)
            ).scalars().all()
            total_floors += len(floors)

            floors_dicts = [
                {
                    "id": str(fl.id),
                    "level_number": fl.level_number,
                    "level_code": fl.level_code,
                    "level_type": fl.level_type,
                    "z_min": fl.z_min,
                    "z_max": fl.z_max,
                    "floor_height_m": fl.floor_height_m,
                    "footprint_geojson": fl.footprint_geojson
                }
                for fl in floors
            ]

            building_units_list: List[Dict[str, Any]] = []

            # 2a. Building Geometry & Containment in Parcel
            bld_ctx = {
                "id": bld_id,
                "entity_type": "BUILDING",
                "identifier": b.building_code,
                "footprint_geojson": b.footprint_geojson,
                "parcel_geometry_geojson": parcel.geometry_geojson,
                "floors": floors_dicts,
                "building_code": b.building_code,
            }
            for r_id in ["RULE-GEO-001", "RULE-GEO-002", "RULE-GEO-003", "RULE-HIER-001"]:
                r = ValidationRuleRegistry.get_rule(r_id)
                if r:
                    rules_executed_count += 1
                    iss = r.evaluate(bld_ctx)
                    if iss:
                        all_issues.append(iss)

            # 2b. Floor Strata Rules on Building
            for r_id in ["RULE-FLR-001", "RULE-FLR-002", "RULE-FLR-003", "RULE-FLR-004"]:
                r = ValidationRuleRegistry.get_rule(r_id)
                if r:
                    rules_executed_count += 1
                    iss = r.evaluate(bld_ctx)
                    if iss:
                        all_issues.append(iss)

            # 2c. Floor-Level Rules
            bld_top_z = b.ground_elevation_m + b.total_height_m
            bld_bottom_z = b.ground_elevation_m - (b.basement_floors * 4.0)

            for fl in floors:
                units = db.execute(
                    select(VerticalUnit).where(VerticalUnit.floor_id == fl.id).order_by(VerticalUnit.unit_number)
                ).scalars().all()
                total_units += len(units)

                fl_ctx = {
                    "id": str(fl.id),
                    "entity_type": "FLOOR",
                    "identifier": fl.level_code,
                    "level_code": fl.level_code,
                    "level_number": fl.level_number,
                    "level_type": fl.level_type,
                    "z_min": fl.z_min,
                    "z_max": fl.z_max,
                    "ground_elevation_m": b.ground_elevation_m,
                    "footprint_geojson": fl.footprint_geojson,
                    "building_footprint_geojson": b.footprint_geojson,
                }
                for r_id in ["RULE-HIER-002", "RULE-FLR-005", "RULE-FLR-006", "RULE-FLR-007"]:
                    r = ValidationRuleRegistry.get_rule(r_id)
                    if r:
                        rules_executed_count += 1
                        iss = r.evaluate(fl_ctx)
                        if iss:
                            all_issues.append(iss)

                # 2d. Units on this Floor
                for u in units:
                    all_ulpins.append(u.ulpin_3d)
                    u_dict = {
                        "id": str(u.id),
                        "unit_number": u.unit_number,
                        "unit_code": u.unit_code,
                        "unit_type": u.unit_type,
                        "ulpin_3d": u.ulpin_3d,
                        "footprint_geojson": u.footprint_geojson,
                        "z_min": u.z_min,
                        "z_max": u.z_max,
                        "volume_cu_m": u.volume_cu_m,
                        "carpet_area_sqm": u.carpet_area_sqm,
                    }
                    all_units_dicts.append(u_dict)
                    building_units_list.append(u_dict)

                    unit_ctx = {
                        "id": str(u.id),
                        "entity_type": "UNIT",
                        "identifier": u.unit_number,
                        "unit_number": u.unit_number,
                        "unit_type": u.unit_type,
                        "ulpin_3d": u.ulpin_3d,
                        "footprint_geojson": u.footprint_geojson,
                        "floor_footprint_geojson": fl.footprint_geojson or b.footprint_geojson,
                        "z_min": u.z_min,
                        "z_max": u.z_max,
                        "volume_cu_m": u.volume_cu_m,
                        "floor_z_min": fl.z_min,
                        "floor_z_max": fl.z_max,
                        "building_top_z": bld_top_z,
                        "building_bottom_z": bld_bottom_z,
                        "is_multi_floor": getattr(u, "is_multi_floor", False),
                        "floor_span": getattr(u, "floor_span", None),
                        "all_ulpins": all_ulpins,
                    }
                    for r_id in [
                        "RULE-GEO-001", "RULE-GEO-002", "RULE-GEO-003",
                        "RULE-HIER-003", "RULE-HIER-004", "RULE-HIER-005",
                        "RULE-UNIT-001"
                    ]:
                        r = ValidationRuleRegistry.get_rule(r_id)
                        if r:
                            rules_executed_count += 1
                            iss = r.evaluate(unit_ctx)
                            if iss:
                                all_issues.append(iss)

            # Check duplicate units per building
            bld_unit_ctx = {
                "id": bld_id,
                "entity_type": "BUILDING",
                "identifier": b.building_code,
                "building_code": b.building_code,
                "units": building_units_list
            }
            r_dupe = ValidationRuleRegistry.get_rule("RULE-UNIT-002")
            if r_dupe:
                rules_executed_count += 1
                iss = r_dupe.evaluate(bld_unit_ctx)
                if iss:
                    all_issues.append(iss)

        # 3. 3D Overlap & Clash Analysis across all units
        clashes = AdvancedClashEngine.analyze_unit_clashes(
            all_units_dicts,
            tolerance_overlap_m=tolerance_z_m,
            tolerance_area_sqm=tolerance_sqm
        )

        # Evaluate 3D topology rules from detected clashes
        topo_ctx = {"clashes": clashes}
        for r_id in ["RULE-TOPO-001", "RULE-TOPO-002", "RULE-TOPO-003", "RULE-INF-001"]:
            r = ValidationRuleRegistry.get_rule(r_id)
            if r:
                rules_executed_count += 1
                iss = r.evaluate(topo_ctx)
                if iss:
                    all_issues.append(iss)

        # 4. Check global 3D ULPIN uniqueness
        for u_dict in all_units_dicts:
            u_ctx = {
                "id": u_dict["id"],
                "entity_type": "UNIT",
                "identifier": u_dict["unit_number"],
                "unit_number": u_dict["unit_number"],
                "ulpin_3d": u_dict["ulpin_3d"],
                "all_ulpins": all_ulpins
            }
            r_ulpin = ValidationRuleRegistry.get_rule("RULE-UNIT-003")
            if r_ulpin:
                rules_executed_count += 1
                iss = r_ulpin.evaluate(u_ctx)
                if iss:
                    all_issues.append(iss)

        # 5. Quality Score Calculation
        quality_score = CadastralQualityScorer.calculate_score(
            issues=all_issues,
            has_crs_metadata=bool(parcel.spatial_metadata and parcel.spatial_metadata.get("crs")),
            has_ulpin=bool(parcel.ulpin),
            has_survey_number=bool(parcel.survey_number),
            has_spatial_metadata=bool(parcel.spatial_metadata)
        )

        critical_errors = [i for i in all_issues if i.severity == RuleSeverity.ERROR]
        warnings = [i for i in all_issues if i.severity == RuleSeverity.WARNING]
        infos = [i for i in all_issues if i.severity == RuleSeverity.INFO]
        is_valid = len(critical_errors) == 0

        rules_failed = len(all_issues)
        rules_passed = max(0, rules_executed_count - rules_failed)

        # Recommended Actions
        recommended_actions = cls._generate_recommendations(all_issues, clashes)

        report = DigitalTwinValidationReport(
            validation_run_id=run_id,
            timestamp=now,
            parcel_id=str(parcel.id),
            parcel_ulpin=parcel.ulpin,
            engine_version=cls.ENGINE_VERSION,
            data_version=str(parcel.updated_at.isoformat()) if parcel.updated_at else None,
            is_valid=is_valid,
            quality_score=quality_score,
            total_rules_executed=rules_executed_count,
            total_rules_passed=rules_passed,
            total_rules_failed=rules_failed,
            critical_errors_count=len(critical_errors),
            warnings_count=len(warnings),
            info_count=len(infos),
            entity_counts={
                "parcels": 1,
                "buildings": len(buildings),
                "floors": total_floors,
                "units": total_units,
                "clashes": len(clashes),
            },
            issues=all_issues,
            clash_findings=clashes,
            recommended_actions=recommended_actions
        )

        # 6. Audit History Persistence
        if persist:
            record = ValidationRunRecord(
                validation_run_id=run_id,
                target_entity_type="PARCEL",
                target_entity_id=str(parcel.id),
                engine_version=cls.ENGINE_VERSION,
                data_version=report.data_version,
                is_valid=is_valid,
                quality_score=quality_score.total_score,
                quality_grade=quality_score.grade.value,
                rules_executed=rules_executed_count,
                rules_passed=rules_passed,
                rules_failed=rules_failed,
                critical_issues_count=len(critical_errors),
                warnings_count=len(warnings),
                info_count=len(infos),
                results=report.model_dump(mode="json")
            )
            db.add(record)
            db.commit()

        return report

    @classmethod
    def validate_building(
        cls,
        db: Session,
        building_id: str,
        persist: bool = True
    ) -> EntityValidationReport:
        b = db.get(Building, building_id)
        if not b:
            raise EntityNotFoundException("Building", building_id)

        issues: List[ValidationIssue] = []

        # Geometry checks
        bld_ctx = {
            "id": str(b.id),
            "entity_type": "BUILDING",
            "identifier": b.building_code,
            "footprint_geojson": b.footprint_geojson,
            "building_code": b.building_code,
        }
        for r_id in ["RULE-GEO-001", "RULE-GEO-002", "RULE-GEO-003"]:
            r = ValidationRuleRegistry.get_rule(r_id)
            if r:
                iss = r.evaluate(bld_ctx)
                if iss:
                    issues.append(iss)

        # Check containment against parcel if parcel exists
        if b.parcel:
            bld_ctx["parcel_geometry_geojson"] = b.parcel.geometry_geojson
            r_hier = ValidationRuleRegistry.get_rule("RULE-HIER-001")
            if r_hier:
                iss = r_hier.evaluate(bld_ctx)
                if iss:
                    issues.append(iss)

        # Floor strata rules
        floors = db.execute(
            select(FloorLevel).where(FloorLevel.building_id == b.id).order_by(FloorLevel.level_number)
        ).scalars().all()
        floors_dicts = [
            {"id": str(fl.id), "level_number": fl.level_number, "level_code": fl.level_code, "z_min": fl.z_min, "z_max": fl.z_max}
            for fl in floors
        ]
        bld_ctx["floors"] = floors_dicts
        for r_id in ["RULE-FLR-001", "RULE-FLR-002", "RULE-FLR-003", "RULE-FLR-004"]:
            r = ValidationRuleRegistry.get_rule(r_id)
            if r:
                iss = r.evaluate(bld_ctx)
                if iss:
                    issues.append(iss)

        critical_errors = [i for i in issues if i.severity == RuleSeverity.ERROR]
        is_valid = len(critical_errors) == 0

        qs = CadastralQualityScorer.calculate_score(issues=issues)

        rep = EntityValidationReport(
            entity_id=str(b.id),
            entity_type="BUILDING",
            entity_code=b.building_code,
            is_valid=is_valid,
            issues=issues,
            quality_score=qs.total_score,
            quality_grade=qs.grade
        )

        if persist:
            record = ValidationRunRecord(
                validation_run_id=str(uuid.uuid4()),
                target_entity_type="BUILDING",
                target_entity_id=str(b.id),
                engine_version="1.0.0-cadastral-validator",
                is_valid=is_valid,
                quality_score=qs.total_score,
                quality_grade=qs.grade.value,
                rules_executed=len(issues) + 5,
                rules_passed=5,
                rules_failed=len(issues),
                critical_issues_count=len(critical_errors),
                warnings_count=len(issues) - len(critical_errors),
                info_count=0,
                results=rep.model_dump(mode="json")
            )
            db.add(record)
            db.commit()

        return rep

    @classmethod
    def validate_unit(
        cls,
        db: Session,
        unit_id: str,
        persist: bool = True
    ) -> EntityValidationReport:
        u = db.get(VerticalUnit, unit_id)
        if not u:
            raise EntityNotFoundException("VerticalUnit", unit_id)

        issues: List[ValidationIssue] = []
        fl = u.floor
        b = fl.building if fl else None

        unit_ctx = {
            "id": str(u.id),
            "entity_type": "UNIT",
            "identifier": u.unit_number,
            "unit_number": u.unit_number,
            "unit_type": u.unit_type,
            "ulpin_3d": u.ulpin_3d,
            "footprint_geojson": u.footprint_geojson,
            "floor_footprint_geojson": fl.footprint_geojson if fl else None,
            "building_footprint_geojson": b.footprint_geojson if b else None,
            "z_min": u.z_min,
            "z_max": u.z_max,
            "volume_cu_m": u.volume_cu_m,
            "floor_z_min": fl.z_min if fl else None,
            "floor_z_max": fl.z_max if fl else None,
            "building_top_z": (b.ground_elevation_m + b.total_height_m) if b else None,
            "building_bottom_z": (b.ground_elevation_m - b.basement_floors * 4.0) if b else None,
            "is_multi_floor": getattr(u, "is_multi_floor", False),
            "floor_span": getattr(u, "floor_span", None),
            "all_ulpins": [u.ulpin_3d]
        }

        for r_id in [
            "RULE-GEO-001", "RULE-GEO-002", "RULE-GEO-003",
            "RULE-HIER-003", "RULE-HIER-004", "RULE-HIER-005",
            "RULE-UNIT-001"
        ]:
            r = ValidationRuleRegistry.get_rule(r_id)
            if r:
                iss = r.evaluate(unit_ctx)
                if iss:
                    issues.append(iss)

        critical_errors = [i for i in issues if i.severity == RuleSeverity.ERROR]
        is_valid = len(critical_errors) == 0

        qs = CadastralQualityScorer.calculate_score(issues=issues)

        rep = EntityValidationReport(
            entity_id=str(u.id),
            entity_type="UNIT",
            entity_code=u.unit_number,
            is_valid=is_valid,
            issues=issues,
            quality_score=qs.total_score,
            quality_grade=qs.grade
        )

        if persist:
            record = ValidationRunRecord(
                validation_run_id=str(uuid.uuid4()),
                target_entity_type="UNIT",
                target_entity_id=str(u.id),
                engine_version="1.0.0-cadastral-validator",
                is_valid=is_valid,
                quality_score=qs.total_score,
                quality_grade=qs.grade.value,
                rules_executed=len(issues) + 4,
                rules_passed=4,
                rules_failed=len(issues),
                critical_issues_count=len(critical_errors),
                warnings_count=len(issues) - len(critical_errors),
                info_count=0,
                results=rep.model_dump(mode="json")
            )
            db.add(record)
            db.commit()

        return rep

    @classmethod
    def get_validation_report_by_run_id(cls, db: Session, run_id: str) -> Optional[Dict[str, Any]]:
        record = db.execute(
            select(ValidationRunRecord).where(ValidationRunRecord.validation_run_id == run_id)
        ).scalar_one_or_none()
        if not record:
            return None
        return record.results

    @classmethod
    def get_validation_history(cls, db: Session, entity_id: str, limit: int = 20) -> List[ValidationRunRecord]:
        return db.execute(
            select(ValidationRunRecord)
            .where(ValidationRunRecord.target_entity_id == entity_id)
            .order_by(ValidationRunRecord.created_at.desc())
            .limit(limit)
        ).scalars().all()

    @staticmethod
    def _generate_recommendations(
        issues: List[ValidationIssue],
        clashes: List[DetailedClashFinding]
    ) -> List[str]:
        recs = []
        if not issues and not clashes:
            recs.append("All deterministic validation rules passed. Spatial data meets high-confidence criteria.")
            return recs

        seen = set()
        for iss in issues:
            if iss.suggested_remediation and iss.suggested_remediation not in seen:
                recs.append(f"[{iss.rule_id}] {iss.suggested_remediation}")
                seen.add(iss.suggested_remediation)

        for c in clashes:
            if c.suggested_action and c.suggested_action not in seen:
                recs.append(f"[CLASH-{c.classification.value}] {c.suggested_action}")
                seen.add(c.suggested_action)

        return recs
