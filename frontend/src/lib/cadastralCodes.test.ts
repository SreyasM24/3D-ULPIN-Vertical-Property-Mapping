/**
 * Test: Cadastral State Code Resolution
 * Proves that:
 * 1. UI human-readable value 'MH' resolves to API numeric integer 27.
 * 2. Supported state values (MH, TG, TS, DL, AP, KA) resolve to their authoritative Census codes.
 * 3. Numeric string inputs ('27', '36') resolve to numeric integers.
 * 4. Empty/null defaults safely to 27 (Maharashtra benchmark).
 */
import { resolveNumericStateCode, resolveStateAbbreviation, SUPPORTED_STATE_CODES } from './cadastralCodes.ts';

function assertEqual(actual: any, expected: any, message: string) {
  if (actual !== expected) {
    throw new Error(`Assertion failed: ${message}. Expected ${expected}, got ${actual}`);
  }
  console.log(`PASS: ${message}`);
}

// Test 1: UI value 'MH' -> 27
assertEqual(resolveNumericStateCode('MH'), 27, "UI 'MH' maps to integer 27");
assertEqual(resolveNumericStateCode('mh'), 27, "Lowercase 'mh' maps to integer 27");
assertEqual(resolveNumericStateCode(' MH '), 27, "Trimmed ' MH ' maps to integer 27");

// Test 2: Other supported application states
assertEqual(resolveNumericStateCode('TG'), 36, "Telangana 'TG' maps to integer 36");
assertEqual(resolveNumericStateCode('TS'), 36, "Telangana 'TS' maps to integer 36");
assertEqual(resolveNumericStateCode('DL'), 7, "Delhi 'DL' maps to integer 7");
assertEqual(resolveNumericStateCode('AP'), 28, "Andhra Pradesh 'AP' maps to integer 28");
assertEqual(resolveNumericStateCode('KA'), 29, "Karnataka 'KA' maps to integer 29");

// Test 3: Direct numeric inputs
assertEqual(resolveNumericStateCode(27), 27, "Numeric 27 passes through as integer 27");
assertEqual(resolveNumericStateCode('27'), 27, "String '27' parses to integer 27");

// Test 4: Default fallback
assertEqual(resolveNumericStateCode(undefined), 27, "Undefined defaults to integer 27");
assertEqual(resolveNumericStateCode(''), 27, "Empty string defaults to integer 27");

// Test 5: Reverse abbreviation resolution
assertEqual(resolveStateAbbreviation(27), 'MH', "Numeric 27 resolves to display 'MH'");
assertEqual(resolveStateAbbreviation('27'), 'MH', "String '27' resolves to display 'MH'");
assertEqual(resolveStateAbbreviation('MH'), 'MH', "Abbreviation 'MH' preserves 'MH'");

console.log("\nAll cadastral state code mapping tests passed successfully.");
