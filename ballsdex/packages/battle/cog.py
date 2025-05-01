import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import MISSING

from ballsdex.core.models import Player
from ballsdex.core.utils.transformers import (
    BallInstanceTransform,
    BattleCommandType,
    SpecialEnabledTransform,
)
from ballsdex.packages.battle.battle_user import BattlingUser
from ballsdex.packages.battle.menu import BattleMenu
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def seconds_until_midnight_utc():
    now = datetime.utcnow()
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_midnight - now).total_seconds()


class Battle(commands.GroupCog):
    """
    Battle carfigures with other players.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.battles: dict[int, dict[int, list[BattleMenu]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def get_battle(
        self,
        interaction: discord.Interaction | None = None,
        *,
        channel: discord.TextChannel | None = None,
        user: discord.User | discord.Member = MISSING,
    ) -> tuple[BattleMenu, BattlingUser] | tuple[None, None]:
        """
        Find an ongoing battle for the given interaction.

        Parameters
        ----------
        interaction: discord.Interaction
            The current interaction, used for getting the guild, channel and author.
        Returns
        -------
        tuple[BattleMenu, BattlingUser] | tuple[None, None]
            A tuple with the `BattleMenu` and `BattlingUser` if found, else `None`.
        """
        guild: discord.Guild
        if interaction:
            guild = cast(discord.Guild, interaction.guild)
            channel = cast(discord.TextChannel, interaction.channel)
            user = interaction.user
        elif channel:
            guild = channel.guild
        else:
            raise TypeError("Missing interaction or channel")

        if guild.id not in self.battles:
            return (None, None)
        if channel.id not in self.battles[guild.id]:
            return (None, None)
        to_remove: list[BattleMenu] = []
        for battle in self.battles[guild.id][channel.id]:
            if (
                battle.current_view.is_finished()
                or battle.battler1.cancelled
                or battle.battler2.cancelled
            ):
                # remove what was supposed to have been removed
                to_remove.append(battle)
                continue
            try:
                battler = battle._get_battler(user)
            except RuntimeError:
                continue
            else:
                break
        else:
            for battle in to_remove:
                self.battles[guild.id][channel.id].remove(battle)
            return (None, None)

        for battle in to_remove:
            self.battles[guild.id][channel.id].remove(battle)
        return (battle, battler)

    @app_commands.command()
    async def begin(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User,
        max_countryballs: int | None = None,
        wage: int | None = None,
    ):
        """
        Begin a battle with the chosen user.

        Parameters
        ----------
        user: discord.User
            The user you want to battle with.
        max_countryballs: int | None
            The maximum number of countryballs you can use in the battle, 10 if empty.
        wage: int | None
            The amount of coins that both users will give for the battle, winner gets all.
        """
        if user.bot:
            await interaction.response.send_message("You cannot battle with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot battle with yourself.", ephemeral=True
            )
            return

        if max_countryballs is not None and max_countryballs > 50:
            await interaction.response.send_message(
                f"You cannot battle with more than 50 {settings.plural_collectible_name}.",
                ephemeral=True,
            )
            return

        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.get_or_create(discord_id=user.id)

        if wage is not None and (wage > player1.coins or wage > player2.coins):
            await interaction.response.send_message(
                "The wage amount cannot be more than your "
                f"or the other user's amount of {settings.plural_currency_name}.",
                ephemeral=True,
            )
            return

        battle1, battler1 = self.get_battle(interaction)
        battle2, battler2 = self.get_battle(channel=interaction.channel, user=user)  # type: ignore
        if battle1 or battler1:
            await interaction.response.send_message(
                "You already have an ongoing battle.", ephemeral=True
            )
            return
        if battle2 or battler2:
            await interaction.response.send_message(
                "The user you are trying to battle with is already in a battle.", ephemeral=True
            )
            return

        if player2.discord_id in self.bot.blacklist:
            await interaction.response.send_message(
                "You cannot battle with a blacklisted user.", ephemeral=True
            )
            return

        max_drivers = 10 if max_countryballs is None else max_countryballs
        wage_amount = 0 if wage is None else wage

        menu = BattleMenu(
            self,
            interaction,
            BattlingUser(interaction.user, player1),
            BattlingUser(user, player2),
            max_drivers=max_drivers,
            wage=wage_amount,
        )
        self.battles[interaction.guild.id][interaction.channel.id].append(menu)  # type: ignore
        await menu.start()
        await interaction.response.send_message("Battle started!", ephemeral=True)

    @app_commands.command(extras={"battle": BattleCommandType.PICK})
    async def add(
        self,
        interaction: discord.Interaction,
        countryball: BallInstanceTransform,
        special: SpecialEnabledTransform | None = None,
    ):
        """
        Add a countryball to the ongoing battle.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to add to your deck.
        special: SpecialEnabledTransform | None
            Filter the results of autocompletion to a special event. Ignored afterwards.
        """
        if not countryball:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.followup.send("You do not have an ongoing battle.", ephemeral=True)
            return
        if battler.locked:
            await interaction.followup.send(
                "You have locked your deck, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
            return
        if countryball in battler.proposal:
            await interaction.followup.send(
                f"You already have this {settings.collectible_name} in your deck.",
                ephemeral=True,
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(
                f"This {settings.collectible_name} is currently in an active battle, trade or "
                "donation, please try again later.",
                ephemeral=True,
            )
            return
        if battle.max_drivers and len(battler.proposal) >= battle.max_drivers:
            await interaction.followup.send(
                f"You cannot have more than {battle.max_drivers} "
                f"{settings.plural_collectible_name} in your deck.",
                ephemeral=True,
            )
            return

        battler.proposal.append(countryball)
        await interaction.followup.send(
            f"{settings.collectible_name.title()} added.", ephemeral=True
        )

    @app_commands.command(extras={"battle": BattleCommandType.REMOVE})
    async def remove(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        """
        Remove a countryball from what you proposed in the ongoing battle.

        Parameters
        ----------
        countryball: BallInstance
            The countryball you want to remove from your deck
        """
        if not countryball:
            return

        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.response.send_message(
                "You do not have an ongoing battle.", ephemeral=True
            )
            return
        if battler.locked:
            await interaction.response.send_message(
                "You have locked your deck, it cannot be edited! "
                "You can click the cancel button to stop the battle instead.",
                ephemeral=True,
            )
            return
        if countryball not in battler.proposal:
            await interaction.response.send_message(
                f"That {settings.collectible_name} is not in your deck.", ephemeral=True
            )
            return
        battler.proposal.remove(countryball)
        await interaction.response.send_message(
            f"{settings.collectible_name} removed.", ephemeral=True
        )
        await countryball.unlock()

    @app_commands.command()
    async def cancel(self, interaction: discord.Interaction):
        """
        Cancel the ongoing battle.
        """
        battle, battler = self.get_battle(interaction)
        if not battle or not battler:
            await interaction.response.send_message(
                "You do not have an ongoing battle.", ephemeral=True
            )
            return

        await battle.user_cancel(battler)
        await interaction.response.send_message("Battle cancelled.", ephemeral=True)


class BattleResetCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.reset_battles_at_midnight.start()

    @tasks.loop(hours=24)
    async def reset_battles_at_midnight(self):
        await Player.all().update(trades_today=0)

    @reset_battles_at_midnight.before_loop
    async def before_reset(self):
        await self.bot.wait_until_ready()
        sleep_seconds = seconds_until_midnight_utc()
        print(f"Sleeping {sleep_seconds:.0f} seconds until midnight UTC trade reset.")
        await asyncio.sleep(sleep_seconds)
