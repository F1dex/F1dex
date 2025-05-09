import random
import re
from collections import defaultdict
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from ballsdex.core.models import BallInstance, PackInstance, Player, Special
from ballsdex.core.models import Packs as PackModel
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.transformers import PackEnabledTransform
from ballsdex.core.utils.utils import decide_collectible
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def parse_rewards(rewards_str: str) -> dict:
    # TODO: add specify_collectibles to parsing with exact matching
    rewards = {"special": []}
    lines = [line.strip() for line in rewards_str.splitlines() if line.strip()]

    for line in lines:
        if match := re.match(r"special=([\w\s]+)\((\d+)%\)", line):
            name, chance = match.groups()
            rewards["special"].append({"type": name.strip(), "chance": int(chance)})
        elif match := re.match(r"collectible_amount=(\d+)", line):
            rewards["collectible_amount"] = int(match.group(1))
        elif match := re.match(r"currency_amount_choices=(\d+)\((\d+)%\)", line):
            amount, chance = map(int, match.groups())
            rewards.setdefault("currency_amount_choices", []).append(
                {"amount": amount, "chance": chance}
            )
        elif match := re.match(r"currency_amount=(\d+)-(\d+)", line):
            min_amt, max_amt = map(int, match.groups())
            rewards["currency_amount"] = random.randint(min_amt, max_amt)
        elif match := re.match(r"currency_amount=(\d+)", line):
            rewards["currency_amount"] = int(match.group(1))

    return rewards


async def open_pack(
    bot: "BallsDexBot",
    interaction: discord.Interaction,
    player: Player,
    pack: PackModel,
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
    reward_lines.append(
        f"**You have packed {collectible_count} {settings.plural_collectible_name}!**\n"
    )

    for _ in range(collectible_count):
        collectible = await decide_collectible(bot=bot)
        applied_special: Special | None = None

        total_chance = sum(sp["chance"] for sp in special)
        roll = random.uniform(0, 100)

        if roll <= total_chance and special:
            selected_type = random.choices(
                population=[sp["type"].strip() for sp in special],
                weights=[sp["chance"] for sp in special],
                k=1
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

    await interaction.followup.send(embed=result_embed, view=view, ephemeral=True)


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

        await open_pack(self.bot, interaction, self.player, self.pack)

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
    async def list(self, interaction: discord.Interaction):
        """
        List all packs.
        """
        packs = await PackModel.filter(purchasable=True).order_by("price").all()
        if not packs:
            await interaction.response.send_message("No packs available.", ephemeral=True)
            return

        entries: list[tuple[str, str]] = []

        for idx, relation in enumerate(packs, start=1):
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
        pack: PackTransform
            The pack to buy.
        amount: int | None
            The amount of packs to buy. Defaults to 1.
        """
        pack_to_buy = await PackModel.get(name=pack.name)
        player = await Player.get(discord_id=interaction.user.id)
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not pack_to_buy:
            await interaction.followup.send("Pack not found.", ephemeral=True)
            return

        if not pack_to_buy.purchasable:
            await interaction.followup.send("This pack is not purchasable.", ephemeral=True)
            return

        total_price = pack_to_buy.price * amount
        gram = "" if amount == 1 else "s"
        if player.coins < total_price:
            coins_needed = total_price - player.coins
            await interaction.followup.send(
                f"You don't have enough coins to buy {amount} pack{gram}, "
                f"you need {coins_needed} more coins.",
                ephemeral=True,
            )
            return

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
            f"**{total_price} {grammar} {settings.currency_emoji}**?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.value:
            return

        player.coins -= total_price
        await player.save()

        for i in range(amount):
            await PackInstance.create(player=player, pack=pack_to_buy)

        await interaction.followup.send(
            f"You have successfully bought **{amount}x {pack_to_buy.name} pack{gram}**!",
            ephemeral=True,
        )

    @app_commands.command()
    async def inventory(self, interaction: discord.Interaction):
        """
        View your pack inventory.
        """
        player = await Player.get(discord_id=interaction.user.id)
        await interaction.response.defer(thinking=True, ephemeral=True)

        owned_packs = (
            await PackInstance.filter(player=player, opened=False).prefetch_related("pack").all()
        )

        if not owned_packs:
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
        for pack in owned_packs:
            packs[pack.pack.name] += 1

        for pack_name, count in sorted(packs.items(), key=lambda x: x[1], reverse=True):
            pack = await PackModel.get(name=pack_name)

            grammar = (
                f"{settings.currency_name}"
                if pack.price == 1
                else f"{settings.plural_currency_name}"
            )

            embed.add_field(
                name=f"{pack.name} ({count} owned)",
                value=f"Value of each pack: **{pack.price} {grammar} {settings.currency_emoji}**",
                inline=False,
            )

        embed.set_footer(text="Use /buy to get more packs!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command()
    async def open(self, interaction: discord.Interaction, pack: PackEnabledTransform):
        """
        Open a pack you own.

        Parameters
        ----------
        pack: PackEnabledTransform
            The pack to open.
        """
        player = await Player.get(discord_id=interaction.user.id)
        pack_count = await PackInstance.filter(player=player, pack=pack).count()

        if pack_count < 1:
            await interaction.response.send_message(
                f"You don't own any **{pack.name}** packs!", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        view = PackConfirmChoiceView(interaction.client, interaction, player)
        embed = discord.Embed(
            title="🎁 Open Pack?",
            description=(
                f"Do you want to open a **{pack.name}** pack?\n"
                f"You currently have **{pack_count}** of them."
            ),
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.value:
            return

        await open_pack(self.bot, interaction, player, pack)

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
