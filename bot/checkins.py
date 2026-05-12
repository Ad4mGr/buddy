from datetime import date, datetime
from typing import Optional

from bot import config
from bot.database import get_db
from bot.streaks import update_streak


async def record_checkin(
    goal_id: int,
    discord_id: str,
    status: str,
    note: Optional[str] = None,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO checkins (goal_id, discord_id, status, note)
           VALUES (?, ?, ?, ?)""",
        (goal_id, discord_id, status, note),
    )
    checkin_id = cursor.lastrowid
    await update_streak(goal_id, status)
    await db.commit()
    return checkin_id


async def use_freeze_token(discord_id: str, goal_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "SELECT freeze_tokens FROM users WHERE discord_id = ?",
        (discord_id,),
    )
    row = await cursor.fetchone()
    if not row or row["freeze_tokens"] <= 0:
        return False

    await db.execute(
        "UPDATE users SET freeze_tokens = freeze_tokens - 1 WHERE discord_id = ?",
        (discord_id,),
    )
    await record_checkin(goal_id, discord_id, "skipped", "Used freeze token")
    await db.commit()
    return True


async def get_checkin_history(
    goal_id: int, limit: int = 30
) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT * FROM checkins
           WHERE goal_id = ?
           ORDER BY checked_at DESC
           LIMIT ?""",
        (goal_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_recent_checkins_for_server(
    server_id: str, limit: int = 50
) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT c.*, g.title, g.discord_id AS goal_owner
           FROM checkins c
           JOIN goals g ON g.id = c.goal_id
           WHERE g.server_id = ? AND g.status = 'active'
           ORDER BY c.checked_at DESC
           LIMIT ?""",
        (server_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def add_cheer(checkin_id: int, cheerer_id: str) -> bool:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO cheers (checkin_id, cheerer_id) VALUES (?, ?)",
            (checkin_id, cheerer_id),
        )
        await db.commit()
        return True
    except Exception:
        return False


async def get_cheer_count(checkin_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM cheers WHERE checkin_id = ?",
        (checkin_id,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def expire_old_scheduled_jobs():
    db = await get_db()
    await db.execute(
        """UPDATE scheduled_jobs
           SET status = 'expired'
           WHERE status = 'sent'
             AND scheduled_for < datetime('now', ?)""",
        (f"-{config.CHECKIN_TIMEOUT_MINUTES} minutes",),
    )
    await db.commit()
