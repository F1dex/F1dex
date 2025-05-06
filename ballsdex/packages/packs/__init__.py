from typing import TYPE_CHECKING

from ballsdex.packages.packs.cog import Packs

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(Packs(bot))
