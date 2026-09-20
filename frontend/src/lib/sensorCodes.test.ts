/**
 * Test: Evidence Source Type & Sensor Code Resolution
 * Proves that:
 * 1. UI human-readable label 'Drone Photogrammetry (Oblique + Nadir)' maps to API enum 'DRONE_PHOTOGRAMMETRY'.
 * 2. Previous invalid value 'DRONE' maps to 'DRONE_PHOTOGRAMMETRY'.
 * 3. Previous invalid value 'LIDAR' maps to 'POINT_CLOUD'.
 * 4. Previous invalid value 'GEOJSON' maps to 'BUILDING_METADATA'.
 * 5. All 11 authoritative backend EvidenceSourceType enum values resolve cleanly.
 * 6. Default fallback safely resolves to 'DRONE_PHOTOGRAMMETRY'.
 */
import {
  resolveEvidenceSourceType,
  EVIDENCE_SOURCE_OPTIONS,
  EvidenceSourceType,
} from './sensorCodes.ts';

function assertEqual(actual: any, expected: any, message: string) {
  if (actual !== expected) {
    throw new Error(`Assertion failed: ${message}. Expected '${expected}', got '${actual}'`);
  }
  console.log(`PASS: ${message}`);
}

// Test 1: UI Label -> DRONE_PHOTOGRAMMETRY
assertEqual(
  resolveEvidenceSourceType('Drone Photogrammetry (Oblique + Nadir)'),
  'DRONE_PHOTOGRAMMETRY',
  "UI label 'Drone Photogrammetry (Oblique + Nadir)' maps to 'DRONE_PHOTOGRAMMETRY'"
);

// Test 2: 'DRONE' -> 'DRONE_PHOTOGRAMMETRY'
assertEqual(
  resolveEvidenceSourceType('DRONE'),
  'DRONE_PHOTOGRAMMETRY',
  "Raw string 'DRONE' maps to 'DRONE_PHOTOGRAMMETRY'"
);
assertEqual(
  resolveEvidenceSourceType('drone'),
  'DRONE_PHOTOGRAMMETRY',
  "Lowercase 'drone' maps to 'DRONE_PHOTOGRAMMETRY'"
);
assertEqual(
  resolveEvidenceSourceType(' DRONE '),
  'DRONE_PHOTOGRAMMETRY',
  "Trimmed ' DRONE ' maps to 'DRONE_PHOTOGRAMMETRY'"
);

// Test 3: Legacy form options
assertEqual(
  resolveEvidenceSourceType('LIDAR'),
  'POINT_CLOUD',
  "Legacy 'LIDAR' maps to 'POINT_CLOUD'"
);
assertEqual(
  resolveEvidenceSourceType('GEOJSON'),
  'BUILDING_METADATA',
  "Legacy 'GEOJSON' maps to 'BUILDING_METADATA'"
);
assertEqual(
  resolveEvidenceSourceType('CAD_FLOOR_PLAN'),
  'CAD_FLOOR_PLAN',
  "'CAD_FLOOR_PLAN' maps to 'CAD_FLOOR_PLAN'"
);

// Test 4: All 11 authoritative backend enum values pass through identically
const authoritativeEnums: EvidenceSourceType[] = [
  'POINT_CLOUD',
  'DSM_DTM',
  'DRONE_PHOTOGRAMMETRY',
  'CAD_FLOOR_PLAN',
  'BUILDING_METADATA',
  'ASSUMPTION_FALLBACK',
  'EXPLICIT_FLOOR_COUNT',
  'OBSERVED_HEIGHT_DECOMPOSITION',
  'AI_HEIGHT_DECOMPOSITION',
  'DETERMINISTIC_BASELINE',
  'UNRESOLVED',
];

for (const enumVal of authoritativeEnums) {
  assertEqual(
    resolveEvidenceSourceType(enumVal),
    enumVal,
    `Authoritative enum '${enumVal}' passes through unmodified`
  );
}

// Test 5: Verify all options in EVIDENCE_SOURCE_OPTIONS have valid backend enum values
assertEqual(
  EVIDENCE_SOURCE_OPTIONS.length,
  authoritativeEnums.length,
  `EVIDENCE_SOURCE_OPTIONS defines all ${authoritativeEnums.length} backend enum values`
);

for (const opt of EVIDENCE_SOURCE_OPTIONS) {
  assertEqual(
    authoritativeEnums.includes(opt.value),
    true,
    `Option '${opt.label}' has valid backend enum value '${opt.value}'`
  );
}

// Test 6: Default fallback
assertEqual(
  resolveEvidenceSourceType(undefined),
  'DRONE_PHOTOGRAMMETRY',
  "Undefined input defaults to 'DRONE_PHOTOGRAMMETRY'"
);
assertEqual(
  resolveEvidenceSourceType(''),
  'DRONE_PHOTOGRAMMETRY',
  "Empty string input defaults to 'DRONE_PHOTOGRAMMETRY'"
);
assertEqual(
  resolveEvidenceSourceType(null),
  'DRONE_PHOTOGRAMMETRY',
  "Null input defaults to 'DRONE_PHOTOGRAMMETRY'"
);

console.log('\nAll sensor code resolution tests passed successfully.');
