from datetime import date, datetime
from typing import Optional

import discord

from bot import config
from bot.database import get_db
from bot.streaks import update_streak


async def record_checkin(
    goal_id: int,
    discord_id: str,
    status: str,
    note: Optional[str] = None,
) -> int:
    if status == "done" and await already_checked_in_today(goal_id):
        return -1

    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO checkins (goal_id, discord_id, status, note) VALUES (?, ?, ?, ?)",
        (goal_id, discord_id, status, note),
    )
    checkin_id = cursor.lastrowid
    await update_streak(goal_id, status)
    await db.commit()
    return checkin_id


async def already_checked_in_today(goal_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        """SELECT 1 FROM checkins
           WHERE goal_id = ? AND date(checked_at) = date('now') AND status = 'done'
           LIMIT 1""",
        (goal_id,),
    )
    return await cursor.fetchone() is not None


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


async def grant_freeze_token(discord_id: str, amount: int = 1):
    db = await get_db()
    await db.execute(
        "UPDATE users SET freeze_tokens = freeze_tokens + ? WHERE discord_id = ?",
        (amount, discord_id),
    )
    await db.commit()


async def get_consecutive_misses(goal_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        """SELECT status FROM checkins
           WHERE goal_id = ?
           ORDER BY checked_at DESC, id DESC LIMIT 100""",
        (goal_id,),
    )
    rows = await cursor.fetchall()
    count = 0
    for r in rows:
        if r["status"] == "missed":
            count += 1
        elif r["status"] == "done" or r["status"] == "skipped":
            break
    return count


async def check_stake(goal_id: int) -> Optional[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT g.stake_miss_count, g.stake_role_id, g.stake_public_shame,
                  g.discord_id, g.server_id, g.title
           FROM goals g WHERE g.id = ? AND g.stake_miss_count IS NOT NULL""",
        (goal_id,),
    )
    goal = await cursor.fetchone()
    if not goal:
        return None

    misses = await get_consecutive_misses(goal_id)
    if misses < goal["stake_miss_count"]:
        return None

    return {
        "goal_id": goal_id,
        "discord_id": goal["discord_id"],
        "server_id": goal["server_id"],
        "title": goal["title"],
        "stake_role_id": goal["stake_role_id"],
        "stake_public_shame": bool(goal["stake_public_shame"]),
    }


async def get_checkin_history(goal_id: int, limit: int = 30) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM checkins WHERE goal_id = ? ORDER BY checked_at DESC LIMIT ?",
        (goal_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_checkin_stats(goal_id: int) -> dict:
    db = await get_db()
    cursor = await db.execute(
        """SELECT status, COUNT(*) as cnt FROM checkins
           WHERE goal_id = ? GROUP BY status""",
        (goal_id,),
    )
    rows = await cursor.fetchall()
    total = 0
    done = 0
    for r in rows:
        total += r["cnt"]
        if r["status"] == "done":
            done = r["cnt"]
    consistency = round((done / total * 100), 1) if total > 0 else 0.0
    return {"total": total, "done": done, "missed": total - done, "consistency": consistency}


async def get_recent_checkins_for_server(server_id: str, limit: int = 50) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT c.*, g.title, g.discord_id AS goal_owner
           FROM checkins c
           JOIN goals g ON g.id = c.goal_id
           WHERE g.server_id = ? AND g.status = 'active'
           ORDER BY c.checked_at DESC LIMIT ?""",
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


async def post_to_accountability_channel(
    bot, goal_id: int, server_id: str, content: str, embed: Optional[discord.Embed] = None
):
    db = await get_db()
    row = await db.execute(
        "SELECT accountability_channel_id FROM server_config WHERE server_id = ?",
        (server_id,),
    )
    cfg = await row.fetchone()
    if not cfg or not cfg["accountability_channel_id"]:
        return
    channel = bot.get_channel(int(cfg["accountability_channel_id"]))
    if not channel:
        return
    kwargs = {"content": content}
    if embed:
        kwargs["embed"] = embed
    await channel.send(**kwargs)
