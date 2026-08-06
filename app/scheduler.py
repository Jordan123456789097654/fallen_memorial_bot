"""
APScheduler Job Scheduler for Automated News Scans, Daily Roll Call, and Keep-Alive Self-Pings.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app.config import settings
from app.scanner import scan_news_sources, self_ping_keep_alive, daily_moment_of_silence
from app.utils.logger import logger

scheduler = AsyncIOScheduler()


def start_scheduler(bot=None):
    """Starts background APScheduler jobs."""
    if scheduler.running:
        return

    # Interval Job for Automated News Scans (Every 3 hours)
    scheduler.add_job(
        scan_news_sources,
        trigger=IntervalTrigger(hours=settings.SCAN_INTERVAL_HOURS),
        kwargs={"bot": bot},
        id="scan_news_job",
        replace_existing=True
    )

    # Daily Moment of Silence & Roll Call Check (Every morning at 08:00 AM)
    scheduler.add_job(
        daily_moment_of_silence,
        trigger=CronTrigger(hour=8, minute=0),
        kwargs={"bot": bot},
        id="daily_roll_call_job",
        replace_existing=True
    )

    # 1-Minute Public Keep-Alive Worker to prevent Render Web App spin-down
    scheduler.add_job(
        self_ping_keep_alive,
        trigger=IntervalTrigger(minutes=1),
        id="keep_alive_job",
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"APScheduler started. News scan: {settings.SCAN_INTERVAL_HOURS}h | Daily Roll Call: 08:00 AM | Keep-Alive: 1m")


def stop_scheduler():
    """Stops background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped.")
