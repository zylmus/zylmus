from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedPackage:
    source: str               # "inpost" | "amazon"
    tracking_number: str      # unique identifier / dedup key
    carrier: str              # "inpost" | "dhl" | "ups" | "amazon" | ...
    status: str               # "pickup_ready" | "delivered" | "in_transit"
    email_subject: str
    email_date: str           # ISO-format string from email header
    locker_id: Optional[str] = None    # e.g. "WAW01N"
    pickup_code: Optional[str] = None  # 6-digit string
    raw_address: Optional[str] = None  # free-text address for geocoding
