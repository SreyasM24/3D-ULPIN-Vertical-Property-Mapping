/**
 * TypeScript Data Contracts for SIH 26011:
 * 3D ULPIN & Vertical Property Mapping System.
 *
 * Strictly mirrors backend FastAPI Pydantic models with UI presentation accessors.
 */

// -------------------------------------------------------------
// Common & Envelope Types
// -------------------------------------------------------------

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: ApiErrorDetail | string | null;
  request_id?: string;
  message?: string;
}

export interface ApiErrorDetail {
  code?: string;
  message: string;
  details?: unknown;
  request_id?: string;
}

export interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: number[][][]; // Array of linear rings: [ [ [lon, lat], ... ] ]
}

export interface PaginatedList<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// -------------------------------------------------------------
// Cadastral Entity Models
// -------------------------------------------------------------

export interface LandParcel {
  id: string;
  ulpin: string;
  state_code?: string;
  district_code?: string;
  village_code?: string;
  survey_number: string;
  subdivision_number?: string | null;
  area_sqm: number;
  perimeter_m?: number;
  centroid_lat?: number;
  centroid_lon?: number;
  base_elevation_m?: number | null;
  geometry_geojson?: GeoJSONPolygon | any;
  spatial_metadata?: Record<string, any>;
  status: string;
  created_at: string;
  updated_at?: string;

  // UI convenience properties adapted from backend fields
  state?: string;
  district?: string;
  sub_district?: string;
  village?: string;
  ground_elevation_amsl?: number;
  crs?: string;
  coordinates?: [number, number][];
  boundary_beacons?: Array<{
    id: string;
    easting: number;
    northing: number;
    elevation: number;
    marker_type: string;
  }>;
  buildings_count?: number;
  units_count?: number;
}

export interface ParcelCreate {
  state_code: string;
  district_code: string;
  village_code: string;
  survey_number: string;
  subdivision_number?: string | null;
  base_elevation_m?: number | null;
  geometry_geojson: GeoJSONPolygon | any;
  spatial_metadata?: Record<string, any>;
}

export interface Building {
  id: string;
  parcel_id: string;
  building_name: string;
  building_code: string;
  structure_type?: string;
  floors_above_ground?: number;
  basement_floors?: number;
  total_height_m?: number;
  ground_elevation_m?: number;
  footprint_geojson?: GeoJSONPolygon | any;
  footprint_area_sqm?: number;
  gross_volume_cu_m?: number;
  is_within_parcel?: boolean;
  status?: string;
  created_at?: string;
  updated_at?: string;

  // UI convenience aliases
  ml_provenance?: Record<string, any>;
  spatial_metadata?: Record<string, any>;
  total_height?: number;
  ground_elevation?: number;
  levels_above_ground?: number;
  levels_below_ground?: number;
  classification?: string;
  roof_type?: string;
  footprint_polygon?: [number, number][];
}

export interface FloorLevel {
  id: string;
  building_id: string;
  level_number: number;
  level_code: string;
  level_type?: 'BASEMENT' | 'GROUND' | 'TYPICAL' | 'MEZZANINE' | 'TERRACE' | string;
  elevation_min_m?: number;
  elevation_max_m?: number;
  floor_height_m?: number;
  is_basement?: boolean;
  footprint_geojson?: GeoJSONPolygon | null;
  gross_floor_area_sqm?: number;
  gross_floor_volume_cu_m?: number;
  status?: string;
  created_at?: string;
  updated_at?: string;

  // UI convenience aliases
  elevation_bottom?: number;
  elevation_top?: number;
  height?: number;
  is_underground?: boolean;
  level_name?: string;
  units_count?: number;
}

export interface OwnershipRecord {
  id: string;
  unit_id: string;
  owner_name?: string;
  owner_id_hash?: string;
  share_percentage: number;
  title_deed_number?: string;
  deed_registration_date?: string;
  encumbrance_status?: string;
  status?: string;
  created_at?: string;

  // UI convenience aliases
  registered_owner_hash?: string;
  registration_date?: string;
  deed_reference?: string;
}

