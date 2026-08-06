"""
News Scanner Automation, Webhook Broadcaster, Multi-Guild Broadcaster, Daily Moment of Silence Roll Call, and Self-Ping Worker.
"""
import aiohttp
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus, GuildConfig, WebhookSubscription, ResponderCategory
from app.config import settings
from app.ai import get_ai_provider
from app.discord.embeds import create_memorial_embed, create_pending_approval_embed, create_anniversary_embed
from app.discord.views import MemorialInteractionView, PendingReviewView
from app.discord.channels import get_or_create_guild_config
from app.social import SocialPublisher
from app.utils.logger import logger

import re
import random
import feedparser

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=officer+killed+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=firefighter+dies+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=paramedic+killed+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=police+k9+killed&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=deputy+killed+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=trooper+killed+line+of+duty&hl=en-US&gl=US&ceid=US:en",
]


async def scrape_full_article_content(url: str) -> str:
    """Fetches full news article webpage content to extract cause of death & family details."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    text = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text[:4000]
    except Exception as e:
        logger.warning(f"Could not scrape full article URL {url}: {e}")
    return ""


def load_bible_verses():
    import json, os
    if os.path.exists(settings.BIBLE_VERSES_PATH):
        try:
            with open(settings.BIBLE_VERSES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [{
        "text": "Greater love has no one than this: to lay down one's life for one's friends.",
        "reference": "John 15:13"
    }]


async def self_ping_keep_alive():
    """
    Automated background worker running every 60 seconds to ping the public web application URL,
    preventing cloud hosting providers (e.g. Render Web Services) from entering idle sleep mode.
    """
    public_url = "https://fallen-memorial-bot.onrender.com/healthz"
    local_url = "http://127.0.0.1:8000/healthz"
    headers = {"User-Agent": "MemorialKeepAliveWorker/2.5"}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(public_url, timeout=12) as response:
                    if response.status == 200:
                        logger.info("Public Keep-Alive Heartbeat (Render): OK (200)")
            except Exception:
                async with session.get(local_url, timeout=5) as local_resp:
                    if local_resp.status == 200:
                        logger.info("Local Keep-Alive Heartbeat: OK (200)")
    except Exception as e:
        logger.debug(f"Keep-Alive Heartbeat exception: {e}")


async def daily_moment_of_silence(bot=None):
    """
    Scheduled daily roll call job posting morning tributes in Discord for EOW anniversaries today.
    """
    logger.info("Running Daily Moment of Silence & Roll Call check...")
    db: Session = SessionLocal()
    try:
        today_str = datetime.utcnow().strftime("%m-%d")
        records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).all()

        today_matches = []
        for r in records:
            if r.date_of_death and today_str in r.date_of_death:
                today_matches.append(r)

        if not today_matches:
            logger.info("No EOW anniversary matches found for today's date.")
            return

        if bot and hasattr(bot, 'guilds'):
            for guild in bot.guilds:
                cfg = get_or_create_guild_config(db, guild)
                logs_ch = None
                for ch in guild.text_channels:
                    if ch.name in ("fallen-law-enforcement", "memorials", "bot-logs"):
                        logs_ch = ch
                        break

                if logs_ch:
                    role_ping = f"<@&{cfg.alert_role_id}> " if cfg.alert_role_id else ""
                    await logs_ch.send(content=f"🕯️ {role_ping}**DAILY MOMENT OF SILENCE & ROLL CALL OF HONOR:**")
                    for rec in today_matches:
                        embed = create_anniversary_embed(rec, years_ago=1)
                        view = MemorialInteractionView(rec.id)
                        await logs_ch.send(embed=embed, view=view)
    except Exception as e:
        logger.error(f"Error executing Daily Moment of Silence roll call: {e}")
    finally:
        db.close()


async def scan_news_sources(bot=None) -> dict:
    """Scans configured RSS news feeds for line-of-duty responder notices."""
    logger.info("Starting automated RSS news feeds scan...")
    db: Session = SessionLocal()
    ai_provider = get_ai_provider()
    bible_verses = load_bible_verses()

    scanned_count = 0
    new_records_count = 0

    try:
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:5]:
                    scanned_count += 1
                    link = entry.get("link", "")
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")

                    if not link or not title:
                        continue

                    existing = db.query(ResponderRecord).filter(ResponderRecord.article_url == link).first()
                    if existing:
                        continue

                    full_webpage_text = await scrape_full_article_content(link)
                    combined_content = f"Title: {title}\nSummary: {summary}\nFull Webpage Article Text:\n{full_webpage_text}"

                    scraped = {
                        "article_title": title,
                        "article_url": link,
                        "raw_content": combined_content,
                        "source_domain": link.split("/")[2] if "//" in link else "google_news"
                    }

                    parsed_data = await ai_provider.extract_memorial_data(scraped)

                    is_valid_hero = (
                        parsed_data.get("is_line_of_duty_death") or 
                        parsed_data.get("is_fallen_responder") or 
                        True
                    )

                    if not is_valid_hero:
                        continue

                    chosen_verse = random.choice(bible_verses)
                    verse_text = chosen_verse.get("text", "Greater love has no one than this...")
                    verse_ref = chosen_verse.get("reference", "John 15:13")

                    ai_text = await ai_provider.generate_memorial_text(parsed_data)

                    cat_str = parsed_data.get("category", "OTHER").upper()
                    try:
                        cat_enum = ResponderCategory[cat_str]
                    except KeyError:
                        cat_enum = ResponderCategory.OTHER

                    rec = ResponderRecord(
                        name=parsed_data.get("name", "Unknown Hero"),
                        agency=parsed_data.get("agency", "Emergency Services"),
                        category=cat_enum,
                        date_of_incident=parsed_data.get("date_of_incident"),
                        date_of_death=parsed_data.get("date_of_death") or "End of Watch",
                        cause_of_death=parsed_data.get("cause_of_death"),
                        surviving_family=parsed_data.get("surviving_family"),
                        summary=parsed_data.get("summary") or summary,
                        article_title=title,
                        article_url=link,
                        source_domain=scraped["source_domain"],
                        bible_verse=verse_text,
                        bible_reference=verse_ref,
                        ai_memorial_text=ai_text,
                        status=ApprovalStatus.PENDING
                    )
                    db.add(rec)
                    db.commit()
                    db.refresh(rec)
                    new_records_count += 1
                    logger.info(f"Discovered new line-of-duty responder: {rec.name} (#{rec.id})")

                    if bot:
                        await broadcast_pending_review(bot, rec)

            except Exception as fe:
                logger.error(f"Error parsing feed {feed_url}: {fe}")

        return {"status": "success", "scanned": scanned_count, "new_memorials": new_records_count}
    finally:
        db.close()


async def broadcast_pending_review(bot, record: ResponderRecord):
    """Broadcasting pending review embed to #bot-logs across all connected guilds."""
    db: Session = SessionLocal()
    try:
        for guild in bot.guilds:
            cfg = get_or_create_guild_config(db, guild)
            logs_ch = None
            for ch in guild.text_channels:
                if ch.name == "bot-logs":
                    logs_ch = ch
                    break

            if logs_ch:
                embed = create_pending_approval_embed(record)
                role_ping = f"<@&{cfg.alert_role_id}> " if cfg.alert_role_id else ""
                view = PendingReviewView(record.id)
                await logs_ch.send(content=f"🚨 {role_ping}**New Pending Memorial Draft Review:**", embed=embed, view=view)
    except Exception as e:
        logger.error(f"Error broadcasting pending review: {e}")
    finally:
        db.close()


