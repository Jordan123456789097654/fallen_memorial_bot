"""
System Configuration Module using Pydantic Settings.
Includes Social Media API keys and Render storage path auto-detection.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_db_url() -> str:
    """Returns persistent Render path if /var/data exists, else local SQLite path."""
    if os.path.exists("/var/data") and os.access("/var/data", os.W_OK):
        return "sqlite:////var/data/memorials.db"
    return "sqlite:///./memorials.db"


class Settings(BaseSettings):
    # Discord Configuration
    DISCORD_BOT_TOKEN: str = "placeholder_token"
    DISCORD_GUILD_ID: Optional[int] = None

    # AI Configuration (Google Gemini)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Social Media Automation Configuration (X / Twitter & BlueSky)
    ENABLE_SOCIAL_POSTING: bool = True
    X_API_KEY: Optional[str] = None
    X_API_SECRET: Optional[str] = None
    X_ACCESS_TOKEN: Optional[str] = None
    X_ACCESS_SECRET: Optional[str] = None
    BLUESKY_HANDLE: Optional[str] = None
    BLUESKY_PASSWORD: Optional[str] = None

    # Backend & Security Settings
    API_KEY: str = "memorial_secret_admin_key_2026"
    DATABASE_URL: str = get_default_db_url()

    # System Defaults
    APPROVAL_MODE: str = "MANUAL"
    SCAN_INTERVAL_HOURS: int = 3
    LOG_LEVEL: str = "INFO"
    BIBLE_VERSES_PATH: str = "bible_verses.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
