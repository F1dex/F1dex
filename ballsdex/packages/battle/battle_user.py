import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot
    from ballsdex.core.models import BallInstance, Battle, Player

log = logging.getLogger("ballsdex.packages.battle")


@dataclass(slots=True)
class BattlingUser:
    user: "discord.User | discord.Member"
    player: "Player"
    proposal: list["BallInstance"] = field(default_factory=list)
    locked: bool = False
    cancelled: bool = False
    accepted: bool = False

    @classmethod
    async def from_battle_model(cls, battle: "Battle", player: "Player", bot: "BallsDexBot"):
        proposal = await battle.battleobjects.filter(player=player).prefetch_related(
            "Ballinstance"
        )
        user = await bot.fetch_user(player.discord_id)
        return cls(user, player, [x.ballinstance for x in proposal])
