/**
 * TypeScript Data Contracts for SIH 26011:
 * 3D ULPIN & Vertical Property Mapping System.
 *
 * Strictly mirrors backend Pydantic models.
 */

// -------------------------------------------------------------
// Common & Envelope Types
// -------------------------------------------------------------

export interface APIResponse<T> {
  success: boolean;
  data: T;
  error: null;
}

export interface APIErrorDetail {
  code: string;
  message: string;
  details?: any;
  request_id?: string;
}

export interface APIErrorResponse {
  success: false;
  data: null;
  error: APIErrorDetail;
}

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][]; // Array of linear rings: [ [ [lon, lat], ... ] ]
}

// -------------------------------------------------------------
// Cadastral Entity Models
// -------------------------------------------------------------

export interface LandParcel {
  id: string;
  ulpin: string;
  state_code: string;
  district_code: string;
  village_code: string;
  survey_number: string;
  subdivision_number?: string | null;
  area_sqm: number;
  centroid_lat: number;
  centroid_lon: number;
  base_elevation_m?: number | null;
  geometry_geojson: GeoJSONPolygon;
  spatial_metadata?: Record<string, any>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ParcelCreate {
  state_code: string;
  district_code: string;
  village_code: string;
  survey_number: string;
  subdivision_number?: string | null;
  base_elevation_m?: number | null;
  geometry_geojson: GeoJSONPolygon;
  spatial_metadata?: Record<string, any>;
}

export interface Building {
  id: string;
  parcel_id: string;
  building_name: string;
  building_code: string;
  structure_type: string;
  floors_above_ground: number;
  basement_floors: number;
  total_height_m: number;
  ground_elevation_m: number;
  footprint_geojson: GeoJSONPolygon;
  footprint_area_sqm: number;
  gross_volume_cu_m: number;
  is_within_parcel: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface BuildingCreate {
  parcel_id: string;
  building_name: string;
  building_code: string;
  structure_type?: string;
  floors_above_ground: number;
  basement_floors?: number;
  total_height_m: number;
  ground_elevation_m: number;
  footprint_geojson: GeoJSONPolygon;
}

export interface FloorLevel {
  id: string;
  building_id: string;
  level_number: number;
  level_code: string;
  level_type: "BASEMENT" | "GROUND" | "TYPICAL" | "MEZZANINE" | "TERRACE";
  z_min: number;
  z_max: number;
  height_m: number;
  footprint_geojson?: GeoJSONPolygon | null;
  gross_floor_area_sqm: number;
  gross_floor_volume_cu_m: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface FloorCreate {
  building_id: string;
  level_number: number;
  level_code: string;
  level_type?: string;
  z_min: number;
  z_max: number;
  footprint_geojson?: GeoJSONPolygon | null;
}

export interface VerticalUnit {
  id: string;
  floor_id: string;
  unit_number: string;
  unit_code: string;
  unit_type: "APARTMENT" | "COMMERCIAL" | "OFFICE" | "PARKING" | "COMMON_AREA" | "TERRACE" | "UTILITY";
  ulpin_3d: string;
  ulpin_status: string;
  footprint_geojson: GeoJSONPolygon;
  z_min: number;
  z_max: number;
  carpet_area_sqm: number;
  builtup_area_sqm?: number | null;
  volume_cu_m: number;
  is_clash_free: boolean;
  is_multi_floor: boolean;
  floor_span?: string[] | null;
  spatial_metadata?: Record<string, any>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface UnitCreate {
  floor_id: string;
  unit_number: string;
  unit_code: string;
  unit_type?: string;
  z_min: number;
  z_max: number;
  is_multi_floor?: boolean;
  floor_span?: string[] | null;
  builtup_area_sqm?: number | null;
  footprint_geojson: GeoJSONPolygon;
  spatial_metadata?: Record<string, any>;
}

// -------------------------------------------------------------
// Asynchronous Job & Processing Models
// -------------------------------------------------------------

export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type JobStage =
  | "QUEUED"
  | "INSPECTION"
  | "PREPROCESSING"
  | "FEATURE_EXTRACTION"
  | "CADASTRAL_CONSTRUCTION"
  | "ULPIN_GENERATION"
  | "VALIDATION"
  | "DIGITAL_TWIN_UPDATE"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface StageEvent {
  stage: string;
  timestamp: string;
  progress: number;
  message?: string;
  details?: Record<string, any>;
}

export interface JobRead {
  job_id: string;
  job_type: string;
  request_id?: string | null;
  status: JobStatus;
  current_stage: JobStage;
  progress_percent: number;
  entity_type?: string | null;
  entity_id?: string | null;
  source_filename?: string | null;
  stage_details?: {
    events?: StageEvent[];
    [key: string]: any;
  };
  result_reference?: Record<string, any> | null;
  error_message?: string | null;
  error_details?: Record<string, any> | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface JobListResponse {
  jobs: JobRead[];
  total: number;
  skip: number;
  limit: number;
}

// -------------------------------------------------------------
// Validation & Quality Models
// -------------------------------------------------------------

export type QualityGrade = "HIGH_CONFIDENCE" | "GOOD_QUALITY" | "REQUIRES_REVIEW" | "INVALID_OR_INCOMPLETE";

export interface QualityScoreBreakdown {
  geometry_validity: number;
  crs_projection: number;
  hierarchy_containment: number;
  vertical_strata_consistency: number;
  topology_3d_clash_freedom: number;
  provenance_completeness: number;
  total_score: number;
  grade: QualityGrade;
  deductions?: Array<{
    rule_id: string;
    deduction: number;
    reason: string;
  }>;
}

export interface ValidationIssue {
  rule_id: string;
  category: "GEOMETRY" | "CRS_AND_COORDINATES" | "HIERARCHY" | "STRATA" | "CLASH" | "PROVENANCE";
  severity: "CRITICAL" | "ERROR" | "WARNING" | "INFO";
  entity_type: string;
  entity_id: string;
  entity_identifier?: string | null;
  measured_values?: Record<string, any>;
  expected_condition: string;
  actual_condition: string;
  explanation: string;
  suggested_remediation: string;
}

export interface DigitalTwinValidationReport {
  validation_run_id: string;
  timestamp: string;
  parcel_id: string;
  parcel_ulpin: string;
  engine_version: string;
  is_valid: boolean;
  quality_score: QualityScoreBreakdown;
  total_rules_executed: number;
  total_rules_passed: number;
  total_rules_failed: number;
  critical_errors_count: number;
  warnings_count: number;
  info_count: number;
  entity_counts: Record<string, number>;
  issues: ValidationIssue[];
  clash_findings: any[];
  recommended_actions: string[];
}

// -------------------------------------------------------------
// 3D Digital Twin Models
// -------------------------------------------------------------

export interface DigitalTwinSummary {
  parcel_ulpin: string;
  total_buildings: number;
  total_floors: number;
  total_units: number;
  total_volume_cu_m: number;
  total_carpet_area_sqm: number;
  elevation_bounds: {
    min_z: number;
    max_z: number;
    span_m: number;
  };
}

export interface DigitalTwin3D {
  parcel_id: string;
  parcel_ulpin: string;
  summary: DigitalTwinSummary;
  features_3d: {
    type: "FeatureCollection";
    features: Array<{
      type: "Feature";
      geometry: {
        type: "Polygon" | "MultiPolygon";
        coordinates: any;
      };
      properties: {
        id: string;
        entity_type: "PARCEL" | "BUILDING" | "FLOOR" | "UNIT";
        identifier: string;
        ulpin?: string;
        ulpin_3d?: string;
        z_min: number;
        z_max: number;
        volume_cu_m?: number;
        unit_type?: string;
        is_multi_floor?: boolean;
        is_clash_free?: boolean;
        [key: string]: any;
      };
    }>;
  };
}
