"""
Discord UI Component Views and Modals.
Provides interactive buttons and modals for one-click approval, editing, candle lighting, and AI eulogies.
"""
import random
import discord
from discord import ui
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ResponderRecord, ApprovalStatus
from app.discord.embeds import create_memorial_embed, create_pending_approval_embed, create_eulogy_embed
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
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send("❌ Record not found.", ephemeral=True)
                return

            record.status = ApprovalStatus.APPROVED
            db.commit()
            db.refresh(record)

            from app.scanner import post_approved_memorial
            await post_approved_memorial(interaction.client, record)

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(content=f"✅ **APPROVED by {interaction.user.name}**", view=self)
            await interaction.followup.send(f"✅ Approved Memorial ID `#{record.id}`!", ephemeral=True)
        finally:
            db.close()

    @ui.button(label="Edit", style=discord.ButtonStyle.blurple, custom_id="edit_btn", emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = EditDraftModal(self.record_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_btn", emoji="❌")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if record:
                record.status = ApprovalStatus.REJECTED
                db.commit()

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(content=f"❌ **REJECTED by {interaction.user.name}**", view=self)
            await interaction.followup.send(f"❌ Rejected Memorial ID `#{self.record_id}`.", ephemeral=True)
        finally:
            db.close()


class MemorialInteractionView(ui.View):
    """
    Interactive View attached to published Discord memorial posts allowing members to light candles & view certificates.
    """

    def __init__(self, record_id: int):
        super().__init__(timeout=None)
        self.record_id = record_id
        cert_url = f"https://fallen-memorial-bot.onrender.com/responders/{record_id}/certificate"
        self.add_item(ui.Button(label="📜 Certificate", url=cert_url, style=discord.ButtonStyle.link))

    @ui.button(label="Light Candle", style=discord.ButtonStyle.gold, custom_id="light_candle_btn", emoji="🕯️")
    async def light_candle_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send("❌ Record not found.", ephemeral=True)
                return

            record.candle_count += 1
            db.commit()
            db.refresh(record)

            embed = create_memorial_embed(record)
            await interaction.message.edit(embed=embed)
            await interaction.followup.send(f"🕯️ You lit a solemn memorial candle for **{record.name}**! Total Candles: **{record.candle_count}**", ephemeral=True)
        finally:
            db.close()

    @ui.button(label="Read Eulogy", style=discord.ButtonStyle.secondary, custom_id="read_eulogy_btn", emoji="📖")
    async def read_eulogy_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        db: Session = SessionLocal()
        try:
            record = db.query(ResponderRecord).filter(ResponderRecord.id == self.record_id).first()
            if not record:
                await interaction.followup.send("❌ Record not found.", ephemeral=True)
                return

            ai_provider = get_ai_provider()
            eulogy_text = await ai_provider.generate_eulogy(record.to_dict())
            embed = create_eulogy_embed(record, eulogy_text)
            await interaction.followup.send(embed=embed, ephemeral=True)
        finally:
            db.close()
