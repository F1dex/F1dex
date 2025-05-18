import discord
from discord import app_commands

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import PackInstance, Player
from ballsdex.core.utils.logging import log_action
from ballsdex.core.utils.transformers import PackEnabledTransform
from ballsdex.settings import settings


class Packs(app_commands.Group):
    """
    Pack management
    """

    @app_commands.command(name="add")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def packs_add(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        pack: PackEnabledTransform,
        amount: int = 1,
    ):
        """
        Add an amount of packs to a user.

        Parameters
        ----------
        user: discord.User
            The user you want to add the packs to.
        pack: PackEnabledTransform
            The pack you want to add to the user.
        amount: int
            The amount of packs you want to add to the user.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        if amount <= 0:
            await interaction.followup.send(
                "You must enter a positive number for the amount.", ephemeral=True
            )
            return
        if amount > 1000000:
            await interaction.followup.send(
                "You cannot give more than 1000000 packs at once.", ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=user.id)
        plural = "" if amount == 1 else "s"

        for i in range(amount):
            await PackInstance.create(player=player, pack=pack)

        await interaction.followup.send(
            f"Successfully added {amount} '{pack.name}' pack{plural} to {user.name}.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user} added {amount} '{pack.name}' pack{plural} to {user.name}.",
            interaction.client,
        )

    @app_commands.command(name="remove")
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def packs_remove(
        self,
        interaction: discord.Interaction[BallsDexBot],
        user: discord.User,
        pack: PackEnabledTransform,
        amount: int = 1,
    ):
        """
        Remove an amount of packs from a user.

        Parameters
        ----------
        user: discord.User
            The user you want to remove the packs from.
        pack: PackEnabledTransform
            The pack you want to remove from the user.
        amount: int
            The amount of packs you want to remove from the user.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        player, _ = await Player.get_or_create(discord_id=user.id)
        packs = await PackInstance.filter(player=player, pack=pack, opened=False).count()

        if amount < 1:
            await interaction.followup.send(
                "The `amount` must be superior or equal to 1.", ephemeral=True
            )
            return

        if amount > packs:
            await interaction.followup.send(
                "You cannot remove more packs than the amount of packs the user currently has."
            )
            return

        packs_to_delete = await PackInstance.filter(player=player, pack=pack, opened=False).limit(
            amount
        )
        for p in packs_to_delete:
            await p.delete()

        plural = "" if amount == 1 else "s"

        await interaction.followup.send(
            f"Successfully removed {amount} '{pack.name}' pack{plural} from {user.name}.",
            ephemeral=True,
        )
        await log_action(
            f"{interaction.user} removed {amount} '{pack.name}' pack{plural} from {user.name}.",
            interaction.client,
        )  # TODO: use packtransform
