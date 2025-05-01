from typing import TYPE_CHECKING

from ballsdex.packages.battle.cog import Battle, BattleResetCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Battle(bot))
    await bot.add_cog(BattleResetCog(bot))
