import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from bot import config
from bot.goals import get_goals_due_for_checkin, mark_jobs_sent

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot_instance = None
_send_checkin_callback = None


def setup(bot_instance, send_checkin_cb):
    global _scheduler, _bot_instance, _send_checkin_callback
    _bot_instance = bot_instance
    _send_checkin_callback = send_checkin_cb

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _process_pending_checkins,
        IntervalTrigger(seconds=config.CHECKIN_INTERVAL_SECONDS),
        id="process_checkins",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started with %ss interval", config.CHECKIN_INTERVAL_SECONDS)


def add_digest_job(callback, day: str = "sun", hour: int = 9):
    if not _scheduler:
        logger.warning("Scheduler not initialized, cannot add digest job")
        return
    cron_day = day.lower()[:3]
    _scheduler.add_job(
        callback,
        CronTrigger(day_of_week=cron_day, hour=hour),
        id="weekly_digest",
        replace_existing=True,
    )
    logger.info("Digest scheduled for %s at %d:00", day, hour)


async def _process_pending_checkins():
    try:
        jobs = await get_goals_due_for_checkin()
        if not jobs:
            return

        goal_ids = [j["goal_id"] for j in jobs]
        await mark_jobs_sent(goal_ids)

        for job in jobs:
            if _send_checkin_callback:
                try:
                    job["_bot"] = _bot_instance
                    await _send_checkin_callback(job)
                except Exception as e:
                    logger.error("Failed to send check-in for goal %s: %s", job["goal_id"], e)
    except Exception as e:
        logger.error("Error in check-in processor: %s", e)


async def shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)


async def schedule_next_checkin(
    goal_id: int,
    discord_id: str,
    interval_days: int,
    checkin_hour: int,
    timezone: str,
):
    from datetime import datetime, timedelta, timezone as tz
    from bot.database import get_db

    try:
        import zoneinfo
        user_tz = zoneinfo.ZoneInfo(timezone)
    except Exception:
        user_tz = tz.utc

    now_local = datetime.now(user_tz)
    next_date = now_local.date()

    if now_local.hour >= checkin_hour:
        next_date += timedelta(days=interval_days)

    next_local = datetime(
        next_date.year, next_date.month, next_date.day,
        checkin_hour, 0, 0, tzinfo=user_tz,
    )
    next_utc = next_local.astimezone(tz.utc)

    db = await get_db()
    await db.execute(
        "INSERT INTO scheduled_jobs (goal_id, discord_id, scheduled_for) VALUES (?, ?, ?)",
        (goal_id, discord_id, next_utc.strftime("%Y-%m-%d %H:%M:%S")),
    )
    await db.commit()
