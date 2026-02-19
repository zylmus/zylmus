from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, LargeBinary, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base, fernet


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    imap_host = Column(String(255), nullable=False)
    imap_port = Column(Integer, nullable=False, default=993)
    password_encrypted = Column(LargeBinary, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_polled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    packages = relationship("Package", back_populates="account", cascade="all, delete-orphan")
    seen_uids = relationship("EmailUidSeen", back_populates="account", cascade="all, delete-orphan")

    def set_password(self, plaintext: str):
        self.password_encrypted = fernet.encrypt(plaintext.encode())

    def get_password(self) -> str:
        return fernet.decrypt(self.password_encrypted).decode()


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tracking_number = Column(String(100), nullable=False, unique=True)
    source = Column(String(20), nullable=False)   # "inpost" | "amazon"
    carrier = Column(String(50), nullable=False)  # "inpost" | "dhl" | etc.
    status = Column(String(30), nullable=False, default="in_transit")
    # status values: "pickup_ready" | "delivered" | "in_transit" | "expired"
    locker_id = Column(String(20), nullable=True)
    pickup_code = Column(String(10), nullable=True)
    address_display = Column(String(500), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_date = Column(DateTime, nullable=True)
    email_account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("EmailAccount", back_populates="packages")


class EmailUidSeen(Base):
    __tablename__ = "email_uid_seen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    uid = Column(String(50), nullable=False)
    seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    account = relationship("EmailAccount", back_populates="seen_uids")

    __table_args__ = (UniqueConstraint("account_id", "uid", name="uq_account_uid"),)


class LockerGeoCache(Base):
    __tablename__ = "locker_geo_cache"

    locker_id = Column(String(20), primary_key=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    address_display = Column(String(500), nullable=False)
    cached_at = Column(DateTime, nullable=False, default=datetime.utcnow)
