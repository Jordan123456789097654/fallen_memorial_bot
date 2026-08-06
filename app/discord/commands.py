"""
Discord Slash Commands Implementation.
Includes /config command group for multi-server customization and advanced AI & analytics commands.
"""
import io
import csv
import json
import random
import discord
from discord import app_commands
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus, ResponderCategory, GuildConfig
from app.config import settings
from app.discord.embeds import (
    create_memorial_embed,
    create_eulogy_embed,
    create_timeline_embed,
    create_stats_embed,
    create_config_embed
)
from app.discord.channels import setup_memorial_channels, get_or_create_guild_config
from app.scanner import scan_news_sources, post_approved_memorial, load_bible_verses
from app.ai import get_ai_provider
from app.utils.logger import logger


# Define /config command group
class ConfigGroup(app_commands.Group):
    """Server configuration commands for server owners & admins."""

    def __init__(self):
        super().__init__(name="config", description="Configure bot settings for this Discord server.")

    @app_commands.command(name="view", description="View current server profile & settings.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            config = get_or_create_guild_config(db, interaction.guild)
            embed = create_config_embed(interaction.guild, config)
            await interaction.followup.send(embed=embed, ephemeral=True)
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

    # Register /config sub-command group
    bot.tree.add_command(ConfigGroup())

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
            embed.add_field(name="Server Approval Mode", value=f"`{guild_cfg.approval_mode}`", inline=True)
            embed.add_field(name="Connected Guilds", value=str(len(bot.guilds)), inline=True)
            embed.add_field(name="Total Memorials", value=str(total_records), inline=True)
            embed.add_field(name="Pending Review", value=str(pending_count), inline=True)
            embed.add_field(name="Approved", value=str(approved_count), inline=True)
            embed.add_field(name="Rejected", value=str(rejected_count), inline=True)
            embed.set_footer(text="Fallen Officer Memorial Intelligence System v1.0")

            await interaction.followup.send(embed=embed)
        finally:
            db.close()

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

    @bot.tree.command(name="pending", description="List all pending memorial drafts waiting for approval.")
    async def pending_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            pending_list = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).limit(10).all()
            if not pending_list:
                await interaction.followup.send("✅ No pending memorial drafts waiting for review.")
                return

            embed = discord.Embed(
                title=f"📋 Pending Memorial Review Queue ({len(pending_list)} drafts)",
                description="Use `/approve <id>` or `/reject <id>` to review.",
                color=discord.Color.yellow()
            )
            for rec in pending_list:
                embed.add_field(
                    name=f"Memorial ID #{rec.id} — {rec.name}",
                    value=f"**Agency:** {rec.agency} | **Category:** {rec.category.value if hasattr(rec.category, 'value') else rec.category}",
                    inline=False
                )

            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="eulogy", description="Generate an AI-written formal eulogy speech for a responder ID.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record")
    async def eulogy_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            ai_provider = get_ai_provider()
            eulogy_text = await ai_provider.generate_eulogy(record.to_dict())

            embed = create_eulogy_embed(record, eulogy_text)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="timeline", description="Extract an incident timeline from the news article for a responder ID.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record")
    async def timeline_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            ai_provider = get_ai_provider()
            timeline_events = await ai_provider.extract_timeline(record.summary or record.article_title)

            embed = create_timeline_embed(record, timeline_events)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="edit", description="Edit pending draft details (Name, Agency, Date of Death).")
    @app_commands.describe(
        memorial_id="Target memorial ID",
        name="New responder name",
        agency="New agency name",
        date_of_death="New date of death / EOW"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_cmd(
        interaction: discord.Interaction,
        memorial_id: int,
        name: str = None,
        agency: str = None,
        date_of_death: str = None
    ):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            if name:
                record.name = name
            if agency:
                record.agency = agency
            if date_of_death:
                record.date_of_death = date_of_death

            db.commit()
            db.refresh(record)

            embed = create_memorial_embed(record)
            await interaction.followup.send(
                content=f"✏️ **Updated Memorial Draft ID `#{record.id}`:**",
                embed=embed
            )
        finally:
            db.close()

    @bot.tree.command(name="export", description="Export database records as attached JSON or CSV file.")
    @app_commands.describe(file_format="Format to export (JSON or CSV)")
    @app_commands.choices(file_format=[
        app_commands.Choice(name="JSON", value="JSON"),
        app_commands.Choice(name="CSV", value="CSV"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export_cmd(interaction: discord.Interaction, file_format: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            records = db.query(ResponderRecord).order_by(ResponderRecord.id.asc()).all()
            dict_records = [r.to_dict() for r in records]

            if file_format.value == "JSON":
                data_bytes = json.dumps(dict_records, indent=2).encode("utf-8")
                filename = "memorials_export.json"
            else:
                output = io.StringIO()
                if dict_records:
                    writer = csv.DictWriter(output, fieldnames=dict_records[0].keys())
                    writer.writeheader()
                    writer.writerows(dict_records)
                data_bytes = output.getvalue().encode("utf-8")
                filename = "memorials_export.csv"

            file_attachment = discord.File(io.BytesIO(data_bytes), filename=filename)
            await interaction.followup.send(
                content=f"📦 Exported **{len(records)}** memorial records in `{file_format.value}` format:",
                file=file_attachment,
                ephemeral=True
            )
        finally:
            db.close()

    @bot.tree.command(name="scan", description="Trigger an immediate manual news source scan.")
    async def scan_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send("🔍 Starting news feed scan... This may take a few seconds.")
        results = await scan_news_sources(bot=interaction.client)
        await interaction.channel.send(
            f"✅ Scan complete! Scanned {results.get('scanned', 0)} articles. Created {results.get('new_records', 0)} new memorial draft records."
        )

    @bot.tree.command(name="lookup", description="Look up a memorial by ID to view details.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record")
    async def lookup_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            guild_cfg = get_or_create_guild_config(db, interaction.guild)
            embed = create_memorial_embed(record, custom_header=guild_cfg.custom_header)
            await interaction.followup.send(embed=embed)
        finally:
            db.close()

    @bot.tree.command(name="approve", description="Approve a pending memorial ID and publish to channels.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record to approve")
    async def approve_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
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
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            record.status = ApprovalStatus.REJECTED
            db.commit()

            await interaction.followup.send(f"🚫 **Rejected Memorial ID `#{record.id}`** ({record.name}).")
        finally:
            db.close()

    @bot.tree.command(name="remake", description="Re-trigger Gemini AI to regenerate memorial draft text.")
    @app_commands.describe(memorial_id="The integer ID of the memorial record to regenerate")
    async def remake_cmd(interaction: discord.Interaction, memorial_id: int):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == memorial_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{memorial_id}` not found.")
                return

            ai_provider = get_ai_provider()
            verses = load_bible_verses()
            selected_verse = random.choice(verses)

            extracted_data = {
                "name": record.name,
                "agency": record.agency,
                "category": record.category.value if hasattr(record.category, 'value') else record.category,
                "summary": record.summary or record.article_title,
                "date_of_death": record.date_of_death or "End of Watch"
            }

            new_text = await ai_provider.generate_memorial(extracted_data, selected_verse)

            record.bible_verse = selected_verse.get("text")
            record.bible_reference = selected_verse.get("reference")
            record.ai_memorial_text = new_text
            db.commit()
            db.refresh(record)

            guild_cfg = get_or_create_guild_config(db, interaction.guild)
            embed = create_memorial_embed(record, custom_header=guild_cfg.custom_header)
            await interaction.followup.send(
                content=f"🔄 **Regenerated Memorial Draft for ID `#{record.id}`!**",
                embed=embed
            )
        finally:
            db.close()

    @bot.tree.command(name="latest", description="Display the newest approved memorial.")
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
                await interaction.followup.send("ℹ️ No approved memorial records found in database yet.")
                return

            guild_cfg = get_or_create_guild_config(db, interaction.guild)
            embed = create_memorial_embed(record, custom_header=guild_cfg.custom_header)
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
                "• `/config mode` — Toggle server approval mode (MANUAL or AUTO).\n"
                "• `/config role` — Set alert role to ping for new memorials.\n"
                "• `/config header` — Set custom server header for embeds.\n"
                "• `/config setup` — Re-run channel auto-creation."
            ),
            inline=False
        )
        embed.add_field(
            name="🤖 Memorial Management",
            value=(
                "• `/lookup <id>` — View memorial by sequential ID.\n"
                "• `/approve <id>` — Approve & publish pending memorial.\n"
                "• `/reject <id>` — Reject pending draft.\n"
                "• `/edit <id>` — Edit draft details.\n"
                "• `/remake <id>` — Regenerate AI memorial text.\n"
                "• `/scan` — Trigger news source check."
            ),
            inline=False
        )
        embed.add_field(
            name="🧠 Advanced AI & Analytics",
            value=(
                "• `/eulogy <id>` — Generate a formal solemn eulogy speech.\n"
                "• `/timeline <id>` — Extract incident timeline.\n"
                "• `/stats` — Display intelligence statistics & charts.\n"
                "• `/search <query>` — Full-text search across database.\n"
                "• `/export <format>` — Export data as JSON or CSV attachment."
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)
