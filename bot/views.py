import discord


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
        from bot.checkins import use_freeze_token

        success = await use_freeze_token(interaction.user.id, self.goal_id)
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
        from bot.checkins import record_checkin

        await record_checkin(self.goal_id, str(interaction.user.id), status)
        if status == "done":
            msg = f"Nice work on **{self.goal_title}**! Keep it up! 🎉"
        else:
            msg = f"No worries — tomorrow's a new chance for **{self.goal_title}**. 💪"
        await interaction.response.send_message(msg, ephemeral=True)
        self.disable_all()
        await interaction.edit_original_response(view=self)

    def disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
