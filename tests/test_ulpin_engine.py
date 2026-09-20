import pytest
from app.services.ulpin_engine import (
    generate_2d_ulpin,
    generate_3d_ulpin,
    parse_and_validate_3d_ulpin,
    luhn_mod36_checksum,
)
from app.core.exceptions import ULPINGenerationError


def test_2d_ulpin_generation():
    lat, lon = 18.5204303, 73.8567437
    state_code = "MH"
    survey_no = "145/2"

    ulpin = generate_2d_ulpin(lat, lon, state_code, survey_no)
    assert len(ulpin) == 14
    assert ulpin.isalnum()

    # Determinism: same inputs produce exact same ULPIN
    ulpin2 = generate_2d_ulpin(lat, lon, state_code, survey_no)
    assert ulpin == ulpin2


def test_2d_ulpin_invalid_coordinates():
    with pytest.raises(ULPINGenerationError):
        generate_2d_ulpin(120.0, 73.0, "MH", "1")  # lat out of bounds


def test_3d_ulpin_generation():
    base_ulpin = "14CH78901234AB"
    level_code = "L04"
    unit_code = "U402"

    ulpin_3d = generate_3d_ulpin(base_ulpin, level_code, unit_code)
    assert ulpin_3d.startswith(f"{base_ulpin}-{level_code}-{unit_code}-")
    parts = ulpin_3d.split("-")
    assert len(parts) == 4
    assert len(parts[3]) == 2  # Checksum length


def test_parse_and_validate_3d_ulpin():
    base_ulpin = "14CH78901234AB"
    level_code = "B01"
    unit_code = "PK12"

    ulpin_3d = generate_3d_ulpin(base_ulpin, level_code, unit_code)
    parsed = parse_and_validate_3d_ulpin(ulpin_3d)

    assert parsed["valid"] is True
    assert parsed["base_ulpin"] == base_ulpin
    assert parsed["level_code"] == level_code
    assert parsed["unit_code"] == unit_code


def test_parse_invalid_3d_ulpin():
    # Corrupted checksum
    bad_ulpin = "14CH78901234AB-L04-U402-ZZ"
    with pytest.raises(ULPINGenerationError, match="checksum mismatch"):
        parse_and_validate_3d_ulpin(bad_ulpin)

    # Malformed segments
    with pytest.raises(ULPINGenerationError, match="expected 4 segments"):
        parse_and_validate_3d_ulpin("INVALID-ULPIN-FORMAT")


def test_luhn_mod36_checksum():
    val = "ABC123XYZ"
    chk = luhn_mod36_checksum(val)
    assert len(chk) == 1
    assert chk.isalnum()
