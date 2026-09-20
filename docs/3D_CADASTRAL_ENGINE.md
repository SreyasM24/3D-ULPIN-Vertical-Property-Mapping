# Core 3D Cadastral Engine Specification (SIH 26011)

## 1. Executive Overview

This document specifies the core design, spatial relationship hierarchy, volumetric modeling, and querying engine for the **3D ULPIN and Vertical Property Mapping System** (Smart India Hackathon 26011).

The engine extends traditional 2D surface cadastre (Bhu-Aadhaar) into a rigorous **Volumetric Cadastre Framework** capable of managing subterranean basements, ground-level parcels, elevated high-rise towers, multi-tier parking ramps, and vertical infrastructure corridors.

> **Prototype Specification Notice**: The 3D ULPIN structure (`<BASE_ULPIN>-<LEVEL>-<UNIT>-<CHECKSUM>`) and extruded GeoJSON extensions implemented in this repository represent a project-level prototype engineering solution for SIH 26011. They are not an official Government of India standard.

---

## 2. 3D Cadastral Spatial Hierarchy

The system establishes a strict, auditable topological containment hierarchy:

```
LandParcel (2D Surface Cadastral Boundary, Base ULPIN, WGS84 & Projected UTM Metrics)
  └── Building / Structure (Envelope Bounding Footprint, Total Height, Ground Datum)
        └── FloorLevel (Vertical Elevation Slice: Z-min, Z-max, Height, Level Code)
              └── VerticalPropertyUnit (3D Unit: Volume m³, Area m², 3D ULPIN, Type)
                    └── OwnershipRecord (RoR, SHA-256 Hashed Identifier, Share %)
```

### 2.1 Cadastral Entity Classes
- **`LandParcel`**: The foundational 2D surface cadastre polygon. Holds the 14-character base ULPIN, datum elevation, and projected UTM area ($m^2$).
- **`Building`**: Physical vertical envelope situated on a parcel. Validated to ensure its projected footprint is contained within the parcel boundary.
- **`FloorLevel`**: A horizontal elevation slice ($Z_{min}$ to $Z_{max}$) representing basements, ground floor, podiums, typical residential floors, service floors, or terraces.
- **`VerticalUnit`**: The basic legal unit of 3D property rights (Apartment, Commercial Shop, Office, Parking Bay, Utility Corridor, Subway/Tunnel, or Elevated Walkway).

---

## 3. Volumetric Geometry & Abstraction (`app/core/spatial_volume.py`)

### 3.1 SpatialVolume Abstraction
To avoid binding the architecture exclusively to simple 2D extrusion, the system introduces the `SpatialVolume` abstract base class:

- **`SpatialVolume` (Abstract)**:
  - `z_min`, `z_max`, `height_m`
  - `area_sqm`, `volume_cu_m`
  - `projected_crs`
  - `vertical_classification`
  - `contains_point_3d(lon, lat, z)`
  - `intersects_bbox_3d(min_lon, min_lat, min_z, max_lon, max_lat, max_z)`

- **`PrismVolume` (MVP Standard)**:
  - Models an orthogonal extruded volumetric prism bounded by a normalized 2D footprint polygon and vertical bounds $[Z_{min}, Z_{max}]$.
  - Uses projected Cartesian coordinates (UTM) to guarantee:
    $$\text{Volume } (m^3) = \text{Area}_{projected} (m^2) \times (Z_{max} - Z_{min})$$

- **`PolyhedralMeshVolume` (Extensibility Hook)**:
  - Designed for future LoD2/LoD3 models featuring arbitrary non-vertical walls, sloped roofs, and complex polyhedral boundaries.

### 3.2 Vertical Classification
Every volumetric entity is classified relative to the building's ground elevation datum:
- **`UNDERGROUND`**: $Z_{max} \le \text{ground\_elevation} + 0.5m$ (e.g. basements, subterranean parking).
- **`GROUND_LEVEL`**: Straddles ground elevation datum.
- **`ELEVATED`**: $Z_{min} \ge \text{ground\_elevation} - 0.5m$ (e.g. podiums, typical floors).
- **`MULTI_LEVEL_INFRASTRUCTURE`**: Height spans multiple floor tiers (e.g. multi-story parking ramps, vertical utility shafts, atriums).

---

## 4. Floor Engine & Building Volumetric Modeling (`app/services/floor_engine.py`)

