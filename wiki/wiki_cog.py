import discord
import string
import re
import traceback
import json
import os
from pathlib import Path
from discord.utils import utcnow
from datetime import datetime, timedelta
from redbot.core import commands, Config
from discord import app_commands
from typing import Optional
import logging

log = logging.getLogger("red.Wiki")

class FafoView(discord.ui.View):
    def __init__(self, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.message = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except Exception as e:
                log.warning(f"Failed to delete FAFO message on timeout: {e}")

    @discord.ui.button(label="FAFO", style=discord.ButtonStyle.danger)
    async def fafo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            duration = timedelta(minutes=5)
            until_time = utcnow() + duration
            member = interaction.guild.get_member(interaction.user.id)

            if member is None:
                await interaction.followup.send("Member not found.", ephemeral=True)
                return

            await member.timeout(until_time, reason="FAFO button clicked.")
            await interaction.followup.send("You have been timed out for 5 minutes.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to timeout you. Please check my role position and permissions.",
                ephemeral=True
            )
        except discord.HTTPException as http_err:
            log.exception("HTTP error during FAFO timeout.")
            await interaction.followup.send(f"An error occurred: {http_err}", ephemeral=True)
        except Exception as e:
            log.exception("Unexpected error occurred in FAFO button.")
            await interaction.followup.send("An unexpected error occurred while processing FAFO.", ephemeral=True)

class Wiki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_dir = Path(__file__).parent / "config"

        # Load all configuration from JSON files
        self.load_configs()

        # Use Discord's internal format for the Channels & Roles link.
        self.channels_and_roles_link = "<id:customize>"

    def load_configs(self):
        """Load all configuration from JSON files"""
        try:
            # Load authorized roles
            with open(self.config_dir / "roles.json", "r", encoding="utf-8") as f:
                roles_data = json.load(f)
                self.allowed_roles = roles_data.get("authorized_roles", [])

            # Load game aliases
            with open(self.config_dir / "games.json", "r", encoding="utf-8") as f:
                games_data = json.load(f)
                self.alias_to_role = games_data.get("alias_to_role", {})

            # Load channel mappings
            with open(self.config_dir / "channels.json", "r", encoding="utf-8") as f:
                channels_data = json.load(f)
                self.role_name_to_channel_id = channels_data.get("role_to_channel", {})

            # Load command configurations
            with open(self.config_dir / "commands.json", "r", encoding="utf-8") as f:
                self.commands_config = json.load(f)

            # Load rules
            with open(self.config_dir / "rules.json", "r", encoding="utf-8") as f:
                rules_data = json.load(f)
                self.rules = rules_data.get("rules", {})

            log.info("Wiki configs loaded successfully")
        except Exception as e:
            log.error(f"Error loading wiki configs: {e}")
            # Set defaults if loading fails
            self.allowed_roles = []
            self.alias_to_role = {}
            self.role_name_to_channel_id = {}
            self.commands_config = {}
            self.rules = {}

    def is_authorized(self, ctx):
        """
        Return True if the invoking user has one of the allowed roles.
        """
        return any(role.name in self.allowed_roles for role in ctx.author.roles)

    def is_authorized_interaction(self, interaction: discord.Interaction):
        """
        Return True if the invoking user has one of the allowed roles (for slash commands).
        """
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(role.name in self.allowed_roles for role in interaction.user.roles)

    async def delete_and_check(self, ctx):
        """
        Delete the invoking message and return True if the user is authorized.
        """
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        if not self.is_authorized(ctx):
            return False
        return True

    async def send_reply(self, ctx, *args, **kwargs):
        """
        Helper to reply to the referenced message if available,
        otherwise sends a new message in the current channel.
        Returns the sent message.
        """
        if ctx.message.reference:
            try:
                original_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                msg = await original_message.reply(*args, **kwargs)
                return msg
            except Exception:
                pass
        msg = await ctx.send(*args, **kwargs)
        return msg

    @commands.command(name="lfg")
    async def lfg(self, ctx):
        """
        📌 (Beta) Reply to a message to detect game interest and direct users to the correct LFG channel.
        If a game role is detected, the bot will tag the role and provide an LFG guide.
        If used in the wrong channel, the user is informed and directed to grab the game-specific role from <id:customize>.
        """
        if not await self.delete_and_check(ctx):
            return

        lfg_cfg = self.commands_config.get("lfg", {})

        role_mention = None
        mention_text = ""
        extra_text = ""
        replied_user = ctx.author  # default fallback
        reply_target = ctx

        # Attempt to get role info from the referenced message.
        if ctx.message.reference:
            try:
                replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                content = replied.content.lower().replace(" ", "")
                replied_user = replied.author
                reply_target = replied

                # First pass: check each word after stripping punctuation.
                for word in content.split():
                    cleaned = word.strip(string.punctuation)
                    if cleaned in self.alias_to_role:
                        role_mention = self.alias_to_role[cleaned]
                        break
                # Second pass: regex search for any alias as a whole word.
                if not role_mention:
                    for alias, role_name in self.alias_to_role.items():
                        pattern = r'\b' + re.escape(alias) + r'\b'
                        if re.search(pattern, content):
                            role_mention = role_name
                            break
            except Exception as e:
                log.error(f"Error fetching referenced message: {e}")

        if role_mention is None:
            no_game_msg = lfg_cfg.get("no_game_detected", "No game alias detected in the referenced message.")
            await self.send_reply(ctx, no_game_msg)
            return

        # Get the role object.
        role_obj = discord.utils.get(ctx.guild.roles, name=role_mention)
        if role_obj:
            mention_text = f"{role_obj.mention} {replied_user.mention}\n"
            expected_channel_id = self.role_name_to_channel_id.get(role_obj.name)
            lfg_guide_url = lfg_cfg.get("guide_url", "https://wiki.parentsthatga.me/discord/lfg")
            guide_emoji = lfg_cfg.get("emoji", "📌")

            # CASE 1: Correct channel
            if expected_channel_id and ctx.channel.id == expected_channel_id:
                correct_msg = lfg_cfg.get("correct_channel_text", "Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!")
                output = f"{mention_text}{correct_msg}\n{guide_emoji} [LFG Guide]({lfg_guide_url})"
                await reply_target.reply(output)

            # CASE 2: Wrong channel
            elif expected_channel_id:
                target_channel = ctx.guild.get_channel(expected_channel_id)
                wrong_msg = lfg_cfg.get("wrong_channel_text", "Detected game role: **{role}**. This is not the correct channel, we have a dedicated channel here: {channel}.\nPlease grab the game-specific role from {customize_link}.")
                wrong_msg = wrong_msg.format(
                    role=role_obj.name,
                    channel=target_channel.mention if target_channel else 'Unknown',
                    customize_link=self.channels_and_roles_link
                )
                await reply_target.reply(wrong_msg)

                # Give role if missing
                if role_obj not in replied_user.roles:
                    try:
                        await replied_user.add_roles(role_obj, reason="User redirected by LFG command")
                    except Exception as e:
                        log.error(f"Failed to add role to user: {e}")

                # Also send LFG ping in the right channel
                if target_channel:
                    correct_msg = lfg_cfg.get("correct_channel_text", "Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!")
                    lfg_text = f"{role_obj.mention} {replied_user.mention}\n{correct_msg}\n{guide_emoji} [LFG Guide]({lfg_guide_url})"
                    try:
                        await target_channel.send(lfg_text)
                    except Exception as e:
                        log.error(f"Failed to send LFG in proper channel: {e}")
            else:
                # CASE 3: No mapped channel
                no_channel_msg = lfg_cfg.get("no_channel_text", "Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!")
                output = f"{mention_text}{no_channel_msg}\n{guide_emoji} [LFG Guide]({lfg_guide_url})"
                await reply_target.reply(output)
        else:
            role_not_found_msg = lfg_cfg.get("role_not_found", "Could not find role: {role}.").format(role=role_mention)
            await self.send_reply(ctx, role_not_found_msg)

    @commands.command()
    async def host(self, ctx):
        """
        📣 Reply to a message and the bot will link to the hosting/advertising guidelines in PA.
        """
        if not await self.delete_and_check(ctx):
            return
        host_cfg = self.commands_config.get("host", {})
        if not host_cfg.get("enabled", True):
            return
        text = host_cfg.get("text", "Check out our hosting guidelines:")
        url = host_cfg.get("url", "https://wiki.parentsthatga.me/servers/hosting")
        url_text = host_cfg.get("url_text", "Host/Advertise")
        emoji = host_cfg.get("emoji", "📌")
        output = f"{text}\n{emoji} [{url_text}]({url})"
        await self.send_reply(ctx, output)

    @commands.command()
    async def biweekly(self, ctx):
        """
        🧙 Reply to a message and this will post info about our biweekly D&D sessions and how to get started.
        """
        if not await self.delete_and_check(ctx):
            return
        biweekly_cfg = self.commands_config.get("biweekly", {})
        if not biweekly_cfg.get("enabled", True):
            return
        text = biweekly_cfg.get("text", "Check out our D&D info:")
        url = biweekly_cfg.get("url", "https://wiki.parentsthatga.me/discord/dnd")
        url_text = biweekly_cfg.get("url_text", "D&D Guide")
        emoji = biweekly_cfg.get("emoji", "🧙")
        output = f"{text}\n{emoji} [{url_text}]({url})"
        await self.send_reply(ctx, output)

    @commands.command()
    async def rule(self, ctx, rule_number: int):
        """
        📘 Reply to a message and show a quick summary of the selected rule with a link to the full rules page.
        Use: `-rule 3`
        """
        if not await self.delete_and_check(ctx):
            return
        rule_cfg = self.commands_config.get("rule", {})
        rule_data = self.rules.get(str(rule_number))
        if rule_data:
            rules_url = rule_cfg.get("rules_url", "https://wiki.parentsthatga.me/rules")
            embed_title = rule_cfg.get("embed_title", "Full Rules")
            embed = discord.Embed(
                title=embed_title,
                url=rules_url,
                description=f"**{rule_data['title']}**\n{rule_data['text']}",
                color=discord.Color.orange()
            )
            await self.send_reply(ctx, embed=embed)
        else:
            invalid_msg = rule_cfg.get("invalid_rule_text", "Invalid rule number. Use 1–10.")
            await self.send_reply(ctx, invalid_msg)

    @commands.command()
    async def wow(self, ctx):
        """
        🐉 Reply to a message and this will link to the World of Warcraft wiki section for PA players.
        """
        if not await self.delete_and_check(ctx):
            return
        wow_cfg = self.commands_config.get("wow", {})
        if not wow_cfg.get("enabled", True):
            return
        text = wow_cfg.get("text", "Check out the WoW guide:")
        url = wow_cfg.get("url", "https://wiki.parentsthatga.me/WoW")
        emoji = wow_cfg.get("emoji", "🐉")
        output = f"{text}\n{url}"
        await self.send_reply(ctx, output)

    @commands.command()
    async def fafo(self, ctx):
        """
        ⚠️ Posts a warning message and a 'FAFO' button.
        Users who click it are timed out for 5 minutes.
        """
        if not await self.delete_and_check(ctx):
            return
        warning_text = (
            "__**⚠️ WARNING:**__\n"
            "If you cannot abide by the rules from previous responses,\n"
            "**Click Below To FAFO**"
        )
        view = FafoView()
        msg = await self.send_reply(ctx, warning_text, view=view)
        view.message = msg

    @commands.command()
    async def hosted(self, ctx):
        """
        🖥️ Shows the current list of PA-hosted servers via the wiki.
        """
        if not await self.delete_and_check(ctx):
            return
        hosted_cfg = self.commands_config.get("hosted", {})
        if not hosted_cfg.get("enabled", True):
            return
        text = hosted_cfg.get("text", "Check out our hosted servers:")
        url = hosted_cfg.get("url", "https://wiki.parentsthatga.me/en/servers")
        url_text = hosted_cfg.get("url_text", "Server List")
        emoji = hosted_cfg.get("emoji", "🖥️")
        output = f"{text}\n{emoji} [{url_text}]({url})"
        await self.send_reply(ctx, output)

    @commands.is_owner()
    @commands.command()
    async def wikireload(self, ctx):
        """Reload all wiki configuration files"""
        try:
            self.load_configs()
            await ctx.send("✅ Wiki configurations reloaded successfully!")
        except Exception as e:
            await ctx.send(f"❌ Error reloading configs: {e}")
            log.error(f"Error reloading wiki configs: {e}")

    # Slash Commands
    @app_commands.command(name="host", description="Link to hosting/advertising guidelines")
    async def host_slash(self, interaction: discord.Interaction):
        """Link to the hosting/advertising guidelines in PA."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        host_cfg = self.commands_config.get("host", {})
        if not host_cfg.get("enabled", True):
            await interaction.response.send_message("This command is currently disabled.", ephemeral=True)
            return
        text = host_cfg.get("text", "Check out our hosting guidelines:")
        url = host_cfg.get("url", "https://wiki.parentsthatga.me/servers/hosting")
        url_text = host_cfg.get("url_text", "Host/Advertise")
        emoji = host_cfg.get("emoji", "📌")
        output = f"{text}\n{emoji} [{url_text}]({url})"
        await interaction.response.send_message(output)

    @app_commands.command(name="biweekly", description="Info about biweekly D&D sessions")
    async def biweekly_slash(self, interaction: discord.Interaction):
        """Post info about our biweekly D&D sessions and how to get started."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        biweekly_cfg = self.commands_config.get("biweekly", {})
        if not biweekly_cfg.get("enabled", True):
            await interaction.response.send_message("This command is currently disabled.", ephemeral=True)
            return
        text = biweekly_cfg.get("text", "Check out our D&D info:")
        url = biweekly_cfg.get("url", "https://wiki.parentsthatga.me/discord/dnd")
        url_text = biweekly_cfg.get("url_text", "D&D Guide")
        emoji = biweekly_cfg.get("emoji", "🧙")
        output = f"{text}\n{emoji} [{url_text}]({url})"
        await interaction.response.send_message(output)

    @app_commands.command(name="rule", description="Show a specific server rule")
    @app_commands.describe(rule_number="The rule number (1-10)")
    async def rule_slash(self, interaction: discord.Interaction, rule_number: int):
        """Show a quick summary of the selected rule with a link to the full rules page."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        rule_cfg = self.commands_config.get("rule", {})
        rule_data = self.rules.get(str(rule_number))
        if rule_data:
            rules_url = rule_cfg.get("rules_url", "https://wiki.parentsthatga.me/rules")
            embed_title = rule_cfg.get("embed_title", "Full Rules")
            embed = discord.Embed(
                title=embed_title,
                url=rules_url,
                description=f"**{rule_data['title']}**\n{rule_data['text']}",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
        else:
            invalid_msg = rule_cfg.get("invalid_rule_text", "Invalid rule number. Use 1–10.")
            await interaction.response.send_message(invalid_msg, ephemeral=True)

    @app_commands.command(name="wow", description="Link to World of Warcraft wiki section")
    async def wow_slash(self, interaction: discord.Interaction):
        """Link to the World of Warcraft wiki section for PA players."""
        if not self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        wow_cfg = self.commands_config.get("wow", {})
        if not wow_cfg.get("enabled", True):
            await interaction.response.send_message("This command is currently disabled.", ephemeral=True)
            return
        text = wow_cfg.get("text", "Check out the WoW guide:")
        url = wow_cfg.get("url", "https://wiki.parentsthatga.me/WoW")
        output = f"{text}\n{url}"
        await interaction.response.send_message(output)

    @app_commands.command(name="fafo", description="Post a warning message with FAFO button")
    async def fafo_slash(self, interaction: discord.Interaction):
        """Posts a warning message and a 'FAFO' button. Users who click it are timed out for 5 minutes."""
        if not await self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        warning_text = (
            "__**⚠️ WARNING:**__\n"
            "If you cannot abide by the rules from previous responses,\n"
            "**Click Below To FAFO**"
        )
        view = FafoView()
        await interaction.response.send_message(warning_text, view=view)
        msg = await interaction.original_response()
        view.message = msg

    @app_commands.command(name="hosted", description="Show list of PA-hosted servers")
    async def hosted_slash(self, interaction: discord.Interaction):
        """Shows the current list of PA-hosted servers via the wiki."""
        if not await self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        hosted_url = await self.config.guild(interaction.guild).hosted_url()
        output = (
            "Want to see which servers PA is currently hosting?\n"
            f"🖥️ [Check the Server List]({hosted_url})"
        )
        await interaction.response.send_message(output)

    @app_commands.command(name="lfg", description="Detect game interest and direct to correct LFG channel")
    @app_commands.describe(
        user="The user looking for a group",
        game="The game they want to play"
    )
    async def lfg_slash(self, interaction: discord.Interaction, user: discord.Member, game: str):
        """Direct users to the correct LFG channel based on game interest."""
        if not await self.is_authorized_interaction(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer()

        alias_to_role = await self.config.guild(interaction.guild).alias_to_role()
        role_name_to_channel_id = await self.config.guild(interaction.guild).role_name_to_channel_id()
        lfg_guide_url = await self.config.guild(interaction.guild).lfg_guide_url()

        role_mention = None
        content = game.lower().replace(" ", "")

        # First pass: check each word after stripping punctuation.
        for word in content.split():
            cleaned = word.strip(string.punctuation)
            if cleaned in alias_to_role:
                role_mention = alias_to_role[cleaned]
                break

        # Second pass: regex search for any alias as a whole word.
        if not role_mention:
            for alias, role_name in alias_to_role.items():
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, content):
                    role_mention = role_name
                    break

        if role_mention is None:
            await interaction.followup.send(f"No game alias detected for '{game}'.", ephemeral=True)
            return

        # Get the role object.
        role_obj = discord.utils.get(interaction.guild.roles, name=role_mention)
        if not role_obj:
            await interaction.followup.send(f"Could not find role: {role_mention}.", ephemeral=True)
            return

        mention_text = f"{role_obj.mention} {user.mention}\n"
        expected_channel_id = role_name_to_channel_id.get(role_obj.name)

        # CASE 1: Correct channel
        if expected_channel_id and interaction.channel_id == expected_channel_id:
            output = (
                f"{mention_text}Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!\n"
                f"📌 [LFG Guide]({lfg_guide_url})"
            )
            await interaction.followup.send(output)

        # CASE 2: Wrong channel
        elif expected_channel_id:
            target_channel = interaction.guild.get_channel(expected_channel_id)
            extra_text = (
                f"Detected game role: **{role_obj.name}**. This is not the correct channel, "
                f"we have a dedicated channel here: {target_channel.mention if target_channel else 'Unknown'}.\n"
                f"Please grab the game-specific role from {self.channels_and_roles_link}."
            )
            await interaction.followup.send(extra_text)

            # Give role if missing
            if role_obj not in user.roles:
                try:
                    await user.add_roles(role_obj, reason="User redirected by LFG command")
                except Exception as e:
                    log.error(f"Failed to add role to user: {e}")

            # Also send LFG ping in the right channel
            if target_channel:
                lfg_text = (
                    f"{role_obj.mention} {user.mention}\n"
                    "Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!\n"
                    f"📌 [LFG Guide]({lfg_guide_url})"
                )
                try:
                    await target_channel.send(lfg_text)
                except Exception as e:
                    log.error(f"Failed to send LFG in proper channel: {e}")
        else:
            # CASE 3: No mapped channel
            output = (
                f"{mention_text}Looking for a group? Make sure to tag the game you're playing and check out the LFG channels!\n"
                f"📌 [LFG Guide]({lfg_guide_url})"
            )
            await interaction.followup.send(output)

async def setup(bot):
    cog = Wiki(bot)
    await bot.add_cog(cog)
    # Register slash commands
    bot.tree.add_command(cog.host_slash)
    bot.tree.add_command(cog.biweekly_slash)
    bot.tree.add_command(cog.rule_slash)
    bot.tree.add_command(cog.wow_slash)
    bot.tree.add_command(cog.fafo_slash)
    bot.tree.add_command(cog.hosted_slash)
    bot.tree.add_command(cog.lfg_slash)
