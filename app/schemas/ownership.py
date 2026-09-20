from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class OwnershipBase(BaseModel):
    owner_name: str = Field(..., max_length=150, example="Rajesh Sharma")
    share_percentage: float = Field(default=100.0, ge=0.01, le=100.0, example=100.0)
    ownership_type: str = Field(default="INDIVIDUAL", example="INDIVIDUAL")
    title_deed_number: str = Field(..., max_length=100, example="REG/2026/PUN/89201")
    registration_date: str = Field(..., example="2026-03-15")
    is_encumbered: bool = Field(default=False)
    encumbrance_details: Optional[str] = Field(None, max_length=255)
    meta_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="ACTIVE")


class OwnershipCreate(OwnershipBase):
    unit_id: str = Field(..., description="ID of the target VerticalUnit")
    # Raw identifier provided during registration (e.g. Aadhaar / PAN), which will be securely hashed by service
    owner_identifier_raw: str = Field(..., min_length=4, max_length=50, example="XXXXXXXX1234")


class OwnershipUpdate(BaseModel):
    share_percentage: Optional[float] = None
    is_encumbered: Optional[bool] = None
    encumbrance_details: Optional[str] = None
    meta_info: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class OwnershipRead(OwnershipBase):
    id: str
    unit_id: str
    owner_identifier_hash: str  # Safe hashed value
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
