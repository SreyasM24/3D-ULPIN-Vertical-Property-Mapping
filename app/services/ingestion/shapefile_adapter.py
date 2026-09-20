"""
ESRI Shapefile Ingestion Adapter.
Parses ESRI Shapefiles (zipped or multi-file: .shp, .shx, .dbf, .prj),
normalizes geometries, extracts attributes, and records provenance.
"""

import io
import os
import zipfile
import tempfile
from typing import Any, Dict, Optional, Union, List
import shapefile
from app.services.ingestion.base import BaseIngestionAdapter, compute_sha256_bytes, compute_sha256_str
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


class ShapefileIngestionAdapter(BaseIngestionAdapter):
    def __init__(self, source_name: str = "Shapefile Upload"):
        super().__init__(source_name=source_name, source_type=SourceType.SHAPEFILE)

    def ingest(
        self,
        content: Union[str, bytes],
        options: Optional[Dict[str, Any]] = None
    ) -> IngestionResult:
        """
        Ingests a Shapefile provided as:
        - bytes: Raw zip archive containing .shp, .dbf, .shx, .prj
        - str: File path to a .shp file or a .zip archive
        """
        options = options or {}
        source_crs = options.get("source_crs", "EPSG:4326")
        file_hash = None
        temp_dir_obj = None

        try:
            if isinstance(content, bytes):
                file_hash = compute_sha256_bytes(content)
                zip_buffer = io.BytesIO(content)
                if not zipfile.is_zipfile(zip_buffer):
                    raise ValueError("Binary shapefile upload must be a valid .zip archive containing .shp and .dbf files.")
                temp_dir_obj = tempfile.TemporaryDirectory()
                with zipfile.ZipFile(zip_buffer, "r") as z:
                    z.extractall(temp_dir_obj.name)
                
                shp_files = [f for f in os.listdir(temp_dir_obj.name) if f.lower().endswith(".shp")]
                if not shp_files:
                    raise ValueError("No .shp file found inside the uploaded zip archive.")
                shp_path = os.path.join(temp_dir_obj.name, shp_files[0])
                reader = shapefile.Reader(shp_path)
            elif isinstance(content, str):
                if not os.path.exists(content):
                    raise FileNotFoundError(f"Shapefile path not found: {content}")
                with open(content, "rb") as f:
                    file_hash = compute_sha256_bytes(f.read())
                reader = shapefile.Reader(content)
            else:
                raise ValueError(f"Unsupported content type for Shapefile: {type(content)}")

        except Exception as e:
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
                errors=[f"Failed to open Shapefile: {str(e)}"]
            )

        ingested_features: List[IngestedFeature] = []
        errors: List[str] = []
        all_repairs: List[str] = []
        was_any_repaired = False

        fields = [f[0] for f in reader.fields[1:]]  # Exclude deletion flag

        for idx, shape_rec in enumerate(reader.shapeRecords()):
            shp = shape_rec.shape
            record_dict = dict(zip(fields, shape_rec.record))
            source_id = str(record_dict.get("id", record_dict.get("ID", f"shp_{idx}")))

            # We are interested in Polygon / MultiPolygon cadastral shapes
            if shp.shapeTypeName not in ("POLYGON", "POLYGONZ", "POLYGONM"):
                errors.append(f"Record {source_id} is '{shp.shapeTypeName}', not a Polygon.")
                continue

            try:
                # Convert shape to GeoJSON geometry dict via __geo_interface__
                geojson_geom = shp.__geo_interface__

                # Normalize geometry
                norm_res = GeometryNormalizationService.normalize_geojson(geojson_geom)
                if norm_res.was_repaired:
                    was_any_repaired = True
                    all_repairs.extend([f"Record {source_id}: {r}" for r in norm_res.repair_actions])

                # Calculate projected metric properties
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
                        attributes=record_dict,
                        was_repaired=norm_res.was_repaired,
                        repair_actions=norm_res.repair_actions
                    )
                )
            except InvalidGeometryException as e:
                errors.append(f"Record {source_id} rejected: {str(e)}")
            except Exception as e:
                errors.append(f"Record {source_id} failed: {str(e)}")

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
            metadata_attributes={
                "shape_type": reader.shapeTypeName,
                "total_records_input": len(reader),
                "fields": fields
            }
        )

        result = IngestionResult(
            success=len(ingested_features) > 0,
            provenance=provenance,
            features=ingested_features,
            errors=errors
        )

        if temp_dir_obj:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass

        return result
