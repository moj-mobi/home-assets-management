from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


asset_attachments = Table(
    "asset_attachments", Base.metadata,
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("attachment_id", ForeignKey("attachments.id", ondelete="CASCADE"), primary_key=True),
)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(150))
    model: Mapped[str | None] = mapped_column(String(150))
    serial_number: Mapped[str | None] = mapped_column(String(150))
    purchase_condition: Mapped[str | None] = mapped_column(String(20))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3), default="EUR", server_default="EUR")
    seller: Mapped[str | None] = mapped_column(String(200))
    seller_type: Mapped[str | None] = mapped_column(String(20))
    purchase_country: Mapped[str | None] = mapped_column(String(100))
    product_url: Mapped[str | None] = mapped_column(String(1000))
    invoice_number: Mapped[str | None] = mapped_column(String(150))
    order_number: Mapped[str | None] = mapped_column(String(150))
    location: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str | None] = mapped_column(String(20), default="in_use", server_default="in_use")
    conformity_months: Mapped[int | None] = mapped_column(Integer)
    conformity_start: Mapped[date | None] = mapped_column(Date)
    conformity_end: Mapped[date | None] = mapped_column(Date)
    conformity_source: Mapped[str | None] = mapped_column(String(20))
    warranty_provider: Mapped[str | None] = mapped_column(String(200))
    warranty_months: Mapped[int | None] = mapped_column(Integer)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    warranty_number: Mapped[str | None] = mapped_column(String(150))
    warranty_terms_url: Mapped[str | None] = mapped_column(String(1000))
    warranty_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    attachments: Mapped[list["Attachment"]] = relationship(secondary=asset_attachments, back_populates="assets")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(100), unique=True)
    document_type: Mapped[str] = mapped_column(String(30))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    assets: Mapped[list[Asset]] = relationship(secondary=asset_attachments, back_populates="attachments")


class LocalUser(Base):
    __tablename__ = "local_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    session_id_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
