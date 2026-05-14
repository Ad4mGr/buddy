from datetime import date
from typing import Optional

from bot.database import get_db


MILESTONES = [7, 30, 100]


async def update_streak(goal_id: int, checkin_status: str):
    db = await get_db()
    today = date.today().isoformat()

    row = await db.execute(
        "SELECT current_streak, longest_streak, last_checkin_date FROM streaks WHERE goal_id = ?",
        (goal_id,),
    )
    streak = await row.fetchone()
    if not streak:
        return

    current = streak["current_streak"]
    longest = streak["longest_streak"]
    last_date = streak["last_checkin_date"]

    if checkin_status == "done":
        if last_date == today:
            return
        new_streak = current + 1
        new_longest = max(longest, new_streak)
        await db.execute(
            """UPDATE streaks
               SET current_streak = ?, longest_streak = ?,
                   last_checkin_date = ?, updated_at = datetime('now')
               WHERE goal_id = ?""",
            (new_streak, new_longest, today, goal_id),
        )
    elif checkin_status == "missed":
        await db.execute(
            """UPDATE streaks
               SET current_streak = 0, last_checkin_date = ?,
                   updated_at = datetime('now')
               WHERE goal_id = ?""",
            (today, goal_id),
        )
    elif checkin_status == "skipped":
        await db.execute(
            """UPDATE streaks
               SET last_checkin_date = ?, updated_at = datetime('now')
               WHERE goal_id = ?""",
            (today, goal_id),
        )

    await db.commit()


async def check_milestone(goal_id: int) -> Optional[int]:
    db = await get_db()
    row = await db.execute(
        "SELECT current_streak FROM streaks WHERE goal_id = ?",
        (goal_id,),
    )
    streak = await row.fetchone()
    if not streak:
        return None

    cs = streak["current_streak"]
    if cs not in MILESTONES:
        return None

    already = await db.execute(
        "SELECT 1 FROM milestones WHERE goal_id = ? AND streak_count = ?",
        (goal_id, cs),
    )
    if await already.fetchone():
        return None

    await db.execute(
        "INSERT INTO milestones (goal_id, streak_count) VALUES (?, ?)",
        (goal_id, cs),
    )
    await db.commit()
    return cs


async def get_leaderboard(server_id: str, limit: int = 20) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT g.id, g.discord_id, g.title, g.category,
                  s.current_streak, s.longest_streak
           FROM goals g
           JOIN streaks s ON s.goal_id = g.id
           WHERE g.server_id = ? AND g.status = 'active'
           ORDER BY s.current_streak DESC
           LIMIT ?""",
        (server_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
