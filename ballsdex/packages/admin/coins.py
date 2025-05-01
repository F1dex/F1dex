import discord
from discord import app_commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Player
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings


class Coins(app_commands.Group):
    """
    Coin management
    """

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def coins_add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        amount: int = 1,
    ):
        """
        Add an amount of coints to a user.

        Parameters
        ----------
        user: discord.User
            The user you want to add the coins to.
        amount: int
            The amount of coins you want to add to the user.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        if amount <= 0:
            await interaction.followup.send(
                "You must enter a positive number for the amount.", ephemeral=True
            )
            return
        if amount > 1000000:
            await interaction.followup.send(
                "You cannot give more than 1000000 coins at once.", ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=user.id)
        await player.add_coins(amount)
        plural = f"{settings.currency_name}" if amount == 1 else f"{settings.plural_currency_name}"

        await interaction.followup.send(
            f"Successfully added {amount} {plural} to {user.name}.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user} added {amount} {plural} to {user.name}.",
            interaction.client,
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def coins_remove(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        amount: int = 1,
    ):
        """
        Remove an amount of coins from a user.

        Parameters
        ----------
        user: discord.User
            The user you want to remove the coins from.
        amount: int
            The amount of coins you want to remove from the user.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        if amount < 1:
            await interaction.followup.send(
                "The `amount` must be superior or equal to 1.", ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=user.id)
        if amount > player.coins:
            await interaction.followup.send(
                "You cannot remove more coins than the amount of coins the user currently has."
            )
            return

        await player.remove_coins(amount)
        plural = "s" if amount > 1 else ""

        await interaction.followup.send(
            f"Successfully removed {amount} coin{plural} from {user.name}.", ephemeral=True
        )
        await log_action(
            f"{interaction.user} removed {amount} coin{plural} from {user.name}.",
            interaction.client,
        )
