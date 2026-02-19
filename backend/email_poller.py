import imaplib
import email
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import EmailAccount, Package, EmailUidSeen
from backend.parsers import ParsedPackage
from backend.parsers.inpost import InPostParser
from backend.parsers.amazon import AmazonParser
from backend.geocoding import resolve_coordinates

logger = logging.getLogger(__name__)

PARSERS = [InPostParser, AmazonParser]
LOOKBACK_DAYS = 14

# Sync state shared with the sync router
_sync_state = {
    "last_sync_at": None,
    "last_sync_result": "never",
    "last_sync_new_packages": 0,
    "next_scheduled_at": None,
}


def get_sync_state() -> dict:
    return dict(_sync_state)


def set_next_scheduled(dt: datetime):
    _sync_state["next_scheduled_at"] = dt.isoformat() if dt else None


async def poll_all_accounts():
    """Main entry: poll all active email accounts."""
    logger.info("Starting email poll for all accounts")
    db = SessionLocal()
    new_count = 0
    try:
        accounts = db.query(EmailAccount).filter(EmailAccount.is_active == True).all()
        for account in accounts:
            try:
                count = await asyncio.to_thread(_process_account, account.id)
                new_count += count
                account.last_polled_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                logger.error("Error processing account %s (%s): %s", account.id, account.email, e)
        _sync_state["last_sync_at"] = datetime.utcnow().isoformat()
        _sync_state["last_sync_result"] = "ok"
        _sync_state["last_sync_new_packages"] = new_count
        logger.info("Email poll complete. New packages: %d", new_count)
    except Exception as e:
        _sync_state["last_sync_result"] = f"error: {e}"
        logger.error("Poll failed: %s", e)
    finally:
        db.close()


def _process_account(account_id: int) -> int:
    """
    Synchronous function (run in thread pool).
    Returns count of new packages added.
    """
    db = SessionLocal()
    new_count = 0
    try:
        account = db.query(EmailAccount).filter_by(id=account_id).first()
        if not account:
            return 0

        logger.info("Connecting to %s:%d for %s", account.imap_host, account.imap_port, account.email)
        mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
        mail.login(account.email, account.get_password())
        mail.select("INBOX")

        since_date = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        status, data = mail.uid("SEARCH", None, f"SINCE {since_date}")
        if status != "OK" or not data[0]:
            mail.logout()
            return 0

        all_uids = data[0].split()
        if not all_uids:
            mail.logout()
            return 0

        # Filter already-seen UIDs
        seen_uids = {
            r.uid
            for r in db.query(EmailUidSeen.uid).filter(EmailUidSeen.account_id == account_id)
        }
        new_uids = [uid for uid in all_uids if uid.decode() not in seen_uids]
        logger.info("Account %s: %d total UIDs, %d new", account.email, len(all_uids), len(new_uids))

        for uid in new_uids:
            uid_str = uid.decode()
            try:
                status, msg_data = mail.uid("FETCH", uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # Try each parser
                parsed = None
                for parser_cls in PARSERS:
                    result = parser_cls.parse(msg)
                    if result:
                        parsed = result
                        break

                # Mark UID as seen regardless of whether we parsed it
                seen_entry = EmailUidSeen(account_id=account_id, uid=uid_str)
                db.add(seen_entry)
                db.commit()

                if parsed:
                    added = _upsert_package_sync(db, parsed, account_id)
                    if added:
                        new_count += 1

            except Exception as e:
                logger.warning("Error processing UID %s: %s", uid_str, e)
                # Still mark as seen to avoid retrying broken emails
                try:
                    seen_entry = EmailUidSeen(account_id=account_id, uid=uid_str)
                    db.merge(seen_entry)
                    db.commit()
                except Exception:
                    db.rollback()

        mail.logout()
    except imaplib.IMAP4.error as e:
        logger.error("IMAP error for account %s: %s", account_id, e)
        raise
    finally:
        db.close()
    return new_count


def _upsert_package_sync(db: Session, parsed: ParsedPackage, account_id: int) -> bool:
    """
    Insert or update a package in the DB (synchronous).
    Returns True if a new package was added.
    Note: geocoding is deferred to an async background task after this returns.
    """
    existing = db.query(Package).filter_by(tracking_number=parsed.tracking_number).first()

    try:
        email_date = datetime.fromisoformat(parsed.email_date) if parsed.email_date else None
    except ValueError:
        email_date = None

    if existing:
        # Update mutable fields
        existing.status = parsed.status
        if parsed.pickup_code:
            existing.pickup_code = parsed.pickup_code
        if parsed.locker_id:
            existing.locker_id = parsed.locker_id
        existing.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Updated package: %s", parsed.tracking_number)
        return False
    else:
        address = parsed.raw_address if hasattr(parsed, "raw_address") else None
        pkg = Package(
            tracking_number=parsed.tracking_number,
            source=parsed.source,
            carrier=parsed.carrier,
            status=parsed.status,
            locker_id=parsed.locker_id,
            pickup_code=parsed.pickup_code,
            address_display=address,
            email_subject=parsed.email_subject,
            email_date=email_date,
            email_account_id=account_id,
        )
        db.add(pkg)
        db.commit()
        db.refresh(pkg)
        logger.info("New package: %s (id=%d)", parsed.tracking_number, pkg.id)
        return True


async def geocode_pending_packages():
    """
    Async pass to resolve coordinates for packages without lat/lon.
    Called after polling completes.
    """
    db = SessionLocal()
    try:
        pending = db.query(Package).filter(
            Package.lat.is_(None),
            (Package.locker_id.isnot(None)) | (Package.address_display.isnot(None))
        ).all()

        for pkg in pending:
            # Build a minimal ParsedPackage for geocoding
            parsed = ParsedPackage(
                source=pkg.source,
                tracking_number=pkg.tracking_number,
                carrier=pkg.carrier,
                status=pkg.status,
                email_subject=pkg.email_subject or "",
                email_date=pkg.email_date.isoformat() if pkg.email_date else "",
                locker_id=pkg.locker_id,
                pickup_code=pkg.pickup_code,
                raw_address=pkg.address_display,
            )
            result = await resolve_coordinates(parsed, db)
            if result:
                pkg.lat = result["lat"]
                pkg.lon = result["lon"]
                if result.get("address") and not pkg.address_display:
                    pkg.address_display = result["address"]
                elif result.get("address") and pkg.locker_id:
                    pkg.address_display = result["address"]
                db.commit()
                logger.info("Geocoded package %d: %.4f, %.4f", pkg.id, pkg.lat, pkg.lon)
    except Exception as e:
        logger.error("Geocoding pass failed: %s", e)
    finally:
        db.close()


async def poll_and_geocode():
    """Combined entry point: poll emails then geocode pending packages."""
    await poll_all_accounts()
    await geocode_pending_packages()
