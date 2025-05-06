from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.models import Packs as PackModel
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Packs(commands.GroupCog):
    """
    View and manage packs in the bot.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def list(self, interaction: discord.Interaction):
        """
        List all packs.
        """
        packs = await PackModel.filter().order_by("price").all()
        if not packs:
            await interaction.response.send_message("No packs available.", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []

        for idx, relation in enumerate(packs, start=1):
            entries.append(
                (
                    "",
                    f"**{idx}.** <@{relation.name}> "
                    f"({relation.description})\nPrice: {relation.price} {settings.currency_emoji}",
                )
            )

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "Pack shop"
        source.embed.set_thumbnail(url=interaction.user.display_avatar.url)
        source.embed.set_footer(text="To buy a pack, use `/pack buy`")

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)
