import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from bot.streaks import get_leaderboard as get_top_streaks
from bot.checkins import add_cheer, get_cheer_count, get_recent_checkins_for_server
from bot.database import get_db

logger = logging.getLogger(__name__)


class SocialCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Top streaks on this server")
    @app_commands.describe(limit="How many to show (default 10)")
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        rows = await get_top_streaks(str(interaction.guild_id), limit=min(limit, 50))

        if not rows:
            await interaction.response.send_message(
                "No active goals yet. Be the first — use `/goal`!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏆 Accountability Leaderboard",
            color=discord.Color.gold(),
        )

        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            user = interaction.guild.get_member(int(r["discord_id"]))
            name = user.display_name if user else f"<@{r['discord_id']}>"
            medal = medals[i] if i < 3 else f"{i+1}."
            streak = r["current_streak"]
            emoji = "🔥" if streak >= 30 else "⭐" if streak >= 7 else "📅"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"{emoji} **{streak} days** — {r['title']} ({r['category']})",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="cheer", description="Cheer for someone's recent check-in")
    @app_commands.describe(member="Who do you want to cheer?")
    async def cheer(self, interaction: discord.Interaction, member: discord.Member):
        checkins = await get_recent_checkins_for_server(
            str(interaction.guild_id), limit=20
        )
        target = next(
            (c for c in checkins if c["goal_owner"] == str(member.id) and c["status"] == "done"),
            None,
        )

        if not target:
            await interaction.response.send_message(
                f"No recent check-ins found for {member.display_name}.", ephemeral=True
            )
            return

        success = await add_cheer(target["id"], str(interaction.user.id))
        if success:
            await interaction.response.send_message(
                f"{interaction.user.mention} cheered for {member.display_name}'s check-in on **{target['title']}**! 🎉"
            )
        else:
            await interaction.response.send_message(
                "You already cheered this check-in!", ephemeral=True
            )

    @app_commands.command(name="profile", description="View your accountability profile card")
    async def profile(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        db = await get_db()

        user_row = await db.execute(
            "SELECT * FROM users WHERE discord_id = ?", (discord_id,)
        )
        user = await user_row.fetchone()
        if not user:
            await interaction.response.send_message(
                "No profile yet. Set a goal with `/goal` to get started!", ephemeral=True
            )
            return

        goals = await db.execute(
            """SELECT g.*, s.current_streak, s.longest_streak
               FROM goals g
               LEFT JOIN streaks s ON s.goal_id = g.id
               WHERE g.discord_id = ?
               ORDER BY g.status, s.current_streak DESC""",
            (discord_id,),
        )
        goals_list = await goals.fetchall()

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Profile",
            color=discord.Color.purple(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Freeze Tokens", value=f"🧊 {user['freeze_tokens']}", inline=True)
        embed.add_field(name="Timezone", value=user["timezone"], inline=True)

        active = [g for g in goals_list if g["status"] == "active"]
        completed = [g for g in goals_list if g["status"] == "completed"]

        if active:
            active_str = "\n".join(
                f"• **{g['title']}** — 🔥 {g['current_streak']}d (best: {g['longest_streak']}d)"
                for g in active[:5]
            )
            embed.add_field(name=f"Active Goals ({len(active)})", value=active_str, inline=False)
        else:
            embed.add_field(name="Active Goals", value="None yet", inline=False)

        if completed:
            embed.add_field(
                name="Completed Goals",
                value=f"✅ {len(completed)} goal{'s' if len(completed) != 1 else ''} completed",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set-timezone", description="Set your timezone for check-in scheduling")
    @app_commands.describe(timezone="Your timezone (e.g., US/Eastern, Europe/London, Asia/Tokyo)")
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(timezone)
        except Exception:
            await interaction.response.send_message(
                f"Invalid timezone `{timezone}`. See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                ephemeral=True,
            )
            return

        db = await get_db()
        await db.execute(
            """INSERT INTO users (discord_id, username, timezone)
               VALUES (?, ?, ?)
               ON CONFLICT(discord_id) DO UPDATE SET timezone = ?""",
            (str(interaction.user.id), interaction.user.name, timezone, timezone),
        )
        await db.commit()
        await interaction.response.send_message(
            f"Timezone set to **{timezone}** ✅", ephemeral=True
        )


async def generate_digest(bot: commands.Bot):
    db = await get_db()
    servers = await db.execute("SELECT * FROM server_config WHERE digest_channel_id IS NOT NULL")
    configs = await servers.fetchall()

    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

    for cfg in configs:
        server_id = cfg["server_id"]
        channel_id = cfg["digest_channel_id"]

        top = await get_top_streaks(server_id, limit=5)
        if not top:
            continue

        channel = bot.get_channel(int(channel_id))
        if not channel:
            continue

        embed = discord.Embed(
            title="📊 Weekly Accountability Digest",
            description="Here's how everyone did this week!",
            color=discord.Color.blue(),
        )

        top_str = "\n".join(
            f"{i+1}. <@{r['discord_id']}> — **{r['current_streak']} days** on *{r['title']}*"
            for i, r in enumerate(top)
        )
        embed.add_field(name="🔥 Top Streaks", value=top_str or "No active streaks", inline=False)

        hot = [r for r in top if r["current_streak"] >= 7]
        if hot:
            hot_str = "\n".join(
                f"• <@{r['discord_id']}> — {r['current_streak']} days on **{r['title']}**"
                for r in hot
            )
            embed.add_field(name="⭐ Hot Streaks (7+)", value=hot_str, inline=False)

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send digest to {channel_id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialCog(bot))
