"""
Discord Embed Builder for Rich, Human-Grade Memorial Announcements, Incident Reports, & Stats.
"""
import discord
from datetime import datetime
from typing import Dict, Any, List
from app.models import ResponderRecord, ResponderCategory, GuildConfig, ApprovalStatus

CATEGORY_COLORS = {
    ResponderCategory.LAW_ENFORCEMENT: discord.Color.from_rgb(30, 85, 180),
    ResponderCategory.FIRE: discord.Color.from_rgb(195, 40, 40),
    ResponderCategory.EMS: discord.Color.from_rgb(35, 140, 75),
    ResponderCategory.RESCUE: discord.Color.from_rgb(220, 110, 20),
    ResponderCategory.K9: discord.Color.from_rgb(215, 165, 50),
    ResponderCategory.DISPATCH: discord.Color.from_rgb(125, 60, 180),
    ResponderCategory.OTHER: discord.Color.from_rgb(90, 100, 115),
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
    Constructs a dignified, human-grade Discord Embed for a fallen responder.
    Clean typography, official badges, and zero robotic phrasing.
    """
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = CATEGORY_COLORS.get(category_enum, discord.Color.blue())

    name = clean_text(record.name) or "Fallen Emergency Responder"
    agency = clean_text(record.agency) or "Emergency Services"
    summary = clean_text(record.ai_memorial_text or record.summary)

    title_prefix = f"[{custom_header}] " if custom_header else "🛡️ IN MEMORIAM: "
    title = f"{title_prefix}{name}"

    embed = discord.Embed(
        title=title,
        description=f"**{agency}**\n\n{summary}",
        color=color,
        timestamp=datetime.utcnow()
    )

    # Set Thumbnail
    thumb_url = record.photo_url or CATEGORY_THUMBNAILS.get(category_enum, "https://img.icons8.com/color/96/police-badge.png")
    embed.set_thumbnail(url=thumb_url)

    # Department & End of Watch
    eow_val = record.date_of_death or "End of Watch"
    embed.add_field(name="🏛️ Agency", value=agency, inline=True)
    embed.add_field(name="🛡️ Branch", value=category_enum.value.replace('_', ' ').title(), inline=True)
    embed.add_field(name="🕯️ End of Watch", value=f"**{eow_val}**", inline=True)

    if record.date_of_incident and record.date_of_incident != record.date_of_death:
        embed.add_field(name="📅 Incident Date", value=record.date_of_incident, inline=True)

    # Specialized K9 Profile
    if category_enum == ResponderCategory.K9 or record.k9_handler_name:
        k9_info = ""
        if record.k9_handler_name:
            k9_info += f"• **Handler:** {record.k9_handler_name}\n"
        if record.k9_breed:
            k9_info += f"• **Breed:** {record.k9_breed}\n"
        if record.service_years:
            k9_info += f"• **Service:** {record.service_years}\n"
        if k9_info:
            embed.add_field(name="🐾 K9 Unit Details", value=k9_info, inline=False)

    # Registry Verification & Medals (Only if genuinely verified)
    if record.nleomf_verified or record.odmp_verified or record.fire_hero_verified:
        ver_status = "✅ NLEOMF & ODMP Registry Verified" if (record.nleomf_verified or record.odmp_verified) else "✅ National Fire Hero Verified"
        awards_str = record.unit_awards or "National Line of Duty Honor Roll"
        embed.add_field(name="🎖️ Registry Verification", value=f"{ver_status}\n• **Honors:** {awards_str}", inline=False)

    # Scripture Blessing
    if record.bible_verse and record.bible_reference:
        embed.add_field(
            name="📖 Scripture Tribute",
            value=f"*\"{record.bible_verse}\"*\n— **{record.bible_reference}**",
            inline=False
        )

    # Candles Count
    candles_count = record.candle_count if record.candle_count else 0
    embed.add_field(name="🕯️ Virtual Candles", value=f"`{candles_count}` lit in honor", inline=True)

    # Links & Resources
    article_label = clean_text(record.article_title) or "Official Memorial Record"
    embed.add_field(
        name="🔗 Tribute Resources",
        value=(
            f"🌐 [Web Wall](https://fallen-memorial-bot.onrender.com/wall) | "
            f"📜 [Certificate](https://fallen-memorial-bot.onrender.com/responders/{record.id}/certificate) | "
            f"📰 [{article_label}]({record.article_url})"
        ),
        inline=False
    )

    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} • Line of Duty Honor Roll")
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
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = CATEGORY_COLORS.get(category_enum, discord.Color.blue())
    year_str = f"{years_ago} Year{'s' if years_ago > 1 else ''} Ago Today" if years_ago > 0 else "Annual Anniversary"

    embed = discord.Embed(
        title=f"🕯️ EOW Anniversary Remembrance — {clean_text(record.name)}",
        description=f"**{year_str}**, we lost a hero from **{clean_text(record.agency)}**. Today we honor their lasting legacy and service.",
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="🏛️ Agency", value=clean_text(record.agency), inline=True)
    embed.add_field(name="🕯️ End of Watch", value=record.date_of_death or "Line of Duty", inline=True)

    if record.bible_verse and record.bible_reference:
        embed.add_field(
            name="📖 Scripture Tribute",
            value=f"*\"{record.bible_verse}\"*\n— **{record.bible_reference}**",
            inline=False
        )

    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} • Always Remembered")
    return embed


def create_pending_approval_embed(record: ResponderRecord) -> discord.Embed:
    embed = discord.Embed(
        title=f"🚨 [Pending Review] Memorial ID #{record.id}",
        description=(
            f"**Name:** {clean_text(record.name)}\n"
            f"**Agency:** {clean_text(record.agency)}\n"
            f"**Category:** {record.category}\n\n"
            f"**Draft Bio:**\n{clean_text(record.ai_memorial_text or record.summary)}"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    article_label = clean_text(record.article_title) or "Source News Article"
    embed.add_field(name="Source Article", value=f"[{article_label}]({record.article_url})", inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} • Click buttons below to approve or reject.")
    return embed


def create_eulogy_embed(record: ResponderRecord, eulogy_text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🕊️ Formal Eulogy Speech — {clean_text(record.name)}",
        description=eulogy_text,
        color=discord.Color.dark_purple(),
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
        color=discord.Color.dark_gold(),
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
        color=discord.Color.blue(),
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
        color=discord.Color.gold(),
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
