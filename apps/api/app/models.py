from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
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
