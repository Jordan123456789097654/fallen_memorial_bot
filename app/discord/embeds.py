"""
Discord Embed Builder for Rich, Human-Grade Memorial Announcements, Incident Reports, & Stats.
Matches exact reference layout with solemn chaplain prose, scripture blockquotes, and news links.
"""
import discord
from datetime import datetime
from typing import Dict, Any, List
from app.models import ResponderRecord, ResponderCategory, GuildConfig, ApprovalStatus

CATEGORY_COLORS = {
    ResponderCategory.LAW_ENFORCEMENT: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.FIRE: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.EMS: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.RESCUE: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.K9: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.DISPATCH: discord.Color.from_rgb(46, 160, 67),
    ResponderCategory.OTHER: discord.Color.from_rgb(46, 160, 67),
}

CATEGORY_THUMBNAILS = {
    ResponderCategory.LAW_ENFORCEMENT: "https://img.icons8.com/color/96/police-badge.png",
    ResponderCategory.FIRE: "https://img.icons8.com/color/96/firefighter-helmet.png",
    ResponderCategory.EMS: "https://img.icons8.com/color/96/star-of-life.png",
    ResponderCategory.RESCUE: "https://img.icons8.com/color/96/lifebuoy.png",
    ResponderCategory.K9: "https://img.icons8.com/color/96/dog.png",
    ResponderCategory.DISPATCH: "https://img.icons8.com/color/96/headset.png",
    ResponderCategory.OTHER: "https://img.icons8.com/color/96/ribbon.png",
}


def clean_text(val: str) -> str:
    """Removes bracketed prefixes and AI jargon."""
    if not val:
        return ""
    import re
    text = re.sub(r"\[TEST(?: AI| SAMPLE)?(?: TRIBUTE| DRAFT)?\]", "", val, flags=re.IGNORECASE)
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def create_memorial_embed(record: ResponderRecord, custom_header: str = None) -> discord.Embed:
    """
    Constructs an exact match Discord Embed for a fallen responder following the reference screenshot layout.
    """
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = discord.Color.from_rgb(46, 160, 67)

    name = clean_text(record.name) or "Fallen Emergency Responder"
    agency = clean_text(record.agency) or "Emergency Services Department"
    summary = clean_text(record.article_title or record.summary or record.ai_memorial_text or "")
    article_title = clean_text(record.article_title) or f"Memorial notice for {name}"
    eow_val = record.date_of_death or "End of Watch"
    verse = record.bible_verse or "Then I heard the voice of the Lord saying, 'Whom shall I send? And who will go for us?' And I said, 'Here am I. Send me!'"
    verse_ref = record.bible_reference or "Isaiah 6:8"

    cat_display = category_enum.value.replace('_', ' ').title()

    title_text = custom_header if custom_header else f"In Memory of {name}"
    if name == "Fallen Emergency Responder" or "Hero" in name:
        title_text = f"In Memory of Fallen {cat_display}"

    desc = (
        f"It is with heavy hearts and profound honor that we remember "
        f"**{name}** of **{agency}**. {summary}\n\n"
        f"We honor their noble dedication, courage, and ultimate sacrifice in service to the community. "
        f"May their bravery never be forgotten, and may comfort rest upon their loved ones, colleagues, and agency.\n\n"
        f"> *\"{verse}\"*\n"
        f"> — **{verse_ref}**\n\n"
        f"**End of Watch / Date:** {eow_val}"
    )

    embed = discord.Embed(
        title=title_text,
        description=desc,
        color=color,
        timestamp=record.created_at or datetime.utcnow()
    )

    # 3 Inline Fields
    embed.add_field(name="🏛️ Agency", value=agency, inline=True)
    embed.add_field(name="🛡️ Category", value=cat_display, inline=True)
    embed.add_field(name="🕯️ Date / EOW", value=eow_val, inline=True)

    # Scripture Tribute Block
    embed.add_field(
        name="📖 Scripture Tribute",
        value=f"> *\"{verse}\"*\n\n— **{verse_ref}**",
        inline=False
    )

    # Source News Article Field
    embed.add_field(
        name="🔗 Source News Article",
        value=f"[{article_title}]({record.article_url})",
        inline=False
    )

    status_str = record.status.value if isinstance(record.status, ApprovalStatus) else record.status
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Status: {status_str}")
    return embed


def create_incident_report_embed(record: ResponderRecord, report_text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"📄 Line-of-Duty Incident Analysis — ID #{record.id}",
        description=f"**Responder:** {clean_text(record.name)}\n**Agency:** {clean_text(record.agency)}\n**EOW:** {record.date_of_death or 'Line of Duty'}",
        color=discord.Color.dark_blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="📋 Incident Analysis", value=report_text[:1024], inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id}")
    return embed


