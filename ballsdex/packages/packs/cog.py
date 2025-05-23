import enum
import logging
import random
import re
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from ballsdex.core.models import Ball, BallInstance, PackInstance, Player, Special
from ballsdex.core.models import Packs as PackModel
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.transformers import PackEnabledTransform
from ballsdex.core.utils.utils import decide_collectible
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


def parse_rewards(rewards_str: str) -> dict:
    rewards = {"special": []}
    lines = [line.strip() for line in rewards_str.splitlines() if line.strip()]

    for line in lines:
        if match := re.match(r"special=([\w\s]+)\((\d+(?:\.\d+)?)%\)", line):
            name, chance = match.groups()
            rewards["special"].append({"type": name.strip(), "chance": float(chance)})

        elif match := re.match(r"collectible_amount=(\d+)", line):
            rewards["collectible_amount"] = int(match.group(1))

        elif match := re.match(r"currency_amount_choices=(\d+)\((\d+(?:\.\d+)?)%\)", line):
            amount, chance = match.groups()
            rewards.setdefault("currency_amount_choices", []).append(
                {"amount": int(amount), "chance": float(chance)}
            )

        elif match := re.match(r"currency_amount=(\d+)-(\d+)", line):
            min_amt, max_amt = map(int, match.groups())
            rewards["currency_amount"] = random.randint(min_amt, max_amt)

        elif match := re.match(r"currency_amount=(\d+)", line):
            rewards["currency_amount"] = int(match.group(1))

        elif match := re.match(r"specify_collectibles=(.+)", line, re.IGNORECASE):
            names_str = match.group(1)
            names = re.findall(r'"([^"]+)"', names_str)
            rewards["specify_collectibles"] = [name.strip() for name in names if name.strip()]

    return rewards


async def open_pack(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    player: Player,
    pack: PackModel,
    ephemeral: bool = False,
):
    pack_instance = (
        await PackInstance.filter(player=player, pack=pack).prefetch_related("pack").first()
    )

    if not pack_instance:
        await interaction.followup.send("You don't own any packs!", ephemeral=True)
        return

    await pack_instance.delete()
    parsed = parse_rewards(pack_instance.pack.rewards)
    pack_updated_count = await PackInstance.filter(player=player, pack=pack).count()

    reward_lines = []
    special = parsed.get("special", [])
    collectible_count = parsed.get("collectible_amount", 0)
    specify_names = parsed.get("specify_collectibles", [])
    available_specified: list[Ball] = []
    reward_lines.append(
        f"**You have packed {collectible_count} {settings.plural_collectible_name}!**\n"
    )

    for name in specify_names:
        collectible = await Ball.filter(country__iexact=name).first()
        if collectible:
            available_specified.append(collectible)
        else:
            log.warning(
                f"Collectible with name '{name}' is specified in a pack, but it cannot found, "
                "hence it will not be able to be given out from the pack."
            )
            pass

    for _ in range(collectible_count):
        if available_specified:
            rarities = [ball.rarity for ball in available_specified]
            collectible = random.choices(population=available_specified, weights=rarities, k=1)[0]
        else:
            collectible = decide_collectible()

        applied_special: Special | None = None

        total_chance = sum(sp["chance"] for sp in special)
        roll = random.uniform(0, 100)

        if roll <= total_chance and special:
            selected_type = random.choices(
                population=[sp["type"].strip() for sp in special],
                weights=[sp["chance"] for sp in special],
                k=1,
            )[0]

            applied_special = await Special.get(name=selected_type)

        cb = await BallInstance.create(
            player=player,
            ball=collectible,
            special=applied_special,
            packed=True,
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
        )

        cb_txt = (
            cb.description(short=True, include_emoji=True, bot=bot)
            + f" (`{cb.attack_bonus:+}%/{cb.health_bonus:+}%`)"
        )
        reward_lines.append(cb_txt)

    currency_reward = 0
    if "currency_amount_choices" in parsed:
        choices = parsed["currency_amount_choices"]
        if choices:
            currency_reward = random.choices(
                [c["amount"] for c in choices], weights=[c["chance"] for c in choices], k=1
            )[0]
    elif "currency_amount" in parsed:
        currency_reward = parsed["currency_amount"]

    player.coins += currency_reward
    await player.save()

    grammar = (
        f"{settings.currency_name}" if currency_reward == 1 else f"{settings.plural_currency_name}"
    )

    reward_lines.append(f"\n**+{currency_reward} {grammar} {settings.currency_emoji}**")

    result_embed = discord.Embed(
        title=f"🎉 '{pack.name.title()}' Pack Opened!",
        description="\n".join(reward_lines),
        color=discord.Color.gold(),
    )
    view = OpenMoreView(bot, interaction, player, pack)
    if pack_updated_count == 0:
        result_embed.set_footer(text="You don't have any more packs left!")
    else:
        result_embed.set_footer(
            text=f"You still have {pack_updated_count} {pack.name} packs left!"
        )

    await interaction.followup.send(embed=result_embed, view=view, ephemeral=ephemeral)


class PackSorting(enum.Enum):
    price = "price"
    alphabetical = "alphabetical"
    created_at = "created_at"


