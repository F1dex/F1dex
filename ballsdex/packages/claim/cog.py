import json
from rapidfuzz import process, fuzz
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallEnabledTransform
from ballsdex.core.models import Player, BallInstance, Special

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


with open("ballsdex/packages/claim/amounts.json", "r") as file:
    data = json.load(file)
    data_names = [entry["name"] for entry in data]

def get_amount_by_name(name: str, threshold: int = 85):
    result = process.extractOne(name, data_names, scorer=fuzz.ratio)

    if result and result[1] >= threshold:
        best_match = result[0]
        for entry in data:
            if entry["name"] == best_match:
                return entry["amount"]
    return None


class Claim(commands.GroupCog):
    """
    Claim multiple types of collector cards!
    """

    def __init__(self, bot: "BallsDexBot"):
        super().__init__()
        self.bot = bot

    collector = app_commands.Group(name="collector", description="Collector card commands.")

    @collector.command(name="bronze")
    async def collector_bronze(
        self, interaction: discord.Interaction, countryball: BallEnabledTransform
    ):
        """
        Claim a bronze collector card.

        Parameters
        ----------
        countryball: BallEnabledTransform
            The countryball to claim the card for.
        """
        amount = get_amount_by_name(countryball.country)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        special = await Special.filter(name="Bronze Collector").first()
        owned = await BallInstance.filter(ball=countryball, player=player).count()
        alr_owned = await BallInstance.filter(
            ball=countryball, player=player, special=special
        ).first()

        if alr_owned:
            await interaction.response.send_message(
                f"You already have a {countryball.country} bronze collector card!", ephemeral=True
            )
            return

        amount_needed = int(Decimal(amount * 0.25).quantize(0, rounding=ROUND_HALF_UP))
        if owned < amount_needed:
            await interaction.response.send_message(
                f"You need {amount_needed} {settings.plural_collectible_name} to claim a "
                f"{countryball.country} bronze collector card, you only have {owned}.",
                ephemeral=True,
            )
            return

        await BallInstance.create(
            ball=countryball,
            player=player,
            special=special,
            tradeable=False,
            attack_bonus=0,
            health_bonus=0,
        )
        await interaction.response.send_message(
            f"{countryball.country} bronze collector card made!", ephemeral=True
        )

    @collector.command(name="silver")
    async def collector_silver(
        self, interaction: discord.Interaction, countryball: BallEnabledTransform
    ):
        """
        Claim a silver collector card.

        Parameters
        ----------
        countryball: BallEnabledTransform
            The countryball to claim the card for.
        """
        amount = get_amount_by_name(countryball.country)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        special = await Special.filter(name="Silver Collector").first()
        owned = await BallInstance.filter(ball=countryball, player=player).count()
        alr_owned = await BallInstance.filter(
            ball=countryball, player=player, special=special
        ).first()

        if alr_owned:
            await interaction.response.send_message(
                f"You already have a {countryball.country} silver collector card!", ephemeral=True
            )
            return

        amount_needed = int(Decimal(amount * 0.60).quantize(0, rounding=ROUND_HALF_UP))
        if owned < amount_needed:
            await interaction.response.send_message(
                f"You need {amount_needed} {settings.plural_collectible_name} to claim a "
                f"{countryball.country} silver collector card, you only have {owned}.",
                ephemeral=True,
            )
            return

        await BallInstance.create(
            ball=countryball,
            player=player,
            special=special,
            tradeable=False,
            attack_bonus=0,
            health_bonus=0,
        )
        await interaction.response.send_message(
            f"{countryball.country} silver collector card made!", ephemeral=True
        )

    @collector.command(name="gold")
    async def collector_gold(
        self, interaction: discord.Interaction, countryball: BallEnabledTransform
    ):
        """
        Claim a gold collector card.

        Parameters
        ----------
        countryball: BallEnabledTransform
            The countryball to claim the card for.
        """
        amount = get_amount_by_name(countryball.country)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True
            )
            return

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        special = await Special.filter(name="Gold Collector").first()
        owned = await BallInstance.filter(ball=countryball, player=player).count()
        alr_owned = await BallInstance.filter(
            ball=countryball, player=player, special=special
        ).first()

        if alr_owned:
            await interaction.response.send_message(
                f"You already have a {countryball.country} gold collector card!", ephemeral=True
            )
            return

        if owned < amount:
            await interaction.response.send_message(
                f"You need {amount} {settings.plural_collectible_name} to claim a "
                f"{countryball.country} gold collector card, you only have {owned}.",
                ephemeral=True,
            )
            return

        await BallInstance.create(
            ball=countryball,
            player=player,
            special=special,
            tradeable=False,
            attack_bonus=0,
            health_bonus=0,
        )
        await interaction.response.send_message(
            f"{countryball.country} gold collector card made!", ephemeral=True
        )
