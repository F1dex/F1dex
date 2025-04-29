from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ballsdex.core.models import Ball, BallInstance, Player, Special
from ballsdex.core.utils.transformers import BallEnabledTransform
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def get_amount(instance: Ball) -> int:
    raw = 25 + ((instance.rarity - 0.03) / (0.80 - 0.03)) * (1000 - 25)
    return round(raw / 5) * 5


class Claim(commands.GroupCog):
    """
    Claim multiple types of collector cards!
    """

    def __init__(self, bot: "BallsDexBot"):
        super().__init__()
        self.bot = bot
        self.check_collector_cards.start()

    collector = app_commands.Group(name="collector", description="Collector card commands.")

    @tasks.loop(hours=12)
    async def check_collector_cards(self):
        all_players = await Player.all()
        all_balls = await Ball.filter(enabled=True)

        specials = {
            "Bronze Collector": await Special.filter(name="Bronze Collector").first(),
            "Silver Collector": await Special.filter(name="Silver Collector").first(),
            "Gold Collector": await Special.filter(name="Gold Collector").first(),
        }

        for player in all_players:
            for ball in all_balls:
                total_owned = await BallInstance.filter(ball=ball, player=player).count()

                amount = get_amount(ball)
                bronze_needed = int(Decimal(amount * 0.25).quantize(0, rounding=ROUND_HALF_UP))
                silver_needed = int(Decimal(amount * 0.60).quantize(0, rounding=ROUND_HALF_UP))
                gold_needed = amount

                for name, needed in [
                    ("Bronze Collector", bronze_needed),
                    ("Silver Collector", silver_needed),
                    ("Gold Collector", gold_needed),
                ]:
                    special = specials[name]
                    card = await BallInstance.filter(
                        ball=ball, player=player, special=special
                    ).first()
                    if card and total_owned < needed:
                        await card.delete()

                        user = await self.bot.fetch_user(player.discord_id)
                        try:
                            await user.send(
                                f"Hi {user.name},\n\nUnfortunately, you no longer "
                                f"meet the requirements to keep the {ball.country}"
                                f" {name} card. It has been removed from your collection."
                            )
                        except discord.Forbidden:
                            pass


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
        amount = get_amount(countryball)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True,
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
        amount = get_amount(countryball)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True,
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
        amount = get_amount(countryball)
        if amount is None:
            await interaction.response.send_message(
                f"Sorry, this {settings.collectible_name} is not available for claiming.",
                ephemeral=True,
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
