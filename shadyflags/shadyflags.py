"""
ShadyFlags - Temporary warning/flag system with account age auto-flagging
Features tiered thresholds for new account detection, auto-expiring flags,
and mod notifications for suspicious joins.
"""

import discord
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from redbot.core import commands, Config
from redbot.core.bot import Red
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadyflags")


class AddFlagModal(discord.ui.Modal, title="Add Flag to User"):
    """Modal for adding flags by user ID."""

    user_id = discord.ui.TextInput(
        label="Discord User ID",
        placeholder="Enter the user's Discord ID...",
        required=True,
        max_length=20
    )

    notes = discord.ui.TextInput(
        label="Reason/Notes",
        placeholder="Why are you flagging this user?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    expiry_days = discord.ui.TextInput(
        label="Expiry (days)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3
    )

    def __init__(self, cog: "ShadyFlags"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        """Handle flag submission."""
        try:
            uid = int(self.user_id.value)
        except ValueError:
            await interaction.response.send_message(
                "Invalid user ID. Please provide a numeric Discord user ID.",
                ephemeral=True
            )
            return

        try:
            days = int(self.expiry_days.value) if self.expiry_days.value else 30
            if days < 1 or days > 365:
                days = 30
        except ValueError:
            days = 30

        # Add flag
        await self.cog.add_flag(
            interaction.guild.id,
            uid,
            interaction.user.id,
            self.notes.value,
            days
        )

        # Get user info if available
        try:
            user = await self.cog.bot.fetch_user(uid)
            user_display = f"{user.name} ({uid})"
        except:
            user_display = f"User ID: {uid}"

        embed = discord.Embed(
            title="✅ Flag Added",
            description=f"Flag added to {user_display}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Notes", value=self.notes.value, inline=False)
        embed.add_field(name="Flagged By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Expires", value=f"In {days} days", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to mod channel
        await self.cog.log_to_mod_channel(
            interaction.guild,
            f"🚩 **Flag Added** by {interaction.user.mention}\n"
            f"**User:** <@{uid}> ({uid})\n"
            f"**Notes:** {self.notes.value}\n"
            f"**Expires:** {days} days"
        )


class ShadyFlags(commands.Cog):
    """Temporary warning/flag system with account age auto-flagging."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820738, force_registration=True)

        default_guild = {
            "flags": [],  # List of {id, user_id, moderator_id, reason, created_at, expires_at, priority}
            "mod_log_channel": None,
            "flag_expiry_days": 30,
            # Account age auto-flagging settings
            "auto_flag_enabled": True,
            "threshold_critical_hours": 24,      # < 24 hours = critical (auto-flag, high priority)
            "threshold_high_days": 7,            # < 7 days = high priority
            "threshold_medium_days": 30,         # < 30 days = medium priority
            "flag_expiry_critical_days": 14,     # How long critical flags last
            "flag_expiry_high_days": 7,          # How long high priority flags last
            "flag_expiry_medium_days": 3,        # How long medium priority flags last
            "next_flag_id": 1,
        }
        self.config.register_guild(**default_guild)

    async def is_authorized(self, member: discord.Member) -> bool:
        """Check if user has permission to manage flags."""
        if member.guild_permissions.administrator or member == member.guild.owner:
            return True

        if await self.bot.is_mod(member) or await self.bot.is_admin(member):
            return True

        return False

    # ===== DATABASE METHODS =====

    async def add_flag(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
        expiry_days: int,
        priority: str = "manual"
    ) -> int:
        """Add a flag to a user. Returns the flag ID."""
        async with self.config.guild_from_id(guild_id).all() as guild_data:
            flag_id = guild_data["next_flag_id"]
            guild_data["next_flag_id"] += 1

            expires_at = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()

            flag = {
                "id": flag_id,
                "user_id": user_id,
                "moderator_id": moderator_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at,
                "priority": priority  # "critical", "high", "medium", "manual"
            }
            guild_data["flags"].append(flag)

            return flag_id

    async def get_flags(self, guild_id: int, user_id: int) -> List[dict]:
        """Get all active flags for a user (auto-cleans expired)."""
        await self._cleanup_expired_flags(guild_id)

        flags = await self.config.guild_from_id(guild_id).flags()
        now = datetime.now(timezone.utc)

        return [
            f for f in flags
            if f["user_id"] == user_id and datetime.fromisoformat(f["expires_at"]) > now
        ]

    async def get_all_flagged(self, guild_id: int) -> List[dict]:
        """Get all flagged users with their flag counts."""
        await self._cleanup_expired_flags(guild_id)

        flags = await self.config.guild_from_id(guild_id).flags()
        now = datetime.now(timezone.utc)

        # Count flags per user
        user_flags = {}
        for f in flags:
            if datetime.fromisoformat(f["expires_at"]) > now:
                uid = f["user_id"]
                if uid not in user_flags:
                    user_flags[uid] = {"user_id": uid, "flag_count": 0, "highest_priority": "manual"}
                user_flags[uid]["flag_count"] += 1

                # Track highest priority
                priority_order = {"critical": 0, "high": 1, "medium": 2, "manual": 3}
                if priority_order.get(f["priority"], 3) < priority_order.get(user_flags[uid]["highest_priority"], 3):
                    user_flags[uid]["highest_priority"] = f["priority"]

        return list(user_flags.values())

    async def clear_flags(self, guild_id: int, user_id: int):
        """Clear all flags for a user."""
        async with self.config.guild_from_id(guild_id).flags() as flags:
            flags[:] = [f for f in flags if f["user_id"] != user_id]

    async def remove_flag(self, guild_id: int, flag_id: int) -> Optional[dict]:
        """Remove a specific flag by ID. Returns the removed flag or None."""
        async with self.config.guild_from_id(guild_id).flags() as flags:
            for i, f in enumerate(flags):
                if f["id"] == flag_id:
                    return flags.pop(i)
        return None

    async def _cleanup_expired_flags(self, guild_id: int):
        """Remove expired flags."""
        now = datetime.now(timezone.utc)
        async with self.config.guild_from_id(guild_id).flags() as flags:
            flags[:] = [f for f in flags if datetime.fromisoformat(f["expires_at"]) > now]

    async def log_to_mod_channel(self, guild: discord.Guild, message: str = None, embed: discord.Embed = None):
        """Log message to mod channel."""
        channel_id = await self.config.guild(guild).mod_log_channel()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if channel:
            try:
                if embed:
                    await channel.send(embed=embed)
                elif message:
                    await channel.send(message)
            except discord.Forbidden:
                log.warning(f"Cannot send to mod log channel in {guild.name}")

    # ===== AUTO-FLAG ON JOIN =====

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Auto-flag new accounts based on account age thresholds."""
        if member.bot:
            return

        enabled = await self.config.guild(member.guild).auto_flag_enabled()
        if not enabled:
            return

        # Get thresholds
        guild_config = await self.config.guild(member.guild).all()
        threshold_critical_hours = guild_config["threshold_critical_hours"]
        threshold_high_days = guild_config["threshold_high_days"]
        threshold_medium_days = guild_config["threshold_medium_days"]

        # Calculate account age
        account_age = datetime.now(timezone.utc) - member.created_at.replace(tzinfo=timezone.utc)
        account_age_hours = account_age.total_seconds() / 3600
        account_age_days = account_age.days

        # Determine priority and whether to flag
        priority = None
        expiry_days = 0

        if account_age_hours < threshold_critical_hours:
            priority = "critical"
            expiry_days = guild_config["flag_expiry_critical_days"]
            age_display = f"{int(account_age_hours)} hours" if account_age_hours >= 1 else f"{int(account_age.total_seconds() / 60)} minutes"
        elif account_age_days < threshold_high_days:
            priority = "high"
            expiry_days = guild_config["flag_expiry_high_days"]
            age_display = f"{account_age_days} days"
        elif account_age_days < threshold_medium_days:
            priority = "medium"
            expiry_days = guild_config["flag_expiry_medium_days"]
            age_display = f"{account_age_days} days"

        if not priority:
            return  # Account is old enough, don't flag

        # Create the auto-flag
        reason = f"[AUTO] New account detected - Account age: {age_display}"
        flag_id = await self.add_flag(
            member.guild.id,
            member.id,
            self.bot.user.id,  # Bot is the moderator for auto-flags
            reason,
            expiry_days,
            priority
        )

        # Send notification to mod channel
        priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(priority, "⚪")
        priority_text = priority.upper()

        embed = discord.Embed(
            title=f"{priority_emoji} New Account Auto-Flagged",
            description=f"{member.mention} has joined with a very new account",
            color={"critical": discord.Color.red(), "high": discord.Color.orange(), "medium": discord.Color.gold()}.get(priority, discord.Color.greyple()),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="Account Age", value=age_display, inline=True)
        embed.add_field(name="Priority", value=priority_text, inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
        embed.add_field(name="Flag Expires", value=f"In {expiry_days} days", inline=True)
        embed.add_field(name="Flag ID", value=str(flag_id), inline=True)

        await self.log_to_mod_channel(member.guild, embed=embed)

    # ===== HELPER FOR EPHEMERAL-LIKE PREFIX COMMANDS =====

    async def _send_ephemeral(self, ctx: commands.Context, content: str = None, embed: discord.Embed = None, delete_after: int = 15):
        """Send a response that auto-deletes, mimicking ephemeral behavior."""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        return await ctx.send(content=content, embed=embed, delete_after=delete_after)

    # ===== PREFIX COMMANDS =====

    @commands.group(name="flag", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    async def flag_group(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """Flag a member with a reason."""
        expiry_days = await self.config.guild(ctx.guild).flag_expiry_days()

        flag_id = await self.add_flag(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            reason,
            expiry_days,
            "manual"
        )

        embed = discord.Embed(
            title="✅ Member Flagged",
            description=f"{member.mention} has been flagged",
            color=discord.Color.green()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Expires", value=f"In {expiry_days} days", inline=True)
        embed.add_field(name="Flag ID", value=str(flag_id), inline=True)

        await self._send_ephemeral(ctx, embed=embed)

        await self.log_to_mod_channel(
            ctx.guild,
            f"🚩 **Member Flagged** by {ctx.author.mention}\n"
            f"**User:** {member.mention}\n"
            f"**Reason:** {reason}"
        )

    @flag_group.command(name="view", aliases=["list", "show"])
    @commands.mod_or_permissions(administrator=True)
    async def flag_view(self, ctx: commands.Context, member: discord.Member):
        """View flags for a member."""
        flags = await self.get_flags(ctx.guild.id, member.id)

        if not flags:
            embed = discord.Embed(
                title="ℹ️ No Flags",
                description=f"{member.mention} has no active flags.",
                color=discord.Color.blue()
            )
            await self._send_ephemeral(ctx, embed=embed)
            return

        embed = discord.Embed(
            title=f"🚩 Flags for {member.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for flag in flags:
            created = datetime.fromisoformat(flag["created_at"])
            expires = datetime.fromisoformat(flag["expires_at"])
            days_left = (expires - datetime.now(timezone.utc)).days

            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "manual": "🚩"}.get(flag["priority"], "🚩")

            value = f"**Reason:** {flag['reason']}\n"
            value += f"**Created:** <t:{int(created.timestamp())}:R>\n"
            value += f"**Expires:** <t:{int(expires.timestamp())}:R> ({days_left} days left)\n"
            value += f"**By:** <@{flag['moderator_id']}>"

            embed.add_field(
                name=f"{priority_emoji} Flag #{flag['id']} ({flag['priority'].upper()})",
                value=value,
                inline=False
            )

        await self._send_ephemeral(ctx, embed=embed)

    @flag_group.command(name="clear", aliases=["remove"])
    @commands.mod_or_permissions(administrator=True)
    async def flag_clear(self, ctx: commands.Context, member: discord.Member):
        """Clear all flags for a member."""
        await self.clear_flags(ctx.guild.id, member.id)

        embed = discord.Embed(
            title="✅ Flags Cleared",
            description=f"All flags removed from {member.mention}",
            color=discord.Color.green()
        )
        await self._send_ephemeral(ctx, embed=embed)

    @flag_group.command(name="delete")
    @commands.mod_or_permissions(administrator=True)
    async def flag_delete(self, ctx: commands.Context, flag_id: int):
        """Delete a specific flag by ID."""
        removed = await self.remove_flag(ctx.guild.id, flag_id)

        if removed:
            embed = discord.Embed(
                title="✅ Flag Removed",
                description=f"Flag #{flag_id} has been removed",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=f"<@{removed['user_id']}>", inline=True)
            embed.add_field(name="Original Reason", value=removed["reason"], inline=False)
            await self._send_ephemeral(ctx, embed=embed)
        else:
            await self._send_ephemeral(ctx, f"Flag #{flag_id} not found.")

    @flag_group.command(name="all")
    @commands.mod_or_permissions(administrator=True)
    async def flag_all(self, ctx: commands.Context):
        """Show all flagged members."""
        flagged_users = await self.get_all_flagged(ctx.guild.id)

        if not flagged_users:
            embed = discord.Embed(
                title="ℹ️ No Flagged Members",
                description="No members are currently flagged",
                color=discord.Color.blue()
            )
            await self._send_ephemeral(ctx, embed=embed)
            return

        # Sort by priority (critical first) then by flag count
        priority_order = {"critical": 0, "high": 1, "medium": 2, "manual": 3}
        flagged_users.sort(key=lambda x: (priority_order.get(x["highest_priority"], 3), -x["flag_count"]))

        embed = discord.Embed(
            title="🚩 Flagged Members",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )

        for user_data in flagged_users[:25]:
            member = ctx.guild.get_member(user_data["user_id"])
            name = f"{member.mention}" if member else f"<@{user_data['user_id']}>"

            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "manual": "🚩"}.get(
                user_data["highest_priority"], "🚩"
            )

            embed.add_field(
                name=name,
                value=f"{priority_emoji} **Flags:** {user_data['flag_count']} | Priority: {user_data['highest_priority'].upper()}",
                inline=True
            )

        if len(flagged_users) > 25:
            embed.set_footer(text=f"Showing 25/{len(flagged_users)} flagged members")

        await self._send_ephemeral(ctx, embed=embed)

    # ===== SLASH COMMANDS =====

    @app_commands.command(name="addflag", description="Add a flag to a user by ID")
    async def slash_add_flag(self, interaction: discord.Interaction):
        """Add a flag to a user by their ID - Opens a form."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        modal = AddFlagModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="viewflags", description="View all flags for a user")
    @app_commands.describe(user="User to check")
    async def slash_view_flags(self, interaction: discord.Interaction, user: discord.Member):
        """View flags for a user."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        flags = await self.get_flags(interaction.guild.id, user.id)

        if not flags:
            embed = discord.Embed(
                title="ℹ️ No Flags",
                description=f"No active flags for {user.mention}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🚩 Flags for {user.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=str(user.id), inline=False)

        for flag in flags:
            created = datetime.fromisoformat(flag["created_at"])
            expires = datetime.fromisoformat(flag["expires_at"])
            days_left = (expires - datetime.now(timezone.utc)).days

            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "manual": "🚩"}.get(flag["priority"], "🚩")

            value = f"**Reason:** {flag['reason']}\n"
            value += f"**Created:** <t:{int(created.timestamp())}:R>\n"
            value += f"**Expires:** <t:{int(expires.timestamp())}:R> ({days_left} days left)\n"
            value += f"**By:** <@{flag['moderator_id']}>"

            embed.add_field(
                name=f"{priority_emoji} Flag #{flag['id']} ({flag['priority'].upper()})",
                value=value,
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remflag", description="Remove a specific flag by ID")
    @app_commands.describe(flag_id="The Flag ID to remove")
    async def slash_remove_flag(self, interaction: discord.Interaction, flag_id: int):
        """Remove a specific flag by ID."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        removed = await self.remove_flag(interaction.guild.id, flag_id)

        if removed:
            embed = discord.Embed(
                title="✅ Flag Removed",
                description=f"Flag #{flag_id} has been removed",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=f"<@{removed['user_id']}>", inline=True)
            embed.add_field(name="Original Reason", value=removed["reason"], inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            await self.log_to_mod_channel(
                interaction.guild,
                f"🗑️ **Flag Removed** by {interaction.user.mention}\n"
                f"**Flag ID:** {flag_id}\n"
                f"**User:** <@{removed['user_id']}>"
            )
        else:
            await interaction.response.send_message(
                f"Flag #{flag_id} not found.",
                ephemeral=True
            )

    # ===== SETTINGS =====

    @commands.group(name="flagset")
    @commands.admin_or_permissions(administrator=True)
    async def flagset_group(self, ctx: commands.Context):
        """Configure ShadyFlags settings."""
        if ctx.invoked_subcommand is None:
            settings = await self.config.guild(ctx.guild).all()

            channel = ctx.guild.get_channel(settings["mod_log_channel"]) if settings["mod_log_channel"] else None

            embed = discord.Embed(
                title="ShadyFlags Settings",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Mod Log Channel", value=channel.mention if channel else "Not set", inline=False)
            embed.add_field(name="Default Flag Expiry", value=f"{settings['flag_expiry_days']} days", inline=True)

            embed.add_field(name="\u200b", value="**Account Age Auto-Flagging**", inline=False)
            embed.add_field(name="Enabled", value="Yes" if settings["auto_flag_enabled"] else "No", inline=True)
            embed.add_field(
                name="Thresholds",
                value=f"🔴 Critical: < {settings['threshold_critical_hours']} hours\n"
                      f"🟠 High: < {settings['threshold_high_days']} days\n"
                      f"🟡 Medium: < {settings['threshold_medium_days']} days",
                inline=True
            )
            embed.add_field(
                name="Flag Expiry by Priority",
                value=f"🔴 Critical: {settings['flag_expiry_critical_days']} days\n"
                      f"🟠 High: {settings['flag_expiry_high_days']} days\n"
                      f"🟡 Medium: {settings['flag_expiry_medium_days']} days",
                inline=True
            )

            await self._send_ephemeral(ctx, embed=embed)

    @flagset_group.command(name="channel")
    async def flagset_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the mod log channel for flag notifications."""
        if channel:
            await self.config.guild(ctx.guild).mod_log_channel.set(channel.id)
            await self._send_ephemeral(ctx, f"Mod log channel set to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).mod_log_channel.set(None)
            await self._send_ephemeral(ctx, "Mod log channel cleared.")

    @flagset_group.command(name="expiry")
    async def flagset_expiry(self, ctx: commands.Context, days: int):
        """Set the default flag expiry in days."""
        if days < 1 or days > 365:
            await self._send_ephemeral(ctx, "Expiry must be between 1 and 365 days.")
            return

        await self.config.guild(ctx.guild).flag_expiry_days.set(days)
        await self._send_ephemeral(ctx, f"Default flag expiry set to {days} days.")

    @flagset_group.command(name="autoflag")
    async def flagset_autoflag(self, ctx: commands.Context, enabled: bool):
        """Enable/disable automatic flagging of new accounts."""
        await self.config.guild(ctx.guild).auto_flag_enabled.set(enabled)
        await self._send_ephemeral(ctx, f"Account age auto-flagging {'enabled' if enabled else 'disabled'}.")

    @flagset_group.command(name="threshold")
    async def flagset_threshold(self, ctx: commands.Context, priority: str, value: int):
        """Set account age threshold for auto-flagging.

        Priority: critical, high, or medium
        Value: hours for critical, days for high/medium
        """
        priority = priority.lower()

        if priority == "critical":
            if value < 1 or value > 168:  # 1 hour to 7 days
                await self._send_ephemeral(ctx, "Critical threshold must be between 1 and 168 hours.")
                return
            await self.config.guild(ctx.guild).threshold_critical_hours.set(value)
            await self._send_ephemeral(ctx, f"Critical threshold set to {value} hours.")

        elif priority == "high":
            if value < 1 or value > 90:
                await self._send_ephemeral(ctx, "High threshold must be between 1 and 90 days.")
                return
            await self.config.guild(ctx.guild).threshold_high_days.set(value)
            await self._send_ephemeral(ctx, f"High threshold set to {value} days.")

        elif priority == "medium":
            if value < 1 or value > 365:
                await self._send_ephemeral(ctx, "Medium threshold must be between 1 and 365 days.")
                return
            await self.config.guild(ctx.guild).threshold_medium_days.set(value)
            await self._send_ephemeral(ctx, f"Medium threshold set to {value} days.")

        else:
            await self._send_ephemeral(ctx, "Priority must be: critical, high, or medium")

    @flagset_group.command(name="flagexpiry")
    async def flagset_flag_expiry(self, ctx: commands.Context, priority: str, days: int):
        """Set how long auto-flags last for each priority.

        Priority: critical, high, or medium
        """
        priority = priority.lower()

        if days < 1 or days > 90:
            await self._send_ephemeral(ctx, "Flag expiry must be between 1 and 90 days.")
            return

        if priority == "critical":
            await self.config.guild(ctx.guild).flag_expiry_critical_days.set(days)
            await self._send_ephemeral(ctx, f"Critical flags will now expire after {days} days.")

        elif priority == "high":
            await self.config.guild(ctx.guild).flag_expiry_high_days.set(days)
            await self._send_ephemeral(ctx, f"High priority flags will now expire after {days} days.")

        elif priority == "medium":
            await self.config.guild(ctx.guild).flag_expiry_medium_days.set(days)
            await self._send_ephemeral(ctx, f"Medium priority flags will now expire after {days} days.")

        else:
            await self._send_ephemeral(ctx, "Priority must be: critical, high, or medium")


async def setup(bot: Red):
    await bot.add_cog(ShadyFlags(bot))
