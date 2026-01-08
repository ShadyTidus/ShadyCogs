"""
ShadyVoiceMod - Voice moderation cog for RedBot
Handles timed voice mutes with DM notifications and audit logging.
"""

import asyncio
import discord
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify
from redbot.core.utils.predicates import MessagePredicate
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadyvoicemod")


class ExtendMuteModal(discord.ui.Modal, title="Extend Voice Mute"):
    """Modal for extending an existing voice mute."""

    additional_time = discord.ui.TextInput(
        label="Additional Time",
        placeholder="e.g., 30m, 2h, 1d",
        required=True,
        max_length=20,
    )
    additional_reason = discord.ui.TextInput(
        label="Additional Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this mute being extended?",
        required=True,
        max_length=500,
    )

    def __init__(self, cog: "ShadyVoiceMod", target: discord.Member, current_mute: Dict[str, Any]):
        super().__init__()
        self.cog = cog
        self.target = target
        self.current_mute = current_mute

    async def on_submit(self, interaction: discord.Interaction):
        # Check authorization
        if not self.cog.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to extend mutes.",
                ephemeral=True,
            )
            return

        # Parse the additional duration
        duration = await self.cog.parse_duration(str(self.additional_time))
        if duration is None:
            await interaction.response.send_message(
                "Invalid duration format. Use formats like `30m`, `2h`, `1d`.",
                ephemeral=True,
            )
            return

        # Calculate new expiry
        current_expiry = datetime.fromisoformat(self.current_mute["expires_at"])
        new_expiry = current_expiry + duration
        new_reason = f"{self.current_mute['reason']} | Extended: {self.additional_reason}"

        # Update the mute
        async with self.cog.config.guild(interaction.guild).active_mutes() as mutes:
            mutes[str(self.target.id)]["expires_at"] = new_expiry.isoformat()
            mutes[str(self.target.id)]["reason"] = new_reason
            mutes[str(self.target.id)]["extended_by"] = interaction.user.id

        # DM the user about extension
        await self.cog.dm_user_embed(
            self.target,
            "🔇 Voice Mute Extended",
            f"Your voice mute in **{interaction.guild.name}** has been extended.",
            color=discord.Color.orange(),
            fields=[
                {"name": "Additional Reason", "value": str(self.additional_reason), "inline": False},
                {"name": "New Expiry", "value": f"<t:{int(new_expiry.timestamp())}:F> (<t:{int(new_expiry.timestamp())}:R>)", "inline": False},
            ],
        )

        # Audit log
        await self.cog.send_audit_log(
            interaction.guild,
            "Voice Mute Extended",
            self.target,
            interaction.user,
            str(self.additional_reason),
            new_expiry,
            color=discord.Color.orange(),
        )

        await interaction.response.send_message(
            f"Extended voice mute for {self.target.mention}. New expiry: <t:{int(new_expiry.timestamp())}:R>",
            ephemeral=True,
        )


