import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Package

logger = logging.getLogger(__name__)
router = APIRouter()

OSRM_BASE = "https://router.project-osrm.org/trip/v1/driving"
USER_AGENT = "zylmus/1.0"


class RouteRequest(BaseModel):
    user_lat: float
    user_lon: float


class WaypointInfo(BaseModel):
    package_id: int
    locker_id: Optional[str] = None
    address_display: Optional[str] = None
    lat: float
    lon: float
    pickup_code: Optional[str] = None
    source: str


class RouteResponse(BaseModel):
    ordered_packages: List[WaypointInfo]
    total_distance_km: float
    total_duration_min: float
    geometry: dict  # GeoJSON LineString


@router.post("", response_model=RouteResponse)
async def calculate_route(body: RouteRequest, db: Session = Depends(get_db)):
    # Get all pickup_ready packages with coordinates
    packages = db.query(Package).filter(
        Package.status == "pickup_ready",
        Package.lat.isnot(None),
        Package.lon.isnot(None),
    ).all()

    if not packages:
        raise HTTPException(status_code=404, detail="No pickup-ready packages with known coordinates")

    # Build coordinate string: user first, then packages
    coords_list = [(body.user_lon, body.user_lat)]
    for pkg in packages:
        coords_list.append((pkg.lon, pkg.lat))

    coords_str = ";".join(f"{lon},{lat}" for lon, lat in coords_list)
    url = (
        f"{OSRM_BASE}/{coords_str}"
        "?roundtrip=false&source=first&destination=last"
        "&steps=false&geometries=geojson&overview=full"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error("OSRM request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Routing service error: {e}")

    if data.get("code") != "Ok" or not data.get("trips"):
        raise HTTPException(status_code=502, detail="OSRM returned no route")

    trip = data["trips"][0]
    total_distance_km = trip["distance"] / 1000
    total_duration_min = trip["duration"] / 60
    geometry = trip["geometry"]  # GeoJSON LineString

    # OSRM returns waypoints in optimized order
    # waypoints[0] = user location, waypoints[1..n] = packages in optimal order
    osrm_waypoints = data.get("waypoints", [])

    # Build ordered package list based on OSRM waypoint_index
    # waypoint_index tells us the position of each input point in the optimized trip
    pkg_waypoints = osrm_waypoints[1:]  # skip user location
    ordered = sorted(zip(pkg_waypoints, packages), key=lambda x: x[0].get("waypoint_index", 0))

    ordered_packages = []
    for _, pkg in ordered:
        ordered_packages.append(WaypointInfo(
            package_id=pkg.id,
            locker_id=pkg.locker_id,
            address_display=pkg.address_display,
            lat=pkg.lat,
            lon=pkg.lon,
            pickup_code=pkg.pickup_code,
            source=pkg.source,
        ))

    return RouteResponse(
        ordered_packages=ordered_packages,
        total_distance_km=round(total_distance_km, 2),
        total_duration_min=round(total_duration_min, 1),
        geometry=geometry,
    )
