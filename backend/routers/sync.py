import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks

from backend.email_poller import poll_and_geocode, get_sync_state
from backend.scheduler import get_next_run

logger = logging.getLogger(__name__)
router = APIRouter()

_sync_running = False


async def _run_sync():
    global _sync_running
    _sync_running = True
    try:
        await poll_and_geocode()
    finally:
        _sync_running = False


@router.post("")
async def trigger_sync(background_tasks: BackgroundTasks):
    if _sync_running:
        return {"message": "Sync already in progress", "queued": False}
    background_tasks.add_task(_run_sync)
    return {
        "message": "Sync started",
        "queued": True,
        "started_at": datetime.utcnow().isoformat(),
    }


@router.get("/status")
def sync_status():
    state = get_sync_state()
    state["next_scheduled_at"] = get_next_run()
    state["is_running"] = _sync_running
    return state
