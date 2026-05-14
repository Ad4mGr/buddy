import discord
from discord import app_commands
from discord.ext import commands

from bot.goals import (
    create_goal, get_goal, get_user_goals, delete_goal,
    complete_goal, abandon_goal, update_goal,
)
from bot.checkins import get_checkin_history, get_checkin_stats
from bot.scheduler import schedule_next_checkin
from bot.database import get_db
from bot.views import GoalSelectView

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


async def goal_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
    goals = await get_user_goals(str(interaction.user.id), status="active")
    return [
        app_commands.Choice(
            name=f"{g['title']} (🔥{g['current_streak']}d, {g['category']})"[:100],
            value=g['id'],
        )
        for g in goals if current.lower() in g['title'].lower()
    ][:25]


async def require_goal(interaction: discord.Interaction, goal_id: int | None, label: str, handler):
    if goal_id is not None:
        await interaction.response.defer(ephemeral=True)
        return await handler(interaction, goal_id, from_component=False)
    goals = await get_user_goals(str(interaction.user.id), status="active")
    if not goals:
        await interaction.response.send_message(
            "You have no active goals. Use `/goal` to set one!", ephemeral=True,
        )
        return
    view = GoalSelectView(goals, interaction.user.id, label, lambda i, g: handler(i, g, from_component=True))
    await interaction.response.send_message("Select a goal:", view=view, ephemeral=True)


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
        stake_role="Role to lose if you miss the stake (select a role)",
        stake_public_shame="Public shame ping when stake is triggered",
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
        stake_role: discord.Role = None,
        stake_public_shame: bool = False,
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

        if timezone == "UTC":
            pass

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
            stake_role_id=str(stake_role.id) if stake_role else None,
            stake_public_shame=stake_public_shame,
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
            parts = [f"Miss {stake_miss_count} check-ins"]
            if stake_role:
                parts.append(f"lose {stake_role.mention}")
            if stake_public_shame:
                parts.append("public shame ping")
            embed.add_field(name="Stake", value=" → ".join(parts), inline=True)
        embed.set_footer(text="You'll get a DM when it's time to check in!")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="goals", description="List your active goals")
    async def goal_list(self, interaction: discord.Interaction):
        goals = await get_user_goals(str(interaction.user.id), status="active")
        if not goals:
            await interaction.response.send_message(
                "You have no active goals. Use `/goal` to set one!", ephemeral=True,
            )
            return
        embed = discord.Embed(title="Your Goals", color=discord.Color.blue())
        for g in goals:
            s = g["current_streak"]
            streak_str = f"🔥 {s}d" if s > 0 else "Not started"
            embed.add_field(
                name=f"{g['title']} ({g['category']})",
                value=f"Streak: {streak_str}  |  ID: `{g['id']}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Status ──────────────────────────────────────────────

    @app_commands.command(name="goal-status", description="View detailed status of a goal")
    @app_commands.autocomplete(goal_id=goal_autocomplete)
    async def goal_status(self, interaction: discord.Interaction, goal_id: int = None):
        await require_goal(interaction, goal_id, "view", self._show_goal_status)

    async def _show_goal_status(self, interaction: discord.Interaction, goal_id: int, from_component: bool = False):
        goal = await get_goal(goal_id)
        if not goal:
            if from_component:
                await interaction.response.edit_message(content="Goal not found.", embed=None, view=None)
            else:
                await interaction.followup.send("Goal not found!", ephemeral=True)
            return

        checkins = await get_checkin_history(goal_id, limit=10)
        stats = await get_checkin_stats(goal_id)

        embed = discord.Embed(title=goal["title"], description=goal.get("description") or "", color=discord.Color.blue())
        embed.add_field(name="Category", value=goal["category"].capitalize(), inline=True)
        embed.add_field(name="Frequency", value=goal["frequency"].replace("_", " ").title(), inline=True)
        embed.add_field(name="Status", value=goal["status"].capitalize(), inline=True)
        embed.add_field(name="Current Streak", value=f"🔥 {goal['current_streak']} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"🏆 {goal['longest_streak']} days", inline=True)
        embed.add_field(name="Freeze Tokens", value=f"🧊 {goal.get('freeze_tokens', 0)}", inline=True)
        embed.add_field(name="Consistency", value=f"📊 {stats['consistency']}% ({stats['done']}/{stats['total']})", inline=True)
        if goal.get("end_date"):
            embed.add_field(name="Deadline", value=goal["end_date"], inline=True)
        if goal.get("stake_miss_count"):
            parts = [f"Miss {goal['stake_miss_count']} → penalty"]
            if goal.get("stake_role_id"):
                parts.append(f"Role: <@&{goal['stake_role_id']}>")
            embed.add_field(name="Stake", value=" | ".join(parts), inline=True)
        if checkins:
            recent = "\n".join(
                f"• **{c['status'].capitalize()}** — {c['checked_at'][:10]}" + (f" — *{c['note']}*" if c.get("note") else "")
                for c in checkins[:5]
            )
            embed.add_field(name="Recent Check-ins", value=recent, inline=False)

        if from_component:
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Complete ───────────────────────────────────────────

    @app_commands.command(name="goal-complete", description="Mark a goal as completed")
    @app_commands.autocomplete(goal_id=goal_autocomplete)
    @app_commands.describe(achieved="Did you achieve your goal?")
    async def goal_complete(self, interaction: discord.Interaction, goal_id: int = None, achieved: bool = True):
        await require_goal(interaction, goal_id, "complete", lambda i, g, fc: self._do_complete(i, g, achieved, fc))

    async def _do_complete(self, interaction: discord.Interaction, goal_id: int, achieved: bool, from_component: bool = False):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            msg = "Goal not found or not yours!"
            if from_component:
                await interaction.response.edit_message(content=msg, embed=None, view=None)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return

        await complete_goal(goal_id, achieved)
        embed = discord.Embed(title="Goal Completed! 🏆", description=f"**{goal['title']}**", color=discord.Color.gold())
        embed.add_field(name="Achieved", value="✅ Yes!" if achieved else "Not this time", inline=True)
        embed.add_field(name="Final streak", value=f"{goal['current_streak']} days", inline=True)

        if achieved:
            row = await (await get_db()).execute(
                "SELECT accountability_channel_id FROM server_config WHERE server_id = ?",
                (str(interaction.guild_id),),
            )
            cfg = await row.fetchone()
            if cfg and cfg["accountability_channel_id"]:
                channel = self.bot.get_channel(int(cfg["accountability_channel_id"]))
                if channel:
                    await channel.send(
                        f"🎉 {interaction.user.mention} completed their goal **{goal['title']}**! "
                        f"Final streak: {goal['current_streak']} days!"
                    )

        if from_component:
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Edit ────────────────────────────────────────────────

    @app_commands.command(name="goal-edit", description="Edit an existing goal")
    @app_commands.autocomplete(goal_id=goal_autocomplete)
    @app_commands.describe(title="New title", description="New description", checkin_hour="New hour (0-23)", end_date="New deadline")
    async def goal_edit(
        self,
        interaction: discord.Interaction,
        goal_id: int = None,
        title: str = None,
        description: str = None,
        checkin_hour: int = None,
        end_date: str = None,
    ):
        await require_goal(interaction, goal_id, "edit", lambda i, g, fc: self._do_edit(i, g, fc, title, description, checkin_hour, end_date))

    async def _do_edit(self, interaction: discord.Interaction, goal_id: int, from_component: bool, title, description, checkin_hour, end_date):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            msg = "Goal not found or not yours!"
            if from_component:
                await interaction.response.edit_message(content=msg, embed=None, view=None)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        kwargs = {}
        if title is not None: kwargs["title"] = title
        if description is not None: kwargs["description"] = description
        if checkin_hour is not None: kwargs["checkin_hour"] = checkin_hour
        if end_date is not None: kwargs["end_date"] = end_date
        if not kwargs:
            msg = "Nothing to edit."
            if from_component:
                await interaction.response.edit_message(content=msg, embed=None, view=None)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        await update_goal(goal_id, **kwargs)
        msg = f"Goal **{goal['title']}** updated! ✅"
        if from_component:
            await interaction.response.edit_message(content=msg, embed=None, view=None)
        else:
            await interaction.followup.send(msg, ephemeral=True)

    # ── Delete ──────────────────────────────────────────────

    @app_commands.command(name="goal-delete", description="Delete a goal")
    @app_commands.autocomplete(goal_id=goal_autocomplete)
    async def goal_delete(self, interaction: discord.Interaction, goal_id: int = None):
        await require_goal(interaction, goal_id, "delete", self._do_delete)

    async def _do_delete(self, interaction: discord.Interaction, goal_id: int, from_component: bool = False):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            msg = "Goal not found or not yours!"
            if from_component:
                await interaction.response.edit_message(content=msg, embed=None, view=None)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        await delete_goal(goal_id)
        msg = f"Goal **{goal['title']}** deleted."
        if from_component:
            await interaction.response.edit_message(content=msg, embed=None, view=None)
        else:
            await interaction.followup.send(msg, ephemeral=True)

    # ── Abandon ─────────────────────────────────────────────

    @app_commands.command(name="goal-abandon", description="Mark a goal as abandoned")
    @app_commands.autocomplete(goal_id=goal_autocomplete)
    async def goal_abandon(self, interaction: discord.Interaction, goal_id: int = None):
        await require_goal(interaction, goal_id, "abandon", self._do_abandon)

    async def _do_abandon(self, interaction: discord.Interaction, goal_id: int, from_component: bool = False):
        goal = await get_goal(goal_id)
        if not goal or goal["discord_id"] != str(interaction.user.id):
            msg = "Goal not found or not yours!"
            if from_component:
                await interaction.response.edit_message(content=msg, embed=None, view=None)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        await abandon_goal(goal_id)
        msg = f"Goal **{goal['title']}** marked as abandoned."
        if from_component:
            await interaction.response.edit_message(content=msg, embed=None, view=None)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GoalsCog(bot))
