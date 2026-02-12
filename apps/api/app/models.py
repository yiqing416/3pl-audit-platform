from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
from .db import Base

class InvoiceUpload(Base):
    __tablename__ = "invoice_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )
    headers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    field_map_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice_uploads.id"), index=True)

    fee_type_raw: Mapped[str] = mapped_column(String(255))
    amount_raw: Mapped[str] = mapped_column(String(50))

    order_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tracking_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    raw_row_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    invoice: Mapped["InvoiceUpload"] = relationship(back_populates="line_items")
    row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fee_type_norm: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

class FeeTypeMap(Base):
    __tablename__ = "fee_type_maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255))
    match_type: Mapped[str] = mapped_column(String(20), default="contains")  # contains|regex|exact
    normalized_type: Mapped[str] = mapped_column(String(128))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