export interface VerticalUnit {
  id: string;
  floor_id: string;
  building_id?: string;
  parcel_id?: string;
  unit_number: string;
  unit_code?: string;
  unit_type: 'APARTMENT' | 'COMMERCIAL' | 'OFFICE' | 'PARKING' | 'COMMON_AREA' | 'TERRACE' | 'UTILITY' | 'RESIDENTIAL' | 'COMMON_PROPERTY' | 'UNDERGROUND_VAULT' | 'ELEVATED_AIR_RIGHTS' | string;
  ulpin_3d: string;
  ulpin_status?: string;
  base_ulpin?: string;
  level_code?: string;
  checksum?: string;
  footprint_geojson?: GeoJSONPolygon | any;
  elevation_min_m?: number;
  elevation_max_m?: number;
  carpet_area_sqm?: number;
  builtup_area_sqm?: number | null;
  volume_cu_m?: number;
  is_clash_free?: boolean;
  is_multi_floor?: boolean;
  floor_span?: string[] | null;
  vertical_classification?: string;
  spatial_metadata?: Record<string, any>;
  status?: string;
  stage?: string;
  confidence?: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN' | number | string | null;
  uncertainty_m?: number;
  ownership_records?: OwnershipRecord[];
  ownership_record?: OwnershipRecord;
  anomalies?: AnomalySignal[];
  provenance?: ProvenanceRecord;
  created_at?: string;
  updated_at?: string;

  // UI convenience aliases
  floor_level?: number;
  height_m?: number;
  vertical_range?: {
    z_min: number;
    z_max: number;
  };
  area_sqm?: number;
  volume_cum?: number;
  classification?: string;
  data_stage?: string;
  validation_status?: 'PASSED' | 'WARNING' | 'FAILED';
  geometry_3d?: {
    footprint: [number, number][];
    z_min: number;
    z_max: number;
    color?: string;
  };
}

export interface UndergroundVolume {
  id: string;
  parcel_id: string;
  name: string;
  type: string;
  vertical_range: {
    z_min: number;
    z_max: number;
  };
  volume_cum: number;
  footprint: [number, number][];
  status: string;
}

export interface ElevatedVolume {
  id: string;
  parcel_id: string;
  name: string;
  type: string;
  vertical_range: {
    z_min: number;
    z_max: number;
  };
  volume_cum: number;
  footprint: [number, number][];
  status: string;
}

export interface SharedCommonSpace {
  id: string;
  name: string;
  type: string;
  floor_code: string;
  volume_cum: number;
}

// -------------------------------------------------------------
// Digital Twin Models
// -------------------------------------------------------------

export interface DigitalTwinUnit {
  id: string;
  floor_id: string;
  unit_number: string;
  unit_code: string;
  unit_type: string;
  ulpin_3d: string;
  ulpin_status: string;
  vertical_classification: string;
  z_min: number;
  z_max: number;
  height_m: number;
  carpet_area_sqm: number;
  volume_cu_m: number;
  is_clash_free: boolean;
  status: string;
  footprint_geojson: Record<string, any>;
  stage: string;
  confidence?: number | null;
  ml_provenance?: Record<string, any> | null;
  ownership_records: OwnershipRecord[];
}

export interface DigitalTwinFloor {
  id: string;
  building_id: string;
  level_number: number;
  level_code: string;
  level_type: string;
  z_min: number;
  z_max: number;
  floor_height_m: number;
  stage: string;
  unit_count: number;
  units: DigitalTwinUnit[];
}

export interface DigitalTwinBuilding {
  id: string;
  parcel_id: string;
  building_name: string;
  building_code: string;
  structure_type: string;
  ground_elevation_m: number;
  total_height_m: number;
  top_elevation_m: number;
  footprint_area_sqm: number;
  volume_cu_m: number;
  footprint_geojson: Record<string, any>;
  stage: string;
  confidence?: number | null;
  ml_provenance?: Record<string, any> | null;
  estimated_features?: Record<string, any> | null;
  floors: DigitalTwinFloor[];
}

export interface DigitalTwinParcel {
  id: string;
  ulpin: string;
  state_code: string;
  district_code: string;
  village_code: string;
  survey_number: string;
  area_sqm: number;
  centroid: number[];
  base_elevation_m: number;
  geometry_geojson: Record<string, any>;
  stage: string;
  buildings: DigitalTwinBuilding[];
}

export interface DigitalTwinSummary {
  total_buildings: number;
  total_floors: number;
  total_units: number;
  total_volume_cu_m: number;
  total_carpet_area_sqm: number;
  vertical_breakdown?: Record<string, number>;
  clashes_detected?: number;
  overall_status?: string;
  data_stages?: Record<string, number>;
  anomalies_detected?: Array<Record<string, any>>;
}

export interface CadastralDigitalTwin {
  parcel: DigitalTwinParcel;
  summary: DigitalTwinSummary;
  assembled_at: string;
}

