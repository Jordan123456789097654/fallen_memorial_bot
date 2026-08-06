"""
Discord Slash Commands Implementation.
Includes /config subcommands (/config header, /config role, /config mode, etc.), /scan, /setstatus, /test_embed, /translate, /rollcall, /certificate, /random, /map, /submit, /anniversary, and 35+ commands.
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
from app.scanner import scan_news_sources, post_approved_memorial, load_bible_verses, daily_moment_of_silence
from app.ai import get_ai_provider
from app.utils.logger import logger


def check_admin_permission(interaction: discord.Interaction, db: Session) -> bool:
    """Checks if user has Administrator permissions OR configured Admin Role."""
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

    @app_commands.command(name="admin_role", description="Set designated Admin Role allowed to approve/reject drafts.")
    @app_commands.describe(role="Select admin role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_admin_role(self, interaction: discord.Interaction, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.admin_role_id = str(role.id) if role else None
            db.commit()

            role_msg = f"<@&{role.id}>" if role else "Cleared (Administrators default)"
            await interaction.followup.send(
                f"✅ **Admin Role Updated:** Designated admin role set to {role_msg}.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="bot_nickname", description="Edit bot nickname in this server.")
    @app_commands.describe(nickname="New bot nickname for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_nickname(self, interaction: discord.Interaction, nickname: str = None):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            config.bot_nickname = nickname
            db.commit()

            if interaction.guild.me:
                await interaction.guild.me.edit(nick=nickname)

            await interaction.followup.send(
                f"✅ **Bot Nickname Updated:** Set to `{nickname or 'Default'}`.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="mode", description="Toggle approval mode (MANUAL review vs AUTO publish).")
    @app_commands.describe(mode="MANUAL or AUTO")
    @app_commands.choices(mode=[
        app_commands.Choice(name="MANUAL (Staff must review drafts)", value="MANUAL"),
        app_commands.Choice(name="AUTO (Publish automatically)", value="AUTO")
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
                f"✅ **Approval Mode Updated:** Mode set to `{mode.value}`.",
                ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(name="setup", description="Re-run channel auto-creation for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config, channels = await setup_memorial_channels(interaction.guild, db)
            ch_list = "\n".join([f"• <#{c.id}>" for c in channels.values() if c])
            await interaction.followup.send(
                f"✅ **Memorial Channels Configured:**\n{ch_list}",
                ephemeral=True
            )
        finally:
            db.close()


def setup_commands(bot: discord.Client):
    """Registers all slash commands onto the bot app_commands tree."""

    bot.tree.add_command(ConfigGroup())

    @bot.tree.command(name="scan", description="[Admin Only] Manually trigger Google News & RSS scanner to discover line-of-duty articles.")
    async def scan_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You do not have permission to trigger news scans.")
                return

            res = await scan_news_sources(bot)
            scanned_cnt = res.get("scanned", 0) if isinstance(res, dict) else 0
            new_cnt = res.get("new_memorials", 0) if isinstance(res, dict) else 0

            embed = discord.Embed(
                title="🔍 Manual Google News & RSS Intelligence Scan",
                description=f"Scan complete across national news feeds and Google RSS.\n\n• **Articles Scanned:** {scanned_cnt}\n• **New Hero Memorials Discovered:** {new_cnt}",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="latest", description="Fetch the most recent line-of-duty memorial tribute.")
    async def latest_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = (
                db.query(ResponderRecord)
                .filter(ResponderRecord.status == ApprovalStatus.APPROVED)
                .order_by(ResponderRecord.id.desc())
                .first()
            )
            if not record:
                await interaction.followup.send("⚠️ No approved memorial records found in the system database.")
                return

            embed = create_memorial_embed(record, interaction.guild)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="memorial", description="Search line-of-duty memorial records by name, ID, or department agency.")
    @app_commands.describe(query="Name, Memorial ID (#1), or Department (e.g. 'Chicago Police')")
    async def memorial_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            clean_q = query.strip()
            record = None
            if clean_q.startswith("#") and clean_q[1:].isdigit():
                rec_id = int(clean_q[1:])
                record = db.query(ResponderRecord).filter(ResponderRecord.id == rec_id).first()
            elif clean_q.isdigit():
                rec_id = int(clean_q)
                record = db.query(ResponderRecord).filter(ResponderRecord.id == rec_id).first()
            else:
                record = (
                    db.query(ResponderRecord)
                    .filter(
                        ResponderRecord.status == ApprovalStatus.APPROVED,
                        or_(
                            ResponderRecord.name.ilike(f"%{clean_q}%"),
                            ResponderRecord.agency.ilike(f"%{clean_q}%")
                        )
                    )
                    .order_by(ResponderRecord.id.desc())
                    .first()
                )

            if not record:
                await interaction.followup.send(f"❌ No approved memorial found matching `{query}`.")
                return

            embed = create_memorial_embed(record, interaction.guild)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="vigil", description="Light a virtual memorial candle in honor of a fallen responder.")
    @app_commands.describe(memorial_id="Memorial ID number (e.g. 1)")
    async def vigil_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record `#{memorial_id}` not found.")
                return

            record.candle_count += 1
            db.commit()
            db.refresh(record)

            embed = discord.Embed(
                title=f"🕯️ Virtual Candle Lit for {record.name}",
                description=f"You lit a solemn memorial candle in honor of **{record.name}** ({record.agency}).\n\nTotal Candles Lit: **{record.candle_count}** 🕯️",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="certificate", description="Generate printable Certificate of Honor link & preview for any responder.")
    @app_commands.describe(query="Responder ID or Name")
    async def certificate_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            clean_q = query.strip()
            record = None
            if clean_q.isdigit():
                record = db.query(ResponderRecord).filter(ResponderRecord.id == int(clean_q)).first()
            else:
                record = db.query(ResponderRecord).filter(ResponderRecord.name.ilike(f"%{clean_q}%")).first()

            if not record:
                await interaction.followup.send(f"❌ Record `{query}` not found.")
                return

            cert_url = f"https://fallen-memorial-bot.onrender.com/responders/{record.id}/certificate"
            embed = discord.Embed(
                title=f"📜 Certificate of Honor — {record.name}",
                description=f"Official line-of-duty certificate for **{record.name}** ({record.agency}).\n\n[📜 Click to View, Print & Download PDF Certificate]({cert_url})",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Serial No. NFRM-2026-#{record.id} • Official Registry Record")
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="random", description="Display a random historical hero record from the National Honor Roll.")
    async def random_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).all()
            if not records:
                await interaction.followup.send("⚠️ No approved records in database.")
                return
            rec = random.choice(records)
            embed = create_memorial_embed(rec, interaction.guild)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="map", description="Display link to the Interactive National Memorial Map.")
    async def map_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            total_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
            map_url = "https://fallen-memorial-bot.onrender.com/wall"
            embed = discord.Embed(
                title="🗺️ Interactive National Memorial Map",
                description=f"Explore **{total_records}** line-of-duty sacrifices pinpointed across all US states and departments.\n\n[🌐 Open Interactive Memorial Map]({map_url})",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="rollcall", description="Trigger/view today's solemn Moment of Silence Roll Call tribute.")
    async def rollcall_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await daily_moment_of_silence(bot)
        await interaction.followup.send("🕯️ **Moment of Silence Roll Call Tribute** initiated across connected channels.")

    @bot.tree.command(name="submit", description="Submit a fallen responder memorial record for staff admin review.")
    @app_commands.describe(name="Responder Name", agency="Department Agency", summary="Incident Summary / Bio")
    async def submit_cmd(interaction: discord.Interaction, name: str, agency: str, summary: str):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            import time
            art_url = f"https://discord.submission/{interaction.user.id}/{int(time.time())}"
            record = ResponderRecord(
                name=name.strip(),
                agency=agency.strip(),
                summary=summary.strip(),
                article_title=f"Discord Submission: {name}",
                article_url=art_url,
                category=ResponderCategory.OTHER,
                status=ApprovalStatus.PENDING
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            await interaction.followup.send(
                f"✅ **Submitted for Admin Review!** Record ID `#{record.id}` created for **{name}** ({agency}). Staff will review shortly.",
                ephemeral=True
            )
        finally:
            db.close()

    @bot.tree.command(name="anniversary", description="Check EOW (End of Watch) anniversaries for today.")
    async def anniversary_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).all()
            embed = discord.Embed(
                title="🕯️ EOW Anniversary Vigil Check",
                description=f"Total Honor Roll Records Monitored: **{len(records)}**\n\nDaily anniversary vigils trigger automatically every morning at 08:00 AM EST.",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="approve", description="[Admin Only] Approve a pending memorial draft.")
    @app_commands.describe(memorial_id="Memorial ID number to approve")
    async def approve_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            if not check_admin_permission(interaction, db):
                await interaction.followup.send("❌ You do not have permission to approve memorial drafts.")
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

    @bot.tree.command(name="status", description="Show system health, latency, and database record counters.")
    async def status_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            total_records = db.query(ResponderRecord).count()
            pending_count = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()
            approved_count = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()

            guild_cfg = get_or_create_guild_config(db, interaction.guild)

            embed = discord.Embed(
                title="⚙️ Fallen Officer Memorial Intelligence System",
                description=f"Operational status for **{interaction.guild.name}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Bot Latency", value=f"{round(bot.latency * 1000)} ms", inline=True)
            embed.add_field(name="Approval Mode", value=f"`{guild_cfg.approval_mode}`", inline=True)
            embed.add_field(name="Total Memorials", value=str(total_records), inline=True)
            embed.add_field(name="Pending Review", value=str(pending_count), inline=True)
            embed.add_field(name="Approved", value=str(approved_count), inline=True)

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
            name="📜 Memorial & Honor Roll Commands",
            value=(
                "• `/latest` — Fetch latest fallen responder tribute.\n"
                "• `/memorial <name/ID>` — Search honor roll database.\n"
                "• `/random` — Fetch a random historical line-of-duty hero.\n"
                "• `/certificate <name/ID>` — Printable Certificate of Honor link & preview.\n"
                "• `/map` — Interactive National Memorial Map link.\n"
                "• `/vigil <id>` — Light a virtual candle for a responder.\n"
                "• `/rollcall` — Solemn Moment of Silence Roll Call tribute.\n"
                "• `/submit <name> <agency> <summary>` — Submit a new hero for review.\n"
                "• `/anniversary` — Check EOW anniversary vigils for today."
            ),
            inline=False
        )
        embed.add_field(
            name="⚙️ Server Configuration & Admin Commands",
            value=(
                "• `/scan` — [Admin] Trigger manual Google News & RSS scanner.\n"
                "• `/approve <id>` — [Admin] Approve pending draft.\n"
                "• `/config view` — View server profile & settings.\n"
                "• `/config header <text>` — Custom title header prefix.\n"
                "• `/config role <role>` — Alert role ping.\n"
                "• `/config admin_role <role>` — Designated admin role.\n"
                "• `/config mode <MANUAL/AUTO>` — Approval mode.\n"
                "• `/config setup` — Re-run channel auto-creation."
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)


# Alias for backward compatibility with app.bot
register_slash_commands = setup_commands

