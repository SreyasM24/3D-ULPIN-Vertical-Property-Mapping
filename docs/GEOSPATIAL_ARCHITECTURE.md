# Geospatial Architecture & Normalization Layer (SIH 26011)

## 1. Executive Summary

This document specifies the technical architecture of the **Geospatial Data and Normalization Layer** for the **3D ULPIN and Vertical Property Mapping System** (Smart India Hackathon 26011).

Traditional 2D land administration relies on geographic surface representations (such as Bhu-Aadhaar 14-digit ULPIN). To support multi-tier urban environments—including high-rise towers, multi-tier basements, underground utilities, and vertical sub-parcels—spatial operations must operate with strict cartographic precision and unambiguous 3D volumetric boundaries.

---

## 2. Coordinate Reference System (CRS) Handling

### 2.1 Geographic vs. Projected Coordinate Systems
A critical design requirement is that **no metric calculations (area in $m^2$, perimeter in $m$, distance, or volume in $m^3$) may ever be calculated directly from geographic coordinates (degrees of longitude and latitude)**.

- **Storage & Ingestion CRS**: `EPSG:4326` (WGS84 Geographic 2D/3D). All external GeoJSON APIs and user payloads accept and return WGS84 coordinates `[longitude, latitude, elevation]`.
- **Computation / Metric Projected CRS**: Dynamic local **Universal Transverse Mercator (UTM)** projection determined from the parcel or unit centroid:
  $$\text{UTM Zone} = \left\lfloor \frac{\text{longitude} + 180}{6} \right\rfloor + 1$$
  $$\text{EPSG Code} = \begin{cases} 32600 + \text{zone}, & \text{if latitude} \ge 0 \\ 32700 + \text{zone}, & \text{if latitude} < 0 \end{cases}$$
  *Example*: Pune, Maharashtra coordinates $(73.856^\circ\text{ E}, 18.520^\circ\text{ N})$ map dynamically to **EPSG:32643** (UTM Zone 43N).

### 2.2 Geodesic Transformations
All transformations are implemented in `app/core/crs.py` using `pyproj.Transformer` with `always_xy=True` to eliminate axis order ambiguity:
```python
transformer = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
projected_geom = shapely.ops.transform(transformer.transform, wgs84_geom)
```

---

## 3. Geometry Lifecycle & Normalization Pipeline

Raw cadastral inputs from CAD conversions, digitizers, and legacy shapefiles frequently suffer from minor topological flaws. `GeometryNormalizationService` (`app/services/geometry_normalization.py`) processes all incoming geometries through a deterministic 5-stage pipeline:

```
+--------------------------------------------------------------------------------+
|                             Raw Geometry Input                                 |
|                       (GeoJSON / Shapefile / Ingestion)                        |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
| Stage 1: Coordinate Validation & Snapping                                      |
| - WGS84 coordinate range checks (-180..180 lon, -90..90 lat)                   |
| - Precision snapping to 7 decimal places (~1.1 cm resolution)                  |
| - Consecutive sub-tolerance duplicate vertex removal                           |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
| Stage 2: Ring Closure Enforcement                                              |
| - Tests if ring[0] == ring[-1]; if open, appends first vertex                  |
| - Records "RING_CLOSED" repair note in provenance trail                        |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
| Stage 3: MultiPolygon & Part Decomposition                                     |
| - Validates single-part vs. multi-part geometries                              |
| - Flattens single-part MultiPolygons when required                             |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
| Stage 4: Topological Healing (OGC SFA Compliance)                             |
| - Detects bowties, self-intersections, and spikes                              |
| - Safely applies shapely.make_valid() without semantic distortion              |
| - REJECTS repair if area changes by > 5%, preventing boundary alteration       |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
| Stage 5: Orientation Enforcement (RFC 7946 Right-Hand Rule)                    |
| - Exterior boundaries oriented Counter-Clockwise (CCW)                         |
| - Interior rings (holes/cutouts) oriented Clockwise (CW)                       |
+---------------------------------------+----------------------------------------+
                                        |
                                        v
+--------------------------------------------------------------------------------+
|                       Audit & Metric Calculation Output                        |
| - NormalizationResult (geometry, was_repaired, repair_actions)                 |
| - Projected spatial metrics (area m², perimeter m, bbox, projected CRS)        |
+--------------------------------------------------------------------------------+
```

---

## 4. 2D to 3D Volumetric Representation

### 4.1 Volumetric Prism (MVP Specification)
For the MVP stage, 3D vertical units are represented as extruded volumetric prisms:
- **Horizontal Geometry**: 2D normalized footprint polygon ($F$).
- **Vertical Extent**:
  - $Z_{min}$: Bottom elevation (meters above MSL / Datum).
  - $Z_{max}$: Top elevation (meters above MSL / Datum).
- **Derived Height ($h$)**:
  $$h = Z_{max} - Z_{min} \quad (\text{meters})$$
- **Derived Volume ($V$)**:
  $$V = \text{Area}_{projected}(F) \times h \quad (\text{cubic meters, } m^3)$$

