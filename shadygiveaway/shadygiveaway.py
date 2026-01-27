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

    channel = discord.ui.TextInput(
        label="Channel",
        placeholder="#giveaways or channel ID",
        required=True,
        max_length=100,
    )

    prize = discord.ui.TextInput(
        label="Prize Name",
        placeholder="e.g., Discord Nitro, $10 Steam Gift Card",
        required=True,
        max_length=100,
    )

    description = discord.ui.TextInput(
        label="Description (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Additional details about the prize...",
        required=False,
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
        # Parse channel
        channel_str = str(self.channel).strip()
        channel = None
        
        # Try to parse channel mention or ID
        if channel_str.startswith("<#") and channel_str.endswith(">"):
            # Channel mention format
            channel_id = int(channel_str.replace("<#", "").replace(">", ""))
            channel = interaction.guild.get_channel(channel_id)
        else:
            # Try as channel ID
            try:
                channel_id = int(channel_str)
                channel = interaction.guild.get_channel(channel_id)
            except ValueError:
                # Try finding by name
                for ch in interaction.guild.text_channels:
                    if ch.name.lower() == channel_str.lower() or f"#{ch.name}".lower() == channel_str.lower():
                        channel = ch
                        break
        
        if channel is None:
            await interaction.response.send_message(
                "Invalid channel. Please use a channel mention (#channel), channel ID, or channel name.",
                ephemeral=True
            )
            return
        
        # Parse duration
        duration_delta = await self.cog.parse_duration(str(self.duration))
        if duration_delta is None:
            await interaction.response.send_message(
                "Invalid duration format. Use formats like `30m`, `2h`, `1d`, `3d`, `1w`.",
                ephemeral=True,
            )
            return

        # Parse claim timeout
        claim_timeout_delta = await self.cog.parse_duration(str(self.claim_timeout))
        if claim_timeout_delta is None:
            await interaction.response.send_message(
                "Invalid claim timeout format. Use formats like `30m`, `1h`, `2h`.",
                ephemeral=True,
            )
            return

        # Parse winners count
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

        # Create giveaway
        await self.cog.create_giveaway(
            interaction,
            channel,
            str(self.prize),
            str(self.description) or None,
            duration_delta,
            winners,
            str(self.prize_code),
            claim_timeout_delta,
        )


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
        # Timeout - treat as declined, reroll
        await self.cog.handle_claim_timeout(self.giveaway_id, self.winner_id)


class ShadyGiveaway(commands.Cog):
    """Advanced giveaway system with prize code management and claim verification."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820736, force_registration=True)
        
        # Schema: guild_id -> giveaway_id -> giveaway_data
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
        # In DMs, always allow
        if not isinstance(interaction.user, discord.Member):
            return True
        
        # Check if user is admin
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Check roles from wiki/config/roles.json
        roles_file = Path("E:/wiki/config/roles.json")
        if roles_file.exists():
            try:
                with open(roles_file, "r", encoding="utf-8") as f:
                    allowed_role_ids = json.load(f)
                user_role_ids = [role.id for role in interaction.user.roles]
                if any(role_id in allowed_role_ids for role_id in user_role_ids):
                    return True
            except Exception as e:
                log.error(f"Error reading roles.json: {e}")
        
        return False

    async def parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse duration string like '1h', '30m', '2d' into timedelta."""
        duration_str = duration_str.strip().lower()
        if not duration_str:
            return None
        
        # Extract number and unit
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

    @app_commands.command(name="giveaway", description="Manage giveaways")
    @app_commands.describe(
        action="Action to perform"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Create", value="create"),
        app_commands.Choice(name="List Active", value="list"),
        app_commands.Choice(name="End Early", value="end"),
        app_commands.Choice(name="Cancel", value="cancel"),
    ])
    async def giveaway(
        self,
        interaction: discord.Interaction,
        action: str
    ):
        """Main giveaway command handler."""
        if not await self.is_authorized(interaction):
            await interaction.response.send_message(
                "You don't have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        if action == "create":
            # Show modal for giveaway creation
            modal = GiveawayCreateModal(self)
            await interaction.response.send_modal(modal)
            
        elif action == "list":
            await self.list_giveaways(interaction)
            
        elif action == "end":
            await interaction.response.send_message(
                "Use `/giveaway_manage` to end or cancel specific giveaways.",
                ephemeral=True
            )
            
        elif action == "cancel":
            await interaction.response.send_message(
                "Use `/giveaway_manage` to end or cancel specific giveaways.",
                ephemeral=True
            )

    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        prize: str,
        description: Optional[str],
        duration: timedelta,
        winners_count: int,
        prize_code: str,
        claim_timeout: timedelta,
    ):
        """Create a new giveaway."""
        # Generate unique ID
        giveaway_id = f"{interaction.guild.id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Calculate end time
        end_time = datetime.now(timezone.utc) + duration
        
        # Create embed
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize}",
            description=description or "React to enter!",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Winners", value=str(winners_count), inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
        embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
        
        # Post giveaway
        view = GiveawayEnterView(self, giveaway_id)
        message = await channel.send(embed=embed, view=view)
        
        # Store giveaway data
        async with self.config.guild(interaction.guild).giveaways() as giveaways:
            giveaways[giveaway_id] = {
                "message_id": message.id,
                "channel_id": channel.id,
                "prize": prize,
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
            f"Giveaway created in {channel.mention}! Ends <t:{int(end_time.timestamp())}:R>",
            ephemeral=True
        )

    async def handle_entry(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle user entering a giveaway."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        
        if giveaway_id not in giveaways:
            await interaction.response.send_message("This giveaway no longer exists.", ephemeral=True)
            return
        
        giveaway = giveaways[giveaway_id]
        
        # Check if already entered
        if interaction.user.id in giveaway["entries"]:
            await interaction.response.send_message("You've already entered this giveaway!", ephemeral=True)
            return
        
        # Add entry
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
                await asyncio.sleep(30)  # Check every 30 seconds
                
                for guild in self.bot.guilds:
                    giveaways = await self.config.guild(guild).giveaways()
                    now = datetime.now(timezone.utc).timestamp()
                    
                    for giveaway_id, giveaway in list(giveaways.items()):
                        if not giveaway["ended"] and now >= giveaway["end_timestamp"]:
                            # Giveaway has ended, pick winner
                            await self.end_giveaway(guild, giveaway_id, giveaway)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in giveaway check task: {e}", exc_info=True)

    async def end_giveaway(self, guild: discord.Guild, giveaway_id: str, giveaway: Dict[str, Any]):
        """End a giveaway and pick winners."""
        # Mark as ended
        async with self.config.guild(guild).giveaways() as giveaways:
            giveaways[giveaway_id]["ended"] = True
        
        # Update message
        try:
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.red()
                embed.title = f"🎉 GIVEAWAY ENDED: {giveaway['prize']}"
                await message.edit(embed=embed, view=None)
        except Exception as e:
            log.error(f"Error updating giveaway message: {e}")
        
        # Pick winners
        if not giveaway["entries"]:
            # No entries
            try:
                if channel:
                    await channel.send(f"Giveaway for **{giveaway['prize']}** ended with no entries! 😢")
            except Exception:
                pass
            return
        
        # Pick winners - start with first winner
        await self.pick_and_notify_winner(guild, giveaway_id, giveaway)

    async def pick_and_notify_winner(self, guild: discord.Guild, giveaway_id: str, giveaway: Dict[str, Any]):
        """Pick a random winner from entries and send claim notification."""
        # Get current data
        giveaways = await self.config.guild(guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return
        
        # Check if we already have enough winners
        claimed_count = len([w for w in giveaway.get("winners_claimed", [])])
        if claimed_count >= giveaway["winners_count"]:
            # All winners have been claimed
            return
        
        # Filter out already picked winners
        available_entries = [e for e in giveaway["entries"] if e not in giveaway["winners_picked"]]
        
        if not available_entries:
            # All entries have been tried
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                remaining = giveaway["winners_count"] - claimed_count
                await channel.send(f"No more eligible entries for **{giveaway['prize']}** giveaway. Still need {remaining} more winner(s) but no one left to pick from.")
            return
        
        # Pick random winner
        winner_id = random.choice(available_entries)
        
        # Add to winners_picked
        async with self.config.guild(guild).giveaways() as all_giveaways:
            all_giveaways[giveaway_id]["winners_picked"].append(winner_id)
            # Initialize winners_claimed if not exists
            if "winners_claimed" not in all_giveaways[giveaway_id]:
                all_giveaways[giveaway_id]["winners_claimed"] = []
        
        # Send claim message to winner
        winner = guild.get_member(winner_id)
        if not winner:
            # User left server, reroll
            await self.pick_and_notify_winner(guild, giveaway_id, giveaway)
            return
        
        # Determine winner position
        winner_number = len(giveaway["winners_picked"])
        
        # Create claim embed
        claim_embed = discord.Embed(
            title="🎉 You Won a Giveaway!",
            description=f"Congratulations! You won **{giveaway['prize']}**!",
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
        
        # Create view with timeout
        view = WinnerClaimView(
            self,
            giveaway_id,
            winner_id,
            giveaway["claim_timeout_seconds"]
        )
        
        # Try to DM winner
        try:
            await winner.send(embed=claim_embed, view=view)
        except discord.Forbidden:
            # Can't DM user, announce in channel
            channel = guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(
                    f"{winner.mention} You won **{giveaway['prize']}** but I can't DM you! Please enable DMs and we'll reroll.",
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
        giveaways = await self.config.guild(interaction.guild).giveaways()
        giveaway = giveaways.get(giveaway_id)
        
        if not giveaway:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        
        if claimed:
            # Mark as claimed
            async with self.config.guild(interaction.guild).giveaways() as all_giveaways:
                if "winners_claimed" not in all_giveaways[giveaway_id]:
                    all_giveaways[giveaway_id]["winners_claimed"] = []
                all_giveaways[giveaway_id]["winners_claimed"].append(winner_id)
            
            # Send prize code
            code_embed = discord.Embed(
                title="🎁 Your Prize Code",
                description=f"**Prize:** {giveaway['prize']}\n\n**Code/Key:**\n```\n{giveaway['prize_code']}\n```",
                color=discord.Color.green()
            )
            code_embed.set_footer(text="Congratulations! Enjoy your prize!")
            
            await interaction.response.send_message(embed=code_embed, ephemeral=True)
            
            # Announce in channel
            channel = interaction.guild.get_channel(giveaway["channel_id"])
            
            # Get updated giveaway data
            giveaways_updated = await self.config.guild(interaction.guild).giveaways()
            giveaway_updated = giveaways_updated.get(giveaway_id)
            
            if channel:
                claimed_count = len(giveaway_updated.get("winners_claimed", []))
                if giveaway["winners_count"] > 1:
                    await channel.send(
                        f"🎉 Congratulations {interaction.user.mention} for claiming prize #{claimed_count} of {giveaway['winners_count']} for **{giveaway['prize']}**!"
                    )
                else:
                    await channel.send(f"🎉 Congratulations {interaction.user.mention} for winning **{giveaway['prize']}**!")
            
            # Check if we need more winners
            if claimed_count < giveaway["winners_count"]:
                # Pick next winner
                await self.pick_and_notify_winner(interaction.guild, giveaway_id, giveaway_updated)
                
        else:
            # Declined - reroll
            await interaction.response.send_message(
                "You've declined the prize. We'll pick another winner!",
                ephemeral=True
            )
            
            # Announce reroll
            channel = interaction.guild.get_channel(giveaway["channel_id"])
            if channel:
                await channel.send(f"{interaction.user.mention} declined **{giveaway['prize']}**. Picking a new winner...")
            
            # Pick new winner
            await self.pick_and_notify_winner(interaction.guild, giveaway_id, giveaway)

    async def handle_claim_timeout(self, giveaway_id: str, winner_id: int):
        """Handle when winner doesn't respond in time."""
        # Find guild
        for guild in self.bot.guilds:
            giveaways = await self.config.guild(guild).giveaways()
            if giveaway_id in giveaways:
                giveaway = giveaways[giveaway_id]
                
                # Announce timeout
                channel = guild.get_channel(giveaway["channel_id"])
                winner = guild.get_member(winner_id)
                winner_mention = winner.mention if winner else f"<@{winner_id}>"
                
                if channel:
                    await channel.send(
                        f"⏰ {winner_mention} didn't claim **{giveaway['prize']}** in time. Picking a new winner..."
                    )
                
                # Pick new winner
                await self.pick_and_notify_winner(guild, giveaway_id, giveaway)
                break

    async def list_giveaways(self, interaction: discord.Interaction):
        """List all active giveaways in the guild."""
        giveaways = await self.config.guild(interaction.guild).giveaways()
        
        active = [(gid, g) for gid, g in giveaways.items() if not g["ended"]]
        
        if not active:
            await interaction.response.send_message("No active giveaways.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎉 Active Giveaways",
            color=discord.Color.gold()
        )
        
        for giveaway_id, giveaway in active[:10]:  # Show max 10
            channel = interaction.guild.get_channel(giveaway["channel_id"])
            channel_mention = channel.mention if channel else "Unknown Channel"
            
            end_time = giveaway["end_timestamp"]
            entries_count = len(giveaway["entries"])
            
            embed.add_field(
                name=f"{giveaway['prize']}",
                value=f"Channel: {channel_mention}\n"
                      f"Entries: {entries_count}\n"
                      f"Ends: <t:{end_time}:R>\n"
                      f"ID: `{giveaway_id}`",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Red):
    cog = ShadyGiveaway(bot)
    await bot.add_cog(cog)
