import asyncio
import imaplib
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import EmailAccount

logger = logging.getLogger(__name__)
router = APIRouter()


class AccountCreate(BaseModel):
    label: str
    email: str
    imap_host: str
    imap_port: int = 993
    password: str


class AccountUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None


class AccountOut(BaseModel):
    id: int
    label: str
    email: str
    imap_host: str
    imap_port: int
    is_active: bool
    last_polled_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(EmailAccount).order_by(EmailAccount.created_at).all()


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    existing = db.query(EmailAccount).filter_by(email=body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account with this email already exists")
    account = EmailAccount(
        label=body.label,
        email=body.email,
        imap_host=body.imap_host,
        imap_port=body.imap_port,
    )
    account.set_password(body.password)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db)):
    account = db.query(EmailAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if body.label is not None:
        account.label = body.label
    if body.is_active is not None:
        account.is_active = body.is_active
    if body.imap_host is not None:
        account.imap_host = body.imap_host
    if body.imap_port is not None:
        account.imap_port = body.imap_port
    if body.password is not None:
        account.set_password(body.password)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(EmailAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.post("/{account_id}/test")
async def test_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(EmailAccount).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    host = account.imap_host
    port = account.imap_port
    email_addr = account.email
    password = account.get_password()

    def _test():
        try:
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(email_addr, password)
            mail.logout()
            return {"ok": True, "message": "Connection successful"}
        except imaplib.IMAP4.error as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"Connection failed: {e}"}

    result = await asyncio.to_thread(_test)
    return result
