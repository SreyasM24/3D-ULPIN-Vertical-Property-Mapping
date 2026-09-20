"""
Ownership Service: RoR (Record of Rights) management for Vertical Property Units.
"""

import hashlib
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.ownership import OwnershipRecord
from app.models.unit import VerticalUnit
from app.schemas.ownership import OwnershipCreate, OwnershipUpdate
from app.core.exceptions import EntityNotFoundException, CadastreException
from app.core.logging import logger


class OwnershipService:
    @staticmethod
    def hash_identifier(raw_id: str) -> str:
        """Computes SHA-256 hash of personal identification number for privacy compliance."""
        return hashlib.sha256(raw_id.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def create_ownership(db: Session, data: OwnershipCreate) -> OwnershipRecord:
        unit = db.get(VerticalUnit, data.unit_id)
        if not unit:
            raise EntityNotFoundException("VerticalUnit", data.unit_id)

        # Validate total ownership share for unit does not exceed 100%
        active_records = db.execute(
            select(OwnershipRecord).where(
                OwnershipRecord.unit_id == unit.id,
                OwnershipRecord.status == "ACTIVE"
            )
        ).scalars().all()

        current_total_share = sum(r.share_percentage for r in active_records)
        if current_total_share + data.share_percentage > 100.0 + 1e-4:
            raise CadastreException(
                f"Total share percentage exceeds 100%. Currently allocated: {current_total_share}%, requested: {data.share_percentage}%"
            )

        hashed_id = OwnershipService.hash_identifier(data.owner_identifier_raw)

        record = OwnershipRecord(
            unit_id=unit.id,
            owner_name=data.owner_name,
            owner_identifier_hash=hashed_id,
            share_percentage=data.share_percentage,
            ownership_type=data.ownership_type,
            title_deed_number=data.title_deed_number,
            registration_date=data.registration_date,
            is_encumbered=data.is_encumbered,
            encumbrance_details=data.encumbrance_details,
            meta_info=data.meta_info or {},
            status=data.status
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(f"Registered OwnershipRecord id={record.id} for unit={unit.ulpin_3d}")
        return record

    @staticmethod
    def get_ownership(db: Session, record_id: str) -> OwnershipRecord:
        record = db.get(OwnershipRecord, record_id)
        if not record:
            raise EntityNotFoundException("OwnershipRecord", record_id)
        return record

    @staticmethod
    def list_ownerships(
        db: Session, unit_id: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[List[OwnershipRecord], int]:
        stmt = select(OwnershipRecord)
        count_stmt = select(func.count(OwnershipRecord.id))
        if unit_id:
            stmt = stmt.where(OwnershipRecord.unit_id == unit_id)
            count_stmt = count_stmt.where(OwnershipRecord.unit_id == unit_id)

        total = db.scalar(count_stmt) or 0
        items = db.execute(stmt.offset(skip).limit(limit)).scalars().all()
        return list(items), total

    @staticmethod
    def update_ownership(db: Session, record_id: str, data: OwnershipUpdate) -> OwnershipRecord:
        record = OwnershipService.get_ownership(db, record_id)
        update_data = data.model_dump(exclude_unset=True)

        if "share_percentage" in update_data and update_data["share_percentage"] is not None:
            # Check share constraint
            other_records = db.execute(
                select(OwnershipRecord).where(
                    OwnershipRecord.unit_id == record.unit_id,
                    OwnershipRecord.id != record.id,
                    OwnershipRecord.status == "ACTIVE"
                )
            ).scalars().all()
            other_share = sum(r.share_percentage for r in other_records)
            if other_share + update_data["share_percentage"] > 100.0 + 1e-4:
                raise CadastreException("Total share percentage cannot exceed 100%.")

        for key, value in update_data.items():
            setattr(record, key, value)

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def delete_ownership(db: Session, record_id: str) -> None:
        record = OwnershipService.get_ownership(db, record_id)
        db.delete(record)
        db.commit()
