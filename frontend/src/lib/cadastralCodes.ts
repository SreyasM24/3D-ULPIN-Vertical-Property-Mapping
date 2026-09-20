/**
 * Cadastral Code Utilities
 * Centralizes mapping between Indian human-readable state abbreviations (e.g. "MH")
 * and national census / LGD numeric state codes (e.g. 27 for Maharashtra)
 * as expected by the SIH 26011 backend job processing schema.
 */

export interface StateMetadata {
  code: string;            // 2-letter abbreviation (e.g. "MH")
  numericCode: number;     // 2-digit census/LGD code (e.g. 27)
  name: string;            // Full state name (e.g. "Maharashtra")
  defaultDistrict: string; // Canonical district code in demo/sample data (e.g. "PUN")
}

export const SUPPORTED_STATE_CODES: Record<string, StateMetadata> = {
  MH: {
    code: 'MH',
    numericCode: 27,
    name: 'Maharashtra',
    defaultDistrict: 'PUN',
  },
  TG: {
    code: 'TG',
    numericCode: 36,
    name: 'Telangana',
    defaultDistrict: 'HYD',
  },
  TS: {
    code: 'TS',
    numericCode: 36,
    name: 'Telangana',
    defaultDistrict: 'HYD',
  },
  DL: {
    code: 'DL',
    numericCode: 7,
    name: 'Delhi',
    defaultDistrict: 'DLH',
  },
  AP: {
    code: 'AP',
    numericCode: 28,
    name: 'Andhra Pradesh',
    defaultDistrict: 'VSP',
  },
  KA: {
    code: 'KA',
    numericCode: 29,
    name: 'Karnataka',
    defaultDistrict: 'BLR',
  },
};

/**
 * Resolves a state input (alphabetic abbreviation or numeric string/number)
 * to its authoritative numeric integer code for the backend API.
 * Defaults to 27 (Maharashtra) if unspecified or unmapped.
 */
export function resolveNumericStateCode(input?: string | number | null): number {
  if (input === undefined || input === null || input === '') {
    return 27; // Default Maharashtra (Census code 27)
  }

  if (typeof input === 'number') {
    return Number.isFinite(input) ? Math.floor(input) : 27;
  }

  const clean = input.trim().toUpperCase();

  // If already a numeric string, parse directly
  const parsed = parseInt(clean, 10);
  if (!isNaN(parsed) && String(parsed) === clean) {
    return parsed;
  }

  // Lookup alphabetic code
  if (SUPPORTED_STATE_CODES[clean]) {
    return SUPPORTED_STATE_CODES[clean].numericCode;
  }

  // If numeric parseable with leading zeros or trailing chars
  if (!isNaN(parsed)) {
    return parsed;
  }

  // Default fallback for Maharashtra (benchmark)
  return 27;
}

/**
 * Resolves an authoritative numeric code to its standard 2-letter postal abbreviation.
 */
export function resolveStateAbbreviation(numericOrAlpha?: string | number | null): string {
  if (!numericOrAlpha) return 'MH';

  if (typeof numericOrAlpha === 'string') {
    const clean = numericOrAlpha.trim().toUpperCase();
    if (SUPPORTED_STATE_CODES[clean]) {
      return SUPPORTED_STATE_CODES[clean].code;
    }
  }

  const num = typeof numericOrAlpha === 'number' ? numericOrAlpha : parseInt(String(numericOrAlpha), 10);
  for (const meta of Object.values(SUPPORTED_STATE_CODES)) {
    if (meta.numericCode === num) {
      return meta.code;
    }
  }

  return typeof numericOrAlpha === 'string' && isNaN(num) ? numericOrAlpha.toUpperCase() : 'MH';
}

export * from './sensorCodes.ts';
