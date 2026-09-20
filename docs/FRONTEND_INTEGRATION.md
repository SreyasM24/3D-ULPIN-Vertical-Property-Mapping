# Frontend Integration Guide
## 3D ULPIN & Vertical Property Mapping System (SIH 26011)

This guide documents the API contracts, data models, asynchronous polling patterns, and 3D visualization guidelines for frontend developers integrating with the backend.

---

## 1. General Principles & Base Configuration

- **Default Base URL**: `http://localhost:8000` (Local Development)
- **API Prefix**: `/api/v1`
- **Swagger Documentation**: `http://localhost:8000/docs`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`
- **Authentication**: In this prototype, endpoints are open. Bearer token headers (`Authorization: Bearer <token>`) are supported and forwarded.
- **Traceability**: Every request is assigned a unique `X-Request-ID` header. If provided by the client, it is preserved; otherwise, the server generates a UUIDv4.

---

## 2. Standard API Response Formats

### 2.1 Success Response Envelope (`APIResponse<T>`)
Every successful API endpoint returns JSON wrapped in this envelope:

```typescript
interface APIResponse<T> {
  success: boolean;       // Always true for 2xx responses
  data: T;                // Typed payload
  error: null;            // Always null on success
}
```

### 2.2 Error Response Envelope (`APIErrorResponse`)
All errors (4xx and 5xx) return a standardized error envelope:

```typescript
interface APIErrorResponse {
  success: false;
  data: null;
  error: {
    code: string;         // e.g. "ENTITY_NOT_FOUND", "SPATIAL_CLASH", "VALIDATION_ERROR"
    message: string;      // Human-readable, safe error message
    details: any;         // Specific error metadata (e.g. clash list, invalid field list)
    request_id?: string;  // Correlation ID for support and logging
  };
}
```

---

## 3. Endpoints Overview

| Area | Method | Endpoint | Description |
|------|--------|----------|-------------|
| **System Probes** | `GET` | `/health` | Liveness check (200 OK) |
| | `GET` | `/readiness` | Readiness & DB connectivity check (200 or 503) |
| | `GET` | `/api/v1/capabilities` | System capabilities disclosure |
| **Async Jobs** | `POST` | `/api/v1/jobs/process-parcel` | Convenience end-to-end parcel processing |
| | `POST` | `/api/v1/jobs/ingest-survey` | Ingest raw survey / point cloud data |
| | `GET` | `/api/v1/jobs/{job_id}` | Poll job status, progress, stage events, and results |
| | `POST` | `/api/v1/jobs/{job_id}/cancel`| Cancel an active job |
| | `GET` | `/api/v1/jobs/` | List jobs with pagination and status filters |
| **2D Parcels** | `GET` | `/api/v1/parcels/` | List parcels |
| | `POST` | `/api/v1/parcels/` | Register 2D land parcel (generates 2D ULPIN) |
| | `GET` | `/api/v1/parcels/{id}` | Retrieve parcel details by ID or ULPIN |
| **Buildings** | `GET` | `/api/v1/buildings/` | List buildings (filterable by parcel_id) |
| | `POST` | `/api/v1/buildings/` | Register building structure |
| | `GET` | `/api/v1/buildings/{id}` | Retrieve building details |
| **Floors** | `GET` | `/api/v1/floors/` | List floor levels (filterable by building_id) |
| | `POST` | `/api/v1/floors/` | Register floor level |
| **Vertical Units** | `GET` | `/api/v1/units/` | List 3D units (filterable by floor_id, building_id) |
| | `POST` | `/api/v1/units/` | Register unit (generates 3D ULPIN, checks clashes) |
| | `GET` | `/api/v1/units/{id}` | Retrieve 3D unit details |
| **Cadastral Audit**| `GET` | `/api/v1/validation/parcel/{id}` | Execute & retrieve deterministic validation report |
| | `GET` | `/api/v1/validation/history` | List historical validation audit runs |
| **3D Digital Twin**| `GET` | `/api/v1/spatial/digital-twin/{id}` | Retrieve complete 3D digital twin & GeoJSON 3D |
| | `GET` | `/api/v1/spatial/clashes/building/{id}`| Audit 3D volumetric clashes across all units |

---

## 4. Asynchronous Job Polling Contract

When initiating long-running workflows (survey ingestion, ML extraction, cadastral reconstruction), the frontend receives an immediate HTTP `202 Accepted` response with a `job_id`.

### Recommended Polling Pattern
1. **Poll Interval**: 1.0 to 2.0 seconds.
2. **Terminal States**:
   - `COMPLETED`: Stop polling. The `result_reference` field contains IDs, ULPINs, quality score, and digital twin summary.
   - `FAILED`: Stop polling. Display `error_message` and inform the user.
   - `CANCELLED`: Stop polling.
3. **Stage Transitions**: Display `current_stage` and `progress_percent` in a UI stepper or progress bar:
   - `QUEUED` (0%)
   - `INSPECTION` (15%)
   - `PREPROCESSING` (30%)
   - `FEATURE_EXTRACTION` (45%)
   - `CADASTRAL_CONSTRUCTION` (65%)
   - `ULPIN_GENERATION` (75%)
   - `VALIDATION` (85%)
   - `DIGITAL_TWIN_UPDATE` (95%)
   - `COMPLETED` (100%)

---

## 5. 3D Visualization & Coordinate Guidelines

For integration with **CesiumJS**, **Three.js**, **MapLibre GL**, or **deck.gl**:

1. **Horizontal Coordinates**: WGS84 GeoJSON `[longitude, latitude]` (`EPSG:4326`).
2. **Vertical Coordinates**: Z-values (`z_min`, `z_max`) represent elevation in meters above Mean Sea Level (MSL).
3. **Extrusion**:
   - Building Footprint: Extrude from `ground_elevation_m` to `ground_elevation_m + total_height_m`.
   - Floor Slices: Extrude each floor from its `z_min` to `z_max`.
   - Vertical Units: Extrude unit polygon from `z_min` to `z_max`.
4. **Special Unit Types**:
   - `COMMON_AREA`: Render in neutral translucent grey/blue to indicate shared spaces.
   - `is_multi_floor = true`: Unit spans multiple vertical strata; render as a single volumetric prism across its full elevation range `[z_min, z_max]`.
   - `PARKING` / `BASEMENT`: Units with negative floor levels or $Z < \text{ground\_elevation}$ should be rendered in subterranean view modes.

---

## 6. TypeScript Types

Complete, strongly typed TypeScript definitions mirroring backend Pydantic models are provided in [docs/frontend-types.ts](frontend-types.ts).
