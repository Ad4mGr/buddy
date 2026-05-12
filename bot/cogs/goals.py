import discord
from discord import app_commands
from discord.ext import commands

from bot.goals import create_goal, get_goal, get_user_goals, delete_goal, complete_goal
from bot.checkins import get_checkin_history
from bot.scheduler import schedule_next_checkin
from bot.database import get_db

CATEGORIES = [
    app_commands.Choice(name="Fitness", value="fitness"),
    app_commands.Choice(name="Study", value="study"),
    app_commands.Choice(name="Coding", value="coding"),
    app_commands.Choice(name="Habit", value="habit"),
    app_commands.Choice(name="Creative", value="creative"),
    app_commands.Choice(name="Other", value="other"),
]

FREQUENCIES = [
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Every 2 days", value="every_2_days"),
    app_commands.Choice(name="Weekly", value="weekly"),
]


class GoalsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="goal", description="Set a new accountability goal")
    @app_commands.describe(
        title="What's your goal?",
        description="Optional details about your goal",
        category="Category for your goal",
        frequency="How often to check in",
        checkin_hour="Hour to receive check-in DM (0-23, default 21=9PM)",
        end_date="Deadline (YYYY-MM-DD)",
        stake_miss_count="Miss this many check-ins and face the stake",
    )
    @app_commands.choices(category=CATEGORIES, frequency=FREQUENCIES)
    async def goal_set(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str = None,
        category: str = "other",
        frequency: str = "daily",
        checkin_hour: int = 21,
        end_date: str = None,
        stake_miss_count: int = None,
    ):
        await interaction.response.defer(ephemeral=True)

        interval_days = {"daily": 1, "every_2_days": 2, "weekly": 7}.get(frequency, 1)
        discord_id = str(interaction.user.id)

        db = await get_db()
        row = await db.execute(
            "SELECT timezone FROM users WHERE discord_id = ?", (discord_id,)
        )
        user = await row.fetchone()
        if not user:
            await db.execute(
                "INSERT INTO users (discord_id, username) VALUES (?, ?)",
                (discord_id, interaction.user.name),
            )
            await db.commit()
            timezone = "UTC"
        else:
            timezone = user["timezone"]

        goal_id = await create_goal(
            discord_id=discord_id,
            server_id=str(interaction.guild_id),
            title=title,
            description=description,
            category=category,
            frequency=frequency,
            interval_days=interval_days,
            checkin_hour=checkin_hour,
            end_date=end_date,
            stake_miss_count=stake_miss_count,
            stake_role_id=None,
            stake_public_shame=False,
        )

        await schedule_next_checkin(goal_id, discord_id, interval_days, checkin_hour, timezone)

        embed = discord.Embed(
            title="Goal Set! 🎯",
            description=f"**{title}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Category", value=category.capitalize(), inline=True)
        embed.add_field(name="Frequency", value=frequency.replace("_", " ").title(), inline=True)
        embed.add_field(name="Check-in time", value=f"{checkin_hour}:00 your time", inline=True)
        if end_date:
            embed.add_field(name="Deadline", value=end_date, inline=True)
        if stake_miss_count:
            embed.add_field(name="Stake", value=f"Miss {stake_miss_count} check-ins → penalty", inline=True)
        embed.set_footer(text="You'll get a DM when it's time to check in!")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="goals", description="List your active goals")
    async def goal_list(self, interaction: discord.Interaction):
        goals = await get_user_goals(str(interaction.user.id), status="active")

        if not goals:
            await interaction.response.send_message(
                "You have no active goals. Use `/goal` to set one!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Your Goals",
            color=discord.Color.blue(),
        )
        for g in goals:
            streak = g["current_streak"]
            streak_str = f"🔥 {streak} day{'s' if streak != 1 else ''}" if streak > 0 else "Not started"
            embed.add_field(
                name=f"{g['title']} ({g['category']})",
                value=f"Streak: {streak_str}\nFrequency: {g['frequency'].replace('_', ' ')}\nID: `{g['id']}`",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="goal-delete", description="Delete a goal")
    @app_commands.describe(goal_id="ID of the goal to delete (use /goals to find it)")
    async def goal_delete(self, interaction: discord.Interaction, goal_id: int):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            await interaction.response.send_message("Goal not found or not yours!", ephemeral=True)
            return

        await delete_goal(goal_id)
        await interaction.response.send_message(f"Goal **{goal['title']}** deleted.", ephemeral=True)

    @app_commands.command(name="goal-complete", description="Mark a goal as completed")
    @app_commands.describe(
        goal_id="ID of the goal to complete",
        achieved="Did you achieve your goal?",
    )
    async def goal_complete(
        self,
        interaction: discord.Interaction,
        goal_id: int,
        achieved: bool = True,
    ):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            await interaction.response.send_message("Goal not found or not yours!", ephemeral=True)
            return

        await complete_goal(goal_id, achieved)

        embed = discord.Embed(
            title="Goal Completed! 🏆",
            description=f"**{goal['title']}**",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Achieved", value="✅ Yes!" if achieved else "Not this time", inline=True)
        embed.add_field(name="Final streak", value=f"{goal['current_streak']} days", inline=True)

        if achieved:
            channel_id = None
            row = await (await get_db()).execute(
                "SELECT accountability_channel_id FROM server_config WHERE server_id = ?",
                (str(interaction.guild_id),),
            )
            cfg = await row.fetchone()
            if cfg and cfg["accountability_channel_id"]:
                channel_id = cfg["accountability_channel_id"]

            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(
                        f"🎉 {interaction.user.mention} completed their goal **{goal['title']}**! "
                        f"Final streak: {goal['current_streak']} days!"
                    )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="goal-status", description="View detailed status of a goal")
    @app_commands.describe(goal_id="ID of the goal")
    async def goal_status(self, interaction: discord.Interaction, goal_id: int):
        goal = await get_goal(goal_id)
        if not goal:
            await interaction.response.send_message("Goal not found!", ephemeral=True)
            return

        checkins = await get_checkin_history(goal_id, limit=10)

        embed = discord.Embed(
            title=goal["title"],
            description=goal.get("description") or "",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Category", value=goal["category"].capitalize(), inline=True)
        embed.add_field(name="Frequency", value=goal["frequency"].replace("_", " ").title(), inline=True)
        embed.add_field(name="Status", value=goal["status"].capitalize(), inline=True)
        embed.add_field(name="Current Streak", value=f"🔥 {goal['current_streak']} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"🏆 {goal['longest_streak']} days", inline=True)
        embed.add_field(name="Freeze Tokens", value=f"🧊 {goal.get('freeze_tokens', 0)}", inline=True)

        if checkins:
            recent = "\n".join(
                f"• **{c['status'].capitalize()}** — {c['checked_at'][:10]}"
                + (f" — *{c['note']}*" if c.get("note") else "")
                for c in checkins[:5]
            )
            embed.add_field(name="Recent Check-ins", value=recent or "None yet", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GoalsCog(bot))
