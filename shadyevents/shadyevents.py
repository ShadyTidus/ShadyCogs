"""
ShadyEvents - Tournament and bracket management system
Features solo/team tournaments, pickup players, and bracket generation.
"""

import asyncio
import discord
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from io import BytesIO

from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta
from discord import app_commands

# Optional: Pillow for bracket image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

log = logging.getLogger("red.shadycogs.shadyevents")


class TournamentCreateModal(discord.ui.Modal, title="Create Tournament"):
    """Modal for creating a new tournament."""

    tournament_name = discord.ui.TextInput(
        label="Tournament Name",
        placeholder="e.g., Marvel Rivals Championship",
        required=True,
        max_length=100,
    )
    game = discord.ui.TextInput(
        label="Game/Category",
        placeholder="e.g., Marvel Rivals, Rocket League",
        required=True,
        max_length=50,
    )
    tournament_type = discord.ui.TextInput(
        label="Type",
        placeholder="solo OR team",
        required=True,
        max_length=10,
    )
    team_size = discord.ui.TextInput(
        label="Team Size (for team tournaments)",
        placeholder="e.g., 3, 6 (leave blank for solo)",
        required=False,
        max_length=2,
    )
    team_mode = discord.ui.TextInput(
        label="Team Mode (for team tournaments)",
        placeholder="random OR premade (leave blank for solo)",
        required=False,
        max_length=10,
    )

    def __init__(self, cog: "ShadyEvents", channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        # Validate type
        tourney_type = str(self.tournament_type).strip().lower()
        if tourney_type not in ["solo", "team"]:
            await interaction.response.send_message(
                "Tournament type must be either `solo` or `team`.",
                ephemeral=True
            )
            return
        
        # For team tournaments
        team_size_val = None
        team_mode_val = None
        
        if tourney_type == "team":
            # Validate team size
            try:
                team_size_val = int(str(self.team_size).strip())
                if team_size_val < 2 or team_size_val > 10:
                    raise ValueError
            except (ValueError, AttributeError):
                await interaction.response.send_message(
                    "Team size must be a number between 2 and 10 for team tournaments.",
                    ephemeral=True
                )
                return
            
            # Validate team mode
            team_mode_val = str(self.team_mode).strip().lower()
            if team_mode_val not in ["random", "premade"]:
                await interaction.response.send_message(
                    "Team mode must be either `random` or `premade` for team tournaments.",
                    ephemeral=True
                )
                return
        
        # Create tournament
        await self.cog.create_tournament(
            interaction,
            self.channel,
            str(self.tournament_name),
            str(self.game),
            tourney_type,
            team_size_val,
            team_mode_val,
        )


class TeamRegisterModal(discord.ui.Modal, title="Register Team"):
    """Modal for captains to register a team."""

    team_name = discord.ui.TextInput(
        label="Team Name",
        placeholder="e.g., Team Alpha, The Champions",
        required=True,
        max_length=50,
    )
    players = discord.ui.TextInput(
        label="Players (mention or IDs)",
        style=discord.TextStyle.paragraph,
        placeholder="@player1 @player2 @player3 (include yourself)",
        required=True,
        max_length=500,
    )

    def __init__(self, cog: "ShadyEvents", tournament_id: str, team_size: int):
        super().__init__()
        self.cog = cog
        self.tournament_id = tournament_id
        self.team_size = team_size
        self.players.label = f"Players - Need {team_size} (mention or IDs)"

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.register_team(
            interaction,
            self.tournament_id,
            str(self.team_name),
            str(self.players),
            self.team_size,
        )


class TournamentSignupView(discord.ui.View):
    """View with signup buttons for tournaments."""

    def __init__(self, cog: "ShadyEvents", tournament_id: str, tournament_type: str, team_mode: Optional[str], team_size: Optional[int]):
        super().__init__(timeout=None)
        self.cog = cog
        self.tournament_id = tournament_id
        
        # Add appropriate buttons based on tournament type
        if tournament_type == "solo":
            # Solo tournament - just join button
            self.add_item(self.join_solo_button)
        elif tournament_type == "team" and team_mode == "random":
            # Random teams - just join button
            self.add_item(self.join_random_button)
        elif tournament_type == "team" and team_mode == "premade":
            # Pre-made teams - both buttons
            self.add_item(self.register_team_button)
            self.add_item(self.join_pickup_button)
        
        self.team_size = team_size

    @discord.ui.button(label="Join Tournament", style=discord.ButtonStyle.green, custom_id="join_solo", row=0)
    async def join_solo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_solo_join(interaction, self.tournament_id)

    @discord.ui.button(label="Join Tournament", style=discord.ButtonStyle.green, custom_id="join_random", row=0)
    async def join_random_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_random_join(interaction, self.tournament_id)

    @discord.ui.button(label="⭐ Register Team", style=discord.ButtonStyle.blurple, custom_id="register_team", row=0)
    async def register_team_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamRegisterModal(self.cog, self.tournament_id, self.team_size)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🎲 Join as Pickup", style=discord.ButtonStyle.gray, custom_id="join_pickup", row=1)
    async def join_pickup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_pickup_join(interaction, self.tournament_id)


class ShadyEvents(commands.Cog):
    """Tournament and bracket management system."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820737, force_registration=True)
        
        # Schema: guild_id -> tournament_id -> tournament_data
        default_guild = {
            "tournaments": {},
        }
        self.config.register_guild(**default_guild)

    async def is_authorized(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to manage tournaments."""
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

    @app_commands.command(name="tournament", description="Create and manage tournaments")
    @app_commands.describe(
        action="Action to perform",
        channel="Channel to post tournament in (for create)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Create", value="create"),
        app_commands.Choice(name="List Active", value="list"),
        app_commands.Choice(name="Start Bracket", value="start"),
        app_commands.Choice(name="View Bracket", value="bracket"),
    ])
    async def tournament(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: Optional[discord.TextChannel] = None
    ):
        """Main tournament command handler."""
        if not await self.is_authorized(interaction):
            await interaction.response.send_message(
                "You don't have permission to manage tournaments.",
                ephemeral=True
            )
            return
        
        if action == "create":
            if channel is None:
                await interaction.response.send_message(
                    "Please specify a channel to post the tournament in.",
                    ephemeral=True
                )
                return
            modal = TournamentCreateModal(self, channel)
            await interaction.response.send_modal(modal)
            
        elif action == "list":
            await self.list_tournaments(interaction)
            
        elif action == "start":
            await interaction.response.send_message(
                "Use `/tournament_manage start tournament_id:<id>` to start a specific tournament.",
                ephemeral=True
            )
            
        elif action == "bracket":
            await interaction.response.send_message(
                "Use `/tournament_manage bracket tournament_id:<id>` to view a specific bracket.",
                ephemeral=True
            )


    async def create_tournament(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        name: str,
        game: str,
        tournament_type: str,
        team_size: Optional[int],
        team_mode: Optional[str],
    ):
        """Create a new tournament."""
        # Generate unique ID
        tournament_id = f"{interaction.guild.id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Create embed
        embed = discord.Embed(
            title=f"🏆 {name}",
            description=f"**Game:** {game}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if tournament_type == "solo":
            embed.add_field(name="Type", value="Solo (1v1 or FFA)", inline=True)
            embed.add_field(name="Participants", value="0", inline=True)
        elif tournament_type == "team":
            embed.add_field(name="Type", value=f"Team ({team_size}v{team_size})", inline=True)
            embed.add_field(name="Team Mode", value=team_mode.capitalize(), inline=True)
            
            if team_mode == "premade":
                embed.add_field(
                    name="⚠️ Signup Options",
                    value="**⭐ Register Team:** Captain registers full team\n"
                          "**🎲 Join as Pickup:** Individuals randomly assigned to incomplete teams",
                    inline=False
                )
                embed.add_field(name="Registered Teams", value="0", inline=True)
                embed.add_field(name="Pickup Players", value="0", inline=True)
            elif team_mode == "random":
                embed.add_field(
                    name="Teams",
                    value="Teams will be randomly assigned when bracket starts",
                    inline=False
                )
                embed.add_field(name="Participants", value="0", inline=True)
        
        embed.add_field(name="Status", value="🟢 Open for Signups", inline=False)
        embed.set_footer(text=f"Tournament ID: {tournament_id}")
        
        # Post tournament
        view = TournamentSignupView(self, tournament_id, tournament_type, team_mode, team_size)
        message = await channel.send(embed=embed, view=view)
        
        # Store tournament data
        async with self.config.guild(interaction.guild).tournaments() as tournaments:
            tournaments[tournament_id] = {
                "message_id": message.id,
                "channel_id": channel.id,
                "name": name,
                "game": game,
                "host_id": interaction.user.id,
                "type": tournament_type,
                "team_size": team_size,
                "team_mode": team_mode,
                "participants": [],  # For solo or random team mode
                "teams": {},  # For premade teams: team_name -> [player_ids]
                "pickup_players": [],  # For premade team mode
                "started": False,
                "bracket": None,
            }
        
        await interaction.response.send_message(
            f"Tournament **{name}** created in {channel.mention}!",
            ephemeral=True
        )

    async def handle_solo_join(self, interaction: discord.Interaction, tournament_id: str):
        """Handle solo tournament join."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        if interaction.user.id in tournament["participants"]:
            await interaction.response.send_message("You've already joined this tournament!", ephemeral=True)
            return
        
        # Add participant
        tournament["participants"].append(interaction.user.id)
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        # Update embed
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        await interaction.response.send_message(
            f"You've joined the tournament! ({len(tournament['participants'])} participants)",
            ephemeral=True
        )

    async def handle_random_join(self, interaction: discord.Interaction, tournament_id: str):
        """Handle random team tournament join (same as solo)."""
        await self.handle_solo_join(interaction, tournament_id)

    async def handle_pickup_join(self, interaction: discord.Interaction, tournament_id: str):
        """Handle pickup player join for premade team tournaments."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        # Check if already in a team
        for team_players in tournament["teams"].values():
            if interaction.user.id in team_players:
                await interaction.response.send_message("You're already on a registered team!", ephemeral=True)
                return
        
        if interaction.user.id in tournament["pickup_players"]:
            await interaction.response.send_message("You've already joined as a pickup player!", ephemeral=True)
            return
        
        # Add to pickup pool
        tournament["pickup_players"].append(interaction.user.id)
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        # Update embed
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        await interaction.response.send_message(
            f"✅ You've joined as a pickup player!\n\n"
            f"⚠️ **Note:** You will be randomly assigned to a team that needs players when the tournament starts. "
            f"({len(tournament['pickup_players'])} pickup players)",
            ephemeral=True
        )


    async def register_team(
        self,
        interaction: discord.Interaction,
        tournament_id: str,
        team_name: str,
        players_str: str,
        team_size: int,
    ):
        """Register a team for a tournament."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        # Check if team name already exists
        if team_name in tournament["teams"]:
            await interaction.response.send_message(f"Team name **{team_name}** is already taken!", ephemeral=True)
            return
        
        # Parse player mentions/IDs
        player_ids = []
        tokens = players_str.replace("<@", " <@").replace(">", "> ").split()
        
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            
            # Try to extract user ID
            user_id = None
            if token.startswith("<@") and token.endswith(">"):
                # Mention format
                user_id_str = token.replace("<@", "").replace("!", "").replace(">", "")
                try:
                    user_id = int(user_id_str)
                except ValueError:
                    pass
            else:
                # Try parsing as raw ID
                try:
                    user_id = int(token)
                except ValueError:
                    pass
            
            if user_id and user_id not in player_ids:
                player_ids.append(user_id)
        
        # Validate player count
        if len(player_ids) == 0:
            await interaction.response.send_message(
                "No valid players found. Please mention players or provide their user IDs.",
                ephemeral=True
            )
            return
        
        if len(player_ids) > team_size:
            await interaction.response.send_message(
                f"Too many players! Team size is {team_size}, you provided {len(player_ids)}.",
                ephemeral=True
            )
            return
        
        # Check for duplicate players across teams
        for existing_team_name, existing_players in tournament["teams"].items():
            for player_id in player_ids:
                if player_id in existing_players:
                    await interaction.response.send_message(
                        f"<@{player_id}> is already on team **{existing_team_name}**!",
                        ephemeral=True
                    )
                    return
        
        # Check if any players are in pickup pool
        for player_id in player_ids:
            if player_id in tournament["pickup_players"]:
                # Remove from pickup pool
                tournament["pickup_players"].remove(player_id)
        
        # Register team
        tournament["teams"][team_name] = player_ids
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        # Update embed
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        player_mentions = [f"<@{pid}>" for pid in player_ids]
        
        status_msg = f"✅ Team **{team_name}** registered!\n\n**Roster ({len(player_ids)}/{team_size}):**\n" + ", ".join(player_mentions)
        
        if len(player_ids) < team_size:
            status_msg += f"\n\n⚠️ **Incomplete Team:** Your team needs {team_size - len(player_ids)} more player(s). "
            status_msg += "Pickup players will be randomly assigned to fill your roster when the tournament starts."
        
        await interaction.response.send_message(status_msg, ephemeral=True)

    async def update_tournament_embed(self, guild: discord.Guild, tournament_id: str, tournament: Dict[str, Any]):
        """Update the tournament embed with current signup counts."""
        try:
            channel = guild.get_channel(tournament["channel_id"])
            if not channel:
                return
            
            message = await channel.fetch_message(tournament["message_id"])
            embed = message.embeds[0]
            
            # Update participant counts
            if tournament["type"] == "solo":
                # Update participants field
                for i, field in enumerate(embed.fields):
                    if field.name == "Participants":
                        embed.set_field_at(i, name="Participants", value=str(len(tournament["participants"])), inline=True)
                        break
            
            elif tournament["type"] == "team" and tournament["team_mode"] == "random":
                # Update participants field
                for i, field in enumerate(embed.fields):
                    if field.name == "Participants":
                        embed.set_field_at(i, name="Participants", value=str(len(tournament["participants"])), inline=True)
                        break
            
            elif tournament["type"] == "team" and tournament["team_mode"] == "premade":
                # Update teams and pickup counts
                for i, field in enumerate(embed.fields):
                    if field.name == "Registered Teams":
                        embed.set_field_at(i, name="Registered Teams", value=str(len(tournament["teams"])), inline=True)
                    elif field.name == "Pickup Players":
                        embed.set_field_at(i, name="Pickup Players", value=str(len(tournament["pickup_players"])), inline=True)
            
            await message.edit(embed=embed)
            
        except Exception as e:
            log.error(f"Error updating tournament embed: {e}")

    async def list_tournaments(self, interaction: discord.Interaction):
        """List all active tournaments."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        active = [(tid, t) for tid, t in tournaments.items() if not t["started"]]
        
        if not active:
            await interaction.response.send_message("No active tournaments.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🏆 Active Tournaments",
            color=discord.Color.blue()
        )
        
        for tournament_id, tournament in active[:10]:
            channel = interaction.guild.get_channel(tournament["channel_id"])
            channel_mention = channel.mention if channel else "Unknown"
            
            if tournament["type"] == "solo":
                count_str = f"{len(tournament['participants'])} participants"
            elif tournament["type"] == "team" and tournament["team_mode"] == "random":
                count_str = f"{len(tournament['participants'])} participants"
            else:  # premade teams
                count_str = f"{len(tournament['teams'])} teams, {len(tournament['pickup_players'])} pickups"
            
            embed.add_field(
                name=f"{tournament['name']} ({tournament['game']})",
                value=f"Channel: {channel_mention}\n{count_str}\nID: `{tournament_id}`",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Red):
    cog = ShadyEvents(bot)
    await bot.add_cog(cog)