class VoiceMuteModal(discord.ui.Modal, title="Voice Mute User"):
    """Modal for voice muting a user."""

    duration = discord.ui.TextInput(
        label="Duration",
        placeholder="e.g., 30m, 2h, 1d, 1h30m",
        required=True,
        max_length=20,
    )
    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this user being voice muted?",
        required=True,
        max_length=500,
    )

    def __init__(self, cog: "ShadyVoiceMod", target: discord.Member, moderator: discord.Member):
        super().__init__()
        self.cog = cog
        self.target = target
        self.moderator = moderator

    async def on_submit(self, interaction: discord.Interaction):
        # Parse duration
        delta = await self.cog.parse_duration(str(self.duration))
        if delta is None:
            await interaction.response.send_message(
                "Invalid duration format. Use formats like `30m`, `2h`, `1d`, or combine them like `1h30m`.",
                ephemeral=True,
            )
            return

        # Check for existing mute
        active_mutes = await self.cog.config.guild(interaction.guild).active_mutes()
        user_id_str = str(self.target.id)

        if user_id_str in active_mutes:
            current_mute = active_mutes[user_id_str]
            expires_at = datetime.fromisoformat(current_mute["expires_at"])
            original_mod = interaction.guild.get_member(current_mute["mod_id"])
            original_mod_name = original_mod.mention if original_mod else f"Unknown (ID: {current_mute['mod_id']})"

            embed = discord.Embed(
                title="⚠️ User Already Voice Muted",
                description=(
                    f"**{self.target.mention}** is already voice muted.\n\n"
                    f"**Original Moderator:** {original_mod_name}\n"
                    f"**Reason:** {current_mute['reason']}\n"
                    f"**Expires:** <t:{int(expires_at.timestamp())}:R>"
                ),
                color=discord.Color.yellow(),
            )

            view = StackedMuteView(self.cog, self.target, current_mute)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + delta

        # Store mute data
        mute_data = {
            "mod_id": self.moderator.id,
            "reason": str(self.reason),
            "expires_at": expires_at.isoformat(),
            "applied": False,
            "expired": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try to apply immediately if in voice
        if self.target.voice:
            success = await self.cog.apply_mute(self.target)
            if success:
                mute_data["applied"] = True
            else:
                await interaction.response.send_message(
                    "Failed to apply voice mute. Check my permissions.",
                    ephemeral=True,
                )
                return

        # Save to config
        async with self.cog.config.guild(interaction.guild).active_mutes() as mutes:
            mutes[user_id_str] = mute_data

        # DM the user
        dm_success = await self.cog.dm_user_embed(
            self.target,
            "🔇 You Have Been Voice Muted",
            f"You have been voice muted in **{interaction.guild.name}**.\n\nYou will not be able to speak in voice channels until this mute expires or is lifted.",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": str(self.reason), "inline": False},
                {"name": "Duration", "value": humanize_timedelta(timedelta=delta), "inline": True},
                {"name": "Expires", "value": f"<t:{int(expires_at.timestamp())}:F> (<t:{int(expires_at.timestamp())}:R>)", "inline": True},
            ],
        )

        # Audit log
        await self.cog.send_audit_log(
            interaction.guild,
            "Voice Mute Issued",
            self.target,
            self.moderator,
            str(self.reason),
            expires_at,
        )

        # Confirmation
        status = "applied" if mute_data["applied"] else "pending (will apply when user joins voice)"
        dm_status = "" if dm_success else "\n⚠️ Could not DM user."

        embed = discord.Embed(
            title="🔇 Voice Mute Issued",
            color=discord.Color.red(),
        )
        embed.add_field(name="User", value=self.target.mention, inline=True)
        embed.add_field(name="Duration", value=humanize_timedelta(timedelta=delta), inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Reason", value=str(self.reason), inline=False)
        embed.add_field(name="Status", value=status, inline=False)

        if dm_status:
            embed.add_field(name="Notice", value=dm_status, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class VoiceUnmuteModal(discord.ui.Modal, title="Remove Voice Mute"):
    """Modal for removing a voice mute."""

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this mute being removed early?",
        required=False,
        max_length=500,
        default="Manual unmute",
    )

    def __init__(self, cog: "ShadyVoiceMod", target: discord.Member, moderator: discord.Member):
        super().__init__()
        self.cog = cog
        self.target = target
        self.moderator = moderator

    async def on_submit(self, interaction: discord.Interaction):
        active_mutes = await self.cog.config.guild(interaction.guild).active_mutes()
        user_id_str = str(self.target.id)

        if user_id_str not in active_mutes:
            await interaction.response.send_message(
                f"{self.target.mention} does not have an active voice mute.",
                ephemeral=True,
            )
            return

        # Remove from config
        async with self.cog.config.guild(interaction.guild).active_mutes() as mutes:
            mutes.pop(user_id_str, None)

        # Remove Discord mute if in voice
        if self.target.voice:
            await self.cog.remove_mute(self.target)

        # DM user
        await self.cog.dm_user_embed(
            self.target,
            "✅ Voice Mute Removed",
            f"Your voice mute in **{interaction.guild.name}** has been lifted.\n\nYou may now speak in voice channels again.",
            color=discord.Color.green(),
            fields=[
                {"name": "Reason", "value": str(self.reason) or "Manual unmute", "inline": False},
            ],
        )

        # Audit log
        await self.cog.send_audit_log(
            interaction.guild,
            "Voice Mute Removed",
            self.target,
            self.moderator,
            str(self.reason) or "Manual unmute",
            color=discord.Color.green(),
        )

        await interaction.response.send_message(
            f"✅ Voice mute removed from {self.target.mention}.",
            ephemeral=True,
        )


class StackedMuteView(discord.ui.View):
    """View shown when trying to mute an already-muted user."""

    def __init__(self, cog: "ShadyVoiceMod", target: discord.Member, current_mute: Dict[str, Any]):
        super().__init__(timeout=60)
        self.cog = cog
        self.target = target
        self.current_mute = current_mute

    @discord.ui.button(label="This was an error", style=discord.ButtonStyle.secondary)
    async def error_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "No changes made to the existing mute.", ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Extend Mute", style=discord.ButtonStyle.danger)
    async def extend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ExtendMuteModal(self.cog, self.target, self.current_mute)
        await interaction.response.send_modal(modal)
        self.stop()


class ShadyVoiceMod(commands.Cog):
    """Voice moderation with timed mutes, DM notifications, and audit logging."""

    __version__ = "1.0.0"
    __author__ = "Barry"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=86753090, force_registration=True)

        default_guild = {
            "log_channel": None,
            "active_mutes": {},  # str(user_id): {mod_id, reason, expires_at, applied, created_at}
        }
        self.config.register_guild(**default_guild)

        self.expiry_task: Optional[asyncio.Task] = None

        # Load authorized roles from wiki config
        self.allowed_roles = []
        self.load_authorized_roles()

    def load_authorized_roles(self):
        """Load authorized roles from wiki/config/roles.json"""
        try:
            # Get the path to wiki/config/roles.json
            cogs_dir = Path(__file__).parent.parent
            roles_file = cogs_dir / "wiki" / "config" / "roles.json"

            if roles_file.exists():
                with open(roles_file, "r", encoding="utf-8") as f:
                    roles_data = json.load(f)
                    self.allowed_roles = roles_data.get("authorized_roles", [])
                    log.info(f"Loaded {len(self.allowed_roles)} authorized roles from wiki config")
            else:
                log.warning(f"Wiki roles.json not found at {roles_file}, using empty role list")
                self.allowed_roles = []
        except Exception as e:
            log.error(f"Error loading authorized roles: {e}")
            self.allowed_roles = []

    def is_authorized(self, ctx: commands.Context) -> bool:
        """Check if user has one of the allowed roles or admin permissions."""
        # Admin/guild owner always authorized
        if ctx.author.guild_permissions.administrator or ctx.author == ctx.guild.owner:
            return True

        # Check if user has any of the allowed roles
        return any(role.name in self.allowed_roles for role in ctx.author.roles)

    def is_authorized_interaction(self, interaction: discord.Interaction) -> bool:
        """Check if user has one of the allowed roles or admin permissions (for interactions)."""
        if not isinstance(interaction.user, discord.Member):
            return False

        # Admin/guild owner always authorized
        if interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner:
            return True

        # Check if user has any of the allowed roles
        return any(role.name in self.allowed_roles for role in interaction.user.roles)

    async def cog_load(self):
        """Start background task on cog load."""
        self.expiry_task = asyncio.create_task(self.check_expired_mutes())

    async def cog_unload(self):
        """Clean up background task on cog unload."""
        if self.expiry_task:
            self.expiry_task.cancel()

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    async def parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse a duration string like '30m', '2h', '1d' into a timedelta."""
        duration_str = duration_str.strip().lower()
        if not duration_str:
            return None

        units = {
            "s": "seconds",
            "m": "minutes",
            "h": "hours",
            "d": "days",
            "w": "weeks",
        }

        # Try to parse compound durations like "1h30m"
        total_seconds = 0
        current_num = ""

        for char in duration_str:
            if char.isdigit():
                current_num += char
            elif char in units and current_num:
                num = int(current_num)
                if char == "s":
                    total_seconds += num
                elif char == "m":
                    total_seconds += num * 60
                elif char == "h":
                    total_seconds += num * 3600
                elif char == "d":
                    total_seconds += num * 86400
                elif char == "w":
                    total_seconds += num * 604800
                current_num = ""
            else:
                return None

        if total_seconds == 0:
            return None

        return timedelta(seconds=total_seconds)

    async def dm_user(self, user: discord.Member, message: str) -> bool:
        """Attempt to DM a user. Returns True if successful."""
        try:
            await user.send(message)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def dm_user_embed(
        self,
        user: discord.Member,
        title: str,
        description: str,
        color: discord.Color = discord.Color.blue(),
        fields: Optional[list] = None,
    ) -> bool:
        """Attempt to DM a user with an embed. Returns True if successful."""
        try:
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.now(timezone.utc),
            )

            if fields:
                for field in fields:
                    embed.add_field(
                        name=field.get("name", ""),
                        value=field.get("value", ""),
                        inline=field.get("inline", False),
                    )

            embed.set_footer(text=f"Server: {user.guild.name}")
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def send_audit_log(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.Member,
        moderator: discord.Member,
        reason: str,
        expires_at: Optional[datetime] = None,
        color: discord.Color = discord.Color.red(),
    ):
        """Send an embed to the configured audit log channel."""
        log_channel_id = await self.config.guild(guild).log_channel()
        if not log_channel_id:
            return

        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(
            title=f"🔇 {action}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User", value=f"{target.mention} ({target.id})", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        if expires_at:
            embed.add_field(
                name="Expires",
                value=f"<t:{int(expires_at.timestamp())}:F> (<t:{int(expires_at.timestamp())}:R>)",
                inline=False,
            )

        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"User ID: {target.id}")

        try:
            await log_channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def apply_mute(self, member: discord.Member) -> bool:
        """Apply server mute to a member. Returns True if successful."""
        try:
            await member.edit(mute=True, reason="ShadyVoiceMod: Timed voice mute")
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def remove_mute(self, member: discord.Member) -> bool:
        """Remove server mute from a member. Returns True if successful."""
        try:
            await member.edit(mute=False, reason="ShadyVoiceMod: Voice mute expired/removed")
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    # -------------------------------------------------------------------------
    # Background Task
    # -------------------------------------------------------------------------

    async def check_expired_mutes(self):
        """Background task to check for and process expired mutes."""
        await self.bot.wait_until_ready()

        while True:
            try:
                all_guilds = await self.config.all_guilds()

                for guild_id, guild_data in all_guilds.items():
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue

                    active_mutes = guild_data.get("active_mutes", {})

                    for user_id_str, mute_data in active_mutes.items():
                        expires_at = datetime.fromisoformat(mute_data["expires_at"])

                        # Skip if already marked as expired
                        if mute_data.get("expired", False):
                            continue

                        if datetime.now(timezone.utc) >= expires_at:
                            member = guild.get_member(int(user_id_str))

                            # Mark as expired
                            async with self.config.guild(guild).active_mutes() as mutes:
                                if user_id_str in mutes:
                                    mutes[user_id_str]["expired"] = True

                            if member:
                                # DM user immediately (regardless of voice state)
                                await self.dm_user_embed(
                                    member,
                                    "✅ Voice Mute Expired",
                                    f"Your voice mute in **{guild.name}** has expired.\n\nYou may now speak in voice channels again.",
                                    color=discord.Color.green(),
                                )

                                # Audit log
                                bot_member = guild.get_member(self.bot.user.id)
                                await self.send_audit_log(
                                    guild,
                                    "Voice Mute Expired",
                                    member,
                                    bot_member,
                                    "Mute duration completed",
                                    color=discord.Color.green(),
                                )

                                # If in voice, remove mute now and clean up
                                if member.voice:
                                    await self.remove_mute(member)
                                    async with self.config.guild(guild).active_mutes() as mutes:
                                        mutes.pop(user_id_str, None)
                                # If not in voice but was never applied, clean up now
                                elif not mute_data.get("applied", False):
                                    async with self.config.guild(guild).active_mutes() as mutes:
                                        mutes.pop(user_id_str, None)
                                # If not in voice but was applied, keep in config for removal on next join
                            else:
                                # User not found, clean up
                                async with self.config.guild(guild).active_mutes() as mutes:
                                    mutes.pop(user_id_str, None)

            except Exception as e:
                # Log errors but don't crash the loop
                log.exception(f"Error in check_expired_mutes task: {e}")

            await asyncio.sleep(30)

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Apply pending mutes when user joins voice."""
        # Only care about joining a voice channel
        if before.channel is not None or after.channel is None:
            return

        # Check if user has a pending mute
        active_mutes = await self.config.guild(member.guild).active_mutes()
        user_id_str = str(member.id)

        if user_id_str not in active_mutes:
            return

        mute_data = active_mutes[user_id_str]

        # Check if mute has expired
        if mute_data.get("expired", False):
            # Mute expired and user joined voice
            # If it was applied at some point, remove it now
            if mute_data.get("applied", False):
                await self.remove_mute(member)

            # Clean up
            async with self.config.guild(member.guild).active_mutes() as mutes:
                mutes.pop(user_id_str, None)
            return

        # Mute is still active - check if already applied
        if mute_data.get("applied", False):
            return

        # Apply the mute
        success = await self.apply_mute(member)

        if success:
            async with self.config.guild(member.guild).active_mutes() as mutes:
                if user_id_str in mutes:
                    mutes[user_id_str]["applied"] = True

    # -------------------------------------------------------------------------
    # Commands - Voice Mute Management
    # -------------------------------------------------------------------------

    @commands.command(name="vmute")
    @commands.guild_only()
    async def voice_mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str,
    ):
        """
        Voice mute a user for a specified duration.

        Duration formats: 30s, 5m, 2h, 1d, 1w (can combine: 1h30m)

        Examples:
            [p]vmute @user 30m Being disruptive in voice
            [p]vmute @user 2h Mic spamming
        """
        # Check authorization
        if not self.is_authorized(ctx):
            return await ctx.send("You do not have permission to use this command.")

        # Can't mute yourself
        if member.id == ctx.author.id:
            return await ctx.send("You cannot voice mute yourself.")

        # Can't mute bots
        if member.bot:
            return await ctx.send("You cannot voice mute bots.")

        # Check hierarchy
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot voice mute someone with an equal or higher role.")

        # Parse duration
        delta = await self.parse_duration(duration)
        if delta is None:
            return await ctx.send(
                "Invalid duration format. Use formats like `30m`, `2h`, `1d`, or combine them like `1h30m`."
            )

        # Check for existing mute
        active_mutes = await self.config.guild(ctx.guild).active_mutes()
        user_id_str = str(member.id)

        if user_id_str in active_mutes:
            current_mute = active_mutes[user_id_str]
            expires_at = datetime.fromisoformat(current_mute["expires_at"])
            original_mod = ctx.guild.get_member(current_mute["mod_id"])
            original_mod_name = original_mod.mention if original_mod else f"Unknown (ID: {current_mute['mod_id']})"

            embed = discord.Embed(
                title="⚠️ User Already Voice Muted",
                description=(
                    f"**{member.mention}** is already voice muted.\n\n"
                    f"**Original Moderator:** {original_mod_name}\n"
                    f"**Reason:** {current_mute['reason']}\n"
                    f"**Expires:** <t:{int(expires_at.timestamp())}:R>"
                ),
                color=discord.Color.yellow(),
            )

            view = StackedMuteView(self, member, current_mute)
            await ctx.send(embed=embed, view=view)
            return

        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + delta

        # Store mute data
        mute_data = {
            "mod_id": ctx.author.id,
            "reason": reason,
            "expires_at": expires_at.isoformat(),
            "applied": False,
            "expired": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try to apply immediately if in voice
        if member.voice:
            success = await self.apply_mute(member)
            if success:
                mute_data["applied"] = True
            else:
                return await ctx.send(
                    "Failed to apply voice mute. Check my permissions."
                )

        # Save to config
        async with self.config.guild(ctx.guild).active_mutes() as mutes:
            mutes[user_id_str] = mute_data

        # DM the user
        dm_success = await self.dm_user_embed(
            member,
            "🔇 You Have Been Voice Muted",
            f"You have been voice muted in **{ctx.guild.name}**.\n\nYou will not be able to speak in voice channels until this mute expires or is lifted.",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": reason, "inline": False},
                {"name": "Duration", "value": humanize_timedelta(timedelta=delta), "inline": True},
                {"name": "Expires", "value": f"<t:{int(expires_at.timestamp())}:F> (<t:{int(expires_at.timestamp())}:R>)", "inline": True},
            ],
        )

        # Audit log
        await self.send_audit_log(
            ctx.guild,
            "Voice Mute Issued",
            member,
            ctx.author,
            reason,
            expires_at,
        )

        # Confirmation
        status = "applied" if mute_data["applied"] else "pending (will apply when user joins voice)"
        dm_status = "" if dm_success else "\n⚠️ Could not DM user."

        embed = discord.Embed(
            title="🔇 Voice Mute Issued",
            color=discord.Color.red(),
        )
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Duration", value=humanize_timedelta(timedelta=delta), inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Status", value=status, inline=False)

        if dm_status:
            embed.add_field(name="Notice", value=dm_status, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="vunmute")
    @commands.guild_only()
    async def voice_unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Manual unmute"):
        """
        Manually remove a voice mute from a user.

        Examples:
            [p]vunmute @user
            [p]vunmute @user Appealed successfully
        """
        # Check authorization
        if not self.is_authorized(ctx):
            return await ctx.send("You do not have permission to use this command.")

        active_mutes = await self.config.guild(ctx.guild).active_mutes()
        user_id_str = str(member.id)

        if user_id_str not in active_mutes:
            return await ctx.send(f"{member.mention} does not have an active voice mute.")

        # Remove from config
        async with self.config.guild(ctx.guild).active_mutes() as mutes:
            mutes.pop(user_id_str, None)

        # Remove Discord mute if in voice
        if member.voice:
            await self.remove_mute(member)

        # DM user
        await self.dm_user_embed(
            member,
            "✅ Voice Mute Removed",
            f"Your voice mute in **{ctx.guild.name}** has been lifted.\n\nYou may now speak in voice channels again.",
            color=discord.Color.green(),
            fields=[
                {"name": "Reason", "value": reason, "inline": False},
            ],
        )

        # Audit log
        await self.send_audit_log(
            ctx.guild,
            "Voice Mute Removed",
            member,
            ctx.author,
            reason,
            color=discord.Color.green(),
        )

        await ctx.send(f"✅ Voice mute removed from {member.mention}.")

    @commands.command(name="vmutes")
    @commands.guild_only()
    async def list_voice_mutes(self, ctx: commands.Context):
        """List all active and pending voice mutes."""
        # Check authorization
        if not self.is_authorized(ctx):
            return await ctx.send("You do not have permission to use this command.")

        active_mutes = await self.config.guild(ctx.guild).active_mutes()

        if not active_mutes:
            return await ctx.send("No active voice mutes.")

        lines = []
        now = datetime.now(timezone.utc)

        for user_id_str, mute_data in active_mutes.items():
            member = ctx.guild.get_member(int(user_id_str))
            expires_at = datetime.fromisoformat(mute_data["expires_at"])
            mod = ctx.guild.get_member(mute_data["mod_id"])

            # Skip expired (cleanup will handle these)
            if now >= expires_at:
                continue

            user_str = member.mention if member else f"Unknown ({user_id_str})"
            mod_str = mod.display_name if mod else f"Unknown"
            status = "✅ Applied" if mute_data["applied"] else "⏳ Pending"

            lines.append(
                f"**{user_str}**\n"
                f"  └ By: {mod_str} | Expires: <t:{int(expires_at.timestamp())}:R> | {status}\n"
                f"  └ Reason: {mute_data['reason'][:50]}{'...' if len(mute_data['reason']) > 50 else ''}"
            )

        if not lines:
            return await ctx.send("No active voice mutes.")

        embed = discord.Embed(
            title="🔇 Active Voice Mutes",
            description="\n\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Total: {len(lines)} mute(s)")

        await ctx.send(embed=embed)

    # -------------------------------------------------------------------------
    # Commands - Settings
    # -------------------------------------------------------------------------

    @commands.group(name="vmodset")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def vmod_settings(self, ctx: commands.Context):
        """ShadyVoiceMod settings."""
        if ctx.invoked_subcommand is None:
            log_channel_id = await self.config.guild(ctx.guild).log_channel()
            log_channel = ctx.guild.get_channel(log_channel_id) if log_channel_id else None

            embed = discord.Embed(
                title="ShadyVoiceMod Settings",
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name="Log Channel",
                value=log_channel.mention if log_channel else "Not set",
                inline=False,
            )

            await ctx.send(embed=embed)

    @vmod_settings.command(name="logchannel")
    async def set_log_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """
        Set the audit log channel for voice mod actions.

        Leave channel empty to disable logging.

        Examples:
            [p]vmodset logchannel #mod-logs
            [p]vmodset logchannel
        """
        if channel is None:
            await self.config.guild(ctx.guild).log_channel.set(None)
            return await ctx.send("✅ Audit logging disabled.")

        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"✅ Audit log channel set to {channel.mention}.")

    # -------------------------------------------------------------------------
    # Info Command
    # -------------------------------------------------------------------------

    @commands.command(name="vmodinfo")
    @commands.guild_only()
    async def vmod_info(self, ctx: commands.Context):
        """Show ShadyVoiceMod information and commands."""
        embed = discord.Embed(
            title="🔇 ShadyVoiceMod",
            description="Voice moderation with timed mutes, DM notifications, and audit logging.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Commands",
            value=(
                f"`{ctx.prefix}vmute <user> <duration> <reason>` - Voice mute a user\n"
                f"`{ctx.prefix}vunmute <user> [reason]` - Remove a voice mute\n"
                f"`{ctx.prefix}vmutes` - List active voice mutes\n"
                f"`{ctx.prefix}vmodset` - Configure settings\n"
                f"`{ctx.prefix}vmodinfo` - This help message"
            ),
            inline=False,
        )

        embed.add_field(
            name="Duration Formats",
            value="`30s` (seconds), `5m` (minutes), `2h` (hours), `1d` (days), `1w` (weeks)\nCombine: `1h30m`, `2d12h`",
            inline=False,
        )

        embed.set_footer(text=f"v{self.__version__} by {self.__author__}")

        await ctx.send(embed=embed)

    # -------------------------------------------------------------------------
    # Slash Commands
    # -------------------------------------------------------------------------

    @app_commands.command(name="vmute", description="Voice mute a user for a specified duration")
    @app_commands.describe(member="The user to voice mute")
    @app_commands.guild_only()
    async def vmute_slash(self, interaction: discord.Interaction, member: discord.Member):
        """Voice mute a user with a modal for duration and reason."""
        # Check authorization
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        # Can't mute yourself
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot voice mute yourself.",
                ephemeral=True,
            )
            return

        # Can't mute bots
        if member.bot:
            await interaction.response.send_message(
                "You cannot voice mute bots.",
                ephemeral=True,
            )
            return

        # Check hierarchy
        if isinstance(interaction.user, discord.Member):
            if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
                await interaction.response.send_message(
                    "You cannot voice mute someone with an equal or higher role.",
                    ephemeral=True,
                )
                return

        # Show modal
        modal = VoiceMuteModal(self, member, interaction.user)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="vunmute", description="Remove a voice mute from a user")
    @app_commands.describe(member="The user to unmute")
    @app_commands.guild_only()
    async def vunmute_slash(self, interaction: discord.Interaction, member: discord.Member):
        """Remove a voice mute with a modal for the reason."""
        # Check authorization
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        # Check if user has an active mute
        active_mutes = await self.config.guild(interaction.guild).active_mutes()
        user_id_str = str(member.id)

        if user_id_str not in active_mutes:
            await interaction.response.send_message(
                f"{member.mention} does not have an active voice mute.",
                ephemeral=True,
            )
            return

        # Show modal
        modal = VoiceUnmuteModal(self, member, interaction.user)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="vmutes", description="List all active voice mutes")
    @app_commands.guild_only()
    async def vmutes_slash(self, interaction: discord.Interaction):
        """List all active and pending voice mutes."""
        # Check authorization
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        active_mutes = await self.config.guild(interaction.guild).active_mutes()

        if not active_mutes:
            await interaction.response.send_message("No active voice mutes.", ephemeral=True)
            return

        lines = []
        now = datetime.now(timezone.utc)

        for user_id_str, mute_data in active_mutes.items():
            member = interaction.guild.get_member(int(user_id_str))
            expires_at = datetime.fromisoformat(mute_data["expires_at"])
            mod = interaction.guild.get_member(mute_data["mod_id"])

            # Skip expired (cleanup will handle these)
            if now >= expires_at:
                continue

            user_str = member.mention if member else f"Unknown ({user_id_str})"
            mod_str = mod.display_name if mod else f"Unknown"
            status = "✅ Applied" if mute_data["applied"] else "⏳ Pending"

            lines.append(
                f"**{user_str}**\n"
                f"  └ By: {mod_str} | Expires: <t:{int(expires_at.timestamp())}:R> | {status}\n"
                f"  └ Reason: {mute_data['reason'][:50]}{'...' if len(mute_data['reason']) > 50 else ''}"
            )

        if not lines:
            await interaction.response.send_message("No active voice mutes.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔇 Active Voice Mutes",
            description="\n\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Total: {len(lines)} mute(s)")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="vmodinfo", description="Show ShadyVoiceMod information and commands")
    @app_commands.guild_only()
    async def vmodinfo_slash(self, interaction: discord.Interaction):
        """Show ShadyVoiceMod information and commands."""
        embed = discord.Embed(
            title="🔇 ShadyVoiceMod",
            description="Voice moderation with timed mutes, DM notifications, and audit logging.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Slash Commands",
            value=(
                "`/vmute <user>` - Voice mute a user (opens modal)\n"
                "`/vunmute <user>` - Remove a voice mute (opens modal)\n"
                "`/vmutes` - List active voice mutes\n"
                "`/vmodinfo` - This help message"
            ),
            inline=False,
        )

        embed.add_field(
            name="Prefix Commands",
            value=(
                f"`{interaction.client.command_prefix if hasattr(interaction.client, 'command_prefix') else '[p]'}vmute <user> <duration> <reason>` - Voice mute a user\n"
                f"`{interaction.client.command_prefix if hasattr(interaction.client, 'command_prefix') else '[p]'}vunmute <user> [reason]` - Remove a voice mute\n"
                f"`{interaction.client.command_prefix if hasattr(interaction.client, 'command_prefix') else '[p]'}vmutes` - List active voice mutes\n"
                f"`{interaction.client.command_prefix if hasattr(interaction.client, 'command_prefix') else '[p]'}vmodset` - Configure settings"
            ),
            inline=False,
        )

        embed.add_field(
            name="Duration Formats",
            value="`30s` (seconds), `5m` (minutes), `2h` (hours), `1d` (days), `1w` (weeks)\nCombine: `1h30m`, `2d12h`",
            inline=False,
        )

        embed.set_footer(text=f"v{self.__version__} by {self.__author__}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
