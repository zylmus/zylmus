import re
import email
import logging
from email.message import Message
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup
from backend.parsers import ParsedPackage

logger = logging.getLogger(__name__)

# Sender patterns
RE_SENDER = re.compile(r"@inpost\.pl|@easypack24\.net|@paczkomat\.com", re.IGNORECASE)

# Subject triggers
RE_SUBJECT = re.compile(
    r"gotowa\s+do\s+odbioru|paczka\s+czeka|twoja\s+paczka|"
    r"paczkomat|ready\s+for\s+collection|parcel\s+ready|"
    r"przesyłka\s+czeka|shipment\s+ready|your\s+parcel",
    re.IGNORECASE,
)

# Locker ID: 2-4 uppercase letters + 2-3 digits + 0-3 uppercase letters
# Examples: WAW01N, KRA02, GDA01M, POZ123A, SZC01APP
RE_LOCKER_ID = re.compile(r"\b([A-Z]{2,4}\d{2,4}[A-Z]{0,3})\b")

# Pickup code — labeled (preferred)
RE_PICKUP_LABELED = re.compile(
    r"(?:kod\s+odbioru|kod\s+do\s+paczkomatu|kod\s+qr|pickup\s+code|twój\s+kod)"
    r"[:\s*\-–]+(\d{6})",
    re.IGNORECASE,
)

# Pickup code — standalone 6 digits (fallback)
RE_PICKUP_FALLBACK = re.compile(r"(?<!\d)(\d{6})(?!\d)")

# InPost 24-digit tracking number
RE_TRACKING = re.compile(r"\b(\d{24})\b")


def _extract_body(msg: Message) -> str:
    """Return best plain-text representation of an email message."""
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and not plain:
                plain = decoded
            elif ctype == "text/html" and not html:
                html = decoded
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        body = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html = body
        else:
            plain = body

    if not plain and html:
        plain = BeautifulSoup(html, "html.parser").get_text(separator="\n")
    return plain


def _find_locker_id(text: str) -> Optional[str]:
    """Find InPost locker ID, preferring occurrences near 'paczkomat'."""
    # First try to find near a paczkomat label
    for m in re.finditer(r"(?:paczkomat[®\s]*|locker[\s:]+)([A-Z]{2,4}\d{2,4}[A-Z]{0,3})", text, re.IGNORECASE):
        candidate = m.group(1).upper()
        if len(candidate) >= 4:
            return candidate

    # Fallback: any match of the locker pattern
    candidates = RE_LOCKER_ID.findall(text.upper())
    # Filter out common false positives (short all-letter words, etc.)
    for c in candidates:
        if re.match(r"^[A-Z]{2,4}\d{2,4}", c):
            return c
    return None


def _find_pickup_code(text: str) -> Optional[str]:
    """Find 6-digit pickup code."""
    m = RE_PICKUP_LABELED.search(text)
    if m:
        return m.group(1)
    # Fallback: first standalone 6-digit number
    m = RE_PICKUP_FALLBACK.search(text)
    if m:
        return m.group(1)
    return None


def _parse_email_date(msg: Message) -> str:
    """Return ISO date string from email Date header."""
    date_str = msg.get("Date", "")
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


class InPostParser:
    @staticmethod
    def parse(msg: Message) -> Optional[ParsedPackage]:
        from_header = msg.get("From", "")
        subject = msg.get("Subject", "")

        # Decode subject
        decoded_parts = email.header.decode_header(subject)
        subject = ""
        for part, enc in decoded_parts:
            if isinstance(part, bytes):
                subject += part.decode(enc or "utf-8", errors="replace")
            else:
                subject += part

        # Validate sender or subject
        if not RE_SENDER.search(from_header) and not RE_SUBJECT.search(subject):
            return None

        # Must match at least subject trigger if sender didn't match
        if not RE_SENDER.search(from_header) and not RE_SUBJECT.search(subject):
            return None

        body = _extract_body(msg)
        combined = subject + "\n" + body
        email_date = _parse_email_date(msg)

        locker_id = _find_locker_id(combined)
        pickup_code = _find_pickup_code(combined)

        # Tracking number
        m = RE_TRACKING.search(body)
        if m:
            tracking_number = m.group(1)
        elif locker_id:
            date_part = email_date[:10].replace("-", "")
            tracking_number = f"inpost_{locker_id}_{date_part}"
        else:
            # Can't identify the package at all
            logger.debug("InPost email could not be parsed: no locker ID or tracking number. Subject: %s", subject)
            return None

        logger.info("InPost package parsed: tracking=%s locker=%s code=%s", tracking_number, locker_id, pickup_code)

        return ParsedPackage(
            source="inpost",
            tracking_number=tracking_number,
            carrier="inpost",
            status="pickup_ready",
            email_subject=subject,
            email_date=email_date,
            locker_id=locker_id,
            pickup_code=pickup_code,
        )
