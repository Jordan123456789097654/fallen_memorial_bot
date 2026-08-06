"""
Automated News Monitoring, Scraper Module, & EOW Anniversary Scheduler.
Includes component button attachments for #bot-logs alerts.
"""
import json
import random
import os
import aiohttp
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus, ResponderCategory, GuildConfig
from app.ai import get_ai_provider
from app.discord.embeds import create_memorial_embed, create_pending_approval_embed, create_anniversary_embed
from app.discord.channels import get_target_channel_name, ARCHIVE_CHANNEL_NAME, LOGS_CHANNEL_NAME, get_or_create_guild_config
from app.discord.views import PendingReviewView
from app.utils.logger import logger

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=fallen+police+officer+end+of+watch&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=firefighter+killed+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=paramedic+emt+died+line+of+duty&hl=en-US&gl=US&ceid=US:en",
]


def load_bible_verses() -> List[Dict[str, str]]:
    """Loads scripture verses from local JSON file."""
    path = settings.BIBLE_VERSES_PATH
    if not os.path.exists(path):
        return [{
            "reference": "John 15:13",
            "text": "Greater love has no one than this: to lay down one's life for one's friends."
        }]
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading scripture file {path}: {e}")
        return [{
            "reference": "John 15:13",
            "text": "Greater love has no one than this: to lay down one's life for one's friends."
        }]


async def fetch_article_text(url: str) -> str:
    """Fetches article HTML and extracts body paragraph text."""
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    paragraphs = [p.get_text().strip() for p in soup.find_all("p")]
                    return "\n".join(paragraphs[:10])
    except Exception as e:
        logger.warning(f"Could not fetch full text from {url}: {e}")
    return ""


async def scan_news_sources(bot=None) -> Dict[str, Any]:
    """
    Main scanner function. Fetches news from feeds, parses with AI,
    prevents duplicate entries, and manages multi-guild approval flows.
    """
    logger.info("Starting automated news source scan...")
    ai_provider = get_ai_provider()
    verses = load_bible_verses()
    db: Session = SessionLocal()

    new_records_count = 0
    scanned_count = 0

    try:
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:5]:
                    scanned_count += 1
                    article_title = getattr(entry, "title", "No Title")
                    article_url = getattr(entry, "link", "")

                    if not article_url:
                        continue

                    existing = db.query(ResponderRecord).filter(ResponderRecord.article_url == article_url).first()
                    if existing:
                        continue

                    full_text = await fetch_article_text(article_url)
                    summary_text = getattr(entry, "summary", full_text)

                    extracted = await ai_provider.extract_info(
                        raw_text=full_text or summary_text,
                        article_title=article_title
                    )

                    if not extracted.get("is_fallen_responder", False):
                        continue

                    selected_verse = random.choice(verses)
                    memorial_text = await ai_provider.generate_memorial(extracted, selected_verse)

                    cat_str = extracted.get("category", "OTHER").upper()
                    try:
                        category_enum = ResponderCategory[cat_str]
                    except KeyError:
                        category_enum = ResponderCategory.OTHER

                    domain = article_url.split("/")[2] if "//" in article_url else ""

                    record = ResponderRecord(
                        name=extracted.get("name", "Unknown Hero"),
                        agency=extracted.get("agency", "Unknown Agency"),
                        category=category_enum,
                        date_of_incident=extracted.get("date_of_incident"),
                        date_of_death=extracted.get("date_of_death"),
                        summary=extracted.get("summary"),
                        k9_handler_name=extracted.get("k9_handler_name"),
                        k9_breed=extracted.get("k9_breed"),
                        service_years=extracted.get("service_years"),
                        unit_badge=extracted.get("unit_badge"),
                        article_title=article_title,
                        article_url=article_url,
                        source_domain=domain,
                        bible_verse=selected_verse.get("text"),
                        bible_reference=selected_verse.get("reference"),
                        ai_memorial_text=memorial_text,
                        status=ApprovalStatus.PENDING
                    )

                    db.add(record)
                    db.commit()
                    db.refresh(record)

                    new_records_count += 1
                    logger.info(f"Created Memorial Record ID #{record.id} for {record.name} ({record.agency})")

                    if bot:
                        await broadcast_new_memorial(bot, record)

            except Exception as e:
                logger.error(f"Error scanning feed {feed_url}: {e}")

        logger.info(f"Scan complete. Examined {scanned_count} articles, added {new_records_count} new memorial drafts.")
        return {"scanned": scanned_count, "new_records": new_records_count}

    finally:
        db.close()


