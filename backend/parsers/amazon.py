import re
import email
import logging
from email.message import Message
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup
from backend.parsers import ParsedPackage

logger = logging.getLogger(__name__)

RE_SENDER = re.compile(
    r"@amazon\.pl|@amazon\.com|@amazon\.co\.uk|@amazon\.de|"
    r"ship-confirm@amazon|no-reply@amazon|shipment-tracking@amazon",
    re.IGNORECASE,
)

RE_SUBJECT = re.compile(
    r"dostarczono|paczka\s+dostarczona|twoja\s+przesyłka|"
    r"your\s+(?:package|shipment|order)\s+(?:has\s+been\s+)?delivered|"
    r"delivered\s+to\s+locker|przesyłka\s+dostarczona|"
    r"zamówienie\s+.*\s+zostało\s+dostarczone",
    re.IGNORECASE,
)

RE_ORDER_NUMBER = re.compile(
    r"(?:zamówienie|order|order\s*#|nr\s+zamówienia)\s*[:\s#]*(\d{3}-\d{7}-\d{7})",
    re.IGNORECASE,
)

RE_INPOST_LOCKER = re.compile(
    r"(?:paczkomat|locker|InPost)\s*[:\s#®]*\s*([A-Z]{2,4}\d{2,4}[A-Z]{0,3})",
    re.IGNORECASE,
)

RE_PICKUP_CODE = re.compile(
    r"(?:kod\s+odbioru|kod\s+do\s+paczkomatu|pickup\s+code)[:\s*\-–]+(\d{6})",
    re.IGNORECASE,
)

RE_ADDRESS_BLOCK = re.compile(
    r"(?:dostarczone\s+(?:na\s+)?adres|delivered\s+to|shipping\s+address|adres\s+dostawy)[:\s]+(.+?)(?:\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Generic tracking: postal format or long alphanumeric
RE_TRACKING = re.compile(r"\b([A-Z]{2}\d{9}[A-Z]{2}|\d{22,24}|[A-Z0-9]{15,30})\b")


def _extract_body(msg: Message) -> str:
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


def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result


def _parse_email_date(msg: Message) -> str:
    date_str = msg.get("Date", "")
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


class AmazonParser:
    @staticmethod
    def parse(msg: Message) -> Optional[ParsedPackage]:
        from_header = msg.get("From", "")
        subject = _decode_header(msg.get("Subject", ""))

        if not RE_SENDER.search(from_header):
            return None

        # Log unmatched Amazon emails for later pattern improvements
        if not RE_SUBJECT.search(subject):
            logger.debug("Amazon email from %s not matched by subject trigger: %s", from_header, subject)
            return None

        body = _extract_body(msg)
        combined = subject + "\n" + body
        email_date = _parse_email_date(msg)

        # Check if delivered to InPost locker
        locker_match = RE_INPOST_LOCKER.search(combined)
        locker_id = locker_match.group(1).upper() if locker_match else None
        status = "pickup_ready" if locker_id else "delivered"

        # Pickup code (only relevant if InPost locker)
        pickup_code = None
        if locker_id:
            pm = RE_PICKUP_CODE.search(combined)
            if pm:
                pickup_code = pm.group(1)

        # Extract order number as primary tracking key
        order_match = RE_ORDER_NUMBER.search(combined)
        if order_match:
            tracking_number = "amazon_" + order_match.group(1)
        else:
            # Fallback: generic tracking number from body
            tracking_match = RE_TRACKING.search(body)
            if tracking_match:
                tracking_number = tracking_match.group(1)
            else:
                date_part = email_date[:10].replace("-", "")
                tracking_number = f"amazon_{date_part}_{abs(hash(subject)) % 100000:05d}"

        # Extract delivery address
        raw_address = None
        addr_match = RE_ADDRESS_BLOCK.search(combined)
        if addr_match:
            raw_address = " ".join(addr_match.group(1).split())[:500]

        logger.info("Amazon package parsed: tracking=%s locker=%s status=%s", tracking_number, locker_id, status)

        return ParsedPackage(
            source="amazon",
            tracking_number=tracking_number,
            carrier="amazon",
            status=status,
            email_subject=subject,
            email_date=email_date,
            locker_id=locker_id,
            pickup_code=pickup_code,
            raw_address=raw_address,
        )
