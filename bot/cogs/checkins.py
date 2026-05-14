import logging

import discord
from discord.ext import commands

from bot.checkins import (
    record_checkin,
    check_stake,
    post_to_accountability_channel,
    grant_freeze_token,
)
from bot.goals import get_goal, get_user_goals
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

    view = CheckinView(goal_id=job["goal_id"], goal_title=job["title"])
    embed = discord.Embed(
        title="⏰ Check-in Time!",
        description=f"Did you work on **{job['title']}** today?",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Respond within the hour or it counts as missed!")

    try:
        await user.send(embed=embed, view=view)
    except discord.Forbidden:
        logger.warning("Cannot DM user %s", job["discord_id"])


async def send_deadline_dm(goal: dict):
    bot = goal.get("_bot")
    if not bot:
        logger.error("No bot instance on deadline goal")
        return

    user = bot.get_user(int(goal["discord_id"]))
    if not user:
        try:
            user = await bot.fetch_user(int(goal["discord_id"]))
        except Exception:
            return

    embed = discord.Embed(
        title="🎯 Goal Deadline Reached!",
        description=f"Your goal **{goal['title']}** was due today!\n"
                    f"Did you achieve it? Use `/goal-complete goal_id:{goal['id']}` to report.",
        color=discord.Color.gold(),
    )
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        logger.warning("Cannot DM user %s for deadline", goal["discord_id"])


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
            responses = []
            for g in goals:
                cid = await record_checkin(g["id"], discord_id, "done")
                if cid == -1:
                    responses.append(f"**{g['title']}**: Already checked in today ✅")
                    continue
                milestone = await check_milestone(g["id"])
                streak_msg = ""
                if milestone:
                    await grant_freeze_token(discord_id)
                    streak_msg = f" 🏆 {milestone}-day milestone! Freeze token earned!"
                responses.append(f"**{g['title']}**: Checked in!{streak_msg}")
                await self._post_update(g, "done")
            await message.channel.send("\n".join(responses))

        elif content in ("no", "n", "missed", "didn't"):
            for g in goals:
                await record_checkin(g["id"], discord_id, "missed")
                await self._post_update(g, "missed")
                await self._handle_stake(g)
            await message.channel.send("No worries — tomorrow's a new day! 💪")

        elif content.startswith("note "):
            note = content[5:]
            for g in goals:
                await record_checkin(g["id"], discord_id, "done", note)
                await self._post_update(g, "done")
            await message.channel.send(f"Noted! Checked in with: {note} ✅")

        else:
            await message.channel.send(
                "Not sure what that means. Reply with **yes** or **no** to check in!"
            )

    async def _post_update(self, goal: dict, status: str):
        emoji = "✅" if status == "done" else "❌"
        content = f"{emoji} <@{goal['discord_id']}> checked in **{status}** for **{goal['title']}**"
        if status == "done":
            content += f" (🔥 {goal['current_streak'] + 1}d streak)"
        await post_to_accountability_channel(
            self.bot, goal["id"], goal["server_id"], content,
        )

    async def _handle_stake(self, goal: dict):
        stake = await check_stake(goal["id"])
        if not stake:
            return
        guild = self.bot.get_guild(int(stake["server_id"]))
        if not guild:
            return
        if stake["stake_public_shame"]:
            content = f"⚠️ <@{stake['discord_id']}> missed their stake on **{stake['title']}**!"
            await post_to_accountability_channel(
                self.bot, goal["id"], stake["server_id"], content,
            )
        if stake["stake_role_id"]:
            member = guild.get_member(int(stake["discord_id"]))
            if member:
                role = guild.get_role(int(stake["stake_role_id"]))
                if role:
                    await member.remove_roles(role, reason="Stake: missed too many check-ins")


async def setup(bot: commands.Bot):
    await bot.add_cog(CheckinCog(bot))
