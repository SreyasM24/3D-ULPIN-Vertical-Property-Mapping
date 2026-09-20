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
  for (const opt of EVIDENCE_SOURCE_OPTIONS) {
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
