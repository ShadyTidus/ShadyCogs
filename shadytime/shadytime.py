"""
ShadyTime - 7 Days to Die server time query
Queries the configured 7DTD server via Steam A2S protocol and reports
the current in-game day, hour, minute, and days until next blood moon.
"""

import discord
import logging
import socket
import struct
import time

from redbot.core import commands
from redbot.core.bot import Red
from discord import app_commands

log = logging.getLogger("red.shadycogs.shadytime")

# Server config
SERVER_IP = "gaming.unrealdj.nl"
SERVER_PORT = 26900
POST_CHANNEL_ID = 1472052288297107488

# Rate limit: seconds between uses per user (3600 = 1 hour)
RATE_LIMIT_SECONDS = 3600


def query_7dtd_time(ip: str, port: int, timeout: float = 5.0) -> dict:
    """
    Query a 7DTD server via Steam A2S_RULES and return parsed time info.
    Returns a dict with: day, hour, minute, players, max_players, server_name,
                         blood_moon_day, days_until_blood_moon
    Raises RuntimeError on failure.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    try:
        # Step 1: Send challenge request
        challenge_req = b'\xFF\xFF\xFF\xFFV\xFF\xFF\xFF\xFF'
        sock.sendto(challenge_req, (ip, port))
        data, _ = sock.recvfrom(4096)

        # Parse challenge number
        challenge = data[5:9] if len(data) >= 9 and data[4:5] == b'A' else b'\xFF\xFF\xFF\xFF'

        # Step 2: Send actual rules request with challenge
        rules_req = b'\xFF\xFF\xFF\xFFV' + challenge
        sock.sendto(rules_req, (ip, port))
        data, _ = sock.recvfrom(65535)

    except socket.timeout:
        raise RuntimeError("Server did not respond (timeout).")
    finally:
        sock.close()

    if len(data) < 7 or data[4:5] != b'E':
        raise RuntimeError("Unexpected response from server.")

    # Parse key-value rules
    num_rules = struct.unpack_from('<H', data, 5)[0]
    offset = 7
    rules = {}

    for _ in range(num_rules):
        end = data.index(b'\x00', offset)
        key = data[offset:end].decode('utf-8', errors='replace')
        offset = end + 1
        end = data.index(b'\x00', offset)
        val = data[offset:end].decode('utf-8', errors='replace')
        offset = end + 1
        rules[key] = val

    raw_time = rules.get('CurrentServerTime')
    if raw_time is None:
        raise RuntimeError("Server did not return CurrentServerTime.")

    # Time math
    current_time = int(raw_time)
    day = (current_time // 24000) + 1
    hour = (current_time % 24000) // 1000
    minute = (current_time % 1000) * 60 // 1000

    # Blood moon frequency from server rules (default 7 if not present)
    bm_freq = int(rules.get('BloodMoonFrequency', 7))

    # Days until next blood moon
    # Blood moons land on multiples of bm_freq (7, 14, 21...)
    day_in_cycle = day % bm_freq
    if day_in_cycle == 0:
        days_until = 0  # Tonight IS the blood moon
        next_bm_day = day
    else:
        days_until = bm_freq - day_in_cycle
        next_bm_day = day + days_until

    return {
        "day": day,
        "hour": hour,
        "minute": minute,
        "players": int(rules.get('CurrentPlayers', 0)),
        "max_players": int(rules.get('MaxPlayers', 0)),
        "server_name": rules.get('GameHost', '7 Days to Die'),
        "bm_freq": bm_freq,
        "next_bm_day": next_bm_day,
        "days_until_blood_moon": days_until,
    }


def build_time_embed(info: dict, requester: discord.User | discord.Member) -> discord.Embed:
    """Build the server time embed from query results."""

    # Blood moon field logic
    days_until = info["days_until_blood_moon"]
    if days_until == 0:
        bm_value = "🩸 **TONIGHT!** Survive the night!"
        bm_color = discord.Color.red()
    elif days_until == 1:
        bm_value = f"⚠️ **Tomorrow** (Day {info['next_bm_day']})"
        bm_color = discord.Color.orange()
    else:
        bm_value = f"**{days_until} days** (Day {info['next_bm_day']})"
        bm_color = discord.Color.dark_green()

    embed = discord.Embed(
        title="🧟 Parental Advisory — 7DTD Server Time",
        color=bm_color,
    )
    embed.add_field(
        name="📅 In-Game Day",
        value=f"**Day {info['day']}**",
        inline=True,
    )
    embed.add_field(
        name="🕐 In-Game Time",
        value=f"**{info['hour']:02d}:{info['minute']:02d}**",
        inline=True,
    )
    embed.add_field(
        name="👤 Players Online",
        value=f"**{info['players']} / {info['max_players']}**",
        inline=True,
    )
    embed.add_field(
        name="🩸 Next Blood Moon",
        value=bm_value,
        inline=False,
    )
    embed.set_footer(text=f"Requested by {requester.display_name} • {SERVER_IP}:{SERVER_PORT}")
    return embed


class ShadyTime(commands.Cog):
    """7 Days to Die server time query."""

    __version__ = "1.0.0"
    __author__ = "ShadyTidus"

    def __init__(self, bot: Red):
        self.bot = bot
        # user_id -> timestamp of last use
        self._rate_limits: dict[int, float] = {}

    def _check_rate_limit(self, user_id: int) -> float | None:
        """Returns None if allowed, or seconds remaining on cooldown."""
        last_used = self._rate_limits.get(user_id)
        if last_used is None:
            return None
        remaining = RATE_LIMIT_SECONDS - (time.time() - last_used)
        return remaining if remaining > 0 else None

    def _record_use(self, user_id: int):
        self._rate_limits[user_id] = time.time()

    @app_commands.command(name="zedtime", description="Check the current in-game time on the PA 7DTD server")
    async def zed_time(self, interaction: discord.Interaction):
        """Query the 7DTD server and report in-game day, time, and blood moon countdown."""

        # Rate limit check
        remaining = self._check_rate_limit(interaction.user.id)
        if remaining is not None:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            await interaction.response.send_message(
                f"⏳ You can check the server time again in **{mins}m {secs}s**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            info = query_7dtd_time(SERVER_IP, SERVER_PORT)
        except Exception as e:
            log.error(f"Failed to query 7DTD server: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Server Query Failed",
                    description=f"Could not reach the server right now.\n`{e}`",
                    color=discord.Color.red(),
                )
            )
            return

        self._record_use(interaction.user.id)

        embed = build_time_embed(info, interaction.user)

        # Post to the designated channel
        channel = self.bot.get_channel(POST_CHANNEL_ID)
        if channel is not None and channel.id != interaction.channel_id:
            try:
                await channel.send(embed=embed)
                await interaction.followup.send(
                    f"✅ Server time posted in <#{POST_CHANNEL_ID}>!",
                    ephemeral=True,
                )
            except discord.Forbidden:
                log.warning(f"No permission to post in channel {POST_CHANNEL_ID}, posting in-place.")
                await interaction.followup.send(embed=embed)
        else:
            # Already in the right channel, or channel not found
            await interaction.followup.send(embed=embed)


async def setup(bot: Red):
    """Add the cog to the bot."""
    cog = ShadyTime(bot)
    await bot.add_cog(cog)
