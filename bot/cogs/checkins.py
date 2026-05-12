import logging

import discord
from discord.ext import commands

from bot.checkins import record_checkin
from bot.goals import get_user_goals
from bot.streaks import check_milestone
from bot.views import CheckinView

logger = logging.getLogger(__name__)


async def send_checkin_dm(job: dict):
    bot = job.get("_bot")
    if not bot:
        logger.error("No bot instance on job")
        return

    user = bot.get_user(int(job["discord_id"]))
    if not user:
        try:
            user = await bot.fetch_user(int(job["discord_id"]))
        except Exception:
            logger.warning("Could not fetch user %s", job["discord_id"])
            return

    goal_id = job["goal_id"]
    goal_title = job["title"]
    view = CheckinView(goal_id=goal_id, goal_title=goal_title)

    embed = discord.Embed(
        title="⏰ Check-in Time!",
        description=f"Did you work on **{goal_title}** today?",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Respond within the hour or it counts as missed!")

    try:
        await user.send(embed=embed, view=view)
    except discord.Forbidden:
        logger.warning("Cannot DM user %s", job["discord_id"])


class CheckinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        content = message.content.strip().lower()
        discord_id = str(message.author.id)

        goals = await get_user_goals(discord_id, status="active")
        if not goals:
            await message.channel.send(
                "You don't have any active goals! Use `/goal` in a server to set one."
            )
            return

        if content in ("yes", "y", "done", "did it"):
            for g in goals:
                await record_checkin(g["id"], discord_id, "done")
                milestone = await check_milestone(g["id"])
                if milestone:
                    await self._announce_milestone(discord_id, g["title"], milestone)
            await message.channel.send(
                "Awesome, keep it up! 🔥" if len(goals) == 1
                else "Awesome, checked in for all your goals! 🔥"
            )

        elif content in ("no", "n", "missed", "didn't"):
            for g in goals:
                await record_checkin(g["id"], discord_id, "missed")
            await message.channel.send("No worries — tomorrow's a new day! 💪")

        elif content.startswith("note "):
            note = content[5:]
            for g in goals:
                await record_checkin(g["id"], discord_id, "done", note)
            await message.channel.send(f"Noted! Checked in with: {note} ✅")

        else:
            await message.channel.send(
                "Not sure what that means. Reply with **yes** or **no** to check in!"
            )

    async def _announce_milestone(self, discord_id: str, goal_title: str, days: int):
        from bot.database import get_db

        db = await get_db()
        goals = await get_user_goals(discord_id, status="active")
        goal = next((g for g in goals if g["title"] == goal_title), None)
        if not goal:
            return

        row = await db.execute(
            "SELECT accountability_channel_id FROM server_config WHERE server_id = ?",
            (goal["server_id"],),
        )
        cfg = await row.fetchone()
        if not cfg or not cfg["accountability_channel_id"]:
            return

        channel = self.bot.get_channel(int(cfg["accountability_channel_id"]))
        if not channel:
            return

        messages = {
            7: f"🔥 **{days}-DAY STREAK!** Keep the momentum going!",
            30: f"🎊 **{days}-DAY STREAK!** A whole month of consistency! You're on fire!",
            100: f"🏆 **{days}-DAY STREAK!** Triple digits! Legendary dedication!",
        }
        msg = messages.get(days, f"🎉 **{days}-day streak** on **{goal_title}**!")
        await channel.send(f"<@{discord_id}> {msg}")


async def setup(bot: commands.Bot):
    await bot.add_cog(CheckinCog(bot))
