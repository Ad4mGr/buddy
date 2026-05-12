import discord
from discord import app_commands
from discord.ext import commands

from bot.database import get_db


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configure the bot for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        accountability_channel: discord.TextChannel = None,
        digest_channel: discord.TextChannel = None,
        digest_day: str = "sunday",
        digest_hour: int = 9,
        shame_pings: bool = False,
    ):
        db = await get_db()
        await db.execute(
            """INSERT INTO server_config
               (server_id, accountability_channel_id, digest_channel_id,
                digest_day, digest_hour, shame_pings_enabled)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(server_id) DO UPDATE SET
               accountability_channel_id = COALESCE(excluded.accountability_channel_id, accountability_channel_id),
               digest_channel_id = COALESCE(excluded.digest_channel_id, digest_channel_id),
               digest_day = COALESCE(excluded.digest_day, digest_day),
               digest_hour = COALESCE(excluded.digest_hour, digest_hour),
               shame_pings_enabled = COALESCE(excluded.shame_pings_enabled, shame_pings_enabled)""",
            (
                str(interaction.guild_id),
                str(accountability_channel.id) if accountability_channel else None,
                str(digest_channel.id) if digest_channel else None,
                digest_day,
                digest_hour,
                int(shame_pings),
            ),
        )
        await db.commit()

        parts = ["Bot setup complete!"]
        if accountability_channel:
            parts.append(f"Accountability updates → {accountability_channel.mention}")
        if digest_channel:
            parts.append(f"Weekly digest → {digest_channel.mention} ({digest_day}s at {digest_hour}:00)")
        if shame_pings:
            parts.append("Shame pings enabled")
        await interaction.response.send_message("\n".join(parts), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