def create_anniversary_embed(record: ResponderRecord, years_ago: int) -> discord.Embed:
    color = discord.Color.from_rgb(46, 160, 67)
    year_str = f"{years_ago} Year{'s' if years_ago > 1 else ''} Ago Today" if years_ago > 0 else "Annual Anniversary"
    verse = record.bible_verse or "Then I heard the voice of the Lord saying, 'Whom shall I send? And who will go for us?' And I said, 'Here am I. Send me!'"
    verse_ref = record.bible_reference or "Isaiah 6:8"

    embed = discord.Embed(
        title=f"🕯️ EOW Anniversary Remembrance — {clean_text(record.name)}",
        description=f"**{year_str}**, we lost a hero from **{clean_text(record.agency)}**. Today we honor their lasting legacy and service.",
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="🏛️ Agency", value=clean_text(record.agency), inline=True)
    embed.add_field(name="🕯️ End of Watch", value=record.date_of_death or "Line of Duty", inline=True)

    embed.add_field(
        name="📖 Scripture Tribute",
        value=f"> *\"{verse}\"*\n\n— **{verse_ref}**",
        inline=False
    )

    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} • Always Remembered")
    return embed


def create_pending_approval_embed(record: ResponderRecord) -> discord.Embed:
    color = discord.Color.from_rgb(46, 160, 67)
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    cat_display = category_enum.value.replace('_', ' ').title()

    name = clean_text(record.name) or "Fallen Emergency Responder"
    agency = clean_text(record.agency) or "Emergency Services Department"
    summary = clean_text(record.article_title or record.summary or "")
    article_title = clean_text(record.article_title) or f"Memorial notice for {name}"
    eow_val = record.date_of_death or "End of Watch"
    verse = record.bible_verse or "Then I heard the voice of the Lord saying, 'Whom shall I send? And who will go for us?' And I said, 'Here am I. Send me!'"
    verse_ref = record.bible_reference or "Isaiah 6:8"

    desc = (
        f"It is with heavy hearts and profound honor that we remember "
        f"**{name}** of **{agency}**. {summary}\n\n"
        f"We honor their noble dedication, courage, and ultimate sacrifice in service to the community.\n\n"
        f"> *\"{verse}\"*\n"
        f"> — **{verse_ref}**\n\n"
        f"**End of Watch / Date:** {eow_val}"
    )

    embed = discord.Embed(
        title=f"🚨 [Pending Review] Memorial ID #{record.id}",
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="🏛️ Agency", value=agency, inline=True)
    embed.add_field(name="🛡️ Category", value=cat_display, inline=True)
    embed.add_field(name="🕯️ Date / EOW", value=eow_val, inline=True)

    embed.add_field(name="🔗 Source News Article", value=f"[{article_title}]({record.article_url})", inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Status: PENDING • Click buttons below to approve or reject.")
    return embed


def create_eulogy_embed(record: ResponderRecord, eulogy_text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🕊️ Formal Eulogy Speech — {clean_text(record.name)}",
        description=eulogy_text,
        color=discord.Color.from_rgb(46, 160, 67),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Agency", value=clean_text(record.agency), inline=True)
    embed.add_field(name="End of Watch", value=record.date_of_death or "Line of Duty", inline=True)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} • Chaplain Honor Roll")
    return embed


def create_timeline_embed(record: ResponderRecord, timeline_events: List[Dict[str, str]]) -> discord.Embed:
    embed = discord.Embed(
        title=f"⏱️ Incident Timeline — {clean_text(record.name)}",
        description=f"Chronological details for Memorial ID **#{record.id}** ({clean_text(record.agency)})",
        color=discord.Color.from_rgb(46, 160, 67),
        timestamp=datetime.utcnow()
    )
    for event in timeline_events[:8]:
        embed.add_field(
            name=f"📍 {event.get('time_or_date', 'Event')}",
            value=event.get('event', 'No description'),
            inline=False
        )
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id}")
    return embed


def create_stats_embed(stats: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title="📊 Intelligence System Analytics & Statistics",
        description="Comprehensive breakdown of emergency responder memorial data.",
        color=discord.Color.from_rgb(46, 160, 67),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Total Memorials", value=str(stats.get("total", 0)), inline=True)
    embed.add_field(name="Approved", value=str(stats.get("approved", 0)), inline=True)
    embed.add_field(name="Pending Review", value=str(stats.get("pending", 0)), inline=True)

    cat_text = ""
    for cat, count in stats.get("by_category", {}).items():
        cat_text += f"• **{cat.replace('_', ' ').title()}:** {count}\n"
    embed.add_field(name="Categories Breakdown", value=cat_text or "No data", inline=False)

    embed.set_footer(text="Fallen Officer Memorial Intelligence System")
    return embed


def create_config_embed(guild: discord.Guild, config: GuildConfig) -> discord.Embed:
    embed = discord.Embed(
        title=f"⚙️ Server Profile & Configuration — {guild.name}",
        description=f"Per-server settings for Guild ID: `{guild.id}`",
        color=discord.Color.from_rgb(46, 160, 67),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Approval Workflow Mode", value=f"`{config.approval_mode}`", inline=True)
    embed.add_field(name="Alert Role", value=f"<@&{config.alert_role_id}>" if config.alert_role_id else "*None configured*", inline=True)
    embed.add_field(name="Admin Role", value=f"<@&{config.admin_role_id}>" if config.admin_role_id else "`Administrators Only`", inline=True)
    embed.add_field(name="Bot Nickname", value=f"`{config.bot_nickname or 'Default'}`", inline=True)
    embed.add_field(name="Category Name", value=f"`{config.category_name}`", inline=True)
    embed.add_field(name="Custom Embed Header", value=f"`{config.custom_header or 'None'}`", inline=False)
    embed.set_footer(text="Use /config to customize server settings")
    return embed