async def post_approved_memorial(bot, record: ResponderRecord):
    """Broadcasts approved memorial to category channels, webhooks, and social media."""
    db: Session = SessionLocal()
    try:
        if bot and hasattr(bot, 'guilds'):
            for guild in bot.guilds:
                cfg = get_or_create_guild_config(db, guild)
                category_name = record.category.value if hasattr(record.category, 'value') else str(record.category)
                target_channel_name = f"fallen-{category_name.lower().replace('_', '-')}"

                target_ch = None
                for ch in guild.text_channels:
                    if ch.name == target_channel_name:
                        target_ch = ch
                        break

                if target_ch:
                    embed = create_memorial_embed(record, custom_header=cfg.custom_header)
                    view = MemorialInteractionView(record.id)
                    msg = await target_ch.send(embed=embed, view=view)
                    if msg:
                        record.discord_message_id = str(msg.id)
                        record.discord_channel_id = str(target_ch.id)
                        db.commit()

        await dispatch_webhooks(record)

        social_pub = SocialPublisher()
        await social_pub.publish_memorial(record.to_dict())

    except Exception as e:
        logger.error(f"Error posting approved memorial: {e}")
    finally:
        db.close()


async def update_posted_discord_embeds(bot, record: ResponderRecord):
    """
    Live Updates original posted Discord message embeds when candle count or staff edits occur.
    """
    if not bot or not hasattr(bot, 'guilds'):
        return

    db: Session = SessionLocal()
    try:
        for guild in bot.guilds:
            cfg = get_or_create_guild_config(db, guild)
            category_name = record.category.value if hasattr(record.category, 'value') else str(record.category)
            target_channel_name = f"fallen-{category_name.lower().replace('_', '-')}"

            for ch in guild.text_channels:
                if ch.name in (target_channel_name, "memorials", "fallen-law-enforcement"):
                    try:
                        async for msg in ch.history(limit=30):
                            if msg.author == bot.user and msg.embeds:
                                if f"#{record.id}" in msg.embeds[0].footer.text or record.name in msg.embeds[0].title:
                                    updated_embed = create_memorial_embed(record, custom_header=cfg.custom_header)
                                    view = MemorialInteractionView(record.id)
                                    await msg.edit(embed=updated_embed, view=view)
                                    logger.info(f"Live updated Discord message #{msg.id} for Record #{record.id}")
                    except Exception as ex:
                        logger.debug(f"Error scanning channel {ch.name} for live update: {ex}")
    except Exception as e:
        logger.error(f"Error live updating posted Discord embeds: {e}")
    finally:
        db.close()


async def dispatch_webhooks(record: ResponderRecord):
    """Dispatches payload to registered webhook subscriptions."""
    db: Session = SessionLocal()
    try:
        subs = db.query(WebhookSubscription).filter(WebhookSubscription.is_active == True).all()
        payload = record.to_dict()

        async with aiohttp.ClientSession() as session:
            for sub in subs:
                if sub.category_filter != "ALL" and sub.category_filter != payload.get("category"):
                    continue
                try:
                    await session.post(sub.url, json=payload, timeout=5)
                except Exception as e:
                    logger.error(f"Failed to post to webhook {sub.url}: {e}")
    finally:
        db.close()
