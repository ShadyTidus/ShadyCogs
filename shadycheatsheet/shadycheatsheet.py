"""
ShadyCheatSheet - D&D 5e skill check reference guide for DMs
Comprehensive cheat sheet covering when to call for checks, DCs, contested checks,
group checks, skill confusions, and more.
"""

import discord
import json
import logging
from pathlib import Path
from typing import Optional

from redbot.core import commands
from redbot.core.bot import Red
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadycheatsheet")


class ShadyCheatSheet(commands.Cog):
    """D&D 5e skill check reference guide for DMs."""

    __version__ = "1.0.0"
    __author__ = "ShadyTidus"

    def __init__(self, bot: Red):
        self.bot = bot
        self.allowed_roles = []
        self.load_authorized_roles()

    def load_authorized_roles(self):
        """Load authorized roles from wiki/config/roles.json"""
        try:
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

    def is_authorized_interaction(self, interaction: discord.Interaction) -> bool:
        """Check if user has one of the allowed roles or admin permissions. Always allow DMs."""
        # Allow DMs - anyone can use in DM
        if not isinstance(interaction.user, discord.Member):
            return True

        # In guilds: Admin/guild owner always authorized
        if interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner:
            return True

        # Check if user has any of the allowed roles
        return any(role.name in self.allowed_roles for role in interaction.user.roles)

    @app_commands.command(name="skillcheatsheet", description="Full D&D 5e skill check guide for DMs")
    async def full_guide(self, interaction: discord.Interaction):
        """Send the complete skill check cheat sheet."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: When to Call for a Check
        embed1 = discord.Embed(
            title="📋 D&D 5e Skill Check Cheat Sheet",
            description="**When to Call for a Skill Check**",
            color=discord.Color.blue(),
        )
        embed1.add_field(
            name="DON'T call for a check if:",
            value=(
                "• The task is trivial for the character\n"
                "• Failure has no consequences (no time pressure, can retry infinitely)\n"
                "• Success is impossible\n"
                "• The outcome doesn't matter to the story"
            ),
            inline=False,
        )
        embed1.add_field(
            name="DO call for a check when:",
            value=(
                "• There's a meaningful chance of both success and failure\n"
                "• The outcome significantly affects the situation\n"
                "• There's time pressure, risk, or limited attempts"
            ),
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: Setting DCs
        embed2 = discord.Embed(
            title="🎯 Setting DCs",
            color=discord.Color.green(),
        )
        embed2.add_field(
            name="DC Table",
            value=(
                "**5** - Very Easy (Climb a knotted rope)\n"
                "**10** - Easy (Hear a loud conversation through a door)\n"
                "**15** - Medium (Pick a simple lock, track recent footprints)\n"
                "**20** - Hard (Climb a slippery cliff, identify rare poison)\n"
                "**25** - Very Hard (Swim in a stormy sea, recall obscure lore)\n"
                "**30** - Nearly Impossible (Convince a king to abdicate, leap a 30ft chasm)"
            ),
            inline=False,
        )
        embed2.add_field(
            name="Passive Checks",
            value="**Passive checks = 10 + modifier** (use for things they'd notice without trying)",
            inline=False,
        )
        embeds.append(embed2)

        # Embed 3: Contested Checks Preview
        embed3 = discord.Embed(
            title="⚔️ Contested Checks",
            description="When one creature's efforts directly oppose another, both roll and highest wins.",
            color=discord.Color.red(),
        )
        embed3.add_field(
            name="Common Contests",
            value=(
                "**Stealth vs Perception** - Ties go to the one hiding\n"
                "**Grapple/Shove** - Athletics vs Athletics/Acrobatics\n"
                "**Social Contests** - Intimidation/Persuasion/Deception vs Insight"
            ),
            inline=False,
        )
        embed3.add_field(
            name="Use /contestedchecks for full details",
            value="Environmental modifiers, creature abilities, and social interaction rules",
            inline=False,
        )
        embeds.append(embed3)
        # Embed 4: Group Checks Preview
        embed4 = discord.Embed(
            title="👥 Group Checks",
            description="When the party works together toward one goal. If at least half succeed, the whole group succeeds.",
            color=discord.Color.purple(),
        )
        embed4.add_field(
            name="Common Group Check Situations",
            value=(
                "• Stealth (sneaking as a group)\n"
                "• Climbing/Swimming (traversing together)\n"
                "• Survival (group navigation)\n"
                "• Rowing a boat in sync\n"
                "• Pulling/lifting heavy objects together"
            ),
            inline=False,
        )
        embed4.add_field(
            name="Use /groupchecks for full details",
            value="When to use group checks and when NOT to use them",
            inline=False,
        )
        embeds.append(embed4)

        # Embed 5: Common Confusions
        embed5 = discord.Embed(
            title="🤔 Common Skill Confusions",
            color=discord.Color.orange(),
        )
        embed5.add_field(
            name="STR Check vs Athletics",
            value="**Athletics:** Climbing, jumping, swimming, grappling\n**Raw STR:** Breaking objects, forcing doors, lifting",
            inline=False,
        )
        embed5.add_field(
            name="Athletics vs Acrobatics",
            value="**Athletics:** Power through (climb, jump, swim)\n**Acrobatics:** Finesse around (balance, tumble, escape grapples)",
            inline=False,
        )
        embed5.add_field(
            name="Perception vs Investigation",
            value="**Perception:** Noticing with senses - 'What do I see/hear?'\n**Investigation:** Searching and deducing - 'What does this mean?'",
            inline=False,
        )
        embed5.add_field(
            name="Use /skillconfusions for complete list",
            value="Includes Insight vs Perception, Survival vs Nature, and social skill differences",
            inline=False,
        )
        embeds.append(embed5)

        # Embed 6: Quick Reference & Pro Tips
        embed6 = discord.Embed(
            title="⚡ Quick Reference & Pro Tips",
            color=discord.Color.gold(),
        )
        embed6.add_field(
            name="Physical Skills",
            value="STR: Force, break, lift\nAthletics: Climb, jump, swim, grapple\nAcrobatics: Balance, tumble, escape",
            inline=True,
        )
        embed6.add_field(
            name="Mental Skills",
            value="Perception: Spot with senses\nInvestigation: Search and deduce\nInsight: Read motives/emotions",
            inline=True,
        )
        embed6.add_field(
            name="Social Skills",
            value="Persuasion: Honest influence\nDeception: Dishonest influence\nIntimidation: Influence through fear",
            inline=True,
        )
        embed6.add_field(
            name="Pro Tips",
            value=(
                "✅ **Advantage/Disadvantage** is better than +5/-5 bonuses\n"
                "✅ **'Can I try?'** - Others can try IF they have a different approach\n"
                "✅ **Failed forward** - Failure doesn't mean nothing happens, it means complications\n"
                "✅ **Contest or DC?** - If NPC actively opposes, contest. If just difficult, DC."
            ),
            inline=False,
        )
        embed6.add_field(
            name="More Commands",
            value=(
                "`/whentocall` - When to call for checks\n"
                "`/settingdcs` - DC guidelines\n"
                "`/contestedchecks` - Opposed rolls\n"
                "`/groupchecks` - Party working together\n"
                "`/skillconfusions` - Common mistakes\n"
                "`/skillreference` - Complete skill list\n"
                "`/protips` - DM best practices\n"
                "`/masteries` - Weapon mastery properties (2024)"
            ),
            inline=False,
        )
        embed6.set_footer(text=f"ShadyCheatSheet v{self.__version__} by {self.__author__}")
        embeds.append(embed6)

        await interaction.response.send_message(embeds=embeds)

    @app_commands.command(name="whentocall", description="When to call for skill checks")
    async def when_to_call(self, interaction: discord.Interaction):
        """Detailed guide on when to call for skill checks."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 When to Call for a Skill Check",
            description="Understanding when checks are needed helps maintain good pacing and tension.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="❌ DON'T call for a check if:",
            value=(
                "• **The task is trivial for the character**\n"
                "  Example: A barbarian lifting a chair, a rogue unlocking an unlocked door\n\n"
                "• **Failure has no consequences**\n"
                "  Example: No time pressure, can retry infinitely\n\n"
                "• **Success is impossible**\n"
                "  Example: Jumping to the moon, persuading a god to give up divinity\n\n"
                "• **The outcome doesn't matter to the story**\n"
                "  Example: Basic everyday activities with no risk"
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ DO call for a check when:",
            value=(
                "• **There's a meaningful chance of both success and failure**\n"
                "  The result isn't predetermined\n\n"
                "• **The outcome significantly affects the situation**\n"
                "  Success or failure changes what happens next\n\n"
                "• **There's time pressure, risk, or limited attempts**\n"
                "  They can't just keep trying until they succeed"
            ),
            inline=False,
        )
        embed.set_footer(text="Use /skillcheatsheet for the full guide")

        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="settingdcs", description="Guide for setting skill check DCs")
    async def setting_dcs(self, interaction: discord.Interaction):
        """Detailed DC setting guide."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎯 Setting DCs (Difficulty Class)",
            description="Choose a DC that reflects the task's difficulty and the consequences of failure.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="DC Reference Table",
            value=(
                "**DC 5** - Very Easy\n"
                "└ Examples: Climb a knotted rope, notice something large in plain sight\n\n"
                "**DC 10** - Easy\n"
                "└ Examples: Hear a loud conversation through a door, climb a rope\n\n"
                "**DC 15** - Medium\n"
                "└ Examples: Pick a simple lock, track recent footprints, calm a domestic animal\n\n"
                "**DC 20** - Hard\n"
                "└ Examples: Climb a slippery cliff, identify rare poison, pick a complex lock\n\n"
                "**DC 25** - Very Hard\n"
                "└ Examples: Swim in a stormy sea, recall obscure lore, track over solid rock\n\n"
                "**DC 30** - Nearly Impossible\n"
                "└ Examples: Convince a king to abdicate, leap a 30ft chasm, track a ghost"
            ),
            inline=False,
        )
        embed.add_field(
            name="Passive Checks",
            value=(
                "**Passive check = 10 + modifier**\n\n"
                "Use passive checks for things characters would notice without actively trying:\n"
                "• Passive Perception for noticing hidden enemies\n"
                "• Passive Investigation for spotting clues while traveling\n"
                "• Passive Insight for sensing when something is 'off'"
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Pro Tip",
            value="Don't overthink it! Most checks should be DC 10 (easy), 15 (medium), or 20 (hard). Save DC 25+ for truly exceptional feats.",
            inline=False,
        )
        embed.set_footer(text="Use /skillcheatsheet for the full guide")

        await interaction.response.send_message(embed=embed)
    @app_commands.command(name="contestedchecks", description="Guide for contested skill checks")
    async def contested_checks(self, interaction: discord.Interaction):
        """Detailed guide on contested checks."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: Overview and Stealth
        embed1 = discord.Embed(
            title="⚔️ Contested Checks",
            description="When one creature's efforts directly oppose another, both roll and highest wins.",
            color=discord.Color.red(),
        )
        embed1.add_field(
            name="🥷 Stealth vs Perception",
            value=(
                "• Attacker rolls Stealth, defender uses Passive Perception (or active if searching)\n"
                "• Ties go to the person trying NOT to be noticed\n\n"
                "**Environmental Modifiers:**\n"
                "• Heavy rain/snow: **Advantage** on Stealth (sound covered)\n"
                "• Fresh snow: **Disadvantage** on Stealth (leaves obvious tracks)\n"
                "• Darkness: **Advantage** for those without darkvision\n"
                "• Bright light/open terrain: **Disadvantage** on Stealth"
            ),
            inline=False,
        )
        embed1.add_field(
            name="🐺 Creature Abilities that Counter Stealth",
            value=(
                "• **Keen Smell** (wolves, bears): Can detect hidden creatures - consider advantage or auto-success if downwind\n"
                "• **Blindsight** (bats, oozes): Stealth is useless within range\n"
                "• **Tremorsense** (purple worms): Moving on the ground can't be hidden\n"
                "• **Truesight** (devils, couatls): Sees through invisibility and illusions"
            ),
            inline=False,
        )
        embed1.add_field(
            name="💡 DM Tip",
            value="Visible tracks don't mean they see YOU - use Survival check to follow tracks vs your Stealth to cover them",
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: Physical and Social Contests
        embed2 = discord.Embed(
            title="⚔️ Contested Checks (cont.)",
            color=discord.Color.red(),
        )
        embed2.add_field(
            name="🤼 Grapple/Shove",
            value=(
                "• **Attacker:** Athletics check\n"
                "• **Defender:** Athletics OR Acrobatics (their choice)\n"
            ),
            inline=False,
        )
        embed2.add_field(
            name="🎭 Hiding Objects vs Finding Them",
            value=(
                "• **Hider:** Sleight of Hand\n"
                "• **Searcher:** Investigation (active search) or Perception (pat-down)\n"
            ),
            inline=False,
        )
        embed2.add_field(
            name="💪 Tug-of-War/Arm Wrestling",
            value="• Both: Athletics vs Athletics\n• Can also use straight STR checks for raw power contests",
            inline=False,
        )
        embed2.add_field(
            name="🗣️ Social Contests",
            value=(
                "**When NPCs resist social influence:**\n"
                "• Intimidation → NPC Insight or WIS save\n"
                "• Persuasion → NPC Insight (if they doubt sincerity)\n"
                "• Deception → NPC Insight (if they suspect a lie)\n"
                "• Performance → NPC Insight or flat CHA check"
            ),
            inline=False,
        )
        embeds.append(embed2)

        # Embed 3: Social Contest Guidance
        embed3 = discord.Embed(
            title="⚔️ Social Contest Guidance",
            color=discord.Color.red(),
        )
        embed3.add_field(
            name="DM Guidance for Social Contests",
            value=(
                "• **Friendly NPCs:** Don't contest, just set a DC (they want to help)\n"
                "• **Neutral NPCs:** Contest if they have reason to doubt\n"
                "• **Hostile NPCs:** Always contest or give them advantage\n"
                "• **Impossible asks:** No check succeeds (persuading a king to give up his crown)"
            ),
            inline=False,
        )
        embed3.add_field(
            name="Example",
            value=(
                "Rogue tries to intimidate the guard captain.\n"
                "**Roll:** Intimidation vs captain's Insight\n"
                "**If captain wins:** He's offended and calls for backup"
            ),
            inline=False,
        )
        embed3.add_field(
            name="🏃 Chases",
            value=(
                "• **Pursuer:** Athletics or Acrobatics (based on terrain)\n"
                "• **Fleeing:** Athletics or Acrobatics\n"
                "• Repeat each round until someone wins by 5+ or escapes"
            ),
            inline=False,
        )
        embed3.set_footer(text="Use /skillcheatsheet for the full guide")
        embeds.append(embed3)

        await interaction.response.send_message(embeds=embeds)
    @app_commands.command(name="groupchecks", description="Guide for group skill checks")
    async def group_checks(self, interaction: discord.Interaction):
        """Detailed guide on group checks."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: Overview and Common Situations
        embed1 = discord.Embed(
            title="👥 Group Checks",
            description=(
                "Call for a group check when the party works together toward one goal "
                "and individual failure affects the group.\n\n"
                "**How it works:** Everyone rolls. If at least half the group succeeds, the whole group succeeds."
            ),
            color=discord.Color.purple(),
        )
        embed1.add_field(
            name="🥷 Stealth (sneaking as a group)",
            value=(
                "• Party trying to sneak past guards together\n"
                "• At least half succeed = group isn't detected\n"
                "• Failure means noise/movement gives away position\n\n"
                "**💡 DM Tip:** Heavily armored characters can impose disadvantage on the group - "
                "consider having them create a distraction instead"
            ),
            inline=False,
        )
        embed1.add_field(
            name="🧗 Climbing/Swimming (traversing together)",
            value=(
                "• Crossing a chasm on a rope bridge\n"
                "• Swimming across a rapid river\n"
                "• Group succeeds = everyone makes it (successful members help stragglers)\n"
                "• Group fails = everyone faces consequences or must backtrack"
            ),
            inline=False,
        )
        embed1.add_field(
            name="🗺️ Survival (group navigation)",
            value=(
                "• Party navigating through wilderness without getting lost\n"
                "• At least half succeed = they stay on course\n"
                "• Failure = they wander off-path, lose time, or trigger an encounter"
            ),
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: More Situations
        embed2 = discord.Embed(
            title="👥 Group Checks (cont.)",
            color=discord.Color.purple(),
        )
        embed2.add_field(
            name="🚣 Rowing a Boat",
            value=(
                "• Everyone rowing in sync to escape a whirlpool\n"
                "• Group success = escape\n"
                "• Group failure = pulled in"
            ),
            inline=False,
        )
        embed2.add_field(
            name="🎭 Performance (group entertainment)",
            value=(
                "• Band playing together, troupe performing a play\n"
                "• Group success = audience loves it\n"
                "• Group failure = booed off stage"
            ),
            inline=False,
        )
        embed2.add_field(
            name="💪 Pulling/Lifting (heavy object)",
            value=(
                "• Pushing a massive stone door together\n"
                "• Lifting a portcullis so the party can escape\n"
                "• Each success adds to the total STR check"
            ),
            inline=False,
        )
        embeds.append(embed2)

        # Embed 3: When NOT to Use
        embed3 = discord.Embed(
            title="👥 When NOT to Use Group Checks",
            color=discord.Color.purple(),
        )
        embed3.add_field(
            name="❌ Don't use group checks when:",
            value=(
                "• **Individual success/failure matters**\n"
                "  Example: One person can pick the lock while others watch\n\n"
                "• **Failure doesn't affect others**\n"
                "  Example: One person fails to climb, others can still help them up\n\n"
                "• **Only one person is doing the task**\n"
                "  Example: Rogue picks lock alone - not a group effort"
            ),
            inline=False,
        )
        embed3.add_field(
            name="💡 Pro Tip",
            value=(
                "Group checks work best when:\n"
                "1. The whole party is participating\n"
                "2. One person's failure could jeopardize everyone\n"
                "3. Success requires coordination, not individual mastery"
            ),
            inline=False,
        )
        embed3.set_footer(text="Use /skillcheatsheet for the full guide")
        embeds.append(embed3)

        await interaction.response.send_message(embeds=embeds)
    @app_commands.command(name="skillconfusions", description="Common skill confusions explained")
    async def skill_confusions(self, interaction: discord.Interaction):
        """Detailed guide on commonly confused skills."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: Physical Skills
        embed1 = discord.Embed(
            title="🤔 Common Skill Confusions",
            description="Clear explanations of commonly confused skill pairs.",
            color=discord.Color.orange(),
        )
        embed1.add_field(
            name="💪 STR Check vs Athletics",
            value=(
                "• **Athletics (trained skill):** Climbing, jumping, swimming, grappling, shoving\n"
                "• **Raw Strength:** Breaking objects, forcing doors, lifting/carrying\n\n"
                "**Rule of thumb:** Use Athletics for technique-based physical activities. "
                "Use raw STR for pure force."
            ),
            inline=False,
        )
        embed1.add_field(
            name="🏃 Athletics vs Acrobatics",
            value=(
                "• **Athletics:** Overcoming obstacles through power (climb, jump, swim)\n"
                "• **Acrobatics:** Staying on your feet, tumbling, balancing, escaping grapples, "
                "squeezing through tight spaces\n\n"
                "**Ask yourself:** 'Power through it or finesse around it?'"
            ),
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: Mental Skills
        embed2 = discord.Embed(
            title="🤔 Common Skill Confusions (cont.)",
            color=discord.Color.orange(),
        )
        embed2.add_field(
            name="👁️ Perception vs Investigation",
            value=(
                "• **Perception (Wisdom):** Noticing things passively or with your senses - "
                "'What do I see/hear/smell?'\n"
                "• **Investigation (Intelligence):** Active searching and deduction - "
                "'What does this mean? What am I missing?'\n\n"
                "**Example:** Perception = spotting the bloodstain. "
                "Investigation = determining it's 2 hours old and from a dagger wound."
            ),
            inline=False,
        )
        embed2.add_field(
            name="🧠 Insight vs Perception (social)",
            value=(
                "• **Perception:** Reading body language, noticing someone is nervous\n"
                "• **Insight:** Understanding *why* they're nervous, detecting lies, "
                "discerning intentions"
            ),
            inline=False,
        )
        embeds.append(embed2)

        # Embed 3: Outdoor and Social Skills
        embed3 = discord.Embed(
            title="🤔 Common Skill Confusions (cont.)",
            color=discord.Color.orange(),
        )
        embed3.add_field(
            name="🌲 Survival vs Nature",
            value=(
                "• **Survival:** Practical outdoor skills - tracking, foraging, navigating, "
                "predicting weather\n"
                "• **Nature:** Academic knowledge - identifying creatures/plants, "
                "recalling beast behaviors"
            ),
            inline=False,
        )
        embed3.add_field(
            name="🎭 Sleight of Hand vs Stealth",
            value=(
                "• **Sleight of Hand:** Pickpocketing, hiding objects on your person, "
                "performing tricks, subtle hand movements\n"
                "• **Stealth:** Hiding your whole body, moving quietly"
            ),
            inline=False,
        )
        embed3.add_field(
            name="🗣️ Persuasion vs Deception vs Intimidation",
            value=(
                "• **Persuasion:** Honest appeal, negotiation, diplomacy "
                "(they believe you and you're telling the truth)\n"
                "• **Deception:** Lying, disguises, fast-talking "
                "(they believe you but you're lying)\n"
                "• **Intimidation:** Threats, showing force "
                "(they comply out of fear, not agreement)"
            ),
            inline=False,
        )
        embed3.set_footer(text="Use /skillreference for a complete skill list")
        embeds.append(embed3)

        await interaction.response.send_message(embeds=embeds)
    @app_commands.command(name="skillreference", description="Complete D&D 5e skill reference")
    async def skill_reference(self, interaction: discord.Interaction):
        """Complete skill reference organized by category."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: Physical and Mental Skills
        embed1 = discord.Embed(
            title="⚡ Quick Skill Reference",
            description="All D&D 5e skills organized by category",
            color=discord.Color.gold(),
        )
        embed1.add_field(
            name="💪 Physical Skills",
            value=(
                "**STR (raw):** Force, break, lift\n"
                "**Athletics:** Climb, jump, swim, grapple\n"
                "**Acrobatics:** Balance, tumble, escape"
            ),
            inline=False,
        )
        embed1.add_field(
            name="🧠 Mental Skills",
            value=(
                "**Perception:** Spot with senses\n"
                "**Investigation:** Search and deduce\n"
                "**Insight:** Read motives/emotions"
            ),
            inline=False,
        )
        embed1.add_field(
            name="🗣️ Social Skills",
            value=(
                "**Persuasion:** Honest influence\n"
                "**Deception:** Dishonest influence\n"
                "**Intimidation:** Influence through fear\n"
                "**Performance:** Entertain"
            ),
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: Knowledge and Specialized Skills
        embed2 = discord.Embed(
            title="⚡ Quick Skill Reference (cont.)",
            color=discord.Color.gold(),
        )
        embed2.add_field(
            name="📚 Knowledge Skills (recall info)",
            value=(
                "**Arcana:** Magic, planes\n"
                "**History:** Events, legends\n"
                "**Nature:** Terrain, beasts, plants\n"
                "**Religion:** Gods, undead, celestials"
            ),
            inline=False,
        )
        embed2.add_field(
            name="🔧 Specialized Skills",
            value=(
                "**Animal Handling:** Calm/control animals\n"
                "**Medicine:** Stabilize, diagnose\n"
                "**Survival:** Track, navigate, forage\n"
                "**Sleight of Hand:** Pickpocket, tricks"
            ),
            inline=False,
        )
        embed2.add_field(
            name="💡 Quick Tips",
            value=(
                "• Most physical challenges → Athletics or Acrobatics\n"
                "• Noticing things → Perception\n"
                "• Understanding things → Investigation\n"
                "• Social situations → Persuasion, Deception, or Intimidation\n"
                "• Recalling knowledge → Arcana, History, Nature, or Religion"
            ),
            inline=False,
        )
        embed2.set_footer(text="Use /skillconfusions for detailed comparisons")
        embeds.append(embed2)

        await interaction.response.send_message(embeds=embeds)
    @app_commands.command(name="protips", description="DM pro tips for skill checks")
    async def pro_tips(self, interaction: discord.Interaction):
        """DM best practices and pro tips."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="💡 Pro Tips for DMs",
            description="Best practices for running skill checks smoothly",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="✅ Group Checks",
            value=(
                "When the party works together, half or more must succeed. "
                "Use this for stealth, navigation, rowing, etc."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Advantage/Disadvantage",
            value=(
                "Better than numerical bonuses! Advantage/disadvantage is roughly equivalent to "
                "±5 on a d20, but feels more dramatic. Use it for circumstantial help/hindrance."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ 'Can I try?'",
            value=(
                "If one player fails, others can try IF they have a different approach. "
                "Don't let the whole party spam the same check with no variation."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Fail Forward",
            value=(
                "Failure doesn't mean nothing happens - it means complications arise. "
                "Instead of 'you fail to pick the lock' try 'you pick the lock, but it takes "
                "10 minutes and you hear footsteps approaching.'"
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Contest or DC?",
            value=(
                "If an NPC or creature actively opposes the action, use a contested check. "
                "If it's just difficult, set a DC. Don't make everything a contest."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Passive Perception",
            value=(
                "Use passive checks (10 + modifier) for things characters would notice without "
                "actively looking. This keeps the game flowing and maintains tension - "
                "they don't know if they passed or failed!"
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ Don't Over-Roll",
            value=(
                "Not everything needs a check. Save rolls for meaningful moments with real stakes. "
                "Trivial tasks and impossible tasks don't need dice."
            ),
            inline=False,
        )
        embed.set_footer(text="Use /skillcheatsheet for the full guide")

        await interaction.response.send_message(embed=embed)


async def setup(bot: Red):
    """Add the cog to the bot."""
    cog = ShadyCheatSheet(bot)
    await bot.add_cog(cog)
    @app_commands.command(name="masteries", description="D&D 5e weapon mastery properties (2024 rules)")
    async def masteries(self, interaction: discord.Interaction):
        """Display weapon mastery properties from 2024 rules."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True,
            )
            return

        embeds = []

        # Embed 1: Introduction and First 4 Masteries
        embed1 = discord.Embed(
            title="⚔️ Weapon Mastery Properties (2024)",
            description="Special properties that enhance weapons when you have proficiency mastery.",
            color=discord.Color.red(),
        )
        embed1.add_field(
            name="🪓 Cleave",
            value=(
                "**Weapons:** Greataxe, Halberd\n\n"
                "Hit multiple opponents with one swing! When you hit a creature with a Melee Weapon Attack, "
                "you can make another Melee Attack Roll against a second creature within 5ft of the first. "
                "On a hit, the second target takes weapon damage without Ability Modifier (unless negative). "
                "Perfect for crowd control!"
            ),
            inline=False,
        )
        embed1.add_field(
            name="✨ Graze",
            value=(
                "**Weapons:** Glaive, Greatsword\n\n"
                "Never waste a missed attack! When your weapon misses an attack, deal damage equal to your "
                "Ability Modifier used for the Attack Roll. Scales with your Ability Modifier increases."
            ),
            inline=False,
        )
        embed1.add_field(
            name="⚡ Nick",
            value=(
                "**Weapons:** Dagger, Light Hammer, Sickle, Scimitar\n\n"
                "Make an additional attack as part of your Attack Action when wielding light weapons in both hands. "
                "**Important:** This does NOT allow a third bonus action attack - it frees up your bonus action "
                "for spells or other tactics!"
            ),
            inline=False,
        )
        embed1.add_field(
            name="💨 Push",
            value=(
                "**Weapons:** Greatclub, Pike, Warhammer, Heavy Crossbow\n\n"
                "Push a Large or smaller creature up to 10 feet away in a straight line. Perfect for creating "
                "breathing room for ranged attacks or disengaging."
            ),
            inline=False,
        )
        embeds.append(embed1)

        # Embed 2: Remaining 4 Masteries
        embed2 = discord.Embed(
            title="⚔️ Weapon Mastery Properties (cont.)",
            color=discord.Color.red(),
        )
        embed2.add_field(
            name="🎯 Sap",
            value=(
                "**Weapons:** Mace, Spear, Flail, Longsword, Morningstar, War Pick\n\n"
                "Landing an attack inflicts disadvantage on the enemy's next Attack Roll before the start "
                "of your next turn. Excellent for characters who go early in initiative!"
            ),
            inline=False,
        )
        embed2.add_field(
            name="🐌 Slow",
            value=(
                "**Weapons:** Club, Javelin, Light Crossbow, Sling, Whip, Longbow, Musket\n\n"
                "Reduce a creature's Speed by 10 feet until the start of your next turn when you deal damage "
                "with this weapon. Buy time for ranged party members and keep enemies at bay!"
            ),
            inline=False,
        )
        embed2.add_field(
            name="⬇️ Topple",
            value=(
                "**Weapons:** Quarterstaff, Battleaxe, Lance, Maul, Trident\n\n"
                "Force a creature to make a Constitution saving throw or fall Prone on a successful weapon attack. "
                "Perfect for setting up advantage on your next attack!"
            ),
            inline=False,
        )
        embed2.add_field(
            name="🎪 Vex",
            value=(
                "**Weapons:** Handaxe, Dart, Shortbow, Rapier, Shortsword, Blowgun, Hand Crossbow, Pistol\n\n"
                "Gain advantage on your next attack roll against the same target after hitting with a Vex weapon. "
                "Great for chaining attacks and essential for sneak attack or burst damage builds!"
            ),
            inline=False,
        )
        embed2.set_footer(text="2024 Player's Handbook | Use /skillcheatsheet for skill check reference")
        embeds.append(embed2)

        await interaction.response.send_message(embeds=embeds)

