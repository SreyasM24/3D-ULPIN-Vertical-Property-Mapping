/**
 * Evidence Source Type & Sensor Code Utilities
 * Aligns frontend sensor options strictly with backend EvidenceSourceType enum (app/ml/schemas.py).
 */

export type EvidenceSourceType =
  | 'POINT_CLOUD'
  | 'DSM_DTM'
  | 'DRONE_PHOTOGRAMMETRY'
  | 'CAD_FLOOR_PLAN'
  | 'BUILDING_METADATA'
  | 'ASSUMPTION_FALLBACK'
  | 'EXPLICIT_FLOOR_COUNT'
  | 'OBSERVED_HEIGHT_DECOMPOSITION'
  | 'AI_HEIGHT_DECOMPOSITION'
  | 'DETERMINISTIC_BASELINE'
  | 'UNRESOLVED';

export interface SourceOption {
  value: EvidenceSourceType;
  label: string;
  description?: string;
}

// User-facing options for UI selection (9 meaningful cadastral sources)
export const EVIDENCE_SOURCE_OPTIONS: SourceOption[] = [
  {
    value: 'DRONE_PHOTOGRAMMETRY',
    label: 'Drone Photogrammetry (Oblique + Nadir)',
    description: 'High-resolution aerial photogrammetry mesh and orthophotos',
  },
  {
    value: 'POINT_CLOUD',
    label: 'Terrestrial / Aerial LiDAR Point Cloud',
    description: 'Direct 3D laser scanning point cloud telemetry',
  },
  {
    value: 'DSM_DTM',
    label: 'DSM / DTM Elevation Difference',
    description: 'Digital Surface Model minus Digital Terrain Model raster heights',
  },
  {
    value: 'CAD_FLOOR_PLAN',
    label: 'Architectural CAD / Floor Plan Vectors',
    description: 'Architectural blueprints or vector floor layout plans',
  },
  {
    value: 'BUILDING_METADATA',
    label: 'Cadastral Vector Boundary / Building Metadata',
    description: 'Existing registered cadastral polygons and survey records',
  },
  {
    value: 'EXPLICIT_FLOOR_COUNT',
    label: 'Explicit Architectural Floor Count',
    description: 'Surveyor-recorded physical storey count',
  },
  {
    value: 'OBSERVED_HEIGHT_DECOMPOSITION',
    label: 'Observed Height Strata Decomposition',
    description: 'Direct physical height partitioned into uniform floor strata',
  },
  {
    value: 'AI_HEIGHT_DECOMPOSITION',
    label: 'AI Height Inferred Strata Decomposition',
    description: 'Neural network estimated building height partitioned into strata',
  },
  {
    value: 'DETERMINISTIC_BASELINE',
    label: 'Deterministic Cadastral Baseline',
    description: 'Pre-registered cadastral parcel boundaries without 3D sensor update',
  },
];

// Internal options including degradation/unresolved states (retained for backend, provenance, and tests)
export const ALL_INTERNAL_EVIDENCE_SOURCE_OPTIONS: SourceOption[] = [
  ...EVIDENCE_SOURCE_OPTIONS,
  {
    value: 'ASSUMPTION_FALLBACK',
    label: 'Statistical Assumption Fallback',
    description: 'Standard municipal zonal building height defaults',
  },
  {
    value: 'UNRESOLVED',
    label: 'Unresolved Sensor Source',
    description: 'Unidentified or raw telemetry pending surveyor verification',
  },
];

