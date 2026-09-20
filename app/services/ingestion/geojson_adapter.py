"""
GeoJSON Ingestion Adapter.
Parses, normalizes, and calculates metric attributes for GeoJSON cadastral datasets.
"""

import json
from typing import Any, Dict, Optional, Union, List
from app.services.ingestion.base import BaseIngestionAdapter, compute_sha256_str, compute_sha256_bytes
from app.services.geometry_normalization import GeometryNormalizationService
from app.services.spatial_engine import compute_projected_spatial_metrics
from app.schemas.provenance import (
    IngestionResult,
    DatasetProvenance,
    IngestedFeature,
    SourceType,
    ProcessingStatus,
    ValidationStatus,
)
from app.core.exceptions import InvalidGeometryException
from app.core.logging import logger


class GeoJSONIngestionAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "GeoJSON Upload"):
        super().__init__(source_name=source_name, source_type=SourceType.GEOJSON)

    def ingest(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> IngestionResult:
        options = options or {}
        source_crs = options.get("source_crs", "EPSG:4326")

        # Compute hash
        if isinstance(content, bytes):
            file_hash = compute_sha256_bytes(content)
            raw_text = content.decode("utf-8")
            data = json.loads(raw_text)
        elif isinstance(content, str):
            file_hash = compute_sha256_str(content)
            data = json.loads(content)
        elif isinstance(content, dict):
            raw_json = json.dumps(content, sort_keys=True)
            file_hash = compute_sha256_str(raw_json)
            data = content
        else:
            raise ValueError(f"Unsupported content type for GeoJSON ingestion: {type(content)}")

        features_raw: List[Dict[str, Any]] = []
        doc_type = data.get("type", "")

        if doc_type == "FeatureCollection":
            features_raw = data.get("features", [])
        elif doc_type == "Feature":
            features_raw = [data]
        elif doc_type in ("Polygon", "MultiPolygon"):
            features_raw = [{"type": "Feature", "geometry": data, "properties": {}}]
        else:
            return IngestionResult(
                success=False,
                provenance=DatasetProvenance(
                    source_name=self.source_name,
                    source_type=self.source_type,
                    original_crs=source_crs,
                    processing_status=ProcessingStatus.REJECTED,
                    validation_status=ValidationStatus.INVALID,
                    source_file_hash=file_hash,
                ),
                errors=[f"Unsupported GeoJSON object type: '{doc_type}'"]
            )

        ingested_features: List[IngestedFeature] = []
        errors: List[str] = []
        all_repairs: List[str] = []
        was_any_repaired = False

        for idx, feat in enumerate(features_raw):
            geom_dict = feat.get("geometry")
            props = feat.get("properties") or {}
            source_id = str(feat.get("id", props.get("id", f"feat_{idx}")))

            if not geom_dict:
                errors.append(f"Feature at index {idx} has no geometry.")
                continue

            try:
                # 1. Normalize geometry
                norm_res = GeometryNormalizationService.normalize_geojson(geom_dict)
                if norm_res.was_repaired:
                    was_any_repaired = True
                    all_repairs.extend([f"Feature {source_id}: {r}" for r in norm_res.repair_actions])

                # 2. Compute projected spatial metrics in metric UTM
                metrics = compute_projected_spatial_metrics(norm_res.geojson)

                ingested_features.append(
                    IngestedFeature(
                        source_id=source_id,
                        geometry_geojson=norm_res.geojson,
                        area_sqm=metrics["area_sqm"],
                        perimeter_m=metrics["perimeter_m"],
                        centroid_lat=metrics["centroid_lat"],
                        centroid_lon=metrics["centroid_lon"],
                        bbox=metrics["bbox"],
                        projected_crs=metrics["projected_crs"],
                        attributes=props,
                        was_repaired=norm_res.was_repaired,
                        repair_actions=norm_res.repair_actions
                    )
                )
            except InvalidGeometryException as e:
                errors.append(f"Feature {source_id} rejected: {str(e)}")
            except Exception as e:
                errors.append(f"Feature {source_id} failed: {str(e)}")

        success = len(ingested_features) > 0 and len(errors) == 0
        proc_status = (
            ProcessingStatus.REPAIRED if was_any_repaired and len(errors) == 0
            else ProcessingStatus.COMPLETED if success
            else ProcessingStatus.REJECTED if len(ingested_features) == 0
            else ProcessingStatus.COMPLETED
        )
        val_status = (
            ValidationStatus.VALID if len(errors) == 0
            else ValidationStatus.WARNING if len(ingested_features) > 0
            else ValidationStatus.INVALID
        )

        provenance = DatasetProvenance(
            source_name=self.source_name,
            source_type=self.source_type,
            original_crs=source_crs,
            normalized_crs="EPSG:4326",
            processing_status=proc_status,
            validation_status=val_status,
            source_file_hash=file_hash,
            feature_count=len(ingested_features),
            normalization_notes=all_repairs,
            metadata_attributes={"total_features_input": len(features_raw), "rejected_count": len(errors)}
        )

        logger.info(
            f"GeoJSON Ingestion '{self.source_name}': {len(ingested_features)} features ingested, {len(errors)} errors."
        )

        return IngestionResult(
            success=len(ingested_features) > 0,
            provenance=provenance,
            features=ingested_features,
            errors=errors
        )
