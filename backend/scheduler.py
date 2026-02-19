import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

POLL_INTERVAL_MINUTES = 5


def start_scheduler():
    from backend.email_poller import poll_and_geocode, set_next_scheduled

    trigger = IntervalTrigger(minutes=POLL_INTERVAL_MINUTES)
    scheduler.add_job(
        poll_and_geocode,
        trigger=trigger,
        id="email_poll",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()

    job = scheduler.get_job("email_poll")
    if job and job.next_run_time:
        set_next_scheduled(job.next_run_time)

    logger.info("Scheduler started. Email polling every %d minutes.", POLL_INTERVAL_MINUTES)


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def get_next_run() -> str | None:
    job = scheduler.get_job("email_poll")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