async def broadcast_new_memorial(bot, record: ResponderRecord):
    """Broadcasts new memorial records across connected guilds."""
    db: Session = SessionLocal()
    try:
        for guild in bot.guilds:
            config = get_or_create_guild_config(db, guild)

            if not config.is_enabled:
                continue

            if config.approval_mode == "AUTO":
                await post_approved_memorial_to_guild(guild, record, config)
            else:
                await notify_pending_approval_to_guild(guild, record, config)

    except Exception as e:
        logger.error(f"Error broadcasting memorial #{record.id}: {e}")
    finally:
        db.close()


async def post_approved_memorial(bot, record: ResponderRecord):
    """Broadcasters approved memorial across all guilds."""
    db: Session = SessionLocal()
    try:
        for guild in bot.guilds:
            config = get_or_create_guild_config(db, guild)
            await post_approved_memorial_to_guild(guild, record, config)
    finally:
        db.close()


async def post_approved_memorial_to_guild(guild, record: ResponderRecord, config: GuildConfig):
    """Posts memorial embed to a specific guild."""
    try:
        category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
        target_channel_name = get_target_channel_name(category_enum)

        embed = create_memorial_embed(record, custom_header=config.custom_header)
        role_ping = f"<@&{config.alert_role_id}> " if config.alert_role_id else ""

        channel = None
        archive_channel = None

        for ch in guild.text_channels:
            if ch.name == target_channel_name:
                channel = ch
            elif ch.name == ARCHIVE_CHANNEL_NAME:
                archive_channel = ch

        if channel:
            await channel.send(content=role_ping if role_ping else None, embed=embed)

        if archive_channel:
            await archive_channel.send(embed=embed)

    except Exception as e:
        logger.error(f"Failed to post memorial #{record.id} to guild '{guild.name}': {e}")


async def notify_pending_approval_to_guild(guild, record: ResponderRecord, config: GuildConfig):
    """Sends pending review alert with interactive buttons to #bot-logs."""
    try:
        embed = create_pending_approval_embed(record)
        view = PendingReviewView(record_id=record.id)
        role_ping = f"<@&{config.alert_role_id}> " if config.alert_role_id else ""

        logs_ch = None
        for ch in guild.text_channels:
            if ch.name == LOGS_CHANNEL_NAME:
                logs_ch = ch
                break

        if logs_ch:
            await logs_ch.send(content=f"{role_ping}New pending memorial draft requires approval:", embed=embed, view=view)

    except Exception as e:
        logger.error(f"Failed to send pending approval alert to guild '{guild.name}': {e}")


async def check_eow_anniversaries(bot=None):
    """
    Daily scheduler task checking database for End of Watch anniversaries matching today.
    Posts anniversary tributes ("1 Year Ago Today", "5 Years Ago Today").
    """
    if not bot or not bot.is_ready():
        return

    today = datetime.utcnow()
    db: Session = SessionLocal()

    try:
        approved_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).all()

        for record in approved_records:
            if not record.date_of_death:
                continue

            # Try parsing date formats (YYYY-MM-DD)
            try:
                if "-" in record.date_of_death:
                    parts = record.date_of_death.split("-")
                    if len(parts) >= 3:
                        eow_year, eow_month, eow_day = int(parts[0]), int(parts[1]), int(parts[2])
                        if eow_month == today.month and eow_day == today.day:
                            years_ago = max(1, today.year - eow_year)
                            embed = create_anniversary_embed(record, years_ago)

                            for guild in bot.guilds:
                                archive_ch = None
                                for ch in guild.text_channels:
                                    if ch.name == ARCHIVE_CHANNEL_NAME:
                                        archive_ch = ch
                                        break
                                if archive_ch:
                                    await archive_ch.send(embed=embed)
            except Exception as e:
                logger.warning(f"Anniversary date calculation skipped for #{record.id}: {e}")

    except Exception as e:
        logger.error(f"Error during EOW anniversary check: {e}")
    finally:
        db.close()
