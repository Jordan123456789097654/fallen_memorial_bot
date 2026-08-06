"""
Discord Channel Structure Management.
Creates required category and channels automatically on startup per server.
"""
import discord
from typing import Dict
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import ResponderCategory, GuildConfig
from app.utils.logger import logger

CHANNEL_MAP = {
    ResponderCategory.LAW_ENFORCEMENT: "fallen-law-enforcement",
    ResponderCategory.FIRE: "fallen-fire-service",
    ResponderCategory.EMS: "fallen-ems",
    ResponderCategory.RESCUE: "fallen-rescue",
    ResponderCategory.K9: "fallen-k9",
    ResponderCategory.DISPATCH: "fallen-dispatch",
    ResponderCategory.OTHER: "fallen-other-responders",
}

ARCHIVE_CHANNEL_NAME = "memorial-archive"
LOGS_CHANNEL_NAME = "bot-logs"


def get_or_create_guild_config(db: Session, guild: discord.Guild) -> GuildConfig:
    """Retrieves or initializes a GuildConfig record for a server."""
    config = db.query(GuildConfig).filter(GuildConfig.guild_id == str(guild.id)).first()
    if not config:
        config = GuildConfig(
            guild_id=str(guild.id),
            guild_name=guild.name,
            approval_mode="MANUAL",
            category_name="Memorials"
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


async def setup_memorial_channels(guild: discord.Guild) -> Dict[str, discord.TextChannel]:
    """
    Checks for the 'Memorials' category and required sub-channels on startup.
    Creates missing categories or text channels automatically.
    """
    db: Session = SessionLocal()
    try:
        guild_cfg = get_or_create_guild_config(db, guild)
        category_name = guild_cfg.category_name or "Memorials"

        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            logger.info(f"Creating category '{category_name}' in guild '{guild.name}' ({guild.id})...")
            category = await guild.create_category(category_name)

        existing_channels = {ch.name: ch for ch in category.text_channels}
        created_channels: Dict[str, discord.TextChannel] = {}

        target_channels = list(CHANNEL_MAP.values()) + [ARCHIVE_CHANNEL_NAME, LOGS_CHANNEL_NAME]

        for channel_name in target_channels:
            if channel_name in existing_channels:
                created_channels[channel_name] = existing_channels[channel_name]
            else:
                logger.info(f"Creating channel '#{channel_name}' under '{category_name}' in guild '{guild.name}'...")
                ch = await guild.create_text_channel(name=channel_name, category=category)
                created_channels[channel_name] = ch

        return created_channels

    except Exception as e:
        logger.error(f"Error establishing server channel structure in guild {guild.id}: {e}")
        return {}
    finally:
        db.close()


def get_target_channel_name(category: ResponderCategory) -> str:
    """Returns the channel name corresponding to a responder category."""
    return CHANNEL_MAP.get(category, "fallen-other-responders")
