from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Package

router = APIRouter()


class PackageOut(BaseModel):
    id: int
    tracking_number: str
    source: str
    carrier: str
    status: str
    locker_id: Optional[str] = None
    pickup_code: Optional[str] = None
    address_display: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    email_subject: Optional[str] = None
    email_date: Optional[datetime] = None
    email_account_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PackageListResponse(BaseModel):
    total: int
    items: List[PackageOut]


class PackageUpdate(BaseModel):
    status: Optional[str] = None
    pickup_code: Optional[str] = None
    address_display: Optional[str] = None


VALID_STATUSES = {"pickup_ready", "delivered", "in_transit", "expired"}


@router.get("", response_model=PackageListResponse)
def list_packages(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Package)
    if status and status != "all":
        query = query.filter(Package.status == status)
    if source and source != "all":
        query = query.filter(Package.source == source)
    if search:
        like = f"%{search}%"
        query = query.filter(
            Package.tracking_number.ilike(like)
            | Package.address_display.ilike(like)
            | Package.locker_id.ilike(like)
        )
    total = query.count()
    items = query.order_by(Package.email_date.desc().nullslast(), Package.created_at.desc()).offset(offset).limit(limit).all()
    return PackageListResponse(total=total, items=items)


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.query(Package).filter_by(id=package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@router.patch("/{package_id}", response_model=PackageOut)
def update_package(package_id: int, body: PackageUpdate, db: Session = Depends(get_db)):
    pkg = db.query(Package).filter_by(id=package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")
        pkg.status = body.status
    if body.pickup_code is not None:
        pkg.pickup_code = body.pickup_code
    if body.address_display is not None:
        pkg.address_display = body.address_display
    pkg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/{package_id}")
def delete_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.query(Package).filter_by(id=package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    db.delete(pkg)
    db.commit()
    return {"ok": True}
