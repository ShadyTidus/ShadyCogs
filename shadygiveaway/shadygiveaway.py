"""
ShadyGiveaway - Advanced giveaway system with prize code management
Features prize claim verification with Yes/No buttons, automatic rerolls, and role requirements.
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
    """Modal for creating a new giveaway."""

    description = discord.ui.TextInput(
        label="Prize & Description",
        style=discord.TextStyle.paragraph,
        placeholder="e.g., Win a Discord Nitro subscription! Monthly prize for active members.",
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

            await self.cog.create_giveaway(
                interaction,
                channel,
                str(self.description),
                duration_delta,
                winners,
                str(self.prize_code),
                claim_timeout_delta,
            )
        except Exception as e:
            error_msg = f"**Error in modal submission:**\n```\n{type(e).__name__}: {str(e)}\n```"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)
            log.error(f"Error in modal submission: {e}", exc_info=True)


class GiveawayEnterView(discord.ui.View):
    """View with Enter button for giveaway participation."""

    def __init__(self, cog: "ShadyGiveaway", giveaway_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green, custom_id="giveaway_enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_entry(interaction, self.giveaway_id)


class WinnerClaimView(discord.ui.View):
    """View with Yes/No buttons for winners to claim prizes."""

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
            desc = giveaway["description"][:50] + "..." if len(giveaway["description"]) > 50 else giveaway["description"]
            options.append(
                discord.SelectOption(
                    label=desc,
                    value=giveaway_id,
                    description=f"{status} | {len(giveaway['entries'])} entries"
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


class ShadyGiveaway(commands.Cog):
    """Advanced giveaway system with prize code management and claim verification."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820736, force_registration=True)
        
        default_guild = {
            "giveaways": {},
        }
        self.config.register_guild(**default_guild)
        
        self.giveaway_check_task = None
        
    async def cog_load(self):
        """Start background task when cog loads."""
        self.giveaway_check_task = asyncio.create_task(self.check_ended_giveaways())
        
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
                await channel.send(f"Giveaway **{giveaway['description']}** has been cancelled by {interaction.user.mention}.")
        except Exception as e:
            log.error(f"Error updating cancelled giveaway message: {e}")
        
        await interaction.response.send_message(
            f"Giveaway **{giveaway['description']}** has been cancelled.",
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
        
        embed = discord.Embed(
            title="🎉 Giveaway Information",
            description=giveaway["description"],
            color=color
        )
        
        embed.add_field(name="Channel", value=channel.mention if channel else "Unknown", inline=True)
        embed.add_field(name="Host", value=host.mention if host else "Unknown", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Winners Needed", value=str(giveaway["winners_count"]), inline=True)
        embed.add_field(name="Total Entries", value=str(len(giveaway["entries"])), inline=True)
        embed.add_field(name="Winners Claimed", value=str(len(giveaway.get("winners_claimed", []))), inline=True)
        embed.add_field(name="Winners Picked", value=str(len(giveaway.get("winners_picked", []))), inline=True)
        embed.add_field(name="Claim Timeout", value=humanize_timedelta(seconds=giveaway["claim_timeout_seconds"]), inline=True)
        embed.add_field(name="Ends/Ended", value=f"<t:{giveaway['end_timestamp']}:R>", inline=True)
        embed.add_field(name="Giveaway ID", value=f"`{giveaway_id}`", inline=False)
        
        # Show participants if less than 20
        if len(giveaway["entries"]) <= 20 and giveaway["entries"]:
            participants = [f"<@{uid}>" for uid in giveaway["entries"]]
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
        channel: discord.TextChannel,
        description: str,
        duration: timedelta,
        winners_count: int,
        prize_code: str,
        claim_timeout: timedelta,
    ):
        """Create a new giveaway."""
        try:
            giveaway_id = f"{interaction.guild.id}_{int(datetime.now(timezone.utc).timestamp())}"
            end_time = datetime.now(timezone.utc) + duration
            
            embed = discord.Embed(
                title="🎉 GIVEAWAY",
                description=description,
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Winners", value=str(winners_count), inline=True)
            embed.add_field(name="Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
            embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
            embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
            
            view = GiveawayEnterView(self, giveaway_id)
            message = await channel.send(embed=embed, view=view)
            
            async with self.config.guild(interaction.guild).giveaways() as giveaways:
                giveaways[giveaway_id] = {
                    "message_id": message.id,
                    "channel_id": channel.id,
                    "description": description,
                    "host_id": interaction.user.id,
                    "winners_count": winners_count,
                    "prize_code": prize_code,
                    "claim_timeout_seconds": int(claim_timeout.total_seconds()),
                    "end_timestamp": int(end_time.timestamp()),
                    "entries": [],
                    "ended": False,
                    "winners_picked": [],
                    "winners_claimed": [],
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
        
        if interaction.user.id in giveaway["entries"]:
            await interaction.response.send_message("You've already entered this giveaway!", ephemeral=True)
            return
        
        giveaway["entries"].append(interaction.user.id)
        async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id] = giveaway
        
        await interaction.response.send_message(
            f"You've been entered into the giveaway! Good luck! ({len(giveaway['entries'])} entries)",
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
        
        if not giveaway["entries"]:
            async with self.config.guild(guild).giveaways() as giveaways:
                giveaways[giveaway_id]["ended"] = True
            try:
                if channel:
                    await channel.send(f"Giveaway for **{giveaway['description']}** ended with no entries! 😢")
                    # Update message to show ended
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
        """Pick a random winner from entries and send claim notification."""
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return
        
        claimed_count = len(giveaway.get("winners_claimed", []))
        if claimed_count >= giveaway["winners_count"]:
            return
        
        available_entries = [e for e in giveaway["entries"] if e not in giveaway["winners_picked"]]
        
        if not available_entries:
            # No more entries - mark giveaway as ended
            channel = guild.get_channel(giveaway["channel_id"])
            remaining = giveaway["winners_count"] - claimed_count
            
            async with self.config.guild(guild).giveaways() as all_giveaways:
                all_giveaways[giveaway_id]["ended"] = True
            
            if channel:
                await channel.send(
                    f"⚠️ Giveaway **{giveaway['description']}** has ended. "
                    f"Needed {remaining} more winner(s) but no eligible entries remain. "
                    f"Total winners: {claimed_count}/{giveaway['winners_count']}"
                )
                # Update message to show partial completion
                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                    embed = message.embeds[0]
                    embed.color = discord.Color.orange()
                    embed.title = f"🎉 GIVEAWAY ENDED - {claimed_count}/{giveaway['winners_count']} Winners"
                    await message.edit(embed=embed)
                except Exception as e:
                    log.error(f"Error updating partial giveaway message: {e}")
            return
        
        winner_id = random.choice(available_entries)
        
        async with self.config.guild(guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id]["winners_picked"].append(winner_id)
            if "winners_claimed" not in all_giveaways[giveaway_id]:
                all_giveaways[giveaway_id]["winners_claimed"] = []
        
        winner = guild.get_member(winner_id)
        if not winner:
            # Refresh giveaway data and try again
            giveaways = await self.config.guild(guild).giveaways()
            await self.pick_and_notify_winner(guild, giveaway_id, giveaways.get(giveaway_id))
            return
        
        # Get fresh data for winner number
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        winner_number = len(giveaway["winners_picked"])
        
        claim_embed = discord.Embed(
            title="🎉 You Won a Giveaway!",
            description=f"Congratulations! You won **{giveaway['description']}**!",
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
            # Announce in channel that winner was picked
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(f"🎲 {winner.mention} has been selected as a potential winner for **{giveaway['description']}**! Check your DMs to claim.")
        except discord.Forbidden:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(
                    f"{winner.mention} You won **{giveaway['description']}** but I can't DM you! "
                    f"Please respond here within {humanize_timedelta(seconds=giveaway['claim_timeout_seconds'])}.",
                    embed=claim_embed,
                    view=view
                )

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
            
            code_embed = discord.Embed(
                title="🎁 Your Prize Code",
                description=f"**Prize:** {giveaway['description']}\n\n**Code/Key:**\n```\n{giveaway['prize_code']}\n```",
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
                        f"🎉 Congratulations {interaction.user.mention} for claiming prize #{claimed_count} of {giveaway['winners_count']} for **{giveaway['description']}**!"
                    )
                else:
                    await channel.send(f"🎉 Congratulations {interaction.user.mention} for winning **{giveaway['description']}**!")
            
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
                    description=f"**{giveaway['description']}**",
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
            
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(f"{interaction.user.mention} declined **{giveaway['description']}**. Picking a new winner...")
            
            await self.pick_and_notify_winner(guild, giveaway_id, giveaway)

    async def handle_claim_timeout(self, giveaway_id: str, winner_id: int):
        """Handle when winner doesn't respond in time."""
        for guild in self.bot.guilds:
            giveaways = await self.config.guild(guild).giveaways()
            if giveaway_id in giveaways:
                giveaway = giveaways[giveaway_id]
                
                channel = guild.get_channel(giveaway["channel_id"])
                winner = guild.get_member(winner_id)
                winner_mention = winner.mention if winner else f"<@{winner_id}>"
                
                if channel:
                    await channel.send(
                        f"⏰ {winner_mention} didn't claim **{giveaway['description']}** in time. Picking a new winner..."
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
            entries_count = len(giveaway["entries"])
            
            if giveaway.get("picking_winners", False):
                status = "🎲 Picking Winners"
            else:
                status = "🟢 Active"
            
            embed.add_field(
                name=f"{giveaway['description']}",
                value=f"Status: {status}\n"
                      f"Channel: {channel_mention}\n"
                      f"Entries: {entries_count}\n"
                      f"Claimed: {len(giveaway.get('winners_claimed', []))}/{giveaway['winners_count']}\n"
                      f"Ends: <t:{end_time}:R>",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Red):
    cog = ShadyGiveaway(bot)
    await bot.add_cog(cog)
