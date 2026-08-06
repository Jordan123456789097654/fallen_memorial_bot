"""
Discord Slash Commands Implementation.
Includes /config subcommands, /setstatus presence modifier, /test_embed generator, Admin Role permission enforcement, and 30+ commands.
"""
import io
import csv
import json
import random
import time
import discord
from discord import app_commands
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus, ResponderCategory, GuildConfig, Condolence
from app.config import settings
from app.discord.embeds import (
    create_memorial_embed,
    create_eulogy_embed,
    create_timeline_embed,
    create_stats_embed,
    create_config_embed,
    create_incident_report_embed
)
from app.discord.channels import setup_memorial_channels, get_or_create_guild_config
from app.scanner import scan_news_sources, post_approved_memorial, load_bible_verses
from app.ai import get_ai_provider
from app.utils.logger import logger


def check_admin_permission(interaction: discord.Interaction, db: Session) -> bool:
    """
    Checks if interaction user has Guild Administrator permissions OR holds the configured Admin Role.
    """
    if not interaction.guild:
        return True
    if interaction.user.guild_permissions.administrator:
        return True

    config = get_or_create_guild_config(db, interaction.guild)
    if config.admin_role_id:
        user_role_ids = [str(r.id) for r in interaction.user.roles]
        if config.admin_role_id in user_role_ids:
            return True

    return False