### 4.2 Extensibility to Arbitrary 3D Polyhedrons
The spatial engine models 3D units using the `VolumetricPrism` dataclass (`app/services/spatial_engine.py`) with a `representation_type` discriminator:
- `"EXTRUDED_PRISM_LOD1"`: Current MVP footprint extrusion.
- `"POLYHEDRAL_MESH_LOD2"`: Planned support for non-vertical walls, mansard roofs, and complex subterranean utility vaults without changing external REST API contracts.

### 4.3 GeoJSON Standards Disclaimer
Standard RFC 7946 GeoJSON supports 3D coordinate positions `[longitude, latitude, altitude]`. However, RFC 7946 is **not a formal 3D volumetric cadastre standard** (such as ISO 19152 LADM 3D or OGC CityGML).
In this project:
- Boundary footprints are serialized as RFC 7946 GeoJSON.
- 3D cadastral metadata ($Z_{min}$, $Z_{max}$, $h$, $V$, 3D ULPIN) is stored in the GeoJSON `properties` envelope.

---

## 5. Building Containment Evaluation

When validating building footprints against parent cadastral parcels (`evaluate_building_containment`):
1. Both building and parcel geometries are projected to the parcel's local UTM CRS.
2. The intersection and difference are computed in metric Cartesian space:
   $$\text{Excess Area} = \text{Area}(\text{Building}_{UTM} \setminus \text{Parcel}_{UTM})$$
3. A structured status is returned:
   - `CONTAINED`: Excess area $\le 0.05 m^2$.
   - `PARTIALLY_OUTSIDE`: Excess area $> 0.05 m^2$ and intersection area $> 0.05 m^2$.
   - `COMPLETELY_OUTSIDE`: Intersection area $= 0 m^2$.
   - `INVALID_GEOMETRY`: One or both inputs fail topological validation.

---

## 6. Dataset Ingestion & Provenance Framework

The ingestion subsystem (`app/services/ingestion/`) implements an adapter pattern with full provenance auditing:

### 6.1 Supported Formats
| Source Type | Implementation Status | Adapter Class | Description |
|---|---|---|---|
| **GeoJSON** | Fully Implemented | `GeoJSONIngestionAdapter` | FeatureCollections, Features, and Polygons with auto-repair and projected metrics |
| **ESRI Shapefile** | Fully Implemented | `ShapefileIngestionAdapter` | Zipped or directory-based `.shp`, `.shx`, `.dbf`, `.prj` parsing via `pyshp` |
| **LiDAR Point Clouds** | Metadata Model | `LiDARMetadataAdapter` | LAS/LAZ headers, point count, 3D bounding extents, vertical datums |
| **DEM/DSM Rasters** | Metadata Model | `DEMDSMMetadataAdapter` | GeoTIFF elevation rasters, pixel resolution, elevation min/max |
| **Drone Imagery** | Metadata Model | `DroneImageryMetadataAdapter` | Photogrammetric missions, GSD, flight altitude, RTK/CORS |
| **Floor Plans / BIM** | Metadata Model | `FloorPlanMetadataAdapter` | CAD/IFC drawings, scale, floor levels, datum elevation |

### 6.2 Provenance Audit Record
Every ingested asset records:
- `source_name`: Name or filename of the dataset.
- `source_type`: Recognized enum (`GEOJSON`, `SHAPEFILE`, etc.).
- `original_crs`: Coordinate reference system declared at source (e.g., `EPSG:4326`).
- `normalized_crs`: Standardized storage CRS (`EPSG:4326`).
- `source_file_hash`: SHA-256 cryptographic digest of the ingested binary/string.
- `ingestion_timestamp`: UTC timestamp of ingestion.
- `processing_status`: `COMPLETED`, `REPAIRED`, `REJECTED`, or `METADATA_EXTRACTED`.
- `validation_status`: `VALID`, `WARNING`, or `INVALID`.
- `normalization_notes`: Detailed list of every repair applied (e.g., `RING_CLOSED`, `DUPLICATE_VERTICES_REMOVED`, `ORIENTATION_NORMALIZED`).

---

## 7. Current Limitations & PostGIS Migration Path

1. **Local SQLite Architecture**: The current implementation runs on SQLite with zero external dependencies, executing geometry operations via Shapely 2.x and PyProj.
2. **PostGIS Migration Path**:
   - The ORM models (`app/models/`) store GeoJSON dictionaries in generic `JSON` columns.
   - To migrate to PostGIS in production:
     1. Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/cadastre_3d` in `.env`.
     2. Update column definitions to use GeoAlchemy2 `Geometry('POLYGON', srid=4326)`.
     3. The existing service layer (`spatial_engine.py`, `geometry_normalization.py`) remains 100% compatible.
3. **Heavy Ingestion Pipelines**: Raw point cloud filtering (PDAL) and photogrammetry meshing (OpenDroneMap) should be dispatched to asynchronous Celery/Redis workers in subsequent development phases.
