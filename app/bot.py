"""
Discord Bot Client Module using discord.py 2.x.
"""
import discord
from discord.ext import commands
from app.config import settings
from app.discord.commands import register_slash_commands
from app.discord.channels import setup_memorial_channels
from app.utils.logger import logger


class MemorialBot(commands.Bot):
    """Custom discord.py Bot for Memorial Intelligence Management."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        """Called automatically when the bot is initializing."""
        register_slash_commands(self)

        try:
            if settings.DISCORD_GUILD_ID:
                guild = discord.Object(id=settings.DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} slash commands to Guild ID: {settings.DISCORD_GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} global slash commands.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        """Triggered when Discord bot connects and is ready."""
        logger.info(f"Logged in as Discord Bot: {self.user} (ID: {self.user.id})")
        logger.info("Verifying server category and channel structure across guilds...")

        for guild in self.guilds:
            channels = await setup_memorial_channels(guild)
            logger.info(f"Guild '{guild.name}' (ID: {guild.id}) channel setup complete ({len(channels)} channels verified).")


bot = MemorialBot()
