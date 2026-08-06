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
from app.discord.channels import get_or_create_guild_config
from app.social import SocialPublisher
from app.utils.logger import logger

import feedparser

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=officer+killed+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=firefighter+dies+line+of+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=paramedic+killed+duty&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=police+k9+killed&hl=en-US&gl=US&ceid=US:en",
]


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
    Automated background worker running every 5 minutes to ping the web application,
    preventing free tier cloud instances (e.g. Render Web Services) from sleeping.
    """
    url = "http://127.0.0.1:8000/healthz"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    logger.info("Self-Ping Keep-Alive Heartbeat: OK (200)")
                else:
                    logger.warning(f"Self-Ping Keep-Alive Heartbeat returned status: {response.status}")
    except Exception as e:
        logger.debug(f"Self-Ping Keep-Alive Heartbeat ping exception (expected if web server starting): {e}")


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
                        await logs_ch.send(embed=embed)
    except Exception as e:
        logger.error(f"Error executing Daily Moment of Silence roll call: {e}")
    finally:
        db.close()


async def scan_news_sources(bot=None) -> dict:
    """Scans configured RSS news feeds for line-of-duty responder notices."""
    logger.info("Starting automated news source scan...")
    db: Session = SessionLocal()
    scanned_count = 0
    new_records_count = 0

    try:
        ai_provider = get_ai_provider()
        verses = load_bible_verses()

        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:10]:
                    scanned_count += 1
                    article_title = entry.get("title", "")
                    article_url = entry.get("link", "")
                    summary = entry.get("summary", "")

                    existing = db.query(ResponderRecord).filter(ResponderRecord.article_url == article_url).first()
                    if existing:
                        continue

                    extracted = await ai_provider.extract_info(summary, article_title)
                    if not extracted.get("is_fallen_responder", True):
                        continue

                    import random
                    verse = random.choice(verses)

                    memorial_text = await ai_provider.generate_memorial(extracted, verse)

                    category_str = extracted.get("category", "OTHER")
                    try:
                        category_enum = ResponderCategory[category_str]
                    except KeyError:
                        category_enum = ResponderCategory.OTHER

                    record = ResponderRecord(
                        name=extracted.get("name", "Unknown Hero"),
                        agency=extracted.get("agency", "Unknown Agency"),
                        category=category_enum,
                        date_of_incident=extracted.get("date_of_incident"),
                        date_of_death=extracted.get("date_of_death"),
                        summary=extracted.get("summary", article_title),
                        k9_handler_name=extracted.get("k9_handler_name"),
                        k9_breed=extracted.get("k9_breed"),
                        service_years=extracted.get("service_years"),
                        unit_badge=extracted.get("unit_badge"),
                        article_title=article_title,
                        article_url=article_url,
                        source_domain=article_url.split("/")[2] if "/" in article_url else "news",
                        bible_verse=verse.get("text"),
                        bible_reference=verse.get("reference"),
                        ai_memorial_text=memorial_text,
                        status=ApprovalStatus.PENDING
                    )
                    db.add(record)
                    db.commit()
                    db.refresh(record)
                    new_records_count += 1

                    if bot and hasattr(bot, 'guilds'):
                        await broadcast_pending_review(bot, record)

            except Exception as e:
                logger.error(f"Error scanning feed {feed_url}: {e}")

    finally:
        db.close()

    logger.info(f"News scan complete. Scanned {scanned_count} entries. Created {new_records_count} new draft records.")
    return {"scanned": scanned_count, "new_records": new_records_count}


async def broadcast_pending_review(bot, record: ResponderRecord):
    """Broadcasting pending review embed to #bot-logs across all connected guilds."""
    from app.discord.views import PendingReviewView
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
                    await target_ch.send(embed=embed)

        await dispatch_webhooks(record)

        social_pub = SocialPublisher()
        await social_pub.publish_memorial(record.to_dict())

    except Exception as e:
        logger.error(f"Error posting approved memorial: {e}")
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