const ALIAS_TO_SOURCE_TYPE: Record<string, EvidenceSourceType> = {
  // Drone aliases
  DRONE: 'DRONE_PHOTOGRAMMETRY',
  DRONE_PHOTOGRAMMETRY: 'DRONE_PHOTOGRAMMETRY',
  DRONE_SURVEY: 'DRONE_PHOTOGRAMMETRY',
  UAV: 'DRONE_PHOTOGRAMMETRY',
  PHOTOGRAMMETRY: 'DRONE_PHOTOGRAMMETRY',

  // Point cloud / LiDAR aliases
  LIDAR: 'POINT_CLOUD',
  POINT_CLOUD: 'POINT_CLOUD',
  TERRESTRIAL_LIDAR: 'POINT_CLOUD',
  AERIAL_LIDAR: 'POINT_CLOUD',
  LAS: 'POINT_CLOUD',
  LAZ: 'POINT_CLOUD',

  // DSM / DTM
  DSM_DTM: 'DSM_DTM',
  DSM: 'DSM_DTM',
  DEM: 'DSM_DTM',
  DTM: 'DSM_DTM',

  // CAD / BIM
  CAD_FLOOR_PLAN: 'CAD_FLOOR_PLAN',
  CAD: 'CAD_FLOOR_PLAN',
  FLOOR_PLAN: 'CAD_FLOOR_PLAN',
  BIM: 'CAD_FLOOR_PLAN',
  BIM_IFC: 'CAD_FLOOR_PLAN',
  IFC: 'CAD_FLOOR_PLAN',

  // Building metadata / vectors
  BUILDING_METADATA: 'BUILDING_METADATA',
  METADATA: 'BUILDING_METADATA',
  GEOJSON: 'BUILDING_METADATA',
  GEOJSON_CADASTRAL: 'BUILDING_METADATA',
  SHAPEFILE: 'BUILDING_METADATA',
  TOTAL_STATION_VECTOR: 'BUILDING_METADATA',

  // Floor count & height decompositions
  EXPLICIT_FLOOR_COUNT: 'EXPLICIT_FLOOR_COUNT',
  FLOOR_COUNT: 'EXPLICIT_FLOOR_COUNT',
  OBSERVED_HEIGHT_DECOMPOSITION: 'OBSERVED_HEIGHT_DECOMPOSITION',
  OBSERVED_HEIGHT: 'OBSERVED_HEIGHT_DECOMPOSITION',
  AI_HEIGHT_DECOMPOSITION: 'AI_HEIGHT_DECOMPOSITION',
  AI_HEIGHT: 'AI_HEIGHT_DECOMPOSITION',

  // Baseline and fallbacks
  DETERMINISTIC_BASELINE: 'DETERMINISTIC_BASELINE',
  BASELINE: 'DETERMINISTIC_BASELINE',
  ASSUMPTION_FALLBACK: 'ASSUMPTION_FALLBACK',
  FALLBACK: 'ASSUMPTION_FALLBACK',
  UNRESOLVED: 'UNRESOLVED',
};

/**
 * Normalizes any sensor / source input to the exact backend EvidenceSourceType enum value.
 * Defaults safely to 'DRONE_PHOTOGRAMMETRY'.
 */
export function resolveEvidenceSourceType(input?: string | null): EvidenceSourceType {
  if (!input || !input.trim()) {
    return 'DRONE_PHOTOGRAMMETRY';
  }

  const trimmed = input.trim();

  // Check if input matches any option label
  for (const opt of ALL_INTERNAL_EVIDENCE_SOURCE_OPTIONS) {
    if (opt.label.toUpperCase() === trimmed.toUpperCase()) {
      return opt.value;
    }
  }

  const clean = trimmed.toUpperCase().replace(/[\s\-\.]+/g, '_');

  // Direct alias or exact enum match
  if (ALIAS_TO_SOURCE_TYPE[clean]) {
    return ALIAS_TO_SOURCE_TYPE[clean];
  }

  // Check substring matches
  if (clean.includes('DRONE') || clean.includes('PHOTOGRAMMETRY')) {
    return 'DRONE_PHOTOGRAMMETRY';
  }
  if (clean.includes('LIDAR') || clean.includes('POINT') || clean.includes('CLOUD')) {
    return 'POINT_CLOUD';
  }
  if (clean.includes('DSM') || clean.includes('DTM') || clean.includes('DEM')) {
    return 'DSM_DTM';
  }
  if (clean.includes('CAD') || clean.includes('PLAN') || clean.includes('BIM')) {
    return 'CAD_FLOOR_PLAN';
  }
  if (clean.includes('GEOJSON') || clean.includes('METADATA') || clean.includes('SHP')) {
    return 'BUILDING_METADATA';
  }

  return 'DRONE_PHOTOGRAMMETRY';
}

export interface SourceMetaConfig {
  defaultReference: string;
  fieldLabel: string;
  placeholder: string;
  helpText: string;
  isCompatible: (ref: string) => boolean;
}

