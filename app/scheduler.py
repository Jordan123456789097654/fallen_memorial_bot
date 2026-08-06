"""
APScheduler Background Tasks Manager.
Runs news scanning every N hours and daily EOW Anniversary Reminders.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.utils.logger import logger

scheduler = AsyncIOScheduler()

def start_scheduler(bot=None):
    """Starts the background task scheduler."""
    from app.scanner import scan_news_sources, check_eow_anniversaries

    interval_hours = max(1, settings.SCAN_INTERVAL_HOURS)

    # Schedule periodic news scan job
    scheduler.add_job(
        scan_news_sources,
        'interval',
        hours=interval_hours,
        kwargs={'bot': bot},
        id='news_scanner_job',
        replace_existing=True
    )

    # Schedule daily EOW anniversary reminder job (runs at midnight UTC)
    scheduler.add_job(
        check_eow_anniversaries,
        'cron',
        hour=0,
        minute=0,
        kwargs={'bot': bot},
        id='anniversary_reminder_job',
        replace_existing=True
    )

    if not scheduler.running:
        scheduler.start()
        logger.info(f"Started background APScheduler (Scanning every {interval_hours}h, Daily Anniversary check at 00:00 UTC).")

def stop_scheduler():
    """Stops the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Stopped background APScheduler.")
