import logging

import discord
from discord.ext import commands

from bot import config, scheduler
from bot.cogs.checkins import send_checkin_dm, send_deadline_dm
from bot.cogs.social import generate_digest
from bot.database import close_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True


class BuddyBot(commands.Bot):
    async def setup_hook(self):
        await get_db()

        scheduler.setup(self, send_checkin_dm, send_deadline_dm)
        scheduler.add_digest_job(lambda: generate_digest(self))

        for ext in ("setup", "goals", "checkins", "social"):
            await self.load_extension(f"bot.cogs.{ext}")

        await self.tree.sync()
        logger.info("Commands synced")

    async def on_ready(self):
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your goals | /goal",
            )
        )

    async def close(self):
        await scheduler.shutdown()
        await close_db()
        await super().close()


bot = BuddyBot(command_prefix="!", intents=intents)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Command on cooldown. Try again in {error.retry_after:.0f}s.",
            ephemeral=True,
        )
    elif isinstance(error, discord.app_commands.CheckFailure):
        await interaction.response.send_message(
            "You don't have permission to use this command.", ephemeral=True
        )
    else:
        logger.exception("Command error: %s", error)
        try:
            await interaction.response.send_message(
                "Something went wrong. Please try again later.", ephemeral=True
            )
        except Exception:
            pass


if __name__ == "__main__":
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env")
        raise SystemExit(1)
    bot.run(config.BOT_TOKEN)
