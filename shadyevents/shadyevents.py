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

    def __init__(self, cog: "ShadyEvents"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This command must be run in a text channel!",
                ephemeral=True
            )
            return
        
        tourney_type = str(self.tournament_type).strip().lower()
        if tourney_type not in ["solo", "team"]:
            await interaction.response.send_message(
                "Tournament type must be either `solo` or `team`.",
                ephemeral=True
            )
            return
        
        team_size_val = None
        
        if tourney_type == "team":
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
        
        await self.cog.create_tournament(
            interaction,
            channel,
            str(self.tournament_name),
            str(self.game),
            tourney_type,
            team_size_val,
        )


class TeamCreateModal(discord.ui.Modal, title="Create Team"):
    """Modal for captains to create a team - just the name, captain is auto-added."""

    team_name = discord.ui.TextInput(
        label="Team Name",
        placeholder="e.g., Team Alpha, The Champions",
        required=True,
        max_length=50,
    )

    def __init__(self, cog: "ShadyEvents", tournament_id: str):
        super().__init__()
        self.cog = cog
        self.tournament_id = tournament_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.create_team(
            interaction,
            self.tournament_id,
            str(self.team_name).strip(),
        )


class JoinTeamSelectView(discord.ui.View):
    """View with dropdown to select a team to join."""

    def __init__(self, cog: "ShadyEvents", tournament_id: str, teams: Dict[str, List[int]], team_size: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.tournament_id = tournament_id
        
        options = []
        for team_name, players in teams.items():
            if len(players) < team_size:
                spots_left = team_size - len(players)
                options.append(
                    discord.SelectOption(
                        label=team_name,
                        value=team_name,
                        description=f"{len(players)}/{team_size} players ({spots_left} spot{'s' if spots_left > 1 else ''} left)"
                    )
                )
        
        if not options:
            # No teams need players - this shouldn't happen but handle gracefully
            options.append(
                discord.SelectOption(
                    label="No teams available",
                    value="_none_",
                    description="All teams are full"
                )
            )
        
        self.select = discord.ui.Select(
            placeholder="Select a team to join...",
            options=options[:25]  # Discord limit
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        team_name = self.select.values[0]
        
        if team_name == "_none_":
            await interaction.response.send_message("No teams available to join.", ephemeral=True)
            self.stop()
            return
        
        await self.cog.join_team(interaction, self.tournament_id, team_name)
        self.stop()


class SoloSignupView(discord.ui.View):
    """View for solo tournament signups."""

    def __init__(self, cog: "ShadyEvents", tournament_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.tournament_id = tournament_id

    @discord.ui.button(label="🎮 Join Tournament", style=discord.ButtonStyle.green, custom_id="tournament_join_solo")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_solo_join(interaction, self.tournament_id)

    @discord.ui.button(label="🚪 Leave", style=discord.ButtonStyle.red, custom_id="tournament_leave_solo")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_leave(interaction, self.tournament_id)


class TeamSignupView(discord.ui.View):
    """View for team tournament signups."""

    def __init__(self, cog: "ShadyEvents", tournament_id: str, team_size: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.tournament_id = tournament_id
        self.team_size = team_size

    @discord.ui.button(label="⭐ Create Team (Captain)", style=discord.ButtonStyle.blurple, custom_id="tournament_create_team")
    async def create_team_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamCreateModal(self.cog, self.tournament_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👥 Join a Team", style=discord.ButtonStyle.green, custom_id="tournament_join_team")
    async def join_team_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.show_team_selection(interaction, self.tournament_id)

    @discord.ui.button(label="🎲 Join as Pickup", style=discord.ButtonStyle.gray, custom_id="tournament_join_pickup")
    async def join_pickup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_pickup_join(interaction, self.tournament_id)

    @discord.ui.button(label="🚪 Leave", style=discord.ButtonStyle.red, custom_id="tournament_leave_team")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_leave(interaction, self.tournament_id)


class TournamentSelectView(discord.ui.View):
    """View with dropdown to select a tournament for management."""

    def __init__(self, cog: "ShadyEvents", tournaments: List[tuple], action: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.action = action
        
        options = []
        for tournament_id, tournament in tournaments[:25]:
            status = "🏁 Started" if tournament.get("started") else "🟢 Open"
            name = tournament["name"][:50] + "..." if len(tournament["name"]) > 50 else tournament["name"]
            
            if tournament["type"] == "solo":
                count = f"{len(tournament['participants'])} players"
            else:
                count = f"{len(tournament['teams'])} teams"
            
            options.append(
                discord.SelectOption(
                    label=name,
                    value=tournament_id,
                    description=f"{status} | {tournament['game']} | {count}"
                )
            )
        
        self.select = discord.ui.Select(
            placeholder="Select a tournament...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        tournament_id = self.select.values[0]
        
        if self.action == "start":
            await self.cog.start_tournament_from_select(interaction, tournament_id)
        elif self.action == "cancel":
            await self.cog.cancel_tournament(interaction, tournament_id)
        elif self.action == "bracket":
            await self.cog.show_bracket_from_select(interaction, tournament_id)
        elif self.action == "info":
            await self.cog.show_tournament_info(interaction, tournament_id)
        
        self.stop()


class ShadyEvents(commands.Cog):
    """Tournament and bracket management system."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=260288776360820737, force_registration=True)
        
        default_guild = {
            "tournaments": {},
        }
        self.config.register_guild(**default_guild)
        
        self.active_views: Dict[str, discord.ui.View] = {}

    async def cog_load(self):
        """Re-register persistent views on cog load."""
        await self.bot.wait_until_ready()
        await self.restore_views()

    async def restore_views(self):
        """Restore views for active tournaments after bot restart."""
        for guild in self.bot.guilds:
            tournaments = await self.config.guild(guild).tournaments()
            for tournament_id, tournament in tournaments.items():
                if not tournament.get("started") and not tournament.get("cancelled"):
                    try:
                        if tournament["type"] == "solo":
                            view = SoloSignupView(self, tournament_id)
                        else:
                            view = TeamSignupView(self, tournament_id, tournament["team_size"])
                        
                        self.active_views[tournament_id] = view
                        self.bot.add_view(view, message_id=tournament["message_id"])
                    except Exception as e:
                        log.error(f"Error restoring view for tournament {tournament_id}: {e}")

    async def is_authorized(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to manage tournaments."""
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

    @app_commands.command(name="tournament", description="Create or list tournaments")
    @app_commands.describe(action="Action to perform")
    @app_commands.choices(action=[
        app_commands.Choice(name="Create", value="create"),
        app_commands.Choice(name="List Active", value="list"),
    ])
    async def tournament(self, interaction: discord.Interaction, action: str):
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

    @app_commands.command(name="tournamentmanage", description="Manage tournaments (start, cancel, view bracket/info)")
    @app_commands.describe(action="Action to perform")
    @app_commands.choices(action=[
        app_commands.Choice(name="Start Tournament", value="start"),
        app_commands.Choice(name="View Bracket", value="bracket"),
        app_commands.Choice(name="View Info", value="info"),
        app_commands.Choice(name="Cancel Tournament", value="cancel"),
    ])
    async def tournamentmanage(self, interaction: discord.Interaction, action: str):
        """Manage tournaments with dropdown selection."""
        if not await self.is_authorized(interaction):
            await interaction.response.send_message(
                "You don't have permission to manage tournaments.",
                ephemeral=True
            )
            return
        
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if action == "start":
            filtered = [(tid, t) for tid, t in tournaments.items() 
                       if not t.get("started") and not t.get("cancelled")]
        elif action == "cancel":
            filtered = [(tid, t) for tid, t in tournaments.items() 
                       if not t.get("cancelled")]
        else:
            filtered = [(tid, t) for tid, t in tournaments.items() 
                       if not t.get("cancelled")]
        
        if not filtered:
            await interaction.response.send_message(
                "No tournaments available for this action.",
                ephemeral=True
            )
            return
        
        view = TournamentSelectView(self, filtered, action)
        
        action_text = {
            "start": "start (generate bracket)",
            "bracket": "view bracket for",
            "info": "view detailed info for",
            "cancel": "cancel"
        }
        
        await interaction.response.send_message(
            f"Select a tournament to {action_text[action]}:",
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tournamentreport", description="Report a match result")
    @app_commands.describe(
        tournament_id="Tournament ID",
        match_number="Match number",
        winner="Winner team name or @mention"
    )
    async def tournamentreport(
        self,
        interaction: discord.Interaction,
        tournament_id: str,
        match_number: int,
        winner: str
    ):
        """Report a match result."""
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
        await self.report_match(interaction, tournament_id, tournament, match_number, winner)

    async def create_tournament(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        name: str,
        game: str,
        tournament_type: str,
        team_size: Optional[int],
    ):
        """Create a new tournament."""
        tournament_id = f"{interaction.guild.id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        embed = discord.Embed(
            title=f"🏆 {name}",
            description=f"**Game:** {game}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if tournament_type == "solo":
            embed.add_field(name="Type", value="Solo", inline=True)
            embed.add_field(name="Participants", value="0", inline=True)
            view = SoloSignupView(self, tournament_id)
        else:
            embed.add_field(name="Type", value=f"Team ({team_size}v{team_size})", inline=True)
            embed.add_field(
                name="How to Join",
                value="**⭐ Create Team:** Become captain, others join your team\n"
                      "**👥 Join a Team:** Pick an existing team from dropdown\n"
                      "**🎲 Join as Pickup:** Get randomly assigned when tournament starts",
                inline=False
            )
            embed.add_field(name="Teams", value="None yet", inline=False)
            embed.add_field(name="Pickup Players", value="0", inline=True)
            view = TeamSignupView(self, tournament_id, team_size)
        
        embed.add_field(name="Status", value="🟢 Open for Signups", inline=False)
        embed.set_footer(text=f"Tournament ID: {tournament_id}")
        
        message = await channel.send(embed=embed, view=view)
        
        self.active_views[tournament_id] = view
        
        async with self.config.guild(interaction.guild).tournaments() as tournaments:
            tournaments[tournament_id] = {
                "message_id": message.id,
                "channel_id": channel.id,
                "name": name,
                "game": game,
                "host_id": interaction.user.id,
                "type": tournament_type,
                "team_size": team_size,
                "participants": [],
                "teams": {},  # team_name -> {"captain": user_id, "players": [user_ids]}
                "pickup_players": [],
                "started": False,
                "cancelled": False,
                "bracket": None,
            }
        
        await interaction.response.send_message(
            f"✅ Tournament **{name}** created in {channel.mention}!\n"
            f"ID: `{tournament_id}`",
            ephemeral=True
        )

    async def create_team(self, interaction: discord.Interaction, tournament_id: str, team_name: str):
        """Create a new team with the user as captain."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        if tournament.get("cancelled"):
            await interaction.response.send_message("This tournament has been cancelled.", ephemeral=True)
            return
        
        # Check if team name exists
        if team_name in tournament["teams"]:
            await interaction.response.send_message(
                f"Team name **{team_name}** is already taken!",
                ephemeral=True
            )
            return
        
        # Check if user is already on a team
        for existing_team, team_data in tournament["teams"].items():
            if interaction.user.id in team_data["players"]:
                await interaction.response.send_message(
                    f"You're already on team **{existing_team}**! Leave that team first.",
                    ephemeral=True
                )
                return
        
        # Remove from pickup pool if they were there
        if interaction.user.id in tournament["pickup_players"]:
            tournament["pickup_players"].remove(interaction.user.id)
        
        # Create the team with captain
        tournament["teams"][team_name] = {
            "captain": interaction.user.id,
            "players": [interaction.user.id]
        }
        
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        team_size = tournament["team_size"]
        await interaction.response.send_message(
            f"✅ Team **{team_name}** created!\n\n"
            f"You are the captain. Your team needs **{team_size - 1}** more player(s).\n"
            f"Other players can click **👥 Join a Team** and select your team from the dropdown.",
            ephemeral=True
        )

    async def show_team_selection(self, interaction: discord.Interaction, tournament_id: str):
        """Show dropdown to select a team to join."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        if tournament.get("cancelled"):
            await interaction.response.send_message("This tournament has been cancelled.", ephemeral=True)
            return
        
        # Check if user is already on a team
        for team_name, team_data in tournament["teams"].items():
            if interaction.user.id in team_data["players"]:
                await interaction.response.send_message(
                    f"You're already on team **{team_name}**!",
                    ephemeral=True
                )
                return
        
        # Check if user is in pickup pool
        if interaction.user.id in tournament["pickup_players"]:
            await interaction.response.send_message(
                "You're already in the pickup pool! Leave first to join a specific team.",
                ephemeral=True
            )
            return
        
        # Get teams that need players
        team_size = tournament["team_size"]
        available_teams = {
            name: data["players"] 
            for name, data in tournament["teams"].items() 
            if len(data["players"]) < team_size
        }
        
        if not available_teams:
            await interaction.response.send_message(
                "No teams are looking for players right now.\n\n"
                "You can:\n"
                "• **Create your own team** with the ⭐ button\n"
                "• **Join as Pickup** with the 🎲 button",
                ephemeral=True
            )
            return
        
        view = JoinTeamSelectView(self, tournament_id, available_teams, team_size)
        await interaction.response.send_message(
            "Select a team to join:",
            view=view,
            ephemeral=True
        )

    async def join_team(self, interaction: discord.Interaction, tournament_id: str, team_name: str):
        """Join a specific team."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        if team_name not in tournament["teams"]:
            await interaction.response.send_message("That team no longer exists.", ephemeral=True)
            return
        
        team_data = tournament["teams"][team_name]
        team_size = tournament["team_size"]
        
        if len(team_data["players"]) >= team_size:
            await interaction.response.send_message(
                f"Team **{team_name}** is now full!",
                ephemeral=True
            )
            return
        
        # Double-check user isn't already on a team
        for existing_team, existing_data in tournament["teams"].items():
            if interaction.user.id in existing_data["players"]:
                await interaction.response.send_message(
                    f"You're already on team **{existing_team}**!",
                    ephemeral=True
                )
                return
        
        # Add to team
        team_data["players"].append(interaction.user.id)
        
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        current_count = len(team_data["players"])
        spots_left = team_size - current_count
        
        msg = f"✅ You've joined team **{team_name}**! ({current_count}/{team_size})"
        if spots_left > 0:
            msg += f"\n\nTeam needs {spots_left} more player(s)."
        else:
            msg += "\n\n🎉 Team is now complete!"
        
        await interaction.response.send_message(msg, ephemeral=True)

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
        
        if tournament.get("cancelled"):
            await interaction.response.send_message("This tournament has been cancelled.", ephemeral=True)
            return
        
        if interaction.user.id in tournament["participants"]:
            await interaction.response.send_message("You've already joined this tournament!", ephemeral=True)
            return
        
        tournament["participants"].append(interaction.user.id)
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        await interaction.response.send_message(
            f"✅ You've joined **{tournament['name']}**! ({len(tournament['participants'])} participants)",
            ephemeral=True
        )

    async def handle_pickup_join(self, interaction: discord.Interaction, tournament_id: str):
        """Handle pickup player join for team tournaments."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("This tournament has already started.", ephemeral=True)
            return
        
        if tournament.get("cancelled"):
            await interaction.response.send_message("This tournament has been cancelled.", ephemeral=True)
            return
        
        # Check if already in a team
        for team_name, team_data in tournament["teams"].items():
            if interaction.user.id in team_data["players"]:
                await interaction.response.send_message(
                    f"You're already on team **{team_name}**! Leave that team first.",
                    ephemeral=True
                )
                return
        
        if interaction.user.id in tournament["pickup_players"]:
            await interaction.response.send_message("You've already joined as a pickup player!", ephemeral=True)
            return
        
        tournament["pickup_players"].append(interaction.user.id)
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        await interaction.response.send_message(
            f"✅ You've joined as a pickup player!\n\n"
            f"You'll be randomly assigned to a team when the tournament starts. "
            f"({len(tournament['pickup_players'])} pickup players)",
            ephemeral=True
        )

    async def handle_leave(self, interaction: discord.Interaction, tournament_id: str):
        """Handle player leaving a tournament."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        if tournament["started"]:
            await interaction.response.send_message("Cannot leave a tournament that has started.", ephemeral=True)
            return
        
        left = False
        left_from = ""
        
        # Check solo participants
        if interaction.user.id in tournament["participants"]:
            tournament["participants"].remove(interaction.user.id)
            left = True
            left_from = "the tournament"
        
        # Check pickup players
        if interaction.user.id in tournament["pickup_players"]:
            tournament["pickup_players"].remove(interaction.user.id)
            left = True
            left_from = "the pickup pool"
        
        # Check teams
        for team_name, team_data in list(tournament["teams"].items()):
            if interaction.user.id in team_data["players"]:
                team_data["players"].remove(interaction.user.id)
                
                if not team_data["players"]:
                    # Team is empty, delete it
                    del tournament["teams"][team_name]
                    left_from = f"team **{team_name}** (team disbanded)"
                elif team_data["captain"] == interaction.user.id:
                    # Captain left, assign new captain
                    team_data["captain"] = team_data["players"][0]
                    new_captain = interaction.guild.get_member(team_data["captain"])
                    new_captain_name = new_captain.display_name if new_captain else "Unknown"
                    left_from = f"team **{team_name}** ({new_captain_name} is now captain)"
                else:
                    left_from = f"team **{team_name}**"
                
                left = True
                break
        
        if not left:
            await interaction.response.send_message("You're not in this tournament.", ephemeral=True)
            return
        
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id] = tournament
        
        await self.update_tournament_embed(interaction.guild, tournament_id, tournament)
        
        await interaction.response.send_message(
            f"✅ You've left {left_from}.",
            ephemeral=True
        )

    async def update_tournament_embed(self, guild: discord.Guild, tournament_id: str, tournament: Dict[str, Any]):
        """Update the tournament embed with current signup info."""
        try:
            channel = guild.get_channel(tournament["channel_id"])
            if not channel:
                return
            
            message = await channel.fetch_message(tournament["message_id"])
            embed = message.embeds[0]
            
            if tournament["type"] == "solo":
                for i, field in enumerate(embed.fields):
                    if field.name == "Participants":
                        embed.set_field_at(i, name="Participants", value=str(len(tournament["participants"])), inline=True)
                        break
            else:
                team_size = tournament["team_size"]
                
                # Build teams display
                if tournament["teams"]:
                    teams_text = ""
                    for team_name, team_data in tournament["teams"].items():
                        player_mentions = []
                        for pid in team_data["players"]:
                            if pid == team_data["captain"]:
                                player_mentions.append(f"⭐<@{pid}>")
                            else:
                                player_mentions.append(f"<@{pid}>")
                        
                        count = len(team_data["players"])
                        status = "✅" if count == team_size else f"({count}/{team_size})"
                        teams_text += f"**{team_name}** {status}: {', '.join(player_mentions)}\n"
                    
                    if len(teams_text) > 1024:
                        teams_text = f"{len(tournament['teams'])} teams registered"
                else:
                    teams_text = "None yet"
                
                # Update fields
                for i, field in enumerate(embed.fields):
                    if field.name == "Teams":
                        embed.set_field_at(i, name="Teams", value=teams_text, inline=False)
                    elif field.name == "Pickup Players":
                        embed.set_field_at(i, name="Pickup Players", value=str(len(tournament["pickup_players"])), inline=True)
            
            await message.edit(embed=embed)
            
        except Exception as e:
            log.error(f"Error updating tournament embed: {e}")

    async def list_tournaments(self, interaction: discord.Interaction):
        """List all active tournaments."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        active = [(tid, t) for tid, t in tournaments.items() if not t.get("cancelled")]
        
        if not active:
            await interaction.response.send_message(
                "No active tournaments.\n\nUse `/tournament create` to create one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🏆 Tournaments",
            description="Use `/tournamentmanage` to start, view, or cancel.",
            color=discord.Color.blue()
        )
        
        for tournament_id, tournament in active[:10]:
            channel = interaction.guild.get_channel(tournament["channel_id"])
            channel_mention = channel.mention if channel else "Unknown"
            
            status = "🏁 Started" if tournament["started"] else "🟢 Open"
            
            if tournament["type"] == "solo":
                count_str = f"{len(tournament['participants'])} participants"
            else:
                count_str = f"{len(tournament['teams'])} teams, {len(tournament['pickup_players'])} pickups"
            
            embed.add_field(
                name=f"{tournament['name']} ({tournament['game']})",
                value=f"Status: {status}\n"
                      f"Channel: {channel_mention}\n"
                      f"{count_str}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def start_tournament_from_select(self, interaction: discord.Interaction, tournament_id: str):
        """Start tournament from dropdown selection."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        await self.start_tournament(interaction, tournament_id, tournament)

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
        
        guild = interaction.guild
        
        if tournament["type"] == "solo":
            participants = tournament["participants"]
            if len(participants) < 2:
                await interaction.response.send_message(
                    "Need at least 2 participants to start!",
                    ephemeral=True
                )
                return
            
            bracket = self.generate_bracket(participants, is_team=False)
            final_teams = {}
            
        else:  # Team tournament
            teams = {name: data["players"].copy() for name, data in tournament["teams"].items()}
            pickup_players = list(tournament["pickup_players"])
            team_size = tournament["team_size"]
            
            random.shuffle(pickup_players)
            
            # Fill incomplete teams
            for team_name, players in list(teams.items()):
                needed = team_size - len(players)
                if needed > 0 and pickup_players:
                    added = pickup_players[:needed]
                    teams[team_name].extend(added)
                    pickup_players = pickup_players[needed:]
            
            # Create new teams from remaining pickups
            new_team_counter = 1
            while len(pickup_players) >= team_size:
                team_name = f"Pickup Team {new_team_counter}"
                teams[team_name] = pickup_players[:team_size]
                pickup_players = pickup_players[team_size:]
                new_team_counter += 1
            
            # Keep only complete teams
            complete_teams = {name: players for name, players in teams.items() if len(players) == team_size}
            
            if len(complete_teams) < 2:
                await interaction.response.send_message(
                    f"Need at least 2 complete teams of {team_size} players to start!",
                    ephemeral=True
                )
                return
            
            final_teams = complete_teams
            bracket = self.generate_bracket(list(final_teams.keys()), is_team=True)
            participants = []
        
        # Update stored data - convert team structure for started tournament
        async with self.config.guild(guild).tournaments() as all_tournaments:
            if tournament["type"] == "team":
                # Convert to simple format for bracket play
                all_tournaments[tournament_id]["final_teams"] = final_teams
            all_tournaments[tournament_id]["bracket"] = bracket
            all_tournaments[tournament_id]["started"] = True
            all_tournaments[tournament_id]["participants"] = participants
        
        # Update embed
        try:
            channel = guild.get_channel(tournament["channel_id"])
            if channel:
                message = await channel.fetch_message(tournament["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.green()
                
                for i, field in enumerate(embed.fields):
                    if field.name == "Status":
                        embed.set_field_at(i, name="Status", value="🏁 Tournament Started!", inline=False)
                        break
                
                await message.edit(embed=embed, view=None)
        except Exception as e:
            log.error(f"Error updating started tournament embed: {e}")
        
        if tournament_id in self.active_views:
            del self.active_views[tournament_id]
        
        # Announce start
        channel = guild.get_channel(tournament["channel_id"])
        
        announce_embed = discord.Embed(
            title=f"🏆 {tournament['name']} - Tournament Started!",
            description=f"**Game:** {tournament['game']}",
            color=discord.Color.green()
        )
        
        if tournament["type"] == "team":
            teams_text = ""
            for team_name, players in final_teams.items():
                player_mentions = [f"<@{pid}>" for pid in players]
                teams_text += f"**{team_name}:** {', '.join(player_mentions)}\n"
            
            announce_embed.add_field(name="Teams", value=teams_text or "No teams", inline=False)
        else:
            if len(participants) <= 20:
                participant_mentions = [f"<@{pid}>" for pid in participants]
                announce_embed.add_field(
                    name=f"Participants ({len(participants)})",
                    value=", ".join(participant_mentions),
                    inline=False
                )
            else:
                announce_embed.add_field(
                    name="Participants",
                    value=f"{len(participants)} players",
                    inline=False
                )
        
        announce_embed.add_field(
            name="📊 View Bracket",
            value=f"Use `/tournamentmanage` → View Bracket",
            inline=False
        )
        
        announce_embed.add_field(
            name="📝 Report Matches",
            value=f"`/tournamentreport tournament_id:{tournament_id} match_number:X winner:TeamName`",
            inline=False
        )
        
        if channel:
            await channel.send(embed=announce_embed)
        
        await interaction.response.send_message(
            f"✅ Tournament **{tournament['name']}** started with {len(bracket)} Round 1 matches!",
            ephemeral=True
        )

    async def cancel_tournament(self, interaction: discord.Interaction, tournament_id: str):
        """Cancel a tournament."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        async with self.config.guild(interaction.guild).tournaments() as all_tournaments:
            all_tournaments[tournament_id]["cancelled"] = True
        
        try:
            channel = interaction.guild.get_channel(tournament["channel_id"])
            if channel:
                message = await channel.fetch_message(tournament["message_id"])
                embed = message.embeds[0]
                embed.color = discord.Color.red()
                embed.title = f"🚫 {tournament['name']} - CANCELLED"
                
                for i, field in enumerate(embed.fields):
                    if field.name == "Status":
                        embed.set_field_at(i, name="Status", value="🚫 Cancelled", inline=False)
                        break
                
                await message.edit(embed=embed, view=None)
                await channel.send(f"Tournament **{tournament['name']}** has been cancelled by {interaction.user.mention}.")
        except Exception as e:
            log.error(f"Error updating cancelled tournament embed: {e}")
        
        if tournament_id in self.active_views:
            del self.active_views[tournament_id]
        
        await interaction.response.send_message(
            f"✅ Tournament **{tournament['name']}** has been cancelled.",
            ephemeral=True
        )

    async def show_bracket_from_select(self, interaction: discord.Interaction, tournament_id: str):
        """Show bracket from dropdown selection."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        await self.show_bracket(interaction, tournament_id, tournament)

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
            await interaction.response.send_message("No bracket generated!", ephemeral=True)
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
        
        max_round = max(rounds.keys()) if rounds else 0
        
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
                    p2_display = f"<@{p2}>" if p2 != "BYE" else "BYE"
                
                status = "✅" if match["completed"] else "⏳"
                winner_display = ""
                if match["winner"]:
                    if tournament["type"] == "team":
                        winner_display = f" → **{match['winner']}**"
                    else:
                        winner_display = f" → <@{match['winner']}>"
                
                match_text += f"{status} Match #{match['match_number']}: {p1_display} vs {p2_display}{winner_display}\n"
            
            if round_num == max_round and len(matches) == 1:
                round_name = "🏆 Finals"
            elif round_num == max_round - 1 and max_round > 1:
                round_name = "Semifinals"
            else:
                round_name = f"Round {round_num}"
            
            embed.add_field(name=round_name, value=match_text or "No matches", inline=False)
        
        embed.set_footer(text=f"Tournament ID: {tournament_id}")
        
        await interaction.response.send_message(embed=embed)

    async def show_tournament_info(self, interaction: discord.Interaction, tournament_id: str):
        """Show detailed tournament info."""
        tournaments = await self.config.guild(interaction.guild).tournaments()
        
        if tournament_id not in tournaments:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        
        tournament = tournaments[tournament_id]
        
        channel = interaction.guild.get_channel(tournament["channel_id"])
        host = interaction.guild.get_member(tournament["host_id"])
        
        if tournament.get("cancelled"):
            status = "🚫 Cancelled"
            color = discord.Color.red()
        elif tournament["started"]:
            status = "🏁 In Progress"
            color = discord.Color.green()
        else:
            status = "🟢 Open for Signups"
            color = discord.Color.blue()
        
        embed = discord.Embed(
            title=f"🏆 {tournament['name']}",
            description=f"**Game:** {tournament['game']}",
            color=color
        )
        
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Channel", value=channel.mention if channel else "Unknown", inline=True)
        embed.add_field(name="Host", value=host.mention if host else "Unknown", inline=True)
        embed.add_field(name="Type", value=tournament["type"].capitalize(), inline=True)
        
        if tournament["type"] == "team":
            embed.add_field(name="Team Size", value=str(tournament["team_size"]), inline=True)
            embed.add_field(name="Teams", value=str(len(tournament["teams"])), inline=True)
            embed.add_field(name="Pickup Players", value=str(len(tournament["pickup_players"])), inline=True)
            
            if tournament["teams"]:
                teams_text = ""
                for team_name, team_data in list(tournament["teams"].items())[:10]:
                    player_mentions = [f"<@{pid}>" for pid in team_data["players"]]
                    teams_text += f"**{team_name}:** {', '.join(player_mentions)}\n"
                
                if len(tournament["teams"]) > 10:
                    teams_text += f"*...and {len(tournament['teams']) - 10} more teams*"
                
                embed.add_field(name="Registered Teams", value=teams_text, inline=False)
        else:
            embed.add_field(name="Participants", value=str(len(tournament["participants"])), inline=True)
            
            if tournament["participants"] and len(tournament["participants"]) <= 15:
                participant_mentions = [f"<@{pid}>" for pid in tournament["participants"]]
                embed.add_field(
                    name="Player List",
                    value=", ".join(participant_mentions),
                    inline=False
                )
        
        embed.add_field(name="Tournament ID", value=f"`{tournament_id}`", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
            p1 = match["participant1"]
            p2 = match["participant2"]
            if tournament["type"] == "team":
                await interaction.response.send_message(
                    f"Invalid winner! Must be either `{p1}` or `{p2}`.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Invalid winner! Must be <@{p1}> or <@{p2}>.",
                    ephemeral=True
                )
            return
        
        match["completed"] = True
        match["winner"] = winner
        
        current_round = match["round"]
        round_matches = [m for m in bracket if m["round"] == current_round]
        round_complete = all(m["completed"] for m in round_matches)
        
        champion = None
        
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
            
            if champion:
                champion_display = champion if tournament["type"] == "team" else f"<@{champion}>"
                await channel.send(
                    f"🎉🏆 **TOURNAMENT CHAMPION** 🏆🎉\n\n"
                    f"**{tournament['name']}**\n"
                    f"**Champion:** {champion_display}"
                )
        
        winner_display = winner if tournament["type"] == "team" else f"<@{winner}>"
        msg = f"✅ Match #{match_number} recorded! Winner: {winner_display}"
        if champion:
            msg += "\n\n🏆 **Tournament Complete!**"
        
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: Red):
    cog = ShadyEvents(bot)
    await bot.add_cog(cog)