// Normalized presentation model consumable by existing 3D viewer & views
export interface DigitalTwin {
  parcel: LandParcel;
  buildings: Building[];
  floors: FloorLevel[];
  units: VerticalUnit[];
  underground_volumes?: UndergroundVolume[];
  elevated_volumes?: ElevatedVolume[];
  shared_spaces?: SharedCommonSpace[];
  summary?: DigitalTwinSummary;
  anomalies?: AnomalySignal[];
  metadata: {
    crs: string;
    datum: string;
    generated_at: string;
    version: string;
    cadastral_engine_version: string;
    total_volume_cum: number;
    total_vertical_units: number;
  };
}

// -------------------------------------------------------------
// Validation & Quality Models
// -------------------------------------------------------------

export type QualityGrade =
  | 'HIGH_CONFIDENCE'
  | 'GOOD_QUALITY'
  | 'REQUIRES_REVIEW'
  | 'INVALID_OR_INCOMPLETE';

export interface QualityScoreBreakdown {
  geometry_validity?: number;
  crs_projection?: number;
  hierarchy_containment?: number;
  vertical_strata_consistency?: number;
  topology_3d_clash_freedom?: number;
  provenance_completeness?: number;
  total_score: number;
  grade: QualityGrade;
  deductions?: Array<{
    rule_id: string;
    deduction: number;
    reason: string;
  }>;
  disclaimer?: string;
}

export interface ValidationIssue {
  rule_id: string;
  category: string;
  severity: 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO';
  entity_type: string;
  entity_id: string;
  entity_identifier?: string | null;
  measured_values?: Record<string, any>;
  expected_condition: string;
  actual_condition: string;
  explanation: string;
  suggested_remediation: string;
}

export interface DetailedClashFinding {
  entity_a_id?: string;
  entity_a_identifier?: string;
  entity_a_type?: string;
  entity_b_id?: string;
  entity_b_identifier?: string;
  entity_b_type?: string;
  classification?: string;
  horizontal_overlap_sqm?: number;
  vertical_overlap_m?: number;
  overlap_elevation_range?: number[];
  estimated_overlap_volume_cu_m?: number;
  explanation?: string;
  suggested_action?: string;

  // UI convenience aliases
  id?: string;
  type?: string;
  severity?: 'CRITICAL' | 'WARNING' | 'INFO' | 'ADVISORY';
  description?: string;
  unit_a_ulpin?: string;
  unit_b_ulpin?: string;
  overlap_volume_cum?: number;
  z_range?: { z_min: number; z_max: number };
}

export type ClashFinding = DetailedClashFinding;

export interface DigitalTwinValidationReport {
  validation_run_id: string;
  timestamp: string;
  parcel_id: string;
  parcel_ulpin: string;
  engine_version: string;
  data_version?: string | null;
  is_valid: boolean;
  quality_score: QualityScoreBreakdown | any;
  total_rules_executed: number;
  total_rules_passed: number;
  total_rules_failed: number;
  critical_errors_count: number;
  warnings_count: number;
  info_count: number;
  entity_counts: Record<string, number>;
  issues: ValidationIssue[];
  clash_findings: DetailedClashFinding[];
  recommended_actions: string[];

  // UI convenience aliases
  critical_errors?: number;
  warnings?: number;
  disclaimer?: string;
  quality_grade?: QualityGrade;
  validation_status?: 'PASSED' | 'WARNINGS' | 'FAILED';
  evaluated_rules?: ValidationRuleResult[];
  rules_evaluated?: ValidationRuleResult[];
  summary?: any;
  evaluated_at?: string;
}

// Legacy alias for components expecting ValidationReport
export type ValidationReport = DigitalTwinValidationReport;

export interface ValidationRuleResult {
  rule_id: string;
  rule_name: string;
  category: string;
  status: 'PASSED' | 'WARNING' | 'ERROR';
  message: string;
  details?: string;
}

export interface ValidationRuleDefinition {
  rule_id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  affected_entity_types: string[];
}

export interface ValidationHistoryItem {
  id: string;
  validation_run_id: string;
  entity_type: string;
  entity_id: string;
  timestamp: string;
  is_valid: boolean;
  quality_score: number;
  quality_grade: QualityGrade;
  critical_errors_count: number;
  warnings_count: number;
}

// -------------------------------------------------------------
// Processing & Ingestion Job Models
// -------------------------------------------------------------

