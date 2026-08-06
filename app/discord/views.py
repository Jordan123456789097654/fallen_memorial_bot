"""
Discord UI Component Views and Modals.
Provides interactive buttons and modals for one-click approval, editing, and AI regeneration in #bot-logs.
"""
import random
import discord
from discord import ui
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus
from app.discord.embeds import create_memorial_embed, create_pending_approval_embed
from app.scanner import post_approved_memorial, load_bible_verses
from app.ai import get_ai_provider
from app.utils.logger import logger


class EditDraftModal(ui.Modal, title="✏️ Edit Memorial Draft Details"):
    """Pop-up modal allowing admins to edit draft fields directly inside Discord."""

    def __init__(self, record_id: int):
        super().__init__()
        self.record_id = record_id

        db: Session = SessionLocal()
        record = db.query(ResponderRecord).filter(ResponderRecord.id == record_id).first()
        db.close()

        self.name_input = ui.TextInput(
            label="Responder Name",
            default=record.name if record else "",
            placeholder="e.g. Officer John Doe / K9 Rex",
            max_length=255,
            required=True
        )

        self.agency_input = ui.TextInput(
            label="Agency Name",
            default=record.agency if record else "",
            placeholder="e.g. Metro Police Department",
            max_length=255,
            required=True
        )

        self.date_input = ui.TextInput(
            label="Date of Death / End of Watch",
            default=record.date_of_death if record else "",
            placeholder="e.g. 2026-08-01",
            max_length=100,
            required=False
        )

        self.summary_input = ui.TextInput(
            label="Incident Summary",
            default=record.summary if record else "",
            style=discord.TextStyle.paragraph,
            placeholder="Summary of service and incident...",
            max_length=1000,
            required=False
        )

        self.add_item(self.name_input)
        self.add_item(self.agency_input)
        self.add_item(self.date_input)
        self.add_item(self.summary_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send(f"❌ Memorial Record ID `#{self.record_id}` not found.", ephemeral=True)
                return

            record.name = self.name_input.value.strip()
            record.agency = self.agency_input.value.strip()
            record.date_of_death = self.date_input.value.strip()
            record.summary = self.summary_input.value.strip()

            db.commit()
            db.refresh(record)

            embed = create_pending_approval_embed(record)
            await interaction.message.edit(embed=embed)
            await interaction.followup.send(f"✅ **Updated Memorial Draft ID `#{record.id}`!**", ephemeral=True)
        finally:
            db.close()


class PendingReviewView(ui.View):
    """
    Interactive View with One-Click Component Buttons attached to pending review embeds.
    """

    def __init__(self, record_id: int):
        super().__init__(timeout=None)
        self.record_id = record_id

    @ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_btn", emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send(f"❌ Record `#{self.record_id}` not found.")
                return

            if record.status == ApprovalStatus.APPROVED:
                await interaction.followup.send(f"⚠️ Record `#{self.record_id}` is already approved.")
                return

            record.status = ApprovalStatus.APPROVED
            db.commit()
            db.refresh(record)

            await post_approved_memorial(interaction.client, record)

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            await interaction.followup.send(
                f"✅ **Approved & Published Memorial ID `#{record.id}`** for **{record.name}** ({record.agency})!"
            )
        finally:
            db.close()

    @ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_btn", emoji="❌")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=False)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if record:
                record.status = ApprovalStatus.REJECTED
                db.commit()

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            await interaction.followup.send(f"🚫 **Rejected Memorial Draft ID `#{self.record_id}`.**")
        finally:
            db.close()

    @ui.button(label="Edit Draft", style=discord.ButtonStyle.blurple, custom_id="edit_btn", emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = EditDraftModal(self.record_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="Regenerate AI", style=discord.ButtonStyle.gray, custom_id="remake_btn", emoji="🔄")
    async def remake_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send(f"❌ Record `#{self.record_id}` not found.", ephemeral=True)
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

            embed = create_pending_approval_embed(record)
            await interaction.message.edit(embed=embed)

            await interaction.followup.send(f"🔄 **Regenerated AI memorial draft for ID `#{record.id}`!**", ephemeral=True)
        finally:
            db.close()
