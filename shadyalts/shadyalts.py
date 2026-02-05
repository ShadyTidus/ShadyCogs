"""
ShadyAlts - Alt account tracking for moderation
Features bidirectional alt linking, join/leave notifications for known alts,
and slash commands with modal forms.
"""

import discord
import logging
from datetime import datetime, timezone
from typing import Optional, List

from redbot.core import commands, Config
from redbot.core.bot import Red
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadyalts")


class MarkAltModal(discord.ui.Modal, title="Mark Users as Alts"):
    """Modal for marking alt accounts by user ID."""

    user1_id = discord.ui.TextInput(
        label="First User ID",
        placeholder="Enter first user's Discord ID...",
        required=True,
        max_length=20
    )

    user2_id = discord.ui.TextInput(
        label="Second User ID",
        placeholder="Enter second user's Discord ID...",
        required=True,
        max_length=20
    )

    reason = discord.ui.TextInput(
        label="Reason (optional)",
        placeholder="Why are these accounts linked?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    def __init__(self, cog: "ShadyAlts"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        """Handle alt marking submission."""
        try:
            uid1 = int(self.user1_id.value)
            uid2 = int(self.user2_id.value)
        except ValueError:
            await interaction.response.send_message(
                "Invalid user IDs. Please provide numeric Discord user IDs.",
                ephemeral=True
            )
            return

        if uid1 == uid2:
            await interaction.response.send_message(
                "Cannot mark a user as their own alt.",
                ephemeral=True
            )
            return

        reason = self.reason.value if self.reason.value else None

        # Check if already linked
        if await self.cog.is_alt(interaction.guild.id, uid1, uid2):
            await interaction.response.send_message(
                "These accounts are already linked as alts.",
                ephemeral=True
            )
            return

        # Add alt relationship (bidirectional)
        await self.cog.add_alt(interaction.guild.id, uid1, uid2, reason)

        # Get user info
        try:
            u1 = await self.cog.bot.fetch_user(uid1)
            u1_display = f"{u1.name} ({uid1})"
        except:
            u1_display = f"User ID: {uid1}"

        try:
            u2 = await self.cog.bot.fetch_user(uid2)
            u2_display = f"{u2.name} ({uid2})"
        except:
            u2_display = f"User ID: {uid2}"

        # Get full network
        alts = await self.cog.get_alts(interaction.guild.id, uid1)

        embed = discord.Embed(
            title="Alts Linked",
            description=f"Linked {u1_display} ↔ {u2_display}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Network Size", value=f"{len(alts) + 1} accounts", inline=True)
        embed.add_field(name="Marked By", value=interaction.user.mention, inline=True)

        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        if alts:
            network_list = []
            for alt in alts[:10]:
                try:
                    u = await self.cog.bot.fetch_user(alt["alt_id"])
                    network_list.append(f"• {u.name} ({alt['alt_id']})")
                except:
                    network_list.append(f"• User ID: {alt['alt_id']}")

            if len(alts) > 10:
                network_list.append(f"... and {len(alts) - 10} more")

            embed.add_field(name="Full Network", value="\n".join(network_list), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to mod channel
        await self.cog.log_to_mod_channel(
            interaction.guild,
            f"🔗 **Alts Linked** by {interaction.user.mention}\n"
            f"**Users:** <@{uid1}> ↔ <@{uid2}>\n"
            f"**Network Size:** {len(alts) + 1} accounts"
        )


class ShadyAlts(commands.Cog):
    """Alt account tracking and notifications."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820737, force_registration=True)

        default_guild = {
            "alts": [],  # List of {user_id, alt_id, reason, created_at}
            "mod_log_channel": None,
            "notify_on_join": True,
            "notify_on_leave": True,
        }
        self.config.register_guild(**default_guild)

    async def is_authorized(self, member: discord.Member) -> bool:
        """Check if user has permission to manage alts."""
        if member.guild_permissions.administrator or member == member.guild.owner:
            return True

        # Check mod/admin roles
        if await self.bot.is_mod(member) or await self.bot.is_admin(member):
            return True

        return False

    # ===== DATABASE METHODS =====

    async def add_alt(self, guild_id: int, user_id: int, alt_id: int, reason: str = None):
        """Add alt relationship (bidirectional)."""
        async with self.config.guild_from_id(guild_id).alts() as alts:
            # Add both directions
            entry1 = {
                "user_id": user_id,
                "alt_id": alt_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            entry2 = {
                "user_id": alt_id,
                "alt_id": user_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            # Only add if not exists
            exists1 = any(a["user_id"] == user_id and a["alt_id"] == alt_id for a in alts)
            exists2 = any(a["user_id"] == alt_id and a["alt_id"] == user_id for a in alts)

            if not exists1:
                alts.append(entry1)
            if not exists2:
                alts.append(entry2)

    async def remove_alt(self, guild_id: int, user_id: int, alt_id: int):
        """Remove alt relationship (bidirectional)."""
        async with self.config.guild_from_id(guild_id).alts() as alts:
            alts[:] = [
                a for a in alts
                if not ((a["user_id"] == user_id and a["alt_id"] == alt_id) or
                        (a["user_id"] == alt_id and a["alt_id"] == user_id))
            ]

    async def get_alts(self, guild_id: int, user_id: int) -> List[dict]:
        """Get all alts for a user."""
        alts = await self.config.guild_from_id(guild_id).alts()
        return [a for a in alts if a["user_id"] == user_id]

    async def is_alt(self, guild_id: int, user_id: int, alt_id: int) -> bool:
        """Check if two users are linked as alts."""
        alts = await self.config.guild_from_id(guild_id).alts()
        return any(a["user_id"] == user_id and a["alt_id"] == alt_id for a in alts)

    async def log_to_mod_channel(self, guild: discord.Guild, message: str = None, embed: discord.Embed = None):
        """Log message to mod channel."""
        channel_id = await self.config.guild(guild).mod_log_channel()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if channel:
            if embed:
                await channel.send(embed=embed)
            elif message:
                await channel.send(message)

    # ===== EVENTS =====

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Notify when a user with known alts joins."""
        if member.bot:
            return

        notify = await self.config.guild(member.guild).notify_on_join()
        if not notify:
            return

        alts = await self.get_alts(member.guild.id, member.id)

        if alts:
            embed = discord.Embed(
                title="⚠️ Known Alt Joined",
                description=f"{member.mention} (`{member.id}`) just joined and has {len(alts)} known alt(s)",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            alts_text = "\n".join([f"• <@{alt['alt_id']}> (`{alt['alt_id']}`)" for alt in alts[:10]])
            if len(alts) > 10:
                alts_text += f"\n... and {len(alts) - 10} more"

            embed.add_field(name="Known Alts", value=alts_text, inline=False)

            await self.log_to_mod_channel(member.guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Notify when a user with known alts leaves."""
        if member.bot:
            return

        notify = await self.config.guild(member.guild).notify_on_leave()
        if not notify:
            return

        alts = await self.get_alts(member.guild.id, member.id)

        if alts:
            embed = discord.Embed(
                title="ℹ️ Known Alt Left",
                description=f"{member} (`{member.id}`) left the server (had {len(alts)} known alt(s))",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
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

    @commands.group(name="alt", aliases=["alts"], invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    async def alt_group(self, ctx: commands.Context, member: discord.Member):
        """View alt accounts for a member."""
        alts = await self.get_alts(ctx.guild.id, member.id)

        if not alts:
            embed = discord.Embed(
                title="ℹ️ No Alts Found",
                description=f"{member.mention} has no known alt accounts.",
                color=discord.Color.blue()
            )
            await self._send_ephemeral(ctx, embed=embed)
            return

        embed = discord.Embed(
            title=f"🔍 Alt Accounts for {member.display_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        alts_text = ""
        for alt in alts:
            alts_text += f"• <@{alt['alt_id']}> (`{alt['alt_id']}`)\n"
            if alt.get("reason"):
                alts_text += f"  └─ _{alt['reason']}_\n"

        embed.add_field(name=f"Known Alts ({len(alts)})", value=alts_text, inline=False)
        await self._send_ephemeral(ctx, embed=embed)

    @alt_group.command(name="mark", aliases=["add", "link"])
    @commands.mod_or_permissions(administrator=True)
    async def alt_mark(self, ctx: commands.Context, member1: discord.Member, member2: discord.Member, *, reason: str = None):
        """Mark two accounts as alts."""
        if member1.id == member2.id:
            await self._send_ephemeral(ctx, "Cannot mark a user as their own alt.")
            return

        if await self.is_alt(ctx.guild.id, member1.id, member2.id):
            await self._send_ephemeral(ctx, f"{member2.mention} is already marked as an alt of {member1.mention}")
            return

        await self.add_alt(ctx.guild.id, member1.id, member2.id, reason)

        embed = discord.Embed(
            title="✅ Alts Linked",
            description=f"{member2.mention} is now marked as an alt of {member1.mention}",
            color=discord.Color.green()
        )
        if reason:
            embed.add_field(name="Reason", value=reason)

        await self._send_ephemeral(ctx, embed=embed)

        await self.log_to_mod_channel(
            ctx.guild,
            f"🔗 **Alt Linked** by {ctx.author.mention}\n{member1.mention} ↔️ {member2.mention}"
        )

    @alt_group.command(name="unmark", aliases=["remove", "unlink"])
    @commands.mod_or_permissions(administrator=True)
    async def alt_unmark(self, ctx: commands.Context, member1: discord.Member, member2: discord.Member):
        """Unmark alt relationship."""
        if not await self.is_alt(ctx.guild.id, member1.id, member2.id):
            await self._send_ephemeral(ctx, "These accounts are not marked as alts.")
            return

        await self.remove_alt(ctx.guild.id, member1.id, member2.id)

        embed = discord.Embed(
            title="✅ Alts Unlinked",
            description=f"Removed alt relationship between {member1.mention} and {member2.mention}",
            color=discord.Color.green()
        )
        await self._send_ephemeral(ctx, embed=embed)

    # ===== SLASH COMMANDS =====

    @app_commands.command(name="markalt", description="Mark users as alts (link their accounts)")
    async def slash_mark_alt(self, interaction: discord.Interaction):
        """Mark two users as alts of each other - Opens a form."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        modal = MarkAltModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="viewalts", description="View alt network for a user")
    @app_commands.describe(user="User to check (or enter user ID)")
    async def slash_view_alts(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """View all alts for a user."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        if not user:
            await interaction.response.send_message(
                "Please specify a user to check.",
                ephemeral=True
            )
            return

        alts = await self.get_alts(interaction.guild.id, user.id)

        if not alts:
            embed = discord.Embed(
                title="ℹ️ No Alts",
                description=f"No known alts for {user.mention}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔗 Alt Network for {user.display_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Primary Account", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="Network Size", value=f"{len(alts) + 1} accounts", inline=False)

        alt_list = []
        for alt in alts[:20]:
            try:
                u = await self.bot.fetch_user(alt["alt_id"])
                alt_list.append(f"• <@{alt['alt_id']}> - {u.name} ({alt['alt_id']})")
            except:
                alt_list.append(f"• <@{alt['alt_id']}> ({alt['alt_id']})")

        if len(alts) > 20:
            alt_list.append(f"... and {len(alts) - 20} more")

        embed.add_field(name="Linked Accounts", value="\n".join(alt_list), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="viewaltsid", description="View alt network for a user by ID (for users not in server)")
    @app_commands.describe(user_id="Discord User ID")
    async def slash_view_alts_id(self, interaction: discord.Interaction, user_id: str):
        """View all alts for a user by their ID."""
        if not await self.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(
                "Invalid user ID. Please provide a numeric Discord user ID.",
                ephemeral=True
            )
            return

        alts = await self.get_alts(interaction.guild.id, uid)

        # Get user info
        try:
            user = await self.bot.fetch_user(uid)
            user_display = f"{user.name}"
        except:
            user_display = f"User ID: {uid}"

        if not alts:
            embed = discord.Embed(
                title="ℹ️ No Alts",
                description=f"No known alts for {user_display}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔗 Alt Network for {user_display}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Primary Account", value=f"<@{uid}> ({uid})", inline=False)
        embed.add_field(name="Network Size", value=f"{len(alts) + 1} accounts", inline=False)

        alt_list = []
        for alt in alts[:20]:
            try:
                u = await self.bot.fetch_user(alt["alt_id"])
                alt_list.append(f"• <@{alt['alt_id']}> - {u.name} ({alt['alt_id']})")
            except:
                alt_list.append(f"• <@{alt['alt_id']}> ({alt['alt_id']})")

        if len(alts) > 20:
            alt_list.append(f"... and {len(alts) - 20} more")

        embed.add_field(name="Linked Accounts", value="\n".join(alt_list), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ===== SETTINGS =====

    @commands.group(name="altset")
    @commands.admin_or_permissions(administrator=True)
    async def altset_group(self, ctx: commands.Context):
        """Configure ShadyAlts settings."""
        if ctx.invoked_subcommand is None:
            settings = {
                "mod_log_channel": await self.config.guild(ctx.guild).mod_log_channel(),
                "notify_on_join": await self.config.guild(ctx.guild).notify_on_join(),
                "notify_on_leave": await self.config.guild(ctx.guild).notify_on_leave(),
            }

            channel = ctx.guild.get_channel(settings["mod_log_channel"]) if settings["mod_log_channel"] else None

            embed = discord.Embed(
                title="ShadyAlts Settings",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Mod Log Channel", value=channel.mention if channel else "Not set", inline=False)
            embed.add_field(name="Notify on Join", value="Yes" if settings["notify_on_join"] else "No", inline=True)
            embed.add_field(name="Notify on Leave", value="Yes" if settings["notify_on_leave"] else "No", inline=True)

            await self._send_ephemeral(ctx, embed=embed)

    @altset_group.command(name="channel")
    async def altset_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the mod log channel for alt notifications."""
        if channel:
            await self.config.guild(ctx.guild).mod_log_channel.set(channel.id)
            await self._send_ephemeral(ctx, f"Mod log channel set to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).mod_log_channel.set(None)
            await self._send_ephemeral(ctx, "Mod log channel cleared.")

    @altset_group.command(name="joinnotify")
    async def altset_join_notify(self, ctx: commands.Context, enabled: bool):
        """Enable/disable notifications when known alts join."""
        await self.config.guild(ctx.guild).notify_on_join.set(enabled)
        await self._send_ephemeral(ctx, f"Join notifications {'enabled' if enabled else 'disabled'}.")

    @altset_group.command(name="leavenotify")
    async def altset_leave_notify(self, ctx: commands.Context, enabled: bool):
        """Enable/disable notifications when known alts leave."""
        await self.config.guild(ctx.guild).notify_on_leave.set(enabled)
        await self._send_ephemeral(ctx, f"Leave notifications {'enabled' if enabled else 'disabled'}.")


async def setup(bot: Red):
    await bot.add_cog(ShadyAlts(bot))