### 4.1 Floor Validation Rules
Each building enforces vertical strata consistency across all registered floors:
1. **Vertical Interval Validity**: $Z_{max} > Z_{min}$ and $\text{floor\_height\_m} = Z_{max} - Z_{min}$.
2. **Building Envelope Adherence**: Topmost floor cannot exceed the permitted building height ($\text{ground\_elevation} + \text{total\_height}$).
3. **No Overlapping Floors**: Two floors within the same building cannot overlap vertically:
   $$\Delta Z = \min(Z_{max}^{F1}, Z_{max}^{F2}) - \max(Z_{min}^{F1}, Z_{min}^{F2}) \le 0.05m$$
4. **Basement Elevation Rules**: Levels labeled with negative indices or codes starting with `B` must not extend above the ground reference datum.
5. **Elevated Elevation Rules**: Levels labeled with positive indices or codes starting with `L` must not drop below the ground reference datum.
6. **Non-Uniform Heights**: Supports mixed floor heights (e.g. 4.5m ground lobby, 3.0m typical residential, 2.4m service floor).

---

## 5. Hierarchical Spatial Relationship Engine (`app/services/cadastral_relationship_engine.py`)

Rather than relying on naive boolean flags, spatial relationships are audited through structured `SpatialRelationshipResult` objects:

| Relationship | Geometric Criteria | Vertical Criteria |
|---|---|---|
| **Parcel contains Building** | $\text{Building}_{UTM} \subseteq \text{Parcel}_{UTM}$ | N/A (Surface envelope) |
| **Building contains Floor** | $\text{Floor}_{UTM} \subseteq \text{Building}_{UTM}$ | $Z_{min}^{Floor} \ge Z_{bottom}^{Bld}$ and $Z_{max}^{Floor} \le Z_{top}^{Bld}$ |
| **Floor contains Unit** | $\text{Unit}_{UTM} \subseteq \text{Floor}_{UTM}$ | $Z_{min}^{Unit} \ge Z_{min}^{Floor}$ and $Z_{max}^{Unit} \le Z_{max}^{Floor}$ |
| **Building contains Unit** | $\text{Unit}_{UTM} \subseteq \text{Building}_{UTM}$ | $Z_{min}^{Unit} \ge Z_{bottom}^{Bld}$ and $Z_{max}^{Unit} \le Z_{top}^{Bld}$ |
| **Parcel contains Unit** | $\text{Unit}_{UTM} \subseteq \text{Parcel}_{UTM}$ | N/A (Ground footprint containment) |

### 5.1 Multi-Floor Unit Support
Legitimate multi-tier property structures—such as duplex penthouses, parking ramps, and vertical elevator/utility shafts—are recognized with the `MULTI_FLOOR_SPAN` status rather than being erroneously rejected.

---

## 6. Cadastral Digital Twin & 3D View Data

### 6.1 Single-Request Aggregation
The frontend visualizer can retrieve an entire property stack in a single API call:
- `GET /api/v1/parcels/{parcel_id}/digital-twin`:
  Returns the complete hierarchy (Parcel $\rightarrow$ Buildings $\rightarrow$ Floors $\rightarrow$ Units $\rightarrow$ Ownership $\rightarrow$ Validation Summary).

### 6.2 Multi-Layer 3D GeoJSON Export
- `GET /api/v1/parcels/{parcel_id}/digital-twin/geojson3d`:
  Outputs an RFC 7946 FeatureCollection tagged by layer:
  - `PARCEL`: Surface cadastral boundary.
  - `BUILDING`: Building envelope footprint with extrusion metadata.
  - `FLOOR`: Floor elevation slices.
  - `UNIT`: 3D vertical units with carpet area ($m^2$), volume ($m^3$), 3D ULPIN, and vertical classification.

---

## 7. Advanced 3D Spatial Queries

The query API (`GET /api/v1/units/` and `GET /api/v1/units/spatial-query`) enables 3D GIS filtering:
- **Elevation $Z$ Intersection**: `?elevation_z=561.5` returns all units that intersect a specific height above sea level.
- **Vertical Strata**: `?vertical_classification=UNDERGROUND` retrieves all basement/subterranean units.
- **3D Bounding Box**: `?min_lon=...&min_lat=...&min_z=...&max_lon=...&max_lat=...&max_z=...` performs volumetric box intersection.
- **Validation Filtering**: `?has_clashes=true` isolates units with detected 3D spatial collisions.

---

## 8. Current Limitations & Roadmap

1. **Polyhedral Solid Geometry**: The MVP calculates volume via projected Cartesian prism extrusions. Full 3D constructive solid geometry (CSG) for complex non-orthogonal meshes will require integrating a C-level 3D mesh kernel (e.g. CGAL/Trimesh) in future phases.
2. **PostGIS Migration**: Models are prepared for GeoAlchemy2 / PostGIS 3D (`POLYGON Z` / `POLYHEDRALSURFACE`) when scaling beyond SQLite.
