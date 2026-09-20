"""
ULPIN Engine: 2D Bhu-Aadhaar and 3D Prototype ULPIN Generator.

NOTICE:
The 3D ULPIN format implemented herein is a project-level prototype
designed for the SIH 26011 challenge ("3D ULPIN Generation and Vertical Property Mapping System").
It extends the 14-digit Bhu-Aadhaar standard into the vertical dimension.
"""

import hashlib
import re
from typing import Dict, Any, Tuple
from app.core.exceptions import ULPINGenerationError

ALPHANUM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def luhn_mod36_checksum(input_str: str) -> str:
    """Calculates a Luhn mod-36 verification checksum character."""
    factor = 2
    total = 0
    n = len(ALPHANUM_CHARS)
    
    clean_str = re.sub(r"[^0-9A-Z]", "", input_str.upper())
    for char in reversed(clean_str):
        code_point = ALPHANUM_CHARS.index(char)
        addend = factor * code_point
        factor = 1 if factor == 2 else 2
        addend = (addend // n) + (addend % n)
        total += addend

    remainder = total % n
    check_code_point = (n - remainder) % n
    return ALPHANUM_CHARS[check_code_point]


def generate_2d_ulpin(lat: float, lon: float, state_code: str, survey_number: str) -> str:
    """
    Generates a deterministic 14-character 2D ULPIN (Bhu-Aadhaar).
    Combines geodetic coordinates with administrative parcel identifiers.
    """
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ULPINGenerationError(f"Invalid geodetic coordinates: lat={lat}, lon={lon}")

    # Standardized geodetic encoding seed
    seed = f"{lat:.6f}:{lon:.6f}:{state_code.upper()}:{survey_number.upper()}".encode("utf-8")
    raw_hash = hashlib.sha256(seed).hexdigest().upper()

    # Form 13 alphanumeric chars from geodetic hash
    body = "".join([c for c in raw_hash if c in ALPHANUM_CHARS][:13])
    if len(body) < 13:
        body = body.ljust(13, "0")

    # 14th character is Luhn mod-36 checksum
    checksum = luhn_mod36_checksum(body)
    return f"{body}{checksum}"


def generate_3d_ulpin(
    base_ulpin: str,
    level_code: str,
    unit_code: str
) -> str:
    """
    Generates a deterministic Prototype 3D ULPIN.
    
    Format:
      <BASE_14_ULPIN>-<LEVEL_CODE>-<UNIT_CODE>-<CHECKSUM>
    Example:
      14CH78901234AB-L04-U402-K9
    """
    clean_base = re.sub(r"[^0-9A-Z]", "", base_ulpin.upper())
    clean_level = re.sub(r"[^0-9A-Z]", "", level_code.upper())
    clean_unit = re.sub(r"[^0-9A-Z]", "", unit_code.upper())

    if not clean_base or len(clean_base) != 14:
        raise ULPINGenerationError(
            f"Base ULPIN must be 14 alphanumeric characters, got '{base_ulpin}'"
        )
    if not clean_level:
        raise ULPINGenerationError("Level code must not be empty.")
    if not clean_unit:
        raise ULPINGenerationError("Unit code must not be empty.")

    payload = f"{clean_base}{clean_level}{clean_unit}"
    chk1 = luhn_mod36_checksum(payload)
    chk2 = luhn_mod36_checksum(payload + chk1)
    checksum = f"{chk1}{chk2}"

    return f"{clean_base}-{clean_level}-{clean_unit}-{checksum}"


def parse_and_validate_3d_ulpin(ulpin_3d: str) -> Dict[str, Any]:
    """
    Parses and verifies the checksum of a 3D ULPIN.
    Returns parsed components or raises ULPINGenerationError.
    """
    parts = ulpin_3d.strip().split("-")
    if len(parts) != 4:
        raise ULPINGenerationError(
            f"Invalid 3D ULPIN format: expected 4 segments separated by '-', got '{ulpin_3d}'"
        )

    base_ulpin, level_code, unit_code, checksum = parts
    payload = f"{base_ulpin}{level_code}{unit_code}"
    chk1 = luhn_mod36_checksum(payload)
    chk2 = luhn_mod36_checksum(payload + chk1)
    expected_checksum = f"{chk1}{chk2}"

    if checksum != expected_checksum:
        raise ULPINGenerationError(
            f"3D ULPIN checksum mismatch: got '{checksum}', expected '{expected_checksum}'"
        )

    return {
        "valid": True,
        "base_ulpin": base_ulpin,
        "level_code": level_code,
        "unit_code": unit_code,
        "checksum": checksum,
        "spec_status": "PROTOTYPE_SIH_26011"
    }
