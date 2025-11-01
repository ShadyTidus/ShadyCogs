import discord
import asyncio
import requests
from redbot.core import commands, Config
from discord import app_commands

API_URL = "https://pak.mulveycreations.com/api"

EMOJI_TO_INDEX = {
    "1️⃣": 0,
    "2️⃣": 1,
    "3️⃣": 2,
    "4️⃣": 3,
    "5️⃣": 4
}

class KaraokeDownloader(commands.Cog):
    """Cog to search for karaoke videos interactively via DM."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "api_token": None
        }
        self.config.register_global(**default_global)

    @commands.is_owner()
    @commands.command()
    async def setkaraoketoken(self, ctx, token: str):
        """
        Set the API token for the karaoke service. (Owner only)
        Usage: [p]setkaraoketoken <token>
        """
        await self.config.api_token.set(token)
        await ctx.send("API token has been set successfully.", delete_after=5)
        try:
            await ctx.message.delete()
        except:
            pass

    @app_commands.command(name="ksearch", description="Search for karaoke videos")
    @app_commands.describe(song="The song title to search for")
    async def ksearch_slash(self, interaction: discord.Interaction, song: str):
        """
        Search for karaoke videos interactively via DM.
        """
        api_token = await self.config.api_token()
        if not api_token:
            await interaction.response.send_message(
                "The karaoke API token has not been configured. Please contact the bot owner.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        payload = {"song": song}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}"
        }
        try:
            response = requests.post(f"{API_URL}/search", json=payload, headers=headers)
            if response.status_code != 200:
                err = response.json().get("error", "Unknown error")
                await interaction.followup.send(f"Error during search: {err}", ephemeral=True)
                return

            data = response.json()
            results = data.get("results", [])
            if not results:
                await interaction.followup.send("No results found.", ephemeral=True)
                return

            # Limit to 5 results.
            results = results[:5]
            embed = discord.Embed(
                title="Karaoke Search Results",
                description="React with the corresponding number to download the video.",
                color=discord.Color.blue()
            )
            if results[0].get("thumbnail"):
                embed.set_thumbnail(url=results[0].get("thumbnail"))
            for idx, video in enumerate(results, start=1):
                title = video.get("title", "Unknown Title")
                thumbnail = video.get("thumbnail", "No thumbnail")
                embed.add_field(name=f"{idx}. {title}", value=f"[Thumbnail]({thumbnail})", inline=False)
        except Exception as e:
            await interaction.followup.send(f"An exception occurred during search: {e}", ephemeral=True)
            return

        # Send the results in DM.
        try:
            dm_channel = await interaction.user.create_dm()
            search_message = await dm_channel.send(embed=embed)
            await interaction.followup.send("Check your DMs for the search results!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("Unable to send DM. Please check your privacy settings.", ephemeral=True)
            return

        # Add reactions for selection.
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i in range(len(results)):
            await search_message.add_reaction(emojis[i])

        def check(reaction, user):
            return (
                user == interaction.user and
                reaction.message.id == search_message.id and
                str(reaction.emoji) in EMOJI_TO_INDEX
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await dm_channel.send("Timed out. Please try the search command again.")
            return

        selected_index = EMOJI_TO_INDEX.get(str(reaction.emoji))
        if selected_index is None or selected_index >= len(results):
            await dm_channel.send("Invalid selection. Please try again.")
            return

        selected_video = results[selected_index]
        video_url = selected_video.get("url")
        if not video_url:
            await dm_channel.send("Selected video has no URL. Please try another.")
            return

        # Indicate that the download process is starting.
        async with dm_channel.typing():
            await dm_channel.send("Downloading... Please wait.")

        # Trigger the download.
        try:
            payload_download = {"video_url": video_url}
            download_response = requests.post(f"{API_URL}/download", json=payload_download, headers=headers)
            if download_response.status_code != 200:
                err = download_response.json().get("error", "Unknown error")
                await dm_channel.send(f"Error during download: {err}")
                return

            message = download_response.json().get("message", "Download triggered successfully.")
            await dm_channel.send(message)
        except Exception as e:
            await dm_channel.send(f"An exception occurred during download: {e}")

async def setup(bot):
    cog = KaraokeDownloader(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.ksearch_slash)
