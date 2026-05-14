import discord

from bot.checkins import (
    record_checkin,
    use_freeze_token as check_use_freeze_token,
    check_stake,
    post_to_accountability_channel,
    grant_freeze_token,
)
from bot.streaks import check_milestone
from bot.goals import get_goal


class CheckinView(discord.ui.View):
    def __init__(self, goal_id: int, goal_title: str):
        super().__init__(timeout=None)
        self.goal_id = goal_id
        self.goal_title = goal_title

    @discord.ui.button(label="Yes, I did it!", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_response(interaction, "done")

    @discord.ui.button(label="No, I missed it", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_response(interaction, "missed")

    @discord.ui.button(label="Use Freeze Token", style=discord.ButtonStyle.secondary, emoji="🧊")
    async def freeze_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        success = await check_use_freeze_token(str(interaction.user.id), self.goal_id)
        if success:
            await interaction.response.send_message(
                "You used a freeze token! Your streak is protected. 🧊", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You don't have any freeze tokens left!", ephemeral=True
            )
        self.disable_all()
        await interaction.edit_original_response(view=self)

    async def _handle_response(self, interaction: discord.Interaction, status: str):
        checkin_id = await record_checkin(self.goal_id, str(interaction.user.id), status)

        if checkin_id == -1:
            await interaction.response.send_message(
                "You've already checked in today! ✅", ephemeral=True
            )
            return

        if status == "done":
            msg = f"Nice work on **{self.goal_title}**! Keep it up! 🎉"
            milestone = await check_milestone(self.goal_id)
            if milestone:
                await grant_freeze_token(str(interaction.user.id))
                msg += f"\n🏆 **{milestone}-day milestone!** You earned a freeze token!"
        else:
            msg = f"No worries — tomorrow's a new chance for **{self.goal_title}**. 💪"

        await interaction.response.send_message(msg, ephemeral=True)

        await self._post_update(interaction.client, status)
        await self._handle_stake(interaction.client, status)

        self.disable_all()
        await interaction.edit_original_response(view=self)

    async def _post_update(self, bot, status: str):
        goal = await get_goal(self.goal_id)
        if not goal:
            return
        emoji = "✅" if status == "done" else "❌"
        content = f"{emoji} <@{goal['discord_id']}> checked in **{status}** for **{self.goal_title}**"
        if status == "done":
            content += f" (🔥 {goal['current_streak'] + 1}d streak)"
        await post_to_accountability_channel(bot, self.goal_id, goal["server_id"], content)

    async def _handle_stake(self, bot, status: str):
        if status != "missed":
            return
        stake = await check_stake(self.goal_id)
        if not stake:
            return
        guild = bot.get_guild(int(stake["server_id"]))
        if not guild:
            return
        if stake["stake_public_shame"]:
            content = f"⚠️ <@{stake['discord_id']}> missed their stake on **{stake['title']}**!"
            await post_to_accountability_channel(bot, self.goal_id, stake["server_id"], content)
        if stake["stake_role_id"]:
            member = guild.get_member(int(stake["discord_id"]))
            if member:
                role = guild.get_role(int(stake["stake_role_id"]))
                if role:
                    await member.remove_roles(role, reason="Stake: missed too many check-ins")

    def disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
