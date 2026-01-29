"""
ShadyGiveaway - Advanced giveaway system with prize code management
Features prize claim verification with Yes/No buttons, automatic rerolls, role requirements,
and bonus entries for Nitro/special event roles.
"""

import asyncio
import discord
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadygiveaway")


class GiveawayCreateModal(discord.ui.Modal, title="Create Giveaway"):
    """Modal for creating a new giveaway - basic info only."""

    prize_description = discord.ui.TextInput(
        label="Prize Name & Description",
        style=discord.TextStyle.paragraph,
        placeholder="Line 1: Prize name (e.g., Discord Nitro)\nLine 2+: Optional description",
        required=True,
        max_length=500,
    )
    
    duration = discord.ui.TextInput(
        label="Duration",
        placeholder="e.g., 24h, 3d, 1w (s/m/h/d/w)",
        required=True,
        max_length=20,
    )
    
    winners_count = discord.ui.TextInput(
        label="Number of Winners",
        placeholder="1",
        required=True,
        max_length=2,
    )
    
    prize_code = discord.ui.TextInput(
        label="Prize Code/Key",
        placeholder="Code that winners will receive in DM",
        required=True,
        max_length=500,
    )
    
    claim_timeout = discord.ui.TextInput(
        label="Claim Timeout",
        placeholder="e.g., 1h, 30m - Time to claim after winning",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "ShadyGiveaway"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    "This command must be run in a text channel!",
                    ephemeral=True
                )
                return
            
            duration_delta = await self.cog.parse_duration(str(self.duration))
            if duration_delta is None:
                await interaction.response.send_message(
                    "Invalid duration format. Use formats like `30m`, `2h`, `1d`, `3d`, `1w`.",
                    ephemeral=True,
                )
                return

            claim_timeout_delta = await self.cog.parse_duration(str(self.claim_timeout))
            if claim_timeout_delta is None:
                await interaction.response.send_message(
                    "Invalid claim timeout format. Use formats like `30m`, `1h`, `2h`.",
                    ephemeral=True,
                )
                return

            try:
                winners = int(str(self.winners_count))
                if winners < 1 or winners > 20:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "Winners count must be a number between 1 and 20.",
                    ephemeral=True,
                )
                return

            # Parse prize name and description (split on first newline)
            full_text = str(self.prize_description)
            if "\n" in full_text:
                prize_name, description = full_text.split("\n", 1)
                prize_name = prize_name.strip()
                description = description.strip()
            else:
                prize_name = full_text.strip()
                description = ""

            # Store pending giveaway data and show options view
            pending_data = {
                "channel_id": channel.id,
                "prize_name": prize_name,
                "description": description,
                "duration_seconds": int(duration_delta.total_seconds()),
                "winners_count": winners,
                "prize_code": str(self.prize_code),
                "claim_timeout_seconds": int(claim_timeout_delta.total_seconds()),
            }
            
            view = GiveawayOptionsView(self.cog, pending_data, interaction.guild)
            await interaction.response.send_message(
                "**Step 2: Configure Entry Requirements & Bonuses**\n\n"
                "Select role requirements and bonus entry options below:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            error_msg = f"**Error in modal submission:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error in modal submission: {e}", exc_info=True)


class GiveawayOptionsView(discord.ui.View):
    """View for configuring giveaway role requirements and bonus entries."""

    def __init__(self, cog: "ShadyGiveaway", pending_data: Dict[str, Any], guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.pending_data = pending_data
        self.guild = guild
        
        # Selected options
        self.min_role_id: Optional[int] = None
        self.nitro_bonus_enabled: bool = False
        self.special_bonus_role_id: Optional[int] = None
        
        # Build role options (exclude @everyone and bot roles)
        self.available_roles = [
            r for r in sorted(guild.roles, key=lambda x: x.position, reverse=True)
            if not r.is_bot_managed() and not r.is_default() and not r.is_integration()
        ]
        
        # Add dropdowns
        self._add_min_role_select()
        self._add_nitro_toggle_select()
        self._add_special_bonus_select()
    
    def _add_min_role_select(self):
        """Add minimum role requirement dropdown."""
        options = [
            discord.SelectOption(
                label="No requirement",
                value="none",
                description="Anyone can enter",
                emoji="✅"
            )
        ]
        
        for role in self.available_roles[:24]:  # Leave room for "No requirement"
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"Position: {role.position}"
                )
            )
        
        select = discord.ui.Select(
            placeholder="Minimum Role Required to Enter",
            options=options,
            custom_id="min_role_select",
            row=0
        )
        select.callback = self._min_role_callback
        self.add_item(select)
    
    def _add_nitro_toggle_select(self):
        """Add nitro bonus toggle dropdown."""
        options = [
            discord.SelectOption(
                label="Nitro Bonus Disabled",
                value="disabled",
                description="No bonus entry for Nitro role",
                emoji="❌"
            ),
            discord.SelectOption(
                label="Nitro Bonus Enabled",
                value="enabled",
                description="+1 entry for users with Nitro role",
                emoji="💎"
            )
        ]
        
        select = discord.ui.Select(
            placeholder="Nitro Bonus (+1 entry)",
            options=options,
            custom_id="nitro_toggle_select",
            row=1
        )
        select.callback = self._nitro_toggle_callback
        self.add_item(select)
    
    def _add_special_bonus_select(self):
        """Add special bonus role dropdown."""
        options = [
            discord.SelectOption(
                label="No Bonus",
                value="none",
                description="No special bonus role for this giveaway",
                emoji="➖"
            )
        ]
        
        for role in self.available_roles[:24]:  # Leave room for "No Bonus"
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"+1 entry for users with this role"
                )
            )
        
        select = discord.ui.Select(
            placeholder="Special Bonus Role (+1 entry)",
            options=options,
            custom_id="special_bonus_select",
            row=2
        )
        select.callback = self._special_bonus_callback
        self.add_item(select)
    
    async def _min_role_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.min_role_id = None if value == "none" else int(value)
        
        role_name = "No requirement"
        if self.min_role_id:
            role = self.guild.get_role(self.min_role_id)
            role_name = role.name if role else "Unknown"
        
        await interaction.response.send_message(
            f"✅ Minimum role set to: **{role_name}**",
            ephemeral=True
        )
    
    async def _nitro_toggle_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.nitro_bonus_enabled = value == "enabled"
        
        status = "Enabled 💎" if self.nitro_bonus_enabled else "Disabled"
        await interaction.response.send_message(
            f"✅ Nitro bonus: **{status}**",
            ephemeral=True
        )
    
    async def _special_bonus_callback(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        self.special_bonus_role_id = None if value == "none" else int(value)
        
        role_name = "No Bonus"
        if self.special_bonus_role_id:
            role = self.guild.get_role(self.special_bonus_role_id)
            role_name = role.name if role else "Unknown"
        
        await interaction.response.send_message(
            f"✅ Special bonus role set to: **{role_name}**",
            ephemeral=True
        )
    
    @discord.ui.button(label="Create Giveaway", style=discord.ButtonStyle.green, row=3)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and create the giveaway."""
        await self.cog.create_giveaway(
            interaction,
            self.pending_data,
            self.min_role_id,
            self.nitro_bonus_enabled,
            self.special_bonus_role_id
        )
        self.stop()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=3)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel giveaway creation."""
        await interaction.response.send_message("Giveaway creation cancelled.", ephemeral=True)
        self.stop()


class PersistentGiveawayView(discord.ui.View):
    """Persistent view with Enter and Leave buttons for giveaway participation.
    
    This view survives bot restarts by encoding the giveaway_id in the custom_id
    and using a class-level interaction handler.
    """

    def __init__(self, cog: "ShadyGiveaway" = None):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(
        label="🎉 Enter Giveaway",
        style=discord.ButtonStyle.green,
        custom_id="shady_giveaway:enter"
    )
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle enter button click."""
        if not self.cog:
            await interaction.response.send_message(
                "Giveaway system is still loading. Please try again in a moment.",
                ephemeral=True
            )
            return
        
        # Get giveaway_id from the message
        giveaway_id = await self._get_giveaway_id_from_message(interaction)
        if not giveaway_id:
            await interaction.response.send_message(
                "Could not find giveaway information. The giveaway may have been deleted.",
                ephemeral=True
            )
            return
        
        await self.cog.handle_entry(interaction, giveaway_id)
    
    @discord.ui.button(
        label="🚪 Leave Giveaway",
        style=discord.ButtonStyle.secondary,
        custom_id="shady_giveaway:leave"
    )
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle leave button click."""
        if not self.cog:
            await interaction.response.send_message(
                "Giveaway system is still loading. Please try again in a moment.",
                ephemeral=True
            )
            return
        
        # Get giveaway_id from the message
        giveaway_id = await self._get_giveaway_id_from_message(interaction)
        if not giveaway_id:
            await interaction.response.send_message(
                "Could not find giveaway information. The giveaway may have been deleted.",
                ephemeral=True
            )
            return
        
        await self.cog.handle_leave(interaction, giveaway_id)
    
    async def _get_giveaway_id_from_message(self, interaction: discord.Interaction) -> Optional[str]:
        """Extract giveaway_id from the message embed footer."""
        if not interaction.message or not interaction.message.embeds:
            return None
        
        embed = interaction.message.embeds[0]
        if embed.footer and embed.footer.text:
            # Footer format: "Giveaway ID: {giveaway_id}"
            footer_text = embed.footer.text
            if footer_text.startswith("Giveaway ID: "):
                return footer_text.replace("Giveaway ID: ", "")
        
        return None


class WinnerClaimView(discord.ui.View):
    """View with Yes/No buttons for winners to claim prizes.
    
    Note: This view is NOT persistent because it has a timeout and is sent via DM.
    The timeout handler needs the specific winner_id which can't easily be persisted.
    If the bot restarts during a claim window, the winner will need to be rerolled.
    """

    def __init__(self, cog: "ShadyGiveaway", giveaway_id: str, winner_id: int, timeout_seconds: int):
        super().__init__(timeout=timeout_seconds)
        self.cog = cog
        self.giveaway_id = giveaway_id
        self.winner_id = winner_id

    @discord.ui.button(label="✅ Yes, I claim this prize!", style=discord.ButtonStyle.green, custom_id="claim_yes")
    async def claim_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.winner_id:
            await interaction.response.send_message("This claim prompt is not for you!", ephemeral=True)
            return
        await self.cog.handle_claim_response(interaction, self.giveaway_id, self.winner_id, claimed=True)
        self.stop()

    @discord.ui.button(label="❌ No, reroll", style=discord.ButtonStyle.red, custom_id="claim_no")
    async def claim_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.winner_id:
            await interaction.response.send_message("This claim prompt is not for you!", ephemeral=True)
            return
        await self.cog.handle_claim_response(interaction, self.giveaway_id, self.winner_id, claimed=False)
        self.stop()

    async def on_timeout(self):
        await self.cog.handle_claim_timeout(self.giveaway_id, self.winner_id)


class GiveawaySelectView(discord.ui.View):
    """View with dropdown to select a giveaway for management."""

    def __init__(self, cog: "ShadyGiveaway", giveaways: List[tuple], action: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.action = action
        
        options = []
        for giveaway_id, giveaway in giveaways[:25]:  # Discord limit is 25 options
            status = "🎲 Picking" if giveaway.get("picking_winners") else "🟢 Active"
            # Use prize_name if available, fall back to description for old giveaways
            display_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
            desc = display_name[:50] + "..." if len(display_name) > 50 else display_name
            
            # Count total entries (sum of all entry weights)
            total_entries = sum(giveaway.get("entries", {}).values()) if isinstance(giveaway.get("entries"), dict) else len(giveaway.get("entries", []))
            
            options.append(
                discord.SelectOption(
                    label=desc,
                    value=giveaway_id,
                    description=f"{status} | {total_entries} entries"
                )
            )
        
        self.select = discord.ui.Select(
            placeholder="Select a giveaway...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        giveaway_id = self.select.values[0]
        
        if self.action == "end":
            await self.cog.force_end_giveaway(interaction, giveaway_id)
        elif self.action == "cancel":
            await self.cog.cancel_giveaway(interaction, giveaway_id)
        elif self.action == "info":
            await self.cog.show_giveaway_info(interaction, giveaway_id)
        
        self.stop()


class NitroRoleSelectView(discord.ui.View):
    """View for selecting the server's Nitro role."""

    def __init__(self, cog: "ShadyGiveaway", guild: discord.Guild):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild
        
        # Build role options
        available_roles = [
            r for r in sorted(guild.roles, key=lambda x: x.position, reverse=True)
            if not r.is_bot_managed() and not r.is_default() and not r.is_integration()
        ]
        
        options = [
            discord.SelectOption(
                label="Clear Nitro Role",
                value="none",
                description="Remove configured Nitro role",
                emoji="❌"
            )
        ]
        
        for role in available_roles[:24]:
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"Set as Nitro bonus role"
                )
            )
        
        select = discord.ui.Select(
            placeholder="Select the Nitro role for this server...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        value = self.children[0].values[0]
        
        if value == "none":
            await self.cog.config.guild(self.guild).nitro_role_id.set(None)
            await interaction.response.send_message(
                "✅ Nitro role has been cleared. Nitro bonus will not work until a role is set.",
                ephemeral=True
            )
        else:
            role_id = int(value)
            role = self.guild.get_role(role_id)
            await self.cog.config.guild(self.guild).nitro_role_id.set(role_id)
            await interaction.response.send_message(
                f"✅ Nitro role set to: **{role.name}**\n\n"
                f"Users with this role will get +1 entry when Nitro bonus is enabled for a giveaway.",
                ephemeral=True
            )
        
        self.stop()


class ShadyGiveaway(commands.Cog):
    """Advanced giveaway system with prize code management and claim verification."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820736, force_registration=True)
        
        default_guild = {
            "giveaways": {},
            "nitro_role_id": None,
        }
        self.config.register_guild(**default_guild)
        
        self.giveaway_check_task = None
        
        # Create persistent view and set cog reference
        self.persistent_view = PersistentGiveawayView(cog=self)
        
    async def cog_load(self):
        """Start background task and register persistent view when cog loads."""
        # Register the persistent view so buttons work after restart
        self.bot.add_view(self.persistent_view)
        
        self.giveaway_check_task = asyncio.create_task(self.check_ended_giveaways())
        log.info("ShadyGiveaway: Persistent view registered, background task started")
        
    async def cog_unload(self):
        """Cancel background task when cog unloads."""
        if self.giveaway_check_task:
            self.giveaway_check_task.cancel()

    async def is_authorized(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to manage giveaways."""
        if not isinstance(interaction.user, discord.Member):
            return True
        
        if interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner:
            return True
        
        try:
            cogs_dir = Path(__file__).parent.parent
            roles_file = cogs_dir / "wiki" / "config" / "roles.json"
            
            if roles_file.exists():
                with open(roles_file, "r", encoding="utf-8") as f:
                    roles_data = json.load(f)
                    allowed_roles = roles_data.get("authorized_roles", [])
                    return any(role.name in allowed_roles for role in interaction.user.roles)
        except Exception as e:
            log.error(f"Error reading roles.json: {e}")
        
        return False

    async def parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse duration string like '1h', '30m', '2d' into timedelta."""
        duration_str = duration_str.strip().lower()
        if not duration_str:
            return None
        
        unit = duration_str[-1]
        try:
            value = int(duration_str[:-1])
        except ValueError:
            return None
        
        multipliers = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400,
            'w': 604800,
        }
        
        if unit not in multipliers:
            return None
        
        return timedelta(seconds=value * multipliers[unit])

    def calculate_entries(
        self,
        member: discord.Member,
        giveaway: Dict[str, Any],
        nitro_role_id: Optional[int]
    ) -> int:
        """Calculate how many entries a member gets based on their roles."""
        entries = 1  # Base entry
        
        # Check Nitro bonus
        if giveaway.get("nitro_bonus_enabled") and nitro_role_id:
            if any(r.id == nitro_role_id for r in member.roles):
                entries += 1
        
        # Check special bonus role
        special_role_id = giveaway.get("special_bonus_role_id")
        if special_role_id:
            if any(r.id == special_role_id for r in member.roles):
                entries += 1
        
        return entries

    def check_role_requirement(
        self,
        member: discord.Member,
        min_role_id: Optional[int]
    ) -> bool:
        """Check if member meets the minimum role requirement."""
        if not min_role_id:
            return True  # No requirement
        
        min_role = member.guild.get_role(min_role_id)
        if not min_role:
            return True  # Role no longer exists, allow entry
        
        # Check if user has the min role or any role higher in hierarchy
        for role in member.roles:
            if role.position >= min_role.position and not role.is_default():
                return True
        
        return False

    @app_commands.command(name="giveawaynitro", description="Set the Nitro role for bonus entries")
    async def giveawaynitro(self, interaction: discord.Interaction):
        """Configure which role counts as 'Nitro' for bonus entries."""
        try:
            if not await self.is_authorized(interaction):
                await interaction.response.send_message(
                    "You don't have permission to configure giveaways.",
                    ephemeral=True
                )
                return
            
            current_nitro_id = await self.config.guild(interaction.guild).nitro_role_id()
            current_role = interaction.guild.get_role(current_nitro_id) if current_nitro_id else None
            
            current_text = f"**Current Nitro role:** {current_role.mention if current_role else 'Not set'}\n\n"
            
            view = NitroRoleSelectView(self, interaction.guild)
            await interaction.response.send_message(
                f"{current_text}Select the role that represents Nitro subscribers in your server:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            error_msg = f"**Error:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error in giveawaynitro command: {e}", exc_info=True)

    @app_commands.command(name="giveaway", description="Create or list giveaways")
    @app_commands.describe(action="Action to perform")
    @app_commands.choices(action=[
        app_commands.Choice(name="Create", value="create"),
        app_commands.Choice(name="List Active", value="list"),
    ])
    async def giveaway(self, interaction: discord.Interaction, action: str):
        """Main giveaway command handler."""
        try:
            if not await self.is_authorized(interaction):
                await interaction.response.send_message(
                    "You don't have permission to manage giveaways.",
                    ephemeral=True
                )
                return
            
            if action == "create":
                modal = GiveawayCreateModal(self)
                await interaction.response.send_modal(modal)
                
            elif action == "list":
                await self.list_giveaways(interaction)
                
        except Exception as e:
            error_msg = f"**Error in giveaway command:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error in giveaway command: {e}", exc_info=True)

    @app_commands.command(name="giveawaymanage", description="Manage active giveaways (end early, cancel, view info)")
    @app_commands.describe(action="Action to perform on a giveaway")
    @app_commands.choices(action=[
        app_commands.Choice(name="End Early (pick winners now)", value="end"),
        app_commands.Choice(name="Cancel (no winners)", value="cancel"),
        app_commands.Choice(name="View Info", value="info"),
    ])
    async def giveawaymanage(self, interaction: discord.Interaction, action: str):
        """Manage active giveaways with dropdown selection."""
        try:
            if not await self.is_authorized(interaction):
                await interaction.response.send_message(
                    "You don't have permission to manage giveaways.",
                    ephemeral=True
                )
                return
            
            giveaways = await self.config.guild(interaction.guild).giveaways()
            active = [(gid, g) for gid, g in giveaways.items() if not g["ended"]]
            
            if not active:
                await interaction.response.send_message("No active giveaways to manage.", ephemeral=True)
                return
            
            view = GiveawaySelectView(self, active, action)
            
            action_text = {
                "end": "end early (pick winners now)",
                "cancel": "cancel (no winners picked)",
                "info": "view detailed info for"
            }
            
            await interaction.response.send_message(
                f"Select a giveaway to {action_text[action]}:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            error_msg = f"**Error in giveawaymanage command:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error in giveawaymanage command: {e}", exc_info=True)

    async def force_end_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """Force end a giveaway and pick winners."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        
        if giveaway["ended"]:
            await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
            return
        
        await interaction.response.send_message(
            f"Ending giveaway **{giveaway['description']}** and picking winners...",
            ephemeral=True
        )
        
        await self.end_giveaway(interaction.guild, giveaway_id, giveaway)

    async def cancel_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """Cancel a giveaway without picking winners."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        
        if giveaway["ended"]:
            await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
            return
        
        # Mark as ended without picking winners
        async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id]["ended"] = True
            all_giveaways[giveaway_id]["cancelled"] = True
        
        # Update the giveaway message
        try:
            channel = interaction.guild.get_channel(giveaway["channel_id"])
            if channel:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.red()
                embed.title = "🚫 GIVEAWAY CANCELLED"
                await message.edit(embed=embed, view=None)
                prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
                await channel.send(f"Giveaway **{prize_name}** has been cancelled by {interaction.user.mention}.")
        except Exception as e:
            log.error(f"Error updating cancelled giveaway message: {e}")
        
        prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
        await interaction.response.send_message(
            f"Giveaway **{prize_name}** has been cancelled.",
            ephemeral=True
        )

    async def show_giveaway_info(self, interaction: discord.Interaction, giveaway_id: str):
        """Show detailed info about a giveaway."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(giveaway["channel_id"])
        host = interaction.guild.get_member(giveaway["host_id"])
        
        # Determine status
        if giveaway.get("cancelled"):
            status = "🚫 Cancelled"
            color = discord.Color.red()
        elif giveaway["ended"]:
            status = "✅ Complete"
            color = discord.Color.green()
        elif giveaway.get("picking_winners", False):
            status = "🎲 Picking Winners"
            color = discord.Color.orange()
        else:
            status = "🟢 Active"
            color = discord.Color.gold()
        
        prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
        description = giveaway.get("description", "")
        
        embed = discord.Embed(
            title=f"🎉 Giveaway: {prize_name}",
            description=description if description else None,
            color=color
        )
        
        embed.add_field(name="Channel", value=channel.mention if channel else "Unknown", inline=True)
        embed.add_field(name="Host", value=host.mention if host else "Unknown", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Winners Needed", value=str(giveaway["winners_count"]), inline=True)
        
        # Entry count - handle both old (list) and new (dict) formats
        entries = giveaway.get("entries", {})
        if isinstance(entries, dict):
            unique_entrants = len(entries)
            total_entries = sum(entries.values())
            embed.add_field(name="Entrants", value=str(unique_entrants), inline=True)
            embed.add_field(name="Total Entries", value=str(total_entries), inline=True)
        else:
            embed.add_field(name="Total Entries", value=str(len(entries)), inline=True)
        
        embed.add_field(name="Winners Claimed", value=str(len(giveaway.get("winners_claimed", []))), inline=True)
        embed.add_field(name="Winners Picked", value=str(len(giveaway.get("winners_picked", []))), inline=True)
        embed.add_field(name="Claim Timeout", value=humanize_timedelta(seconds=giveaway["claim_timeout_seconds"]), inline=True)
        embed.add_field(name="Ends/Ended", value=f"<t:{giveaway['end_timestamp']}:R>", inline=True)
        
        # Role requirements
        min_role_id = giveaway.get("min_role_id")
        if min_role_id:
            min_role = interaction.guild.get_role(min_role_id)
            embed.add_field(name="Min Role Required", value=min_role.mention if min_role else "Deleted Role", inline=True)
        else:
            embed.add_field(name="Min Role Required", value="None", inline=True)
        
        # Bonus info
        bonuses = []
        if giveaway.get("nitro_bonus_enabled"):
            nitro_role_id = await self.config.guild(interaction.guild).nitro_role_id()
            nitro_role = interaction.guild.get_role(nitro_role_id) if nitro_role_id else None
            bonuses.append(f"💎 Nitro ({nitro_role.mention if nitro_role else 'Not configured'})")
        
        special_role_id = giveaway.get("special_bonus_role_id")
        if special_role_id:
            special_role = interaction.guild.get_role(special_role_id)
            bonuses.append(f"⭐ {special_role.mention if special_role else 'Deleted Role'}")
        
        embed.add_field(name="Bonus Roles", value="\n".join(bonuses) if bonuses else "None", inline=False)
        
        embed.add_field(name="Giveaway ID", value=f"`{giveaway_id}`", inline=False)
        
        # Show participants if less than 20
        if isinstance(entries, dict) and len(entries) <= 20 and entries:
            participants = [f"<@{uid}> ({count})" for uid, count in entries.items()]
            embed.add_field(
                name=f"Participants ({len(participants)})",
                value=", ".join(participants),
                inline=False
            )
        elif isinstance(entries, list) and len(entries) <= 20 and entries:
            participants = [f"<@{uid}>" for uid in entries]
            embed.add_field(
                name=f"Participants ({len(participants)})",
                value=", ".join(participants),
                inline=False
            )
        
        # Show claimed winners
        if giveaway.get("winners_claimed"):
            winners = [f"<@{uid}>" for uid in giveaway["winners_claimed"]]
            embed.add_field(
                name="Claimed Winners",
                value=", ".join(winners),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        pending_data: Dict[str, Any],
        min_role_id: Optional[int],
        nitro_bonus_enabled: bool,
        special_bonus_role_id: Optional[int],
    ):
        """Create a new giveaway with role requirements."""
        try:
            channel = interaction.guild.get_channel(pending_data["channel_id"])
            if not channel:
                await interaction.response.send_message("Channel not found!", ephemeral=True)
                return
            
            giveaway_id = f"{interaction.guild.id}_{int(datetime.now(timezone.utc).timestamp())}"
            duration = timedelta(seconds=pending_data["duration_seconds"])
            end_time = datetime.now(timezone.utc) + duration
            
            # Get prize name and description
            prize_name = pending_data["prize_name"]
            description = pending_data.get("description", "")
            
            # Build embed
            embed = discord.Embed(
                title=f"🎉 GIVEAWAY: {prize_name}",
                description=description if description else None,
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Winners", value=str(pending_data["winners_count"]), inline=True)
            embed.add_field(name="Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
            embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
            
            # Add requirement info
            req_text = []
            if min_role_id:
                min_role = interaction.guild.get_role(min_role_id)
                req_text.append(f"**Requires:** {min_role.mention} or higher" if min_role else "")
            
            bonus_text = []
            if nitro_bonus_enabled:
                nitro_role_id = await self.config.guild(interaction.guild).nitro_role_id()
                if nitro_role_id:
                    nitro_role = interaction.guild.get_role(nitro_role_id)
                    bonus_text.append(f"💎 {nitro_role.mention}: +1 entry" if nitro_role else "")
            
            if special_bonus_role_id:
                special_role = interaction.guild.get_role(special_bonus_role_id)
                bonus_text.append(f"⭐ {special_role.mention}: +1 entry" if special_role else "")
            
            if req_text or bonus_text:
                info_value = ""
                if req_text:
                    info_value += "\n".join(filter(None, req_text))
                if bonus_text:
                    if info_value:
                        info_value += "\n"
                    info_value += "\n".join(filter(None, bonus_text))
                if info_value:
                    embed.add_field(name="Entry Info", value=info_value, inline=False)
            
            embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
            
            # Use the persistent view
            view = PersistentGiveawayView(cog=self)
            message = await channel.send(embed=embed, view=view)
            
            async with self.config.guild(interaction.guild).giveaways() as giveaways:
                giveaways[giveaway_id] = {
                    "message_id": message.id,
                    "channel_id": channel.id,
                    "prize_name": prize_name,
                    "description": description,
                    "host_id": interaction.user.id,
                    "winners_count": pending_data["winners_count"],
                    "prize_code": pending_data["prize_code"],
                    "claim_timeout_seconds": pending_data["claim_timeout_seconds"],
                    "end_timestamp": int(end_time.timestamp()),
                    "entries": {},  # Dict of user_id: entry_count
                    "ended": False,
                    "winners_picked": [],
                    "winners_claimed": [],
                    "min_role_id": min_role_id,
                    "nitro_bonus_enabled": nitro_bonus_enabled,
                    "special_bonus_role_id": special_bonus_role_id,
                }
            
            await interaction.response.send_message(
                f"✅ Giveaway created in {channel.mention}!\nID: `{giveaway_id}`",
                ephemeral=True
            )
        except Exception as e:
            error_msg = f"**Error creating giveaway:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error creating giveaway: {e}", exc_info=True)

    async def handle_entry(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle user entering a giveaway."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        
        if giveaway_id not in giveaways:
            await interaction.response.send_message("This giveaway no longer exists.", ephemeral=True)
            return
        
        giveaway = giveaways[giveaway_id]
        
        if giveaway["ended"]:
            await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
            return
        
        member = interaction.user
        user_id_str = str(member.id)
        
        # Check if already entered
        entries = giveaway.get("entries", {})
        if isinstance(entries, dict) and user_id_str in entries:
            await interaction.response.send_message("You've already entered this giveaway! Use the Leave button if you want to withdraw.", ephemeral=True)
            return
        elif isinstance(entries, list) and member.id in entries:
            await interaction.response.send_message("You've already entered this giveaway! Use the Leave button if you want to withdraw.", ephemeral=True)
            return
        
        # Check role requirement
        min_role_id = giveaway.get("min_role_id")
        if not self.check_role_requirement(member, min_role_id):
            min_role = interaction.guild.get_role(min_role_id)
            await interaction.response.send_message(
                f"You need the **{min_role.name}** role or higher to enter this giveaway!",
                ephemeral=True
            )
            return
        
        # Calculate entries
        nitro_role_id = await self.config.guild(interaction.guild).nitro_role_id()
        entry_count = self.calculate_entries(member, giveaway, nitro_role_id)
        
        # Add entry
        async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
            # Migrate old format if needed
            if isinstance(all_giveaways[giveaway_id].get("entries"), list):
                old_entries = all_giveaways[giveaway_id]["entries"]
                all_giveaways[giveaway_id]["entries"] = {str(uid): 1 for uid in old_entries}
            
            all_giveaways[giveaway_id]["entries"][user_id_str] = entry_count
        
        # Build response - get fresh count
        giveaways_updated = await self.config.guild(interaction.guild).giveaways()
        entries_updated = giveaways_updated[giveaway_id].get("entries", {})
        total_entries = sum(entries_updated.values()) if isinstance(entries_updated, dict) else len(entries_updated)
        
        bonus_info = ""
        if entry_count > 1:
            bonus_info = f"\n🎁 **Bonus entries:** You got {entry_count} entries!"
        
        await interaction.response.send_message(
            f"You've been entered into the giveaway! Good luck!{bonus_info}\n"
            f"*({total_entries} total entries)*",
            ephemeral=True
        )

    async def handle_leave(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle user leaving a giveaway."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        
        if giveaway_id not in giveaways:
            await interaction.response.send_message("This giveaway no longer exists.", ephemeral=True)
            return
        
        giveaway = giveaways[giveaway_id]
        
        if giveaway["ended"]:
            await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
            return
        
        user_id_str = str(interaction.user.id)
        entries = giveaway.get("entries", {})
        
        # Check if user is entered
        if isinstance(entries, dict):
            if user_id_str not in entries:
                await interaction.response.send_message("You haven't entered this giveaway!", ephemeral=True)
                return
            
            removed_entries = entries[user_id_str]
            async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
                del all_giveaways[giveaway_id]["entries"][user_id_str]
            
            await interaction.response.send_message(
                f"You've left the giveaway. ({removed_entries} {'entry' if removed_entries == 1 else 'entries'} removed)",
                ephemeral=True
            )
        elif isinstance(entries, list):
            if interaction.user.id not in entries:
                await interaction.response.send_message("You haven't entered this giveaway!", ephemeral=True)
                return
            
            async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
                all_giveaways[giveaway_id]["entries"].remove(interaction.user.id)
            
            await interaction.response.send_message(
                "You've left the giveaway.",
                ephemeral=True
            )

    async def check_ended_giveaways(self):
        """Background task to check for ended giveaways."""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(30)
                
                for guild in self.bot.guilds:
                    giveaways = await self.config.guild(guild).giveaways()
                    now = datetime.now(timezone.utc).timestamp()
                    
                    for giveaway_id, giveaway in list(giveaways.items()):
                        if not giveaway.get("picking_winners", False) and not giveaway["ended"] and now >= giveaway["end_timestamp"]:
                            await self.end_giveaway(guild, giveaway_id, giveaway)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in giveaway check task: {e}", exc_info=True)

    async def end_giveaway(self, guild: discord.Guild, giveaway_id: str, giveaway: Dict[str, Any]):
        """End a giveaway and start picking winners."""
        async with self.config.guild(guild).giveaways() as giveaways:
            giveaways[giveaway_id]["picking_winners"] = True
        
        channel = None
        try:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.orange()
                embed.title = "🎉 GIVEAWAY - Picking Winners..."
                await message.edit(embed=embed, view=None)
        except Exception as e:
            log.error(f"Error updating giveaway message: {e}")
        
        entries = giveaway.get("entries", {})
        has_entries = (isinstance(entries, dict) and entries) or (isinstance(entries, list) and entries)
        
        if not has_entries:
            async with self.config.guild(guild).giveaways() as giveaways:
                giveaways[giveaway_id]["ended"] = True
            try:
                if channel:
                    prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
                    await channel.send(f"Giveaway for **{prize_name}** ended with no entries! 😢")
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = message.embeds[0]
                    embed.color = discord.Color.red()
                    embed.title = "🎉 GIVEAWAY ENDED - No Entries"
                    await message.edit(embed=embed)
            except Exception:
                pass
            return
        
        await self.pick_and_notify_winner(guild, giveaway_id, giveaway)

    async def pick_and_notify_winner(self, guild: discord.Guild, giveaway_id: str, giveaway: Dict[str, Any]):
        """Pick a random winner from entries using weighted selection."""
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return
        
        claimed_count = len(giveaway.get("winners_claimed", []))
        if claimed_count >= giveaway["winners_count"]:
            return
        
        entries = giveaway.get("entries", {})
        winners_picked = giveaway.get("winners_picked", [])
        
        # Build weighted pool excluding already picked winners
        if isinstance(entries, dict):
            available = {uid: count for uid, count in entries.items() if int(uid) not in winners_picked}
            if not available:
                await self._handle_no_entries_remaining(guild, giveaway_id, giveaway, claimed_count)
                return
            
            # Weighted random selection
            pool = []
            for uid, count in available.items():
                pool.extend([int(uid)] * count)
            
            winner_id = random.choice(pool)
        else:
            # Legacy list format
            available = [uid for uid in entries if uid not in winners_picked]
            if not available:
                await self._handle_no_entries_remaining(guild, giveaway_id, giveaway, claimed_count)
                return
            winner_id = random.choice(available)
        
        async with self.config.guild(guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id]["winners_picked"].append(winner_id)
            if "winners_claimed" not in all_giveaways[giveaway_id]:
                all_giveaways[giveaway_id]["winners_claimed"] = []
        
        winner = guild.get_member(winner_id)
        if not winner:
            giveaways = await self.config.guild(guild).giveaways()
            await self.pick_and_notify_winner(guild, giveaway_id, giveaways.get(giveaway_id))
            return
        
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        winner_number = len(giveaway["winners_picked"])
        
        prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
        
        claim_embed = discord.Embed(
            title="🎉 You Won a Giveaway!",
            description=f"Congratulations! You won **{prize_name}**!",
            color=discord.Color.gold()
        )
        
        if giveaway["winners_count"] > 1:
            claim_embed.add_field(
                name="🏆 Winner Position",
                value=f"You are winner #{winner_number} of {giveaway['winners_count']}",
                inline=False
            )
        
        claim_embed.add_field(
            name="⏰ Time to Claim",
            value=f"You have **{humanize_timedelta(seconds=giveaway['claim_timeout_seconds'])}** to claim your prize.",
            inline=False
        )
        claim_embed.add_field(
            name="📋 Instructions",
            value="Click **Yes** below to receive your prize code.\nClick **No** to decline and we'll pick another winner.",
            inline=False
        )
        claim_embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
        
        view = WinnerClaimView(
            self,
            giveaway_id,
            winner_id,
            giveaway["claim_timeout_seconds"]
        )
        
        try:
            await winner.send(embed=claim_embed, view=view)
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(f"🎲 {winner.mention} has been selected as a potential winner for **{prize_name}**! Check your DMs to claim.")
        except discord.Forbidden:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(
                    f"{winner.mention} You won **{prize_name}** but I can't DM you! "
                    f"Please respond here within {humanize_timedelta(seconds=giveaway['claim_timeout_seconds'])}.",
                    embed=claim_embed,
                    view=view
                )

    async def _handle_no_entries_remaining(self, guild: discord.Guild, giveaway_id: str, giveaway: Dict[str, Any], claimed_count: int):
        """Handle case when no more eligible entries remain."""
        channel = guild.get_channel(giveaway["channel_id"])
        remaining = giveaway["winners_count"] - claimed_count
        prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
        
        async with self.config.guild(guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id]["ended"] = True
        
        if channel:
            await channel.send(
                f"⚠️ Giveaway **{prize_name}** has ended. "
                f"Needed {remaining} more winner(s) but no eligible entries remain. "
                f"Total winners: {claimed_count}/{giveaway['winners_count']}"
            )
            try:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.orange()
                embed.title = f"🎉 GIVEAWAY ENDED - {claimed_count}/{giveaway['winners_count']} Winners"
                await message.edit(embed=embed)
            except Exception as e:
                log.error(f"Error updating partial giveaway message: {e}")

    async def handle_claim_response(
        self,
        interaction: discord.Interaction,
        giveaway_id: str,
        winner_id: int,
        claimed: bool
    ):
        """Handle winner's Yes/No response to claim."""
        try:
            guild_id = int(giveaway_id.split("_")[0])
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await interaction.response.send_message(
                    "Could not find the server for this giveaway. It may have been deleted.",
                    ephemeral=True
                )
                return
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "Invalid giveaway ID format.",
                ephemeral=True
            )
            return
        
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        
        if claimed:
            async with self.config.guild(guild).giveaways() as all_giveaways:
                if "winners_claimed" not in all_giveaways[giveaway_id]:
                    all_giveaways[giveaway_id]["winners_claimed"] = []
                all_giveaways[giveaway_id]["winners_claimed"].append(winner_id)
            
            prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
            
            code_embed = discord.Embed(
                title="🎁 Your Prize Code",
                description=f"**Prize:** {prize_name}\n\n**Code/Key:**\n```\n{giveaway['prize_code']}\n```",
                color=discord.Color.green()
            )
            code_embed.set_footer(text="Congratulations! Enjoy your prize!")
            
            await interaction.response.send_message(embed=code_embed, ephemeral=True)
            
            channel = guild.get_channel(giveaway["channel_id"])
            
            giveaways_updated = await self.config.guild(guild).giveaways()
            giveaway_updated = giveaways_updated.get(giveaway_id)
            
            if channel:
                claimed_count = len(giveaway_updated.get("winners_claimed", []))
                if giveaway["winners_count"] > 1:
                    await channel.send(
                        f"🎉 Congratulations {interaction.user.mention} for claiming prize #{claimed_count} of {giveaway['winners_count']} for **{prize_name}**!"
                    )
                else:
                    await channel.send(f"🎉 Congratulations {interaction.user.mention} for winning **{prize_name}**!")
            
            if claimed_count < giveaway["winners_count"]:
                await self.pick_and_notify_winner(guild, giveaway_id, giveaway_updated)
            else:
                async with self.config.guild(guild).giveaways() as all_giveaways:
                    all_giveaways[giveaway_id]["ended"] = True
                
                try:
                    if channel:
                        message = await channel.fetch_message(giveaway["message_id"])
                        embed = message.embeds[0]
                        embed.color = discord.Color.green()
                        embed.title = "🎉 GIVEAWAY COMPLETE!"
                        await message.edit(embed=embed)
                except Exception as e:
                    log.error(f"Error updating completed giveaway message: {e}")
                
                winners_list = [f"<@{wid}>" for wid in giveaway_updated["winners_claimed"]]
                
                final_embed = discord.Embed(
                    title="🏆 Giveaway Winners!",
                    description=f"**{prize_name}**",
                    color=discord.Color.gold()
                )
                final_embed.add_field(
                    name=f"{'Winner' if len(winners_list) == 1 else 'Winners'}",
                    value=", ".join(winners_list),
                    inline=False
                )
                final_embed.set_footer(text="Congratulations to all winners!")
                
                if channel:
                    await channel.send(embed=final_embed)
                
        else:
            await interaction.response.send_message(
                "You've declined the prize. We'll pick another winner!",
                ephemeral=True
            )
            
            prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(f"{interaction.user.mention} declined **{prize_name}**. Picking a new winner...")
            
            await self.pick_and_notify_winner(guild, giveaway_id, giveaway)

    async def handle_claim_timeout(self, giveaway_id: str, winner_id: int):
        """Handle when winner doesn't respond in time."""
        for guild in self.bot.guilds:
            giveaways = await self.config.guild(guild).giveaways()
            if giveaway_id in giveaways:
                giveaway = giveaways[giveaway_id]
                
                prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
                channel = guild.get_channel(giveaway["channel_id"])
                winner = guild.get_member(winner_id)
                winner_mention = winner.mention if winner else f"<@{winner_id}>"
                
                if channel:
                    await channel.send(
                        f"⏰ {winner_mention} didn't claim **{prize_name}** in time. Picking a new winner..."
                    )
                
                await self.pick_and_notify_winner(guild, giveaway_id, giveaway)
                break

    async def list_giveaways(self, interaction: discord.Interaction):
        """List all active giveaways in the guild."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        
        active = [(gid, g) for gid, g in giveaways.items() if not g["ended"]]
        
        if not active:
            await interaction.response.send_message(
                "No active giveaways.\n\nUse `/giveaway create` to create one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🎉 Active Giveaways",
            description="Use `/giveawaymanage` to end, cancel, or view details.",
            color=discord.Color.gold()
        )
        
        for giveaway_id, giveaway in active[:10]:
            channel = interaction.guild.get_channel(giveaway["channel_id"])
            channel_mention = channel.mention if channel else "Unknown Channel"
            
            end_time = giveaway["end_timestamp"]
            prize_name = giveaway.get("prize_name") or giveaway.get("description", "Unknown")
            
            entries = giveaway.get("entries", {})
            if isinstance(entries, dict):
                entrants_count = len(entries)
                total_entries = sum(entries.values())
                entries_text = f"Entrants: {entrants_count} ({total_entries} entries)"
            else:
                entries_text = f"Entries: {len(entries)}"
            
            if giveaway.get("picking_winners", False):
                status = "🎲 Picking Winners"
            else:
                status = "🟢 Active"
            
            embed.add_field(
                name=f"{prize_name}",
                value=f"Status: {status}\n"
                      f"Channel: {channel_mention}\n"
                      f"{entries_text}\n"
                      f"Claimed: {len(giveaway.get('winners_claimed', []))}/{giveaway['winners_count']}\n"
                      f"Ends: <t:{end_time}:R>",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Red):
    cog = ShadyGiveaway(bot)
    await bot.add_cog(cog)
