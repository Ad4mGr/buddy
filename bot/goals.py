from datetime import date, datetime
from typing import Optional

from bot.database import get_db


async def create_goal(
    discord_id: str,
    server_id: str,
    title: str,
    description: Optional[str],
    category: str,
    frequency: str,
    interval_days: int,
    checkin_hour: int,
    end_date: Optional[str],
    stake_miss_count: Optional[int],
    stake_role_id: Optional[str],
    stake_public_shame: bool,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO goals
           (discord_id, server_id, title, description, category,
            frequency, interval_days, checkin_hour, end_date,
            stake_miss_count, stake_role_id, stake_public_shame)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            discord_id, server_id, title, description, category,
            frequency, interval_days, checkin_hour, end_date,
            stake_miss_count, stake_role_id, stake_public_shame,
        ),
    )
    goal_id = cursor.lastrowid

    await db.execute(
        "INSERT INTO streaks (goal_id) VALUES (?)", (goal_id,)
    )
    await db.commit()
    return goal_id


async def get_goal(goal_id: int) -> Optional[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT g.*, s.current_streak, s.longest_streak,
                  s.last_checkin_date, u.timezone, u.freeze_tokens
           FROM goals g
           LEFT JOIN streaks s ON s.goal_id = g.id
           JOIN users u ON u.discord_id = g.discord_id
           WHERE g.id = ?""",
        (goal_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_user_goals(
    discord_id: str, status: Optional[str] = "active"
) -> list[dict]:
    db = await get_db()
    query = """SELECT g.*, s.current_streak, s.longest_streak,
                      s.last_checkin_date
               FROM goals g
               LEFT JOIN streaks s ON s.goal_id = g.id
               WHERE g.discord_id = ?"""
    params: list = [discord_id]
    if status:
        query += " AND g.status = ?"
        params.append(status)
    query += " ORDER BY g.created_at DESC"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_server_goals(
    server_id: str, status: Optional[str] = "active"
) -> list[dict]:
    db = await get_db()
    query = """SELECT g.*, s.current_streak, s.longest_streak,
                      s.last_checkin_date
               FROM goals g
               LEFT JOIN streaks s ON s.goal_id = g.id
               WHERE g.server_id = ?"""
    params: list = [server_id]
    if status:
        query += " AND g.status = ?"
        params.append(status)
    query += " ORDER BY s.current_streak DESC"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_goal(goal_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    db = await get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [goal_id]
    cursor = await db.execute(
        f"UPDATE goals SET {sets} WHERE id = ?", values
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_goal(goal_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    await db.commit()
    return cursor.rowcount > 0


async def complete_goal(goal_id: int, achieved: bool = True) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE goals SET status = 'completed', end_date = date('now') WHERE id = ? AND status = 'active'",
        (goal_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_goals_due_for_checkin() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT g.*, u.discord_id AS user_id, u.timezone, u.freeze_tokens,
                  s.current_streak
           FROM scheduled_jobs sj
           JOIN goals g ON g.id = sj.goal_id
           JOIN users u ON u.discord_id = g.discord_id
           LEFT JOIN streaks s ON s.goal_id = g.id
           WHERE sj.status = 'pending'
             AND sj.scheduled_for <= datetime('now')
           ORDER BY sj.scheduled_for ASC""",
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def mark_jobs_sent(goal_ids: list[int]):
    db = await get_db()
    placeholders = ", ".join("?" for _ in goal_ids)
    await db.execute(
        f"UPDATE scheduled_jobs SET status = 'sent' WHERE goal_id IN ({placeholders}) AND status = 'pending'",
        goal_ids,
    )
    await db.commit()
