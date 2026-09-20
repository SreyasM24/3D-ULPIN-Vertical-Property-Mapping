"""
Cadastral GeoJSON & 3D GeoJSON Serialization Layer.

Standardizes serialization of Parcels, Buildings, and 3D Vertical Units
into RFC 7946 GeoJSON and extended 3D FeatureCollections.

NOTE ON STANDARDS:
Standard RFC 7946 GeoJSON defines 2D/3D coordinate positions [x, y, z] and features.
It is NOT an official volumetric cadastre standard (such as ISO 19152 LADM 3D or CityGML).
This project extends GeoJSON with property-based vertical boundaries (z_min, z_max, height_m, volume_cu_m)
and 3D ULPIN identifiers as a pragmatic prototype for web visualizers (Cesium, Three.js, Mapbox).
"""

from typing import Dict, Any, List, Optional
from app.models.parcel import LandParcel
from app.models.building import Building
from app.models.unit import VerticalUnit


class CadastralGeoJSONSerializer:
    @staticmethod
    def serialize_parcel(parcel: LandParcel) -> Dict[str, Any]:
        """Serializes LandParcel into a 2D GeoJSON Feature with cadastral properties."""
        return {
            "type": "Feature",
            "id": str(parcel.id),
            "geometry": parcel.geometry_geojson,
            "properties": {
                "ulpin": parcel.ulpin,
                "layer": "PARCEL",
                "entity_type": "LAND_PARCEL",
                "survey_number": parcel.survey_number,
                "subdivision_number": parcel.subdivision_number,
                "state_code": parcel.state_code,
                "district_code": parcel.district_code,
                "village_code": parcel.village_code,
                "area_sqm": parcel.area_sqm,
                "centroid": [parcel.centroid_lon, parcel.centroid_lat],
                "base_elevation_m": parcel.base_elevation_m,
                "status": parcel.status,
                "spatial_metadata": parcel.spatial_metadata or {},
                "crs": "EPSG:4326"
            }
        }

    @staticmethod
    def serialize_building(building: Building) -> Dict[str, Any]:
        """Serializes Building structure into a GeoJSON Feature with vertical envelope properties."""
        return {
            "type": "Feature",
            "id": str(building.id),
            "geometry": building.footprint_geojson,
            "properties": {
                "building_code": building.building_code,
                "building_name": building.building_name,
                "layer": "BUILDING",
                "entity_type": "BUILDING",
                "parcel_id": str(building.parcel_id),
                "rera_number": building.rera_number,
                "structure_type": building.structure_type,
                "floors_above_ground": building.floors_above_ground,
                "basement_floors": building.basement_floors,
                "total_height_m": building.total_height_m,
                "ground_elevation_m": building.ground_elevation_m,
                "top_elevation_m": round(building.ground_elevation_m + building.total_height_m, 2),
                "status": building.status,
                "spatial_metadata": building.spatial_metadata or {},
                "crs": "EPSG:4326"
            }
        }

    @staticmethod
    def serialize_vertical_unit_3d(unit: VerticalUnit) -> Dict[str, Any]:
        """
        Serializes 3D Vertical Property Unit into an extended 3D GeoJSON Feature.
        Properties carry volumetric metrics (volume_cu_m, z_min, z_max, height_m, ulpin_3d).
        """
        return {
            "type": "Feature",
            "id": str(unit.id),
            "geometry": unit.footprint_geojson,
            "properties": {
                "ulpin_3d": unit.ulpin_3d,
                "ulpin_status": unit.ulpin_status,
                "layer": "UNIT",
                "entity_type": "3D_VERTICAL_UNIT",
                "unit_number": unit.unit_number,
                "unit_code": unit.unit_code,
                "unit_type": unit.unit_type,
                "floor_id": str(unit.floor_id),
                "z_min": unit.z_min,
                "z_max": unit.z_max,
                "height_m": round(unit.z_max - unit.z_min, 3),
                "carpet_area_sqm": unit.carpet_area_sqm,
                "builtup_area_sqm": unit.builtup_area_sqm,
                "volume_cu_m": unit.volume_cu_m,
                "is_clash_free": unit.is_clash_free,
                "status": unit.status,
                "crs": "EPSG:4326",
                "representation_standard": "SIH_26011_EXTRUDED_3D_GEOJSON_PROTOTYPE"
            }
        }

    @classmethod
    def serialize_digital_twin_3d(cls, digital_twin: Any) -> Dict[str, Any]:
        """
        Serializes a full CadastralDigitalTwin into a multi-layered 3D FeatureCollection.
        Includes Parcel boundary, Building footprints, Floor slices, and 3D Units.
        """
        features: List[Dict[str, Any]] = []

        # 1. Parcel feature
        p = digital_twin.parcel if hasattr(digital_twin, "parcel") else digital_twin["parcel"]
        features.append({
            "type": "Feature",
            "id": str(p.id if hasattr(p, "id") else p["id"]),
            "geometry": p.geometry_geojson if hasattr(p, "geometry_geojson") else p["geometry_geojson"],
            "properties": {
                "layer": "PARCEL",
                "ulpin": p.ulpin if hasattr(p, "ulpin") else p["ulpin"],
                "area_sqm": p.area_sqm if hasattr(p, "area_sqm") else p["area_sqm"],
                "base_elevation_m": p.base_elevation_m if hasattr(p, "base_elevation_m") else p["base_elevation_m"],
            }
        })

        # 2. Building and child features
        buildings = p.buildings if hasattr(p, "buildings") else p.get("buildings", [])
        for b in buildings:
            b_id = str(b.id if hasattr(b, "id") else b["id"])
            b_geom = b.footprint_geojson if hasattr(b, "footprint_geojson") else b["footprint_geojson"]
            b_ground = b.ground_elevation_m if hasattr(b, "ground_elevation_m") else b["ground_elevation_m"]
            b_height = b.total_height_m if hasattr(b, "total_height_m") else b["total_height_m"]

            features.append({
                "type": "Feature",
                "id": b_id,
                "geometry": b_geom,
                "properties": {
                    "layer": "BUILDING",
                    "building_code": b.building_code if hasattr(b, "building_code") else b["building_code"],
                    "ground_elevation_m": b_ground,
                    "total_height_m": b_height,
                    "z_min": b_ground,
                    "z_max": round(b_ground + b_height, 2),
                    "volume_cu_m": b.volume_cu_m if hasattr(b, "volume_cu_m") else b.get("volume_cu_m", 0.0),
                }
            })

            floors = b.floors if hasattr(b, "floors") else b.get("floors", [])
            for fl in floors:
                fl_id = str(fl.id if hasattr(fl, "id") else fl["id"])
                fl_z_min = fl.z_min if hasattr(fl, "z_min") else fl["z_min"]
                fl_z_max = fl.z_max if hasattr(fl, "z_max") else fl["z_max"]
                fl_height = fl.floor_height_m if hasattr(fl, "floor_height_m") else fl["floor_height_m"]
                fl_code = fl.level_code if hasattr(fl, "level_code") else fl["level_code"]

                features.append({
                    "type": "Feature",
                    "id": fl_id,
                    "geometry": b_geom,  # Floor footprint defaults to building footprint
                    "properties": {
                        "layer": "FLOOR",
                        "level_code": fl_code,
                        "building_id": b_id,
                        "z_min": fl_z_min,
                        "z_max": fl_z_max,
                        "height_m": fl_height
                    }
                })

                units = fl.units if hasattr(fl, "units") else fl.get("units", [])
                for u in units:
                    u_id = str(u.id if hasattr(u, "id") else u["id"])
                    u_geom = u.footprint_geojson if hasattr(u, "footprint_geojson") else u["footprint_geojson"]
                    features.append({
                        "type": "Feature",
                        "id": u_id,
                        "geometry": u_geom,
                        "properties": {
                            "layer": "UNIT",
                            "ulpin_3d": u.ulpin_3d if hasattr(u, "ulpin_3d") else u["ulpin_3d"],
                            "unit_number": u.unit_number if hasattr(u, "unit_number") else u["unit_number"],
                            "unit_code": u.unit_code if hasattr(u, "unit_code") else u["unit_code"],
                            "unit_type": u.unit_type if hasattr(u, "unit_type") else u["unit_type"],
                            "vertical_classification": u.vertical_classification if hasattr(u, "vertical_classification") else u.get("vertical_classification", "ELEVATED"),
                            "floor_id": fl_id,
                            "building_id": b_id,
                            "z_min": u.z_min if hasattr(u, "z_min") else u["z_min"],
                            "z_max": u.z_max if hasattr(u, "z_max") else u["z_max"],
                            "height_m": u.height_m if hasattr(u, "height_m") else u["height_m"],
                            "carpet_area_sqm": u.carpet_area_sqm if hasattr(u, "carpet_area_sqm") else u["carpet_area_sqm"],
                            "volume_cu_m": u.volume_cu_m if hasattr(u, "volume_cu_m") else u["volume_cu_m"],
                            "is_clash_free": u.is_clash_free if hasattr(u, "is_clash_free") else u.get("is_clash_free", True),
                        }
                    })

        summary = digital_twin.summary if hasattr(digital_twin, "summary") else digital_twin.get("summary", {})
        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "crs": "EPSG:4326",
                "summary": summary.model_dump() if hasattr(summary, "model_dump") else summary
            }
        }

    @classmethod
    def to_feature_collection(
        cls,
        features: List[Dict[str, Any]],
        collection_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Wraps a list of GeoJSON features into a standard FeatureCollection."""
        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": collection_metadata or {}
        }
