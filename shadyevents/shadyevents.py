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

    channel = discord.ui.TextInput(
        label="Channel",
        placeholder="#tournaments or channel ID",
        required=True,
        max_length=100,
    )

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

    def __init__(self, cog: "ShadyEvents"):
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
            channel,
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
        
        # Check if user is admin or guild owner
        if interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner:
            return True
        
        # Check roles from wiki/config/roles.json
        try:
            cogs_dir = Path(__file__).parent.parent
            roles_file = cogs_dir / "wiki" / "config" / "roles.json"
            
            if roles_file.exists():
                with open(roles_file, "r", encoding="utf-8") as f:
                    roles_data = json.load(f)
                    allowed_roles = roles_data.get("authorized_roles", [])
                    # Check if user has any of the allowed roles by name
                    return any(role.name in allowed_roles for role in interaction.user.roles)
        except Exception as e:
            log.error(f"Error reading roles.json: {e}")
        
        return False

    @app_commands.command(name="tournament", description="Create and manage tournaments")
    @app_commands.describe(
        action="Action to perform"
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
        action: str
    ):
        """Main tournament command handler."""
        if not await self.is_authorized(interaction):
            await interaction.response.send_message(
                "You don't have permission to manage tournaments.",
                ephemeral=True
            )
            return
        
        if action == "create":
            modal = TournamentCreateModal(self)
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

    @app_commands.command(name="tournament_manage", description="Manage tournament brackets and matches")
    @app_commands.describe(
        action="Action to perform",
        tournament_id="Tournament ID",
        match_number="Match number (for reporting)",
        winner="Winner team name or participant mention (for reporting)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Start Tournament", value="start"),
        app_commands.Choice(name="View Bracket", value="bracket"),
        app_commands.Choice(name="Report Match", value="report"),
    ])
    async def tournament_manage(
        self,
        interaction: discord.Interaction,
        action: str,
        tournament_id: str,
        match_number: Optional[int] = None,
        winner: Optional[str] = None
    ):
        """Manage tournament brackets and results."""
        if not await self.is_authorized(interaction):
            await interaction.response.send_message(
                "You don't have permission to manage tournaments.",
                ephemeral=True
            )
            return
        
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if action == "start":
            await self.start_tournament(interaction, tournament_id, tournament)
        elif action == "bracket":
            await self.show_bracket(interaction, tournament_id, tournament)
        elif action == "report":
            if match_number is None or winner is None:
                await interaction.response.send_message(
                    "Please provide both match_number and winner for match reporting.",
                    ephemeral=True
                )
                return
            await self.report_match(interaction, tournament_id, tournament, match_number, winner)

    async def start_tournament(
        self,
        interaction: discord.Interaction,
        tournament_id: str,
        tournament: Dict[str, Any]
    ):
        """Start tournament, assign pickup players, and generate bracket."""
        if tournament["started"]:
            await interaction.response.send_message("Tournament already started!", ephemeral=True)
            return
        
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        # Handle different tournament types
        if tournament["type"] == "solo":
            participants = tournament["participants"]
            if len(participants) < 2:
                await interaction.response.send_message(
                    "Need at least 2 participants to start tournament!",
                    ephemeral=True
                )
                return
            bracket = self.generate_bracket(participants, is_team=False)
            
        elif tournament["type"] == "team" and tournament["team_mode"] == "random":
            # Random teams - assign participants to random teams
            participants = tournament["participants"]
            team_size = tournament["team_size"]
            
            if len(participants) < team_size * 2:
                await interaction.response.send_message(
                    f"Need at least {team_size * 2} participants to form 2 teams!",
                    ephemeral=True
                )
                return
            
            # Shuffle and create teams
            random.shuffle(participants)
            teams = {}
            team_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", 
                         "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa"]
            
            for i in range(0, len(participants), team_size):
                team_participants = participants[i:i+team_size]
                if len(team_participants) == team_size:
                    team_name = f"Team {team_names[len(teams)]}"
                    teams[team_name] = team_participants
            
            if len(teams) < 2:
                await interaction.response.send_message(
                    f"Not enough complete teams! Need at least 2 complete teams of {team_size}.",
                    ephemeral=True
                )
                return
            
            bracket = self.generate_bracket(list(teams.keys()), is_team=True)
            
            # Store teams in tournament
            async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
                all_tournaments[tournament_id]["teams"] = teams
                all_tournaments[tournament_id]["bracket"] = bracket
                all_tournaments[tournament_id]["started"] = True
            
        elif tournament["type"] == "team" and tournament["team_mode"] == "premade":
            # Pre-made teams with pickup players
            teams = dict(tournament["teams"])
            pickup_players = list(tournament["pickup_players"])
            team_size = tournament["team_size"]
            
            # Shuffle pickup players for random assignment
            random.shuffle(pickup_players)
            
            # Fill incomplete teams
            for team_name, players in list(teams.items()):
                needed = team_size - len(players)
                if needed > 0 and pickup_players:
                    added_players = pickup_players[:needed]
                    teams[team_name].extend(added_players)
                    pickup_players = pickup_players[needed:]
            
            # Create new teams from remaining pickup players
            new_team_counter = 1
            while len(pickup_players) >= team_size:
                team_name = f"Pickup Team {new_team_counter}"
                teams[team_name] = pickup_players[:team_size]
                pickup_players = pickup_players[team_size:]
                new_team_counter += 1
            
            if len(teams) < 2:
                await interaction.response.send_message(
                    "Need at least 2 complete teams to start tournament!",
                    ephemeral=True
                )
                return
            
            bracket = self.generate_bracket(list(teams.keys()), is_team=True)
            
            # Store updated teams and bracket
            async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
                all_tournaments[tournament_id]["teams"] = teams
                all_tournaments[tournament_id]["bracket"] = bracket
                all_tournaments[tournament_id]["started"] = True
                all_tournaments[tournament_id]["pickup_players"] = pickup_players
        
        # Announce tournament start
        channel = interaction.guild.get_channel(tournament["channel_id"])
        
        embed = discord.Embed(
            title=f"🏆 {tournament['name']} - Tournament Started!",
            description=f"**Game:** {tournament['game']}",
            color=discord.Color.green()
        )
        
        if tournament["type"] == "team":
            teams_text = ""
            final_teams = tournaments[tournament_id]["teams"]
            for team_name, players in final_teams.items():
                player_mentions = [f"<@{pid}>" for pid in players]
                teams_text += f"**{team_name}:** {', '.join(player_mentions)}\n"
            
            embed.add_field(name="Teams", value=teams_text or "No teams", inline=False)
        else:
            participant_mentions = [f"<@{pid}>" for pid in participants]
            embed.add_field(
                name=f"Participants ({len(participants)})",
                value=", ".join(participant_mentions) if participant_mentions else "None",
                inline=False
            )
        
        embed.add_field(
            name="📊 View Bracket",
            value=f"Use `/tournament_manage bracket tournament_id:{tournament_id}`",
            inline=False
        )
        
        if channel:
            await channel.send(embed=embed)
        
        await interaction.response.send_message(
            f"Tournament started! {len(bracket)} matches in Round 1.",
            ephemeral=True
        )

    def generate_bracket(self, entities: List, is_team: bool) -> List[Dict[str, Any]]:
        """Generate single-elimination bracket."""
        entities = list(entities)
        random.shuffle(entities)
        
        matches = []
        match_num = 1
        
        for i in range(0, len(entities) - 1, 2):
            matches.append({
                "match_number": match_num,
                "round": 1,
                "participant1": entities[i],
                "participant2": entities[i + 1],
                "winner": None,
                "completed": False
            })
            match_num += 1
        
        if len(entities) % 2 != 0:
            matches.append({
                "match_number": match_num,
                "round": 1,
                "participant1": entities[-1],
                "participant2": "BYE",
                "winner": entities[-1],
                "completed": True
            })
        
        return matches

    async def show_bracket(
        self,
        interaction: discord.Interaction,
        tournament_id: str,
        tournament: Dict[str, Any]
    ):
        """Display current bracket status."""
        if not tournament["started"]:
            await interaction.response.send_message("Tournament hasn't started yet!", ephemeral=True)
            return
        
        bracket = tournament.get("bracket", [])
        if not bracket:
            await interaction.response.send_message("No bracket generated yet!", ephemeral=True)
            return
        
        rounds = {}
        for match in bracket:
            round_num = match["round"]
            if round_num not in rounds:
                rounds[round_num] = []
            rounds[round_num].append(match)
        
        embed = discord.Embed(
            title=f"🏆 {tournament['name']} - Bracket",
            description=f"**Game:** {tournament['game']}",
            color=discord.Color.blue()
        )
        
        for round_num in sorted(rounds.keys()):
            matches = rounds[round_num]
            match_text = ""
            
            for match in matches:
                p1 = match["participant1"]
                p2 = match["participant2"]
                
                if tournament["type"] == "team":
                    p1_display = p1
                    p2_display = p2
                else:
                    p1_display = f"<@{p1}>"
                    p2_display = f"<@{p2}>" if p2 != "BYE" else p2
                
                status = "✅" if match["completed"] else "⏳"
                winner_display = ""
                if match["winner"]:
                    if tournament["type"] == "team":
                        winner_display = f" → **{match['winner']} wins!**"
                    else:
                        winner_display = f" → **<@{match['winner']}> wins!**"
                
                match_text += f"{status} Match #{match['match_number']}: {p1_display} vs {p2_display}{winner_display}\n"
            
            round_name = f"Round {round_num}"
            if round_num == max(rounds.keys()) and len(matches) == 1:
                round_name = "🏆 Finals"
            
            embed.add_field(name=round_name, value=match_text or "No matches", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

    async def report_match(
        self,
        interaction: discord.Interaction,
        tournament_id: str,
        tournament: Dict[str, Any],
        match_number: int,
        winner_input: str
    ):
        """Report match result and advance winner."""
        if not tournament["started"]:
            await interaction.response.send_message("Tournament hasn't started!", ephemeral=True)
            return
        
        bracket = tournament.get("bracket", [])
        
        match = None
        for m in bracket:
            if m["match_number"] == match_number:
                match = m
                break
        
        if not match:
            await interaction.response.send_message(f"Match #{match_number} not found!", ephemeral=True)
            return
        
        if match["completed"]:
            await interaction.response.send_message(f"Match #{match_number} already completed!", ephemeral=True)
            return
        
        winner = None
        if tournament["type"] == "team":
            if winner_input == match["participant1"] or winner_input == match["participant2"]:
                winner = winner_input
        else:
            winner_id = None
            if winner_input.startswith("<@") and winner_input.endswith(">"):
                winner_id = int(winner_input.replace("<@", "").replace("!", "").replace(">", ""))
            else:
                try:
                    winner_id = int(winner_input)
                except ValueError:
                    pass
            
            if winner_id in [match["participant1"], match["participant2"]]:
                winner = winner_id
        
        if not winner:
            await interaction.response.send_message(
                f"Invalid winner! Must be one of the participants in Match #{match_number}.",
                ephemeral=True
            )
            return
        
        match["completed"] = True
        match["winner"] = winner
        
        current_round = match["round"]
        round_matches = [m for m in bracket if m["round"] == current_round]
        round_complete = all(m["completed"] for m in round_matches)
        
        if round_complete:
            round_winners = [m["winner"] for m in round_matches]
            
            if len(round_winners) > 1:
                next_round = current_round + 1
                match_counter = max([m["match_number"] for m in bracket]) + 1
                
                for i in range(0, len(round_winners) - 1, 2):
                    bracket.append({
                        "match_number": match_counter,
                        "round": next_round,
                        "participant1": round_winners[i],
                        "participant2": round_winners[i + 1],
                        "winner": None,
                        "completed": False
                    })
                    match_counter += 1
                
                if len(round_winners) % 2 != 0:
                    bracket.append({
                        "match_number": match_counter,
                        "round": next_round,
                        "participant1": round_winners[-1],
                        "participant2": "BYE",
                        "winner": round_winners[-1],
                        "completed": True
                    })
            else:
                champion = round_winners[0]
                channel = interaction.guild.get_channel(tournament["channel_id"])
                if channel:
                    champion_display = champion if tournament["type"] == "team" else f"<@{champion}>"
                    await channel.send(
                        f"🎉 **TOURNAMENT COMPLETE!** 🎉\n\n"
                        f"**Champion:** {champion_display}\n"
                        f"**Tournament:** {tournament['name']}"
                    )
        
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id]["bracket"] = bracket
        
        channel = interaction.guild.get_channel(tournament["channel_id"])
        if channel:
            p1_display = match["participant1"] if tournament["type"] == "team" else f"<@{match['participant1']}>"
            p2_display = match["participant2"] if tournament["type"] == "team" else f"<@{match['participant2']}>"
            winner_display = winner if tournament["type"] == "team" else f"<@{winner}>"
            
            await channel.send(
                f"📊 **Match #{match_number} Result**\n"
                f"{p1_display} vs {p2_display}\n"
                f"**Winner:** {winner_display}"
            )
        
        await interaction.response.send_message(
            f"Match #{match_number} result recorded! Winner: {winner_display}",
            ephemeral=True
        )


async def setup(bot: Red):
    cog = ShadyEvents(bot)
    await bot.add_cog(cog)

