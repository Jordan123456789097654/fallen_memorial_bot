"""
SQLAlchemy database models for Responder Records, Condolences, Candle Logs, Webhooks, Family Claims, and Multi-Guild Configurations.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base


class ResponderCategory(str, enum.Enum):
    LAW_ENFORCEMENT = "LAW_ENFORCEMENT"
    FIRE = "FIRE"
    EMS = "EMS"
    RESCUE = "RESCUE"
    K9 = "K9"
    DISPATCH = "DISPATCH"
    OTHER = "OTHER"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ResponderRecord(Base):
    __tablename__ = "responder_records"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Responder Information
    name = Column(String(255), nullable=False, default="Unknown Hero")
    agency = Column(String(255), nullable=False, default="Unknown Agency")
    category = Column(Enum(ResponderCategory), nullable=False, default=ResponderCategory.OTHER)
    date_of_incident = Column(String(100), nullable=True)
    date_of_death = Column(String(100), nullable=True)
    summary = Column(Text, nullable=True)

    # Map Coordinates & Photo
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    photo_url = Column(String(1000), nullable=True)

    # Family Claim Portal
    claimed_by_family = Column(Boolean, default=False)
    family_contact = Column(String(255), nullable=True)

    # K9 Details
    k9_handler_name = Column(String(255), nullable=True)
    k9_breed = Column(String(100), nullable=True)
    service_years = Column(String(100), nullable=True)
    unit_badge = Column(String(100), nullable=True)

    # News Source Details
    article_title = Column(String(500), nullable=False)
    article_url = Column(String(1000), nullable=False, unique=True, index=True)
    source_domain = Column(String(255), nullable=True)

    # AI Memorial Details
    bible_verse = Column(Text, nullable=True)
    bible_reference = Column(String(100), nullable=True)
    ai_memorial_text = Column(Text, nullable=True)

    # Virtual Candles
    candle_count = Column(Integer, default=0, nullable=False)

    # Workflow & Tracking
    status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    discord_message_id = Column(String(100), nullable=True)
    discord_channel_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    condolences = relationship("Condolence", back_populates="responder", cascade="all, delete-orphan")
    candle_logs = relationship("CandleLog", back_populates="responder", cascade="all, delete-orphan")
    family_claims = relationship("FamilyClaim", back_populates="responder", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "memorial_id": f"#{self.id}",
            "name": self.name,
            "agency": self.agency,
            "category": self.category.value if isinstance(self.category, enum.Enum) else self.category,
            "date_of_incident": self.date_of_incident,
            "date_of_death": self.date_of_death,
            "summary": self.summary,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "photo_url": self.photo_url,
            "claimed_by_family": self.claimed_by_family,
            "k9_handler_name": self.k9_handler_name,
            "k9_breed": self.k9_breed,
            "service_years": self.service_years,
            "unit_badge": self.unit_badge,
            "article_title": self.article_title,
            "article_url": self.article_url,
            "source_domain": self.source_domain,
            "bible_verse": self.bible_verse,
            "bible_reference": self.bible_reference,
            "ai_memorial_text": self.ai_memorial_text,
            "candle_count": self.candle_count,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Condolence(Base):
    __tablename__ = "condolences"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    record_id = Column(Integer, ForeignKey("responder_records.id"), nullable=False, index=True)
    author_name = Column(String(255), nullable=False, default="Anonymous Visitor")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    responder = relationship("ResponderRecord", back_populates="condolences")

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "author_name": self.author_name,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FamilyClaim(Base):
    __tablename__ = "family_claims"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    record_id = Column(Integer, ForeignKey("responder_records.id"), nullable=False, index=True)
    claimer_name = Column(String(255), nullable=False)
    relationship_type = Column(String(100), nullable=False)
    claimer_email = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)

    responder = relationship("ResponderRecord", back_populates="family_claims")

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "claimer_name": self.claimer_name,
            "relationship_type": self.relationship_type,
            "claimer_email": self.claimer_email,
            "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CandleLog(Base):
    __tablename__ = "candle_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    record_id = Column(Integer, ForeignKey("responder_records.id"), nullable=False, index=True)
    client_ip = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    responder = relationship("ResponderRecord", back_populates="candle_logs")


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    guild_id = Column(String(100), nullable=True, index=True)
    url = Column(String(1000), nullable=False, unique=True, index=True)
    secret = Column(String(255), nullable=True)
    category_filter = Column(String(50), nullable=False, default="ALL")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "url": self.url,
            "category_filter": self.category_filter,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    guild_id = Column(String(100), primary_key=True, index=True)
    guild_name = Column(String(255), nullable=False, default="Unknown Server")
    approval_mode = Column(String(50), nullable=False, default="MANUAL")
    alert_role_id = Column(String(100), nullable=True)
    admin_role_id = Column(String(100), nullable=True)
    category_name = Column(String(100), nullable=False, default="Memorials")
    custom_header = Column(String(255), nullable=True)
    bot_nickname = Column(String(100), nullable=True)
    
    enable_webhooks = Column(Boolean, default=True)
    enable_social = Column(Boolean, default=True)
    enable_keep_alive = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "approval_mode": self.approval_mode,
            "alert_role_id": self.alert_role_id,
            "admin_role_id": self.admin_role_id,
            "category_name": self.category_name,
            "custom_header": self.custom_header,
            "bot_nickname": self.bot_nickname,
            "enable_webhooks": self.enable_webhooks,
            "enable_social": self.enable_social,
            "enable_keep_alive": self.enable_keep_alive,
            "is_enabled": self.is_enabled,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