export const SOURCE_METADATA_CONFIG: Record<EvidenceSourceType, SourceMetaConfig> = {
  POINT_CLOUD: {
    defaultReference: 'sample_pointcloud.las',
    fieldLabel: 'LiDAR Point Cloud Telemetry (.las, .laz)',
    placeholder: 'sample_pointcloud.las',
    helpText: 'Direct 3D laser scan point cloud. Tested with ASPRS Class 2 ground & Z95 roof returns.',
    isCompatible: (ref) => /\.(las|laz)$/i.test(ref) || ref.toLowerCase().includes('pointcloud') || ref.toLowerCase().includes('lidar'),
  },
  DSM_DTM: {
    defaultReference: 'usgs_3dep_dem_patch_512x512.tif',
    fieldLabel: 'Digital Elevation Raster (.tif, .dem, .npy)',
    placeholder: 'usgs_3dep_dem_patch_512x512.tif',
    helpText: 'USGS 3DEP DEM or raster difference grid. Classified as terrain-only or surface.',
    isCompatible: (ref) => /\.(tif|tiff|dem|npy)$/i.test(ref) || ref.toLowerCase().includes('dem') || ref.toLowerCase().includes('dsm'),
  },
  DRONE_PHOTOGRAMMETRY: {
    defaultReference: 'demo_26011_drone_survey.geojson',
    fieldLabel: 'Drone Survey / Vector Reference',
    placeholder: 'e.g. demo_26011_drone_survey.geojson or orthophoto_boundary.geojson',
    helpText: 'Aerial drone survey flight telemetry. Vector footprints used when mesh is not attached.',
    isCompatible: (ref) => !/\.(las|laz|dxf|dwg)$/i.test(ref) && !ref.includes('models/') && !ref.includes('cadastral_parametric'),
  },
  CAD_FLOOR_PLAN: {
    defaultReference: 'architectural_floor_plan_rev2.dxf',
    fieldLabel: 'Architectural CAD / BIM Reference',
    placeholder: 'e.g. floor_plan_level1.dxf or architectural_layout.json',
    helpText: 'Architectural blueprints or vector floor layout plans (DXF/DWG/JSON/IFC).',
    isCompatible: (ref) => /\.(dxf|dwg|ifc|json|geojson)$/i.test(ref) || ref.toLowerCase().includes('cad') || ref.toLowerCase().includes('plan'),
  },
  BUILDING_METADATA: {
    defaultReference: 'registered_cadastral_survey',
    fieldLabel: 'Statutory Cadastral / Survey Reference',
    placeholder: 'e.g. SURVEY-DEMO-26011-001 or bhu_aadhaar_record.geojson',
    helpText: 'Official revenue survey record or municipal building approval permit.',
    isCompatible: (ref) => !/\.(las|laz|tif|tiff|dem|npy|dxf|dwg)$/i.test(ref) && !ref.includes('models/'),
  },
  EXPLICIT_FLOOR_COUNT: {
    defaultReference: 'surveyor_storey_declaration.record',
    fieldLabel: 'Physical Storey Count Survey Record',
    placeholder: 'e.g. field_inspection_report_2026.record',
    helpText: 'Surveyor field measurement declaring above-ground and basement storey counts.',
    isCompatible: (ref) => !/\.(las|laz|tif|tiff|dem|npy|dxf|dwg)$/i.test(ref) && !ref.includes('models/'),
  },
  OBSERVED_HEIGHT_DECOMPOSITION: {
    defaultReference: 'total_station_height_telemetry.obs',
    fieldLabel: 'Observed Height Telemetry Record',
    placeholder: 'e.g. total_station_height_measurement.obs',
    helpText: 'Direct physical total station or EDM laser distance measurement.',
    isCompatible: (ref) => !/\.(las|laz|tif|tiff|dem|npy|dxf|dwg)$/i.test(ref) && !ref.includes('models/'),
  },
  AI_HEIGHT_DECOMPOSITION: {
    defaultReference: 'models/height_estimator.onnx',
    fieldLabel: 'AI Height Model Reference (Neural Regressor)',
    placeholder: 'models/height_estimator.onnx',
    helpText: 'AI evidence mode: Trained ONNX MLP height estimator evaluated independently on building footprint geometry.',
    isCompatible: (ref) => ref.toLowerCase().includes('model') || ref.toLowerCase().includes('onnx') || ref.toLowerCase().includes('ai'),
  },
  DETERMINISTIC_BASELINE: {
    defaultReference: 'cadastral_parametric_rules',
    fieldLabel: 'Cadastral Parametric Rules Reference',
    placeholder: 'cadastral_parametric_rules',
    helpText: 'Deterministic municipal building bylaw baseline (3.0m typical, 3.8m ground floor).',
    isCompatible: (ref) => !/\.(las|laz|tif|tiff|dem|npy|dxf|dwg)$/i.test(ref) && !ref.includes('models/'),
  },
  ASSUMPTION_FALLBACK: {
    defaultReference: 'cadastral_parametric_rules',
    fieldLabel: 'Statistical Assumption Reference',
    placeholder: 'cadastral_parametric_rules',
    helpText: 'Standard municipal zonal building height defaults.',
    isCompatible: () => true,
  },
  UNRESOLVED: {
    defaultReference: 'pending_survey_verification',
    fieldLabel: 'Unresolved Evidence Reference',
    placeholder: 'pending_survey_verification',
    helpText: 'Unidentified or raw telemetry pending surveyor verification.',
    isCompatible: () => true,
  },
};

export function getSourceMetaConfig(sourceType: string): SourceMetaConfig {
  const resolved = resolveEvidenceSourceType(sourceType);
  return SOURCE_METADATA_CONFIG[resolved] || SOURCE_METADATA_CONFIG.DRONE_PHOTOGRAMMETRY;
}

