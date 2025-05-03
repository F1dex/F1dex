from typing import Optional

import discord
from discord import app_commands

from ballsdex.core.models import (
    DonationPolicy,
    FriendPolicy,
    MentionPolicy,
    Player,
    PrivacyPolicy,
    TradeCooldownPolicy,
)


class Privacy(app_commands.Group):
    """
    Privacy management
    """

    @app_commands.command(name="set")
    @app_commands.choices(
        privacy=[
            app_commands.Choice(name="Open Inventory", value=PrivacyPolicy.ALLOW),
            app_commands.Choice(name="Private Inventory", value=PrivacyPolicy.DENY),
            app_commands.Choice(name="Friends Only", value=PrivacyPolicy.FRIENDS),
            app_commands.Choice(name="Same Server", value=PrivacyPolicy.SAME_SERVER),
        ],
        donation=[
            app_commands.Choice(name="Accept all donations", value=DonationPolicy.ALWAYS_ACCEPT),
            app_commands.Choice(
                name="Request your approval first", value=DonationPolicy.REQUEST_APPROVAL
            ),
            app_commands.Choice(name="Deny all donations", value=DonationPolicy.ALWAYS_DENY),
            app_commands.Choice(
                name="Accept donations from friends only", value=DonationPolicy.FRIENDS_ONLY
            ),
        ],
        trade_cooldown=[
            app_commands.Choice(
                name="Use 10s acceptance cooldown", value=TradeCooldownPolicy.COOLDOWN
            ),
            app_commands.Choice(
                name="Bypass acceptance cooldown", value=TradeCooldownPolicy.BYPASS
            ),
        ],
        mention=[
            app_commands.Choice(name="Accept all mentions", value=MentionPolicy.ALLOW),
            app_commands.Choice(name="Deny all mentions", value=MentionPolicy.DENY),
        ],
        friends=[
            app_commands.Choice(name="Accept all friend requests", value=FriendPolicy.ALLOW),
            app_commands.Choice(name="Deny all friend requests", value=FriendPolicy.DENY),
        ],
    )
    async def policy_set(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        privacy: Optional[PrivacyPolicy] = None,
        donation: Optional[DonationPolicy] = None,
        trade_cooldown: Optional[TradeCooldownPolicy] = None,
        mention: Optional[MentionPolicy] = None,
        friends: Optional[FriendPolicy] = None,
    ):
        """
        Set your various bot policies.

        Parameters
        ----------
        user: discord.User
            The user you want to set the policies for.
        privacy: PrivacyPolicy (Optional)
            Set your privacy policy.
        donation: DonationPolicy (Optional)
            Set your donation policy.
        trade_cooldown: TradeCooldownPolicy (Optional)
            Set your trade cooldown policy.
        mention: MentionPolicy (Optional)
            Set your mention policy.
        friends: FriendPolicy (Optional)
            Set your friend request policy.
        """
        player, _ = await Player.get_or_create(discord_id=user.id)
        messages = []

        if privacy:
            if privacy == PrivacyPolicy.SAME_SERVER and not interaction.client.intents.members:
                await interaction.response.send_message(
                    "I need the `members` intent to use this policy.", ephemeral=True
                )
                return
            player.privacy_policy = privacy
            messages.append(
                f"Successfully changed the privacy policy of {user.name} to **{privacy.name}**."
            )

        if donation:
            player.donation_policy = donation
            messages.append(
                f"Successfully changed the privacy policy of {user.name} to **{donation.name}**."
            )

        if trade_cooldown:
            player.trade_cooldown_policy = trade_cooldown
            messages.append(
                "Successfully changed the privacy policy of "
                f"{user.name} to **{trade_cooldown.name}**."
            )

        if mention:
            player.mention_policy = mention
            messages.append(
                f"Successfully changed the privacy policy of {user.name} to **{mention.name}**."
            )

        if friends:
            player.friend_policy = friends
            messages.append(
                f"Successfully changed the privacy policy of {user.name} to **{friends.name}**."
            )

        if messages:
            await interaction.response.send_message("\n".join(messages), ephemeral=True)
            await player.save()
        else:
            await interaction.response.send_message("No policies were updated.", ephemeral=True)
            return