export type JobStatus =
  | 'PENDING'
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type JobStage =
  | 'QUEUED'
  | 'INSPECTION'
  | 'PREPROCESSING'
  | 'FEATURE_EXTRACTION'
  | 'CADASTRAL_CONSTRUCTION'
  | 'ULPIN_GENERATION'
  | 'VALIDATION'
  | 'DIGITAL_TWIN_UPDATE'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface StageEvent {
  stage: string;
  timestamp: string;
  progress: number;
  message?: string;
  details?: Record<string, any>;
}

export interface JobRead {
  job_id: string;
  job_type?: string;
  request_id?: string | null;
  status: JobStatus;
  current_stage: JobStage;
  progress_percent: number;
  entity_type?: string | null;
  entity_id?: string | null;
  source_filename?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  stage_details?: {
    events?: StageEvent[];
    [key: string]: any;
  };
  error_message?: string | null;
  tracking_url?: string | null;

  // UI convenience aliases
  stages?: any[];
  output_artifacts?: {
    digital_twin_id?: string;
    ulpin_list?: string[];
    [key: string]: any;
  };
  [key: string]: any;
}

// Alias for components expecting ProcessingJob
export type ProcessingJob = JobRead;

export interface JobListResponse {
  jobs: JobRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobResultResponse {
  job_id: string;
  status: JobStatus;
  job_type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  quality_score?: number | null;
  quality_grade?: string | null;
  is_valid?: boolean | null;
  created_entities?: {
    parcel_id?: string;
    parcel_ulpin?: string;
    building_id?: string;
    building_code?: string;
    floors_count?: number;
    units_count?: number;
    unit_ulpins?: string[];
  };
  validation_summary?: Record<string, any>;
  digital_twin_url?: string | null;
  anomalies?: Array<Record<string, any>> | AnomalySignal[];
  artifacts?: Record<string, any>;
}

export interface ParcelProcessJobRequest {
  parcel_id?: string | null;
  state_code?: number;
  district_code?: string;
  revenue_district_code?: string;
  village_code?: string;
  survey_number?: string;
  parcel_geojson?: Record<string, any>;
  building_footprint_geojson?: Record<string, any>;
  total_height_m?: number;
  ground_elevation_m?: number;
  floor_count?: number;
  basement_count?: number;
  units_per_floor?: number;
  source_evidence?: Record<string, any>;
  auto_generate_strata?: boolean;
}

export interface SurveyIngestJobRequest {
  source_type: string;
  source_filename: string;
  source_crs?: string;
  dataset_payload?: Record<string, any>;
  metadata?: Record<string, any>;
}

// Form payload request (aligns directly with ParcelProcessJobRequest)
export interface CreateSurveyJobRequest extends ParcelProcessJobRequest {
  survey_source_type?: 'DRONE_PHOTOGRAMMETRY' | 'TERRESTRIAL_LIDAR' | 'BIM_IFC' | 'TOTAL_STATION_VECTOR' | 'GEOJSON_CADASTRAL' | string;
  state?: string;
  district?: string;
  crs?: string;
  ground_sampling_distance_cm?: number;
  source_reference_uri?: string;
  notes?: string;
}

// -------------------------------------------------------------
// ML & Provenance Models
// -------------------------------------------------------------

export interface AnomalySignal {
  id: string;
  target_id: string;
  target_type: 'PARCEL' | 'BUILDING' | 'UNIT' | 'SURFACE' | string;
  type: string;
  severity: 'CRITICAL' | 'WARNING' | 'ADVISORY' | 'INFO';
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
  explanation: string;
  requires_review: boolean;
  advisory_note?: string;
  detected_at: string;
}

export interface ProvenanceRecord {
  id: string;
  target_id: string;
  source: string;
  source_type?: string;
  source_reference?: string;
  method: string;
  model: string;
  model_version: string;
  data_stage: string;
  evidence_tier?: 'OBSERVED' | 'AI_INFERENCE' | 'DETERMINISTIC' | 'TEST_FIXTURE';
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
  uncertainty_m?: number;
  timestamp: string;
  operator_or_system: string;
  requires_review?: boolean;
  vertical_classification?: string;
  floor_span?: string[];
  [key: string]: any;
}

// -------------------------------------------------------------
// System Health & Capabilities
// -------------------------------------------------------------

export interface SystemHealth {
  status: 'healthy' | 'ready' | 'degraded' | 'unready' | 'ok' | string;
  app_name?: string;
  version?: string;
  environment?: string;
  database_connected?: boolean;
  ulpin_spec?: {
    status: string;
    description: string;
  };
  [key: string]: any;
}

export interface SystemCapabilities {
  app_name?: string;
  version?: string;
  environment?: string;
  specification?: string;
  capabilities?: {
    cadastre_2d: {
      supported: boolean;
      features: string[];
    };
    cadastre_3d: {
      supported: boolean;
      features: string[];
    };
    validation_engine: {
      supported: boolean;
      features: string[];
    };
    ml_feature_extraction: {
      supported: boolean;
      is_authoritative: boolean;
      pipeline: string;
      features: string[];
    };
    async_orchestration: {
      supported: boolean;
      features: string[];
    };
    digital_twin: {
      supported: boolean;
      features: string[];
    };
  };
  // Legacy aliases
  engine_version?: string;
  deterministic_rules_count?: number;
  [key: string]: any;
}

// -------------------------------------------------------------
// Temporal 3D Change & Cadastral Intelligence Models
// -------------------------------------------------------------

export type ChangeType =
  | 'BUILDING_ADDED'
  | 'BUILDING_REMOVED'
  | 'FOOTPRINT_CHANGED'
  | 'HEIGHT_CHANGED'
  | 'FLOOR_STRUCTURE_CHANGED'
  | 'VERTICAL_UNIT_CHANGED'
  | 'BASEMENT_CHANGED'
  | 'ELEVATED_STRUCTURE_CHANGED'
  | 'GEOMETRY_UNCERTAIN';

export type ChangeClassification =
  | 'OBSERVED_CHANGE'
  | 'AI_ESTIMATED_CHANGE'
  | 'DETERMINISTIC_CHANGE'
  | 'TEST_FIXTURE_CHANGE';

export type FootprintChangeClass =
  | 'UNCHANGED'
  | 'EXPANDED'
  | 'CONTRACTED'
  | 'SHIFTED'
  | 'COMPLEX_MODIFICATION'
  | 'NEW_BUILDING'
  | 'REMOVED_BUILDING';

export type ChangeSeverity = 'NONE' | 'MINOR' | 'MODERATE' | 'SIGNIFICANT' | 'CRITICAL';

export interface ChangeEvent {
  change_type: ChangeType;
  change_classification: ChangeClassification;
  entity_type: string;
  entity_id?: string | null;
  previous_value?: any;
  new_value?: any;
  delta?: number | null;
  magnitude?: number | null;
  unit?: string | null;
  confidence?: number | null;
  source: string;
  requires_review: boolean;
  explanation: string;
}

export interface FootprintComparisonResult {
  baseline_area_sqm: number;
  new_area_sqm: number;
  area_delta_sqm: number;
  area_change_pct: number;
  perimeter_delta_m: number;
  iou: number;
  centroid_displacement_m: number;
  classification: FootprintChangeClass;
  intersection_area_sqm: number;
  union_area_sqm: number;
}

export interface HeightComparisonResult {
  baseline_height_m?: number | null;
  new_height_m?: number | null;
  height_delta_m?: number | null;
  height_change_pct?: number | null;
  is_height_significant: boolean;
  requires_review: boolean;
  uncertainty_range_m?: number | null;
}

export interface FloorComparisonResult {
  baseline_floor_count: number;
  new_floor_count: number;
  floor_count_delta: number;
  added_floors: string[];
  removed_floors: string[];
  altered_floors: Array<Record<string, any>>;
  basement_delta: number;
  elevated_delta: number;
  requires_review: boolean;
}

export interface UnitComparisonResult {
  baseline_unit_count: number;
  new_unit_count: number;
  unit_count_delta: number;
  added_units: string[];
  removed_units: string[];
  altered_units: Array<Record<string, any>>;
  requires_review: boolean;
}

export interface TemporalChangeReport {
  comparison_id: string;
  baseline_snapshot_id: string;
  observation_snapshot_id: string;
  entity_id: string;
  is_test_fixture: boolean;
  technical_change_score: number;
  change_severity: ChangeSeverity;
  requires_cadastral_review: boolean;
  total_change_events: number;
  change_events: ChangeEvent[];
  footprint_comparison?: FootprintComparisonResult;
  height_comparison?: HeightComparisonResult;
  floor_comparison?: FloorComparisonResult;
  unit_comparison?: UnitComparisonResult;
  cross_referenced_anomalies?: Array<Record<string, any>>;
  legal_disclaimer: string;
}

// Navigation Tab
export type NavigationTab = 'overview' | 'survey' | 'digital-twin' | 'validation' | 'properties';

