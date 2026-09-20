"""
Deterministic Cadastral Quality Scorer for SIH 26011.
Provides an explainable 0–100 data quality score across 6 audited dimensions:
- Geometry Validity (25 pts)
- CRS & Cartographic Projection (15 pts)
- Hierarchical Containment (20 pts)
- Vertical Strata Consistency (15 pts)
- 3D Topology & Clash Freedom (15 pts)
- Provenance & Attribute Completeness (10 pts)

Grades:
- 90–100: HIGH_CONFIDENCE
- 75–89:  GOOD_QUALITY
- 50–74:  REQUIRES_REVIEW
- 0–49:   INVALID_OR_INCOMPLETE

IMPORTANT DISCLAIMER:
This score is a technical, algorithmic data-quality indicator for SIH 26011 prototype testing.
It has no legal meaning and does not constitute government certification or title guarantee.
"""

from typing import List, Dict, Any
from app.schemas.validation import QualityScoreBreakdown, QualityGrade, ValidationIssue, RuleSeverity, RuleCategory


class CadastralQualityScorer:
    """Calculates explainable, deterministic data quality metrics."""

    @classmethod
    def calculate_score(
        cls,
        issues: List[ValidationIssue],
        has_crs_metadata: bool = True,
        has_ulpin: bool = True,
        has_survey_number: bool = True,
        has_spatial_metadata: bool = True
    ) -> QualityScoreBreakdown:
        deductions: List[Dict[str, Any]] = []

        # 1. Geometry Validity (25 pts max)
        geo_score = 25.0
        geo_errors = [i for i in issues if i.category == RuleCategory.GEOMETRY and i.severity == RuleSeverity.ERROR]
        geo_warnings = [i for i in issues if i.category == RuleCategory.GEOMETRY and i.severity == RuleSeverity.WARNING]
        if geo_errors:
            ded = min(25.0, len(geo_errors) * 12.5)
            geo_score -= ded
            deductions.append({
                "dimension": "Geometry Validity",
                "deduction": ded,
                "reason": f"{len(geo_errors)} critical geometry error(s) detected (e.g. self-intersections/unclosed rings)."
            })
        if geo_warnings and geo_score > 0:
            ded = min(geo_score, len(geo_warnings) * 3.0)
            geo_score -= ded
            deductions.append({
                "dimension": "Geometry Validity",
                "deduction": ded,
                "reason": f"{len(geo_warnings)} geometry warning(s) detected (e.g. normalization drift or MultiPolygon parts)."
            })

        # 2. CRS & Cartographic Projection (15 pts max)
        crs_score = 15.0
        if not has_crs_metadata:
            crs_score -= 8.0
            deductions.append({
                "dimension": "CRS / Projection",
                "deduction": 8.0,
                "reason": "Missing explicit coordinate reference system provenance (assumed default WGS84)."
            })

        # 3. Hierarchical Containment (20 pts max)
        hier_score = 20.0
        hier_errors = [i for i in issues if i.category == RuleCategory.HIERARCHY and i.severity == RuleSeverity.ERROR]
        hier_warnings = [i for i in issues if i.category == RuleCategory.HIERARCHY and i.severity == RuleSeverity.WARNING]
        if hier_errors:
            ded = min(20.0, len(hier_errors) * 10.0)
            hier_score -= ded
            deductions.append({
                "dimension": "Hierarchy",
                "deduction": ded,
                "reason": f"{len(hier_errors)} hierarchical containment violation(s) (boundary spills or orphaned entities)."
            })
        if hier_warnings and hier_score > 0:
            ded = min(hier_score, len(hier_warnings) * 2.5)
            hier_score -= ded
            deductions.append({
                "dimension": "Hierarchy",
                "deduction": ded,
                "reason": f"{len(hier_warnings)} hierarchical warning(s)."
            })

        # 4. Vertical Strata Consistency (15 pts max)
        strata_score = 15.0
        strata_errors = [i for i in issues if i.category == RuleCategory.FLOOR_STRATA and i.severity == RuleSeverity.ERROR]
        strata_warnings = [i for i in issues if i.category == RuleCategory.FLOOR_STRATA and i.severity == RuleSeverity.WARNING]
        if strata_errors:
            ded = min(15.0, len(strata_errors) * 7.5)
            strata_score -= ded
            deductions.append({
                "dimension": "Vertical Consistency",
                "deduction": ded,
                "reason": f"{len(strata_errors)} floor strata error(s) (overlapping floors, duplicate codes, or datum inversion)."
            })
        if strata_warnings and strata_score > 0:
            ded = min(strata_score, len(strata_warnings) * 2.0)
            strata_score -= ded
            deductions.append({
                "dimension": "Vertical Consistency",
                "deduction": ded,
                "reason": f"{len(strata_warnings)} floor strata warning(s) (unexplained vertical gaps or unusual floor heights)."
            })

        # 5. 3D Topology & Clash Freedom (15 pts max)
        topo_score = 15.0
        topo_errors = [i for i in issues if i.category == RuleCategory.TOPOLOGY_3D and i.severity == RuleSeverity.ERROR]
        topo_warnings = [i for i in issues if i.category == RuleCategory.TOPOLOGY_3D and i.severity == RuleSeverity.WARNING]
        if topo_errors:
            ded = min(15.0, len(topo_errors) * 7.5)
            topo_score -= ded
            deductions.append({
                "dimension": "3D Topology",
                "deduction": ded,
                "reason": f"{len(topo_errors)} critical 3D volumetric property collision(s) detected."
            })
        if topo_warnings and topo_score > 0:
            ded = min(topo_score, len(topo_warnings) * 2.0)
            topo_score -= ded
            deductions.append({
                "dimension": "3D Topology",
                "deduction": ded,
                "reason": f"{len(topo_warnings)} near-boundary or tolerance condition(s)."
            })

        # 6. Provenance & Attribute Completeness (10 pts max)
        prov_score = 10.0
        if not has_ulpin:
            prov_score -= 4.0
            deductions.append({
                "dimension": "Provenance",
                "deduction": 4.0,
                "reason": "Entity missing base or 3D ULPIN identifier."
            })
        if not has_survey_number:
            prov_score -= 3.0
            deductions.append({
                "dimension": "Provenance",
                "deduction": 3.0,
                "reason": "Entity missing revenue survey / subdivision number."
            })
        if not has_spatial_metadata:
            prov_score -= 3.0
            deductions.append({
                "dimension": "Provenance",
                "deduction": 3.0,
                "reason": "Missing capture methodology or provenance metadata dictionary."
            })

        # Ensure non-negative bounds
        geo_score = round(max(0.0, min(25.0, geo_score)), 1)
        crs_score = round(max(0.0, min(15.0, crs_score)), 1)
        hier_score = round(max(0.0, min(20.0, hier_score)), 1)
        strata_score = round(max(0.0, min(15.0, strata_score)), 1)
        topo_score = round(max(0.0, min(15.0, topo_score)), 1)
        prov_score = round(max(0.0, min(10.0, prov_score)), 1)

        total = round(geo_score + crs_score + hier_score + strata_score + topo_score + prov_score, 1)

        # Neutral Grade mapping
        if total >= 90.0:
            grade = QualityGrade.HIGH_CONFIDENCE
        elif total >= 75.0:
            grade = QualityGrade.GOOD_QUALITY
        elif total >= 50.0:
            grade = QualityGrade.REQUIRES_REVIEW
        else:
            grade = QualityGrade.INVALID_OR_INCOMPLETE

        return QualityScoreBreakdown(
            geometry_validity=geo_score,
            crs_projection=crs_score,
            hierarchy_containment=hier_score,
            vertical_strata_consistency=strata_score,
            topology_3d_clash_freedom=topo_score,
            provenance_completeness=prov_score,
            total_score=total,
            grade=grade,
            deductions=deductions
        )