class PackConfirmChoiceView(View):
    def __init__(
        self,
        bot: "BallsDexBot",
        interaction: discord.Interaction["BallsDexBot"],
        player: Player,
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.original_interaction = interaction
        self.player = player
        self.value = None
        self.ephemeral: bool = False

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        if interaction.user.id != self.player.discord_id:
            await interaction.response.send_message(
                "You are not allowed to interact with this menu.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore

        try:
            await self.original_interaction.followup.edit_message(
                "@original",
                view=self,  # type: ignore
            )
        except discord.NotFound:
            pass

        self.value = False

    @button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        self.value = True

        self.original_interaction = interaction
        await interaction.response.defer()

        self.stop()

    @button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        self.value = False

        self.original_interaction = interaction
        await interaction.response.defer()

        for item in self.children:
            item.disabled = True  # type: ignore

        try:
            await self.original_interaction.followup.edit_message(
                "@original",
                view=self,  # type: ignore
            )
        except discord.NotFound:
            pass

        self.stop()


class OpenMoreView(View):
    def __init__(
        self,
        bot: "BallsDexBot",
        interaction: discord.Interaction["BallsDexBot"],
        player: Player,
        pack: PackModel,
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.original_interaction = interaction
        self.player = player
        self.value = None
        self.pack = pack
        self.confirmview = PackConfirmChoiceView(self.bot, self.original_interaction, self.player)

    async def interaction_check(self, interaction: discord.Interaction["BallsDexBot"], /) -> bool:
        if interaction.user.id != self.player.discord_id:
            await interaction.response.send_message(
                "You are not allowed to interact with this menu.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore

        try:
            await self.original_interaction.followup.edit_message(
                "@original",
                view=self,  # type: ignore
            )
        except discord.NotFound:
            pass

        self.value = False

    @button(style=discord.ButtonStyle.blurple, label="Open More")
    async def open_more(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        self.value = True

        self.original_interaction = interaction
        await interaction.response.defer()

        await open_pack(self.bot, interaction, self.player, self.pack, self.confirmview.ephemeral)

        for item in self.children:
            item.disabled = True  # type: ignore

        try:
            await self.original_interaction.followup.edit_message(
                "@original",
                view=self,  # type: ignore
            )
        except discord.NotFound:
            pass

        self.stop()

    @button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        label="Return",
    )
    async def return_home(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        self.value = False

        self.original_interaction = interaction
        await interaction.response.defer()

        for item in self.children:
            item.disabled = True  # type: ignore

        try:
            await self.original_interaction.followup.edit_message(
                "@original",
                view=self,  # type: ignore
            )
        except discord.NotFound:
            pass

        self.stop()


class Packs(commands.GroupCog):
    """
    View and manage packs in the bot.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def list(
        self,
        interaction: discord.Interaction,
        sorting: PackSorting | None = None,
        reverse: bool = False,
    ):
        """
        List all packs.

        Parameters
        ----------
        sorting: PackSorting | None
            The sorting method to use. Defaults to None.
        reverse: bool
            Whether to reverse the sorting. Defaults to False.
        """
        query = PackModel.filter(purchasable=True)
        if sorting:
            if sorting == PackSorting.price:
                query = query.order_by("price")
            elif sorting == PackSorting.alphabetical:
                query = query.order_by("name")
            elif sorting == PackSorting.created_at:
                query = query.order_by("created_at")

        results = await query
        if reverse:
            results.reverse()

        if not results:
            await interaction.response.send_message("No packs available.", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []

        for idx, relation in enumerate(results, start=1):
            entries.append(
                (
                    "",
                    f"**{idx}.** {relation.name}\n"
                    f"{relation.description}\nPrice: {relation.price} {settings.currency_emoji}",
                )
            )

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "Pack shop"
        source.embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        source.embed.set_footer(text="To buy a pack, use /pack buy")

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    async def buy(
        self,
        interaction: discord.Interaction,
        pack: PackEnabledTransform,
        amount: app_commands.Range[int, 1, 100] | None = 1,
    ):
        """
        Buy a pack.

        Parameters
        ----------
        pack: PackEnabledTransform
            The pack to buy.
        amount: int | None
            The amount of packs to buy. Defaults to 1.
        """
        pack_to_buy = await PackModel.get(name=pack.name)
        player = await Player.get(discord_id=interaction.user.id)

        total_price = pack_to_buy.price * amount
        gram = "" if amount == 1 else "s"
        if player.coins < total_price:
            coins_needed = total_price - player.coins
            await interaction.response.send_message(
                f"You don't have enough coins to buy {amount} pack{gram}, "
                f"you need {coins_needed} more coins.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        view = ConfirmChoiceView(
            interaction,
            accept_message=f"{amount} pack{gram} purchased!",
            cancel_message="This request has been cancelled.",
        )
        grammar = (
            f"{settings.currency_name}"
            if pack_to_buy.price == 1
            else f"{settings.plural_currency_name}"
        )
        await interaction.followup.send(
            f"Are you sure you want to buy **{amount}x {pack_to_buy.name} pack{gram}** for "
            f"**{total_price} {grammar} {settings.currency_emoji}?**",
            view=view,
        )
        await view.wait()
        if not view.value:
            return

        player.coins -= total_price
        await player.save()

        for i in range(amount):
            await PackInstance.create(player=player, pack=pack_to_buy)

        await interaction.followup.send(
            f"You have successfully bought **{amount}x {pack_to_buy.name} pack{gram}!**",
        )

    @app_commands.command()
    async def inventory(
        self,
        interaction: discord.Interaction,
        sorting: PackSorting | None = None,
        reverse: bool = False,
    ):
        """
        View your pack inventory.

        Parameters
        ----------
        sorting: PackSorting | None
            The sorting method to use. Defaults to owned amount.
        reverse: bool
            Whether to reverse the sorting. Defaults to False.
        """
        player = await Player.get(discord_id=interaction.user.id)
        await interaction.response.defer(thinking=True, ephemeral=True)

        query = PackInstance.filter(player=player, opened=False).prefetch_related("pack")
        if sorting:
            if sorting == PackSorting.price:
                query = query.order_by("pack__price")
            elif sorting == PackSorting.alphabetical:
                query = query.order_by("pack__name")
            elif sorting == PackSorting.created_at:
                query = query.order_by("pack__created_at")

        results = await query
        if reverse:
            results.reverse()

        if not results:
            embed = discord.Embed(
                title="🎒 Your Pack Inventory",
                description="You don't own any packs yet.\nBuy some with `/packs buy`!",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="🎒 Your Pack Inventory",
            description="Here's a list of all the packs you own:",
            color=discord.Color.green(),
        )

        packs = defaultdict(int)
        for inst in results:
            packs[inst.pack.name] += 1

        sorted_packs = sorted(packs.items(), key=lambda x: x[1], reverse=True)
        pack_names = [name for name, _ in sorted_packs]
        all_packs = await PackModel.filter(name__in=pack_names)
        pack_map = {p.name: p for p in all_packs}

        entries: list[tuple[str, str]] = []
        for pack_name, count in sorted_packs:
            pack = pack_map[pack_name]
            grammar = (
                f"{settings.currency_name}"
                if pack.price == 1
                else f"{settings.plural_currency_name}"
            )
            entries.append(
                (
                    "",
                    f"{pack.name} ({count} owned)\n"
                    f"Value of each pack: **{pack.price} {grammar} {settings.currency_emoji}**",
                )
            )

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "🎒 Your Pack Inventory"
        source.embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        source.embed.set_footer(text="To buy a pack, use /pack buy")

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)

    @app_commands.command()
    async def open(
        self,
        interaction: discord.Interaction,
        pack: PackEnabledTransform,
        ephemeral: bool | None = None,
    ):
        """
        Open a pack you own.

        Parameters
        ----------
        pack: PackEnabledTransform
            The pack to open.
        ephemeral: bool | None
            Whether the command will be ephemeral or not, not ephemeral by default.
        """
        player = await Player.get(discord_id=interaction.user.id)
        pack_count = await PackInstance.filter(player=player, pack=pack).count()
        if not ephemeral:
            ephemeral = False

        if pack_count < 1:
            await interaction.response.send_message(
                f"You don't own any **{pack.name}** packs!", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=ephemeral)

        view = PackConfirmChoiceView(interaction.client, interaction, player)
        view.ephemeral = ephemeral

        embed = discord.Embed(
            title="🎁 Open Pack?",
            description=(
                f"Do you want to open a **{pack.name}** pack?\n"
                f"You currently have **{pack_count}** of them."
            ),
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)

        await view.wait()
        if not view.value:
            return

        await open_pack(self.bot, interaction, player, pack, ephemeral)

        for item in view.children:
            item.disabled = True  # type: ignore

        try:
            await view.original_interaction.followup.edit_message(
                "@original",
                view=view,  # type: ignore
            )
        except discord.NotFound:
            pass

    @app_commands.command()
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        pack: PackEnabledTransform,
        amount: int | None = None,
    ):
        """
        Give a pack to another user.

        Parameters
        ----------
        user: discord.User
            The user to give the pack to.
        pack: PackEnabledTransform
            The pack to give.
        amount: int | None
            The amount of packs to give. Defaults to 1.
        """
        player = await Player.get(discord_id=interaction.user.id)
        target_player = await Player.get(discord_id=user.id)
        pack_count = await PackInstance.filter(player=player, pack=pack, opened=False).count()

        if pack_count < 1:
            await interaction.response.send_message(
                f"You don't own any **{pack.name}** packs!", ephemeral=True
            )
            return

        if amount is None:
            amount = 1

        if amount > pack_count:
            await interaction.response.send_message(
                f"You don't own that many **{pack.name}** packs!", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "You can't give a negative amount of packs!", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        for i in range(amount):
            pack_instance = await PackInstance.filter(
                player=player, pack=pack, opened=False
            ).first()
            if pack_instance:
                pack_instance.player = target_player
                await pack_instance.save()

        grammar = "" if amount == 1 else "s"
        await interaction.followup.send(
            f"You just gave {amount}x **{pack.name}** pack{grammar} to {user.mention}!"
        )
