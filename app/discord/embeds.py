"""
Discord Embed Builder for Rich, Detailed Memorial Announcements, Incident Reports, & Stats.
"""
import discord
from datetime import datetime
from typing import Dict, Any, List
from app.models import ResponderRecord, ResponderCategory, GuildConfig, ApprovalStatus

CATEGORY_COLORS = {
    ResponderCategory.LAW_ENFORCEMENT: discord.Color.blue(),
    ResponderCategory.FIRE: discord.Color.red(),
    ResponderCategory.EMS: discord.Color.green(),
    ResponderCategory.RESCUE: discord.Color.orange(),
    ResponderCategory.K9: discord.Color.gold(),
    ResponderCategory.DISPATCH: discord.Color.purple(),
    ResponderCategory.OTHER: discord.Color.dark_grey(),
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


def create_memorial_embed(record: ResponderRecord, custom_header: str = None) -> discord.Embed:
    """
    Constructs a rich, highly detailed Discord Embed for a fallen responder.
    Includes department profile, EOW dates, full AI tribute, scripture, K9 profile, registry verification, and sequential ID.
    """
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = CATEGORY_COLORS.get(category_enum, discord.Color.blue())

    title_prefix = f"[{custom_header}] " if custom_header else "🛡️ IN MEMORIAM: "
    title = f"{title_prefix}{record.name}"

    embed = discord.Embed(
        title=title,
        description=(
            f"**Dedicated Service & Line-of-Duty Sacrifice**\n"
            f"> *\"{record.ai_memorial_text or record.summary or 'In solemn honor of courageous public service.'}\"*"
        ),
        color=color,
        timestamp=datetime.utcnow()
    )

    # Set Thumbnail
    thumb_url = record.photo_url or CATEGORY_THUMBNAILS.get(category_enum, "https://img.icons8.com/color/96/police-badge.png")
    embed.set_thumbnail(url=thumb_url)

    # Department & Unit Profile
    embed.add_field(name="🏛️ Agency / Department", value=f"**{record.agency or 'Emergency Services'}**", inline=True)
    embed.add_field(name="🛡️ Service Branch", value=f"**{category_enum.value.replace('_', ' ').title()}**", inline=True)

    # Incident & EOW Dates
    eow_val = record.date_of_death or "End of Watch"
    embed.add_field(name="🕯️ End of Watch (EOW)", value=f"**{eow_val}**", inline=True)

    if record.date_of_incident and record.date_of_incident != record.date_of_death:
        embed.add_field(name="📅 Date of Incident", value=record.date_of_incident, inline=True)

    # Summary of Duty & Incident
    if record.summary:
        embed.add_field(name="📋 Summary of Duty & Incident", value=record.summary, inline=False)

    # National Registry Auto-Verification & Medals
    ver_status = "✅ Verified National Honor Roll"
    if record.nleomf_verified or record.odmp_verified:
        ver_status = "✅ NLEOMF & ODMP Registry Verified"
    elif record.fire_hero_verified:
        ver_status = "✅ National Fire Hero Registry Verified"

    awards_str = record.unit_awards or "Medal of Valor, Line of Duty Honor Roll"
    embed.add_field(
        name="🎖️ National Registry Verification & Unit Medals",
        value=f"• **Verification Status:** `{ver_status}`\n• **Honors & Medals:** {awards_str}",
        inline=False
    )

    # Specialized K9 Profile
    if category_enum == ResponderCategory.K9 or record.k9_handler_name:
        k9_info = ""
        if record.k9_handler_name:
            k9_info += f"• **Handler Name:** {record.k9_handler_name}\n"
        if record.k9_breed:
            k9_info += f"• **Canine Breed:** {record.k9_breed}\n"
        if record.service_years:
            k9_info += f"• **Years of Service:** {record.service_years}\n"
        if record.unit_badge:
            k9_info += f"• **K9 Unit Badge:** {record.unit_badge}\n"
        if k9_info:
            embed.add_field(name="🐾 K9 Unit Badge & Handler Profile", value=k9_info, inline=False)

    # Scripture Blessing
    if record.bible_verse and record.bible_reference:
        embed.add_field(
            name="📖 Scripture Tribute & Blessing",
            value=f"> *\"{record.bible_verse}\"*\n— **{record.bible_reference}**",
            inline=False
        )

    # Public Tributes & Candle Stats
    candles_count = record.candle_count if record.candle_count else 0
    embed.add_field(
        name="🕯️ Public Tribute Metrics",
        value=f"• **Virtual Candles Lit:** `{candles_count}`\n• **Family Claim:** {'Verified Family Page' if record.claimed_by_family else 'Public Tribute Page'}",
        inline=False
    )

    # Links & Official Resources (No 'Staff Entry' text!)
    article_label = record.article_title if (record.article_title and "Staff Entry" not in record.article_title) else "Official Memorial Record"
    embed.add_field(
        name="🔗 Official Links & Resources",
        value=(
            f"🌐 [View on Web Wall](https://fallen-memorial-bot.onrender.com/wall) | "
            f"📜 [Print Certificate](https://fallen-memorial-bot.onrender.com/responders/{record.id}/certificate) | "
            f"📰 [{article_label}]({record.article_url})"
        ),
        inline=False
    )

    embed.set_footer(
        text=f"Sequential Memorial ID: #{record.id} | Status: APPROVED • Honor Roll"
    )

    return embed


def create_incident_report_embed(record: ResponderRecord, report_text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"📄 Line-of-Duty Incident Analysis Report — ID #{record.id}",
        description=f"**Responder:** {record.name}\n**Agency:** {record.agency}\n**EOW:** {record.date_of_death or 'Line of Duty'}",
        color=discord.Color.dark_blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="📋 AI Intelligence Analysis", value=report_text[:1024], inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Fallen Officer Intelligence System")
    return embed


def create_anniversary_embed(record: ResponderRecord, years_ago: int) -> discord.Embed:
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = CATEGORY_COLORS.get(category_enum, discord.Color.blue())
    year_str = f"{years_ago} Year{'s' if years_ago > 1 else ''} Ago Today" if years_ago > 0 else "Annual Anniversary"

    embed = discord.Embed(
        title=f"🕯️ EOW Anniversary Remembrance — {record.name}",
        description=f"**{year_str}**, we lost a hero from **{record.agency}**. Today we honor their lasting legacy and ultimate sacrifice.",
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="🏛️ Agency", value=record.agency, inline=True)
    embed.add_field(name="🕯️ End of Watch", value=record.date_of_death or "Line of Duty", inline=True)

    if record.bible_verse and record.bible_reference:
        embed.add_field(
            name="📖 Scripture Tribute",
            value=f"> *\"{record.bible_verse}\"*\n— **{record.bible_reference}**",
            inline=False
        )

    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Always Remembered, Never Forgotten")
    return embed


def create_pending_approval_embed(record: ResponderRecord) -> discord.Embed:
    embed = discord.Embed(
        title=f"🚨 [Pending Review] Memorial ID #{record.id}",
        description=(
            f"**Name:** {record.name}\n"
            f"**Agency:** {record.agency}\n"
            f"**Category:** {record.category}\n\n"
            f"**AI Memorial Draft:**\n{record.ai_memorial_text}"
        ),
        color=discord.Color.yellow(),
        timestamp=datetime.utcnow()
    )
    if record.k9_handler_name:
        embed.add_field(name="Handler", value=record.k9_handler_name, inline=True)
    if record.k9_breed:
        embed.add_field(name="Breed", value=record.k9_breed, inline=True)

    article_label = record.article_title if (record.article_title and "Staff Entry" not in record.article_title) else "Source News Article"
    embed.add_field(name="Article Title", value=article_label, inline=False)
    embed.add_field(name="Article URL", value=record.article_url, inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Click interactive buttons below to approve, edit, or reject.")
    return embed


def create_eulogy_embed(record: ResponderRecord, eulogy_text: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🕊️ Formal Eulogy Speech — {record.name}",
        description=eulogy_text,
        color=discord.Color.dark_purple(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Agency", value=record.agency, inline=True)
    embed.add_field(name="End of Watch", value=record.date_of_death or "Line of Duty", inline=True)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | AI Chaplain Tribute")
    return embed


def create_timeline_embed(record: ResponderRecord, timeline_events: List[Dict[str, str]]) -> discord.Embed:
    embed = discord.Embed(
        title=f"⏱️ Incident Timeline — {record.name}",
        description=f"Chronological details for Memorial ID **#{record.id}** ({record.agency})",
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
