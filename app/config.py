"""
System Configuration Module using Pydantic Settings.
Includes Maintenance Mode, Staff Admin Password, & Social Media API keys.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Discord Configuration
    DISCORD_BOT_TOKEN: str = "placeholder_token"
    DISCORD_GUILD_ID: Optional[int] = None

    # AI Configuration (Google Gemini)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Social Media Automation Configuration (X / Twitter & BlueSky)
    ENABLE_SOCIAL_POSTING: bool = True
    X_API_KEY: Optional[str] = None
    X_API_SECRET: Optional[str] = None
    X_ACCESS_TOKEN: Optional[str] = None
    X_ACCESS_SECRET: Optional[str] = None
    BLUESKY_HANDLE: Optional[str] = None
    BLUESKY_PASSWORD: Optional[str] = None

    # System Maintenance & Staff Security
    MAINTENANCE_MODE: bool = False
    SITE_OFFLINE: bool = False
    STAFF_ADMIN_PASSWORD: str = "memorial_staff_2026"

    # Backend & Security Settings
    API_KEY: str = "memorial_secret_admin_key_2026"
    DATABASE_URL: str = "sqlite:///./memorials.db"

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

    @property
    def sqlalchemy_db_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


settings = Settings()
