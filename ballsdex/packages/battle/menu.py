from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, cast

import discord
from discord.ui import Button, View, button

from ballsdex.core.models import BallInstance, Special
from ballsdex.packages.battle.battle_user import BattlingUser
from ballsdex.packages.battle.display import fill_battle_embed_fields
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.battle.cog import Battle as BattleCog

log = logging.getLogger("ballsdex.packages.battle.menu")


class InvalidBattleOperation(Exception):
    pass


class BattleView(View):
    def __init__(self, battle: BattleMenu):
        super().__init__(timeout=60 * 30)
        self.battle = battle

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.battle._get_battler(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this battle.", ephemeral=True
            )
            return False
        else:
            return True

    @button(label="Lock your deck", emoji="\N{LOCK}", style=discord.ButtonStyle.primary)
    async def lock(self, interaction: discord.Interaction, button: Button):
        battler = self.battle._get_battler(interaction.user)
        if battler.locked:
            await interaction.response.send_message(
                "You have already locked your deck!", ephemeral=True
            )
            return
        if len(battler.proposal) == 0:
            await interaction.response.send_message(
                f"You need to add at least one {settings.collectible_name} "
                "to your deck before locking it.",
                ephemeral=True,
            )
            return

        await self.battle.lock(battler)

        if self.battle.battler1.locked and self.battle.battler2.locked:
            await interaction.response.send_message(
                "Your deck has been locked. Now confirm again to end the battle.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Your deck has been locked. "
                "You can wait for the other user to lock their proposal.",
                ephemeral=True,
            )

    @button(label="Reset", emoji="\N{DASH SYMBOL}", style=discord.ButtonStyle.secondary)
    async def clear(self, interaction: discord.Interaction, button: Button):
        battler = self.battle._get_battler(interaction.user)
        if battler.locked:
            await interaction.response.send_message(
                "You have locked your deck, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
        else:
            for carfigure in battler.proposal:
                await carfigure.unlock()
            battler.proposal.clear()
            await interaction.response.send_message("Deck cleared.", ephemeral=True)

    @button(
        label="Cancel the battle",
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self.battle.user_cancel(self.battle._get_battler(interaction.user))
        await interaction.response.send_message("Battle has been cancelled.", ephemeral=True)


class ConfirmView(View):
    def __init__(self, battle: BattleMenu):
        super().__init__(timeout=90)
        self.battle = battle

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.battle._get_battler(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this battle.", ephemeral=True
            )
            return False
        else:
            return True

    @discord.ui.button(
        style=discord.ButtonStyle.success, emoji="\N{HEAVY CHECK MARK}\N{VARIATION SELECTOR-16}"
    )
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        battler = self.battle._get_battler(interaction.user)
        if battler.accepted:
            await interaction.response.send_message(
                "You have already accepted this battle.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.battle.confirm(battler, interaction)
        if self.battle.battler1.accepted and self.battle.battler2.accepted:
            if result:
                await interaction.followup.send("The battle is now concluded.", ephemeral=True)
            else:
                await interaction.followup.send(
                    ":warning: An error occurred while concluding the battle.", ephemeral=True
                )
        else:
            await interaction.followup.send(
                "You have accepted the battle, waiting for the other user...", ephemeral=True
            )

    @discord.ui.button(
        style=discord.ButtonStyle.danger,
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
    )
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        await self.battle.user_cancel(self.battle._get_battler(interaction.user))
        await interaction.response.send_message("Battle has been cancelled.", ephemeral=True)


class BattleMenu:
    def __init__(
        self,
        cog: BattleCog,
        interaction: discord.Interaction["BallsDexBot"],
        battler1: BattlingUser,
        battler2: BattlingUser,
        max_drivers: int = 10,
        wage: int = 0,
    ):
        self.cog = cog
        self.bot = interaction.client
        self.channel: discord.TextChannel = cast(discord.TextChannel, interaction.channel)
        self.battler1 = battler1
        self.battler2 = battler2
        self.max_drivers = max_drivers
        self.wage = wage
        self.embed = discord.Embed()
        self.task: asyncio.Task | None = None
        self.current_view: BattleView | ConfirmView = BattleView(self)
        self.message: discord.Message
        self.end_time = math.ceil((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())

    def _get_battler(self, user: discord.User | discord.Member) -> BattlingUser:
        if user.id == self.battler1.user.id:
            return self.battler1
        elif user.id == self.battler2.user.id:
            return self.battler2
        raise RuntimeError(f"User with ID {user.id} cannot be found in the battle")

    def _generate_embed(self):
        add_command = self.cog.add.extras.get("mention", "`/battle add`")
        remove_command = self.cog.remove.extras.get("mention", "`/battle remove`")
        timestamp = f"<t:{self.end_time}:R>"
        plural = (
            f"{settings.currency_name}" if self.wage == 1 else f"{settings.plural_currency_name}"
        )

        self.embed.title = "**Battling**"
        self.embed.color = discord.Colour.blurple()
        self.embed.description = (
            f"Add or remove {settings.collectible_name}s from your deck "
            f"using the {add_command} and {remove_command} commands.\n"
            "Once you're finished, click the lock button below to confirm your deck.\n"
            f"*This battle expires {timestamp}.*\n\n"
            f"### Attention: This battle has a wage of {self.wage * 2} "
            f"{settings.plural_currency_name}, which means that by accepting this battle, the "
            f"loser will lose {self.wage} {plural} and the winner "
            f"will gain {self.wage}."
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, but you can keep on editing your deck."
        )

    async def update_message_loop(self):
        """
        A loop task that updates each 5 second the menu with the new content.
        """

        assert self.task
        start_time = datetime.utcnow()

        while True:
            await asyncio.sleep(15)
            if datetime.utcnow() - start_time > timedelta(minutes=15):
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The battle timed out")
                return

            try:
                fill_battle_embed_fields(self.embed, self.bot, self.battler1, self.battler2)
                await self.message.edit(embed=self.embed)
            except Exception:
                log.exception(
                    "Failed to refresh the battle menu "
                    f"guild={self.message.guild.id} "  # type: ignore
                    f"battler1={self.battler1.user.id} battler2={self.battler2.user.id}"
                )
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The battle timed out")
                return

    async def start(self):
        """
        Start the battle by sending the initial message and opening up the proposals.
        """
        self._generate_embed()
        fill_battle_embed_fields(self.embed, self.bot, self.battler1, self.battler2)
        self.message = await self.channel.send(
            content=f"Hey {self.battler2.user.mention}, {self.battler1.user.name} "
            "is proposing a battle with you!",
            embed=self.embed,
            view=self.current_view,
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The battle has been cancelled."):
        """
        Cancel the battle immediately.
        """
        if self.task:
            self.task.cancel()

        for countryball in self.battler1.proposal + self.battler2.proposal:
            await countryball.unlock()

        if self.wage and self.battler1.locked:
            await self.battler1.player.add_coins(self.wage)
        if self.wage and self.battler2.locked:
            await self.battler2.player.add_coins(self.wage)

        self.current_view.stop()
        for item in self.current_view.children:
            item.disabled = True  # type: ignore

        fill_battle_embed_fields(self.embed, self.bot, self.battler1, self.battler2)
        self.embed.description = f"**{reason}**"
        await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def lock(self, battler: BattlingUser):
        """
        Mark a user's proposal as locked, ready for next stage
        """
        battler.locked = True
        if self.battler1.locked and self.battler2.locked:
            if self.task:
                self.task.cancel()
            self.current_view.stop()
            fill_battle_embed_fields(self.embed, self.bot, self.battler1, self.battler2)

            if self.wage:
                await self.battler1.player.remove_coins(self.wage)
                await self.battler2.player.remove_coins(self.wage)

            self.embed.colour = discord.Colour.yellow()
            self.embed.description = (
                "Both users locked their decks! Now confirm to conclude this battle."
            )
            self.current_view = ConfirmView(self)
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)

    async def user_cancel(self, battler: BattlingUser):
        """
        Register a user request to cancel the battle
        """
        battler.cancelled = True
        self.embed.colour = discord.Colour.red()
        await self.cancel()

    async def confirm(self, battler: BattlingUser, interaction: discord.Interaction) -> bool:
        """
        Mark a user's deck as accepted. If both users accept, end the battle now.
        If the battle is concluded, return True.
        """
        attack1 = health1 = attack2 = health2 = 0

        SPECIAL_BUFFS = [
            (0.08, [1, 2, 5, 6, 7, 9, 13, 14, 15, 17, 21]),
            (0.10, [16]),
            (0.18, [18]),
            (0.25, [22]),
            (0.30, [10, 11]),
            (0.35, [19]),
            (0.80, [12]),
            (1.00, [20]),
            (2.00, [4]),
        ]

        async def apply_special_buff(ball: BallInstance):
            atk, hp = ball.attack, ball.health
            if ball.special:
                special = await Special.get(name=ball.special.name)
                for buff, ids in SPECIAL_BUFFS:
                    if special.pk in ids:
                        atk = int(atk * (1 + buff))
                        hp = int(hp * (1 + buff))
                        break

            return atk, hp

        for ball in self.battler1.proposal:
            atk, hp = await apply_special_buff(ball)
            attack1 += atk
            health1 += hp

        for ball in self.battler2.proposal:
            atk, hp = await apply_special_buff(ball)
            attack2 += atk
            health2 += hp

        worl1 = attack1 / health2 if health2 else 0
        worl2 = attack2 / health1 if health1 else 0

        winner = None
        if worl1 > worl2:
            winner = self.battler1
            if self.wage:
                await winner.player.add_coins(self.wage * 2)
        elif worl2 > worl1:
            winner = self.battler2
            if self.wage:
                await winner.player.add_coins(self.wage * 2)
        elif worl1 == worl2:
            if self.wage:
                await self.battler1.player.add_coins(self.wage)
                await self.battler2.player.add_coins(self.wage)

        if (
            winner == self.battler1
            and self.battler1.player.battles_today < settings.max_profitable_battles_per_day
        ):
            await self.battler1.player.add_coins(10)
        elif (
            winner == self.battler2
            and self.battler2.player.battles_today < settings.max_profitable_battles_per_day
        ):
            await self.battler2.player.add_coins(10)
        elif winner is None:
            if self.battler1.player.battles_today < settings.max_profitable_battles_per_day:
                await self.battler1.player.add_coins(10)
            if self.battler2.player.battles_today < settings.max_profitable_battles_per_day:
                await self.battler2.player.add_coins(10)

        battler.accepted = True
        fill_battle_embed_fields(self.embed, self.bot, self.battler1, self.battler2)

        if self.battler1.accepted and self.battler2.accepted:
            if self.task and not self.task.cancelled():
                self.task.cancel()

            if winner is None:
                self.embed.description = (
                    "This battle has ended in a draw. Use stronger "
                    f"{settings.plural_collectible_name} next time!"
                )
            else:
                self.embed.description = (
                    f"**The battle has concluded! {winner.user.mention} is the winner!**"
                )

            self.embed.colour = discord.Colour.green()
            self.current_view.stop()
            for item in self.current_view.children:
                item.disabled = True  # type: ignore

        await self.message.edit(content=None, embed=self.embed, view=self.current_view)

        self.battler1.player.battles_today += 1
        self.battler2.player.battles_today += 1
        await self.battler1.player.save()
        await self.battler2.player.save()

        return True
