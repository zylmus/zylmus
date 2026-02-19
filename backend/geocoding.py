import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

from backend.parsers import ParsedPackage

logger = logging.getLogger(__name__)

INPOST_API_BASE = "https://api-pl-points.easypack24.net/v1/points"
USER_AGENT = "zylmus/1.0 (self-hosted package tracker)"
CACHE_TTL_DAYS = 30


async def _fetch_inpost_locker(locker_id: str) -> Optional[dict]:
    """Fetch locker coordinates from InPost public API."""
    url = f"{INPOST_API_BASE}/{locker_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                loc = data.get("location", {})
                addr = data.get("address", {})
                addr_details = data.get("address_details", {})
                lat = loc.get("latitude")
                lon = loc.get("longitude")
                if lat is None or lon is None:
                    return None
                line1 = addr.get("line1", "")
                line2 = addr.get("line2", "")
                city = addr_details.get("city", "")
                post_code = addr_details.get("post_code", "")
                address_display = ", ".join(filter(None, [line1, line2, post_code, city]))
                return {"lat": lat, "lon": lon, "address": address_display}
            else:
                logger.warning("InPost API returned %s for locker %s", resp.status_code, locker_id)
    except Exception as e:
        logger.warning("InPost API error for locker %s: %s", locker_id, e)
    return None


_geocoder_instance = None
_geocode_func = None


def _get_geocoder():
    global _geocoder_instance, _geocode_func
    if _geocoder_instance is None:
        _geocoder_instance = Nominatim(user_agent=USER_AGENT)
        _geocode_func = RateLimiter(_geocoder_instance.geocode, min_delay_seconds=1)
    return _geocode_func


def _geocode_address_sync(address: str) -> Optional[dict]:
    """Synchronous geocoding via Nominatim (call inside asyncio.to_thread)."""
    geocode = _get_geocoder()
    try:
        result = geocode(address, addressdetails=False, language="pl")
        if result:
            return {"lat": result.latitude, "lon": result.longitude}
    except Exception as e:
        logger.warning("Nominatim geocoding failed for '%s': %s", address, e)
    return None


async def resolve_coordinates(parsed: ParsedPackage, db) -> Optional[dict]:
    """
    Resolve lat/lon for a parsed package.
    Returns dict with 'lat', 'lon', and optionally 'address'.
    Uses LockerGeoCache for InPost lockers.
    """
    from backend.models import LockerGeoCache
    import asyncio

    if parsed.locker_id:
        locker_id = parsed.locker_id.upper()

        # Check cache
        cached = db.query(LockerGeoCache).filter_by(locker_id=locker_id).first()
        if cached:
            age = datetime.utcnow() - cached.cached_at
            if age < timedelta(days=CACHE_TTL_DAYS):
                return {"lat": cached.lat, "lon": cached.lon, "address": cached.address_display}

        # Fetch from InPost API
        result = await _fetch_inpost_locker(locker_id)
        if result:
            # Update cache
            if cached:
                cached.lat = result["lat"]
                cached.lon = result["lon"]
                cached.address_display = result["address"]
                cached.cached_at = datetime.utcnow()
            else:
                db.add(LockerGeoCache(
                    locker_id=locker_id,
                    lat=result["lat"],
                    lon=result["lon"],
                    address_display=result["address"],
                    cached_at=datetime.utcnow(),
                ))
            db.commit()
            return result

    if parsed.raw_address:
        result = await asyncio.to_thread(_geocode_address_sync, parsed.raw_address)
        if result:
            result["address"] = parsed.raw_address
            return result

    return None