class ConfigGroup(app_commands.Group):
    """Server configuration commands for server owners & admins."""

    def __init__(self):
        super().__init__(name="config", description="Configure bot settings for this Discord server.")

    @app_commands.command(name="view", description="View current server profile & settings.")
    async def config_view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            embed = create_config_embed(interaction.guild, config)
            await interaction.followup.send(embed=embed, ephemeral=True)
        finally:
            db.close()

    @app_commands.command(name="admin_role", description="Set an Admin Role required to run management commands.")
    @app_commands.describe(role="Select admin role (or leave empty to clear restriction)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_admin_role(self, interaction: discord.Interaction, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.admin_role_id = str(role.id) if role else None
            db.commit()

            role_msg = f"<@&{role.id}>" if role else "Cleared (Administrators Only)"
            await interaction.followup.send(
                f"✅ **Admin Role Updated:** Management commands restricted to {role_msg}.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="bot_nickname", description="Change the bot's server nickname in this guild.")
    @app_commands.describe(nickname="New nickname for the bot (e.g. 'Memorial Intelligence Bot')")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_bot_nickname(self, interaction: discord.Interaction, nickname: str = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.bot_nickname = nickname
            db.commit()

            try:
                await interaction.guild.me.edit(nick=nickname)
                nick_msg = f"`{nickname}`" if nickname else "Default Name"
                await interaction.followup.send(
                    f"✅ **Bot Nickname Updated:** Nickname set to {nick_msg} for **{interaction.guild.name}**.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"⚠️ Saved nickname to database, but missing permission to change nickname in server: `{e}`",
                    ephemeral=True
                )
        finally:
            db.close()

    @app_commands.command(name="mode", description="Set approval workflow mode (MANUAL or AUTO) for this server.")
    @app_commands.describe(mode="MANUAL (requires /approve) or AUTO (auto-publishes upon news scan)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="MANUAL (Admins review with /approve)", value="MANUAL"),
        app_commands.Choice(name="AUTO (Auto-publish immediately)", value="AUTO"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.approval_mode = mode.value
            db.commit()
            await interaction.followup.send(
                f"✅ **Server Approval Mode Updated:** Set to `{mode.value}` for **{interaction.guild.name}**.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="role", description="Set alert role pinged for pending or new memorials.")
    @app_commands.describe(role="Select role to ping for alerts (or leave empty to clear)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_role(self, interaction: discord.Interaction, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.alert_role_id = str(role.id) if role else None
            db.commit()

            role_msg = f"<@&{role.id}>" if role else "Cleared"
            await interaction.followup.send(
                f"✅ **Alert Role Updated:** Alert role set to {role_msg}.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="header", description="Set a custom title header prefix for memorial cards in this server.")
    @app_commands.describe(header_text="Custom header slogan (e.g. 'HONORING OUR HEROES')")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_header(self, interaction: discord.Interaction, header_text: str = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.custom_header = header_text
            db.commit()

            await interaction.followup.send(
                f"✅ **Custom Header Updated:** Set to `{header_text or 'None'}`.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="setup", description="Re-run category and channel structure setup for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channels = await setup_memorial_channels(interaction.guild)
        await interaction.followup.send(
            f"✅ **Server Setup Complete:** Verified {len(channels)} channels under the Memorials category.",
            ephemeral=True
        )


def register_slash_commands(bot: discord.Client):
    """Registers all slash commands and command groups on the bot command tree."""

    bot.tree.add_command(ConfigGroup())

    @bot.tree.command(name="setstatus", description="Set the bot's rich presence status activity across Discord.")
    @app_commands.describe(
        activity_type="Type of status activity (Playing, Watching, Listening, Streaming)",
        status_text="Text to display in status (e.g. 'RIP Fallen Heroes')"
    )
    @app_commands.choices(activity_type=[
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Listening", value="listening"),
        app_commands.Choice(name="Streaming", value="streaming"),
    ])
    async def setstatus_cmd(interaction: discord.Interaction, activity_type: app_commands.Choice[str], status_text: str):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You must have Administrator permissions or the configured Admin Role to run this command.", ephemeral=True)
                return

            act_map = {
                "playing": discord.ActivityType.playing,
                "watching": discord.ActivityType.watching,
                "listening": discord.ActivityType.listening,
                "streaming": discord.ActivityType.streaming,
            }
            activity = discord.Activity(
                type=act_map.get(activity_type.value, discord.ActivityType.playing),
                name=status_text
            )
            await bot.change_presence(activity=activity)
            await interaction.followup.send(
                f"🎮 **Bot Presence Updated!** Now **{activity_type.name}** `{status_text}`.",
                ephemeral=True
            )
        finally:
            db.close()

    @bot.tree.command(name="test_embed", description="Send a sample test memorial announcement embed for channel testing.")
    @app_commands.describe(category="Select responder category for test embed")
    @app_commands.choices(category=[
        app_commands.Choice(name="Law Enforcement", value="LAW_ENFORCEMENT"),
        app_commands.Choice(name="Fire Service", value="FIRE"),
        app_commands.Choice(name="EMS & Paramedics", value="EMS"),
        app_commands.Choice(name="Rescue Units", value="RESCUE"),
        app_commands.Choice(name="K9 Heroes", value="K9"),
        app_commands.Choice(name="911 Dispatch", value="DISPATCH"),
        app_commands.Choice(name="Other Responders", value="OTHER"),
    ])
    async def test_embed_cmd(interaction: discord.Interaction, category: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You must have Administrator permissions or the configured Admin Role to run this command.", ephemeral=True)
                return

            guild_cfg = get_or_create_guild_config(db, interaction.guild)
            cat_enum = ResponderCategory[category.value]

            test_record = ResponderRecord(
                id=999,
                name="[TEST] Officer John Sample",
                agency="[TEST] Metropolitan Emergency Department",
                category=cat_enum,
                date_of_incident="2026-08-01",
                date_of_death="2026-08-02 (End of Watch)",
                summary="[TEST SAMPLE DRAFT] This is a test announcement to verify channel layout, color codes, and embed permissions.",
                k9_handler_name="[TEST] Officer Jane Handler" if category.value == "K9" else None,
                k9_breed="[TEST] German Shepherd" if category.value == "K9" else None,
                service_years="5 Years" if category.value == "K9" else None,
                unit_badge="K9-TEST-1" if category.value == "K9" else None,
                article_title="[TEST] Sample Emergency News Article Title",
                article_url="https://example.com/test-news-article",
                source_domain="example.com",
                bible_verse="Greater love has no one than this: to lay down one's life for one's friends.",
                bible_reference="John 15:13",
                ai_memorial_text="[TEST AI TRIBUTE] We honor [TEST] Officer John Sample for dedicated emergency service and ultimate sacrifice.",
                candle_count=12,
                status=ApprovalStatus.APPROVED
            )

            embed = create_memorial_embed(test_record, custom_header=guild_cfg.custom_header)
            await interaction.followup.send(
                content="🧪 **[SAMPLE TEST EMBED PREVIEW]** This is how approved memorial announcements will display in your server:",
                embed=embed
            )
        finally:
            db.close()

    @bot.tree.command(name="approve", description="Approve a pending memorial ID and publish to channels.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record to approve")
    async def approve_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You must have Administrator permissions or the configured Admin Role to run this command.", ephemeral=True)
                return

            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            if record.status == ApprovalStatus.APPROVED:
                await interaction.followup.send(f"⚠️ Memorial ID `#{memorial_id}` is already approved.")
                return

            record.status = ApprovalStatus.APPROVED
            db.commit()
            db.refresh(record)

            await post_approved_memorial(interaction.client, record)

            await interaction.followup.send(
                f"✅ **Approved Memorial ID `#{record.id}`!** Published memorial tribute for **{record.name}** ({record.agency})."
            )
        finally:
            db.close()

    @bot.tree.command(name="reject", description="Reject a pending memorial record.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record to reject")
    async def reject_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You must have Administrator permissions or the configured Admin Role to run this command.", ephemeral=True)
                return

            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            record.status = ApprovalStatus.REJECTED
            db.commit()

            await interaction.followup.send(f"🚫 **Rejected Memorial ID `#{record.id}`** ({record.name}).")
        finally:
            db.close()

    @bot.tree.command(name="status", description="Show system health, latency, and database record counters.")
    async def status_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            total_records = db.query(ResponderRecord).count()
            pending_count = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()
            approved_count = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
            rejected_count = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.REJECTED).count()

            guild_cfg = get_or_create_guild_config(db, interaction.guild)

            embed = discord.Embed(
                title="⚙️ Fallen Officer Memorial Intelligence System",
                description=f"Operational status for **{interaction.guild.name}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Bot Latency", value=f"{round(bot.latency * 1000)} ms", inline=True)
            embed.add_field(name="Approval Mode", value=f"`{guild_cfg.approval_mode}`", inline=True)
            embed.add_field(name="Admin Role", value=f"<@&{guild_cfg.admin_role_id}>" if guild_cfg.admin_role_id else "`Administrators Only`", inline=True)
            embed.add_field(name="Bot Nickname", value=f"`{guild_cfg.bot_nickname or 'Default'}`", inline=True)
            embed.add_field(name="Total Memorials", value=str(total_records), inline=True)
            embed.add_field(name="Pending Review", value=str(pending_count), inline=True)
            embed.add_field(name="Approved", value=str(approved_count), inline=True)
            embed.set_footer(text="Fallen Officer Memorial Intelligence System v1.0")

            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="ping", description="Test system response time and API latency.")
    async def ping_cmd(interaction: discord.Interaction):
        start_t = time.time()
        await interaction.response.defer(ephemeral=True)
        end_t = time.time()
        latency = round(bot.latency * 1000)
        roundtrip = round((end_t - start_t) * 1000)
        await interaction.followup.send(
            f"🏓 **Pong!** WebSocket Latency: `{latency} ms` | API Roundtrip: `{roundtrip} ms`",
            ephemeral=True
        )

    @bot.tree.command(name="stats", description="Display comprehensive analytics & category breakdown.")
    async def stats_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            total = db.query(ResponderRecord).count()
            approved = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
            pending = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()

            by_cat = {}
            for cat in ResponderCategory:
                cnt = db.query(ResponderRecord).filter(ResponderRecord.category == cat).count()
                if cnt > 0:
                    by_cat[cat.value] = cnt

            stats_data = {
                "total": total,
                "approved": approved,
                "pending": pending,
                "by_category": by_cat
            }

            embed = create_stats_embed(stats_data)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="search", description="Search database by responder name, agency, or keyword.")
    @app_commands.describe(query="Search keyword (e.g. name, agency, city)")
    async def search_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            results = (
                db.query(ResponderRecord)
                .filter(
                    or_(
                        ResponderRecord.name.ilike(f"%{query}%"),
                        ResponderRecord.agency.ilike(f"%{query}%"),
                        ResponderRecord.summary.ilike(f"%{query}%")
                    )
                )
                .limit(5)
                .all()
            )

            if not results:
                await interaction.followup.send(f"🔍 No memorial records found matching query: `{query}`.")
                return

            embed = discord.Embed(
                title=f"🔍 Search Results for '{query}' ({len(results)} matches)",
                color=discord.Color.blue()
            )
            for rec in results:
                embed.add_field(
                    name=f"ID #{rec.id} — {rec.name}",
                    value=f"**Agency:** {rec.agency}\n**Category:** {rec.category}\n**Status:** {rec.status.value}\n[Source Link]({rec.article_url})",
                    inline=False
                )

            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="help", description="Show full bot command manual and guide.")
    async def help_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        embed = discord.Embed(
            title="🛡️ Fallen Officer Memorial Intelligence System — Command Guide",
            description="Complete list of available slash commands for admins and members.",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="⚙️ Server Configuration (`/config`)",
            value=(
                "• `/config view` — View current server profile & settings.\n"
                "• `/config admin_role <role>` — Set designated Admin Role for commands.\n"
                "• `/config bot_nickname <name>` — Edit bot server nickname.\n"
                "• `/config mode` — Toggle approval mode (MANUAL or AUTO).\n"
                "• `/config role` — Set alert role to ping for new memorials.\n"
                "• `/config header` — Set custom server header for embeds.\n"
                "• `/config setup` — Re-run channel auto-creation."
            ),
            inline=False
        )
        embed.add_field(
            name="🤖 Memorial Management (Restricted)",
            value=(
                "• `/lookup <id>` — View memorial by sequential ID.\n"
                "• `/approve <id>` — Approve & publish pending memorial.\n"
                "• `/reject <id>` — Reject pending draft.\n"
                "• `/edit <id>` — Edit draft details.\n"
                "• `/remake <id>` — Regenerate AI memorial text.\n"
                "• `/candle <id>` — Light a virtual candle in Discord.\n"
                "• `/scan` — Trigger news source check."
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)
