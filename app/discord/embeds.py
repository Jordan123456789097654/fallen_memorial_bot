"""
Discord Embed Builder for Memorial Announcements, Eulogies, Stats, & Server Configs.
Supports Specialized K9 fields, Virtual Candles counters, and EOW Anniversary Reminders.
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


def create_memorial_embed(record: ResponderRecord, custom_header: str = None) -> discord.Embed:
    """
    Constructs a respectful Discord Embed for a fallen responder.
    Supports K9 handler details, candle counters, and Sequential Memorial ID.
    """
    category_enum = record.category if isinstance(record.category, ResponderCategory) else ResponderCategory(record.category)
    color = CATEGORY_COLORS.get(category_enum, discord.Color.blue())

    title_prefix = f"[{custom_header}] " if custom_header else ""
    title = f"{title_prefix}In Memory of {record.name}"

    embed = discord.Embed(
        title=title,
        description=record.ai_memorial_text or record.summary or "In honor of faithful emergency service.",
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="🏛️ Agency", value=record.agency or "Emergency Services", inline=True)
    embed.add_field(name="🛡️ Category", value=category_enum.value.replace("_", " ").title(), inline=True)

    if record.date_of_death:
        embed.add_field(name="🕯️ Date / EOW", value=record.date_of_death, inline=True)
    elif record.date_of_incident:
        embed.add_field(name="📅 Incident Date", value=record.date_of_incident, inline=True)

    # Specialized K9 fields
    if category_enum == ResponderCategory.K9 or record.k9_handler_name:
        k9_info = ""
        if record.k9_handler_name:
            k9_info += f"• **Handler:** {record.k9_handler_name}\n"
        if record.k9_breed:
            k9_info += f"• **Breed:** {record.k9_breed}\n"
        if record.service_years:
            k9_info += f"• **Service Years:** {record.service_years}\n"
        if record.unit_badge:
            k9_info += f"• **Unit Badge:** {record.unit_badge}\n"
        if k9_info:
            embed.add_field(name="🐾 K9 Unit Profile", value=k9_info, inline=False)

    if record.bible_verse and record.bible_reference:
        embed.add_field(
            name="📖 Scripture Tribute",
            value=f"> *\"{record.bible_verse}\"*\n— **{record.bible_reference}**",
            inline=False
        )

    embed.add_field(
        name="🔗 Source News Article",
        value=f"[{record.article_title or 'Read Full Article'}]({record.article_url})",
        inline=False
    )

    candle_txt = f" | 🕯️ {record.candle_count} Candles Lit" if record.candle_count > 0 else ""
    embed.set_footer(
        text=f"Sequential Memorial ID: #{record.id}{candle_txt} | Status: {record.status.value if hasattr(record.status, 'value') else record.status}"
    )

    return embed


def create_anniversary_embed(record: ResponderRecord, years_ago: int) -> discord.Embed:
    """Creates an EOW Anniversary Remembrance Embed."""
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
    """Creates an admin review embed for pending approvals."""
    embed = discord.Embed(
        title=f"🚨 [Pending Approval] Memorial ID #{record.id}",
        description=f"**Name:** {record.name}\n**Agency:** {record.agency}\n**Category:** {record.category}\n\n**AI Memorial Draft:**\n{record.ai_memorial_text}",
        color=discord.Color.yellow(),
        timestamp=datetime.utcnow()
    )
    if record.k9_handler_name:
        embed.add_field(name="Handler", value=record.k9_handler_name, inline=True)
    if record.k9_breed:
        embed.add_field(name="Breed", value=record.k9_breed, inline=True)

    embed.add_field(name="Article Title", value=record.article_title or "Source", inline=False)
    embed.add_field(name="Article URL", value=record.article_url, inline=False)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | Click buttons below to approve, edit, or reject.")
    return embed


def create_eulogy_embed(record: ResponderRecord, eulogy_text: str) -> discord.Embed:
    """Creates a formal Eulogy Speech embed."""
    embed = discord.Embed(
        title=f"🕊️ Formal Eulogy for {record.name}",
        description=eulogy_text,
        color=discord.Color.dark_purple(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Agency", value=record.agency, inline=True)
    embed.add_field(name="End of Watch", value=record.date_of_death or "Line of Duty", inline=True)
    embed.set_footer(text=f"Sequential Memorial ID: #{record.id} | AI Chaplain Tribute")
    return embed


def create_timeline_embed(record: ResponderRecord, timeline_events: List[Dict[str, str]]) -> discord.Embed:
    """Creates an Incident Timeline embed."""
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
    """Creates a visual statistics breakdown embed."""
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
    """Creates a server configuration profile embed."""
    embed = discord.Embed(
        title=f"⚙️ Server Profile & Configuration — {guild.name}",
        description=f"Per-server settings for Guild ID: `{guild.id}`",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Approval Workflow Mode", value=f"`{config.approval_mode}`", inline=True)
    embed.add_field(name="Alert Role", value=f"<@&{config.alert_role_id}>" if config.alert_role_id else "*None configured*", inline=True)
    embed.add_field(name="Category Name", value=f"`{config.category_name}`", inline=True)
    embed.add_field(name="Custom Embed Header", value=f"`{config.custom_header or 'None'}`", inline=False)
    embed.set_footer(text="Use /config mode, /config role, or /config header to customize")
    return embed
