import discord
import asyncio
import requests
from redbot.core import commands

API_URL = "https://pak.mulveycreations.com/api"
API_TOKEN = "jonlivesunderthedesk"

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

    @commands.command()
    async def ksearch(self, ctx, *, song: str):
        """
        Search for karaoke videos interactively.
        Usage: [p]ksearch <song title>
        """
        # Show typing in the channel while processing the search.
        async with ctx.typing():
            payload = {"song": song}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_TOKEN}"
            }
            try:
                response = requests.post(f"{API_URL}/search", json=payload, headers=headers)
                if response.status_code != 200:
                    err = response.json().get("error", "Unknown error")
                    await ctx.send(f"Error during search: {err}")
                    return

                data = response.json()
                results = data.get("results", [])
                if not results:
                    await ctx.send("No results found.")
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
                await ctx.send(f"An exception occurred during search: {e}")
                return

        # Send the results in DM.
        try:
            dm_channel = await ctx.author.create_dm()
            search_message = await dm_channel.send(embed=embed)
        except Exception as e:
            await ctx.send("Unable to send DM. Please check your privacy settings.")
            return

        # Add reactions for selection.
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i in range(len(results)):
            await search_message.add_reaction(emojis[i])

        def check(reaction, user):
            return (
                user == ctx.author and
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
            await ctx.send(f"An exception occurred during download: {e}")

async def setup(bot):
    await bot.add_cog(KaraokeDownloader(bot))
