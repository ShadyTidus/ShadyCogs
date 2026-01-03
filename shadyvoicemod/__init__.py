"""ShadyVoiceMod - Voice moderation cog for RedBot."""

from .shadyvoicemod import ShadyVoiceMod


async def setup(bot):
    """Load ShadyVoiceMod cog."""
    cog = ShadyVoiceMod(bot)
    await bot.add_cog(cog)
