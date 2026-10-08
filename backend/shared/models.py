"""
SQLAlchemy ORM models for the court monitoring system.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    court_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="other"
    )  # state/federal/bankruptcy/appellate/other
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="all"
    )  # civil/criminal/family/probate/all
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    js_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    css_selector: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    last_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # Relationships
    scan_history: Mapped[list["ScanHistory"]] = relationship(
        "ScanHistory", back_populates="court", cascade="all, delete-orphan"
    )
    changes: Mapped[list["Change"]] = relationship(
        "Change", back_populates="court", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Court id={self.id} name={self.name!r} url={self.url!r}>"


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    court_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courts.id", ondelete="CASCADE"), nullable=False
    )
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )  # success/changed/error/timeout/skipped
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    court: Mapped["Court"] = relationship("Court", back_populates="scan_history")

    def __repr__(self) -> str:
        return (
            f"<ScanHistory id={self.id} court_id={self.court_id} status={self.status!r}>"
        )


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    court_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courts.id", ondelete="CASCADE"), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    old_snapshot_path: Mapped[str] = mapped_column(String(500), nullable=False)
    new_snapshot_path: Mapped[str] = mapped_column(String(500), nullable=False)
    diff_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_is_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ai_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # fees/deadlines/format/e-filing/contact/holiday-closure/new-requirement/removed-requirement/other
    ai_priority: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # high/medium/low
    ai_action: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sharepoint_item_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    email_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new"
    )  # new/in_review/resolved/false_positive
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    court: Mapped["Court"] = relationship("Court", back_populates="changes")

    def __repr__(self) -> str:
        return (
            f"<Change id={self.id} court_id={self.court_id} status={self.status!r}>"
        )


class AlertConfig(Base):
    __tablename__ = "alert_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_recipients: Mapped[str] = mapped_column(
        String(2000), nullable=False, default=""
    )  # comma-separated
    notify_immediately: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notify_digest_time: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # e.g. "08:00"
    min_priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default="low"
    )  # low/medium/high
    ai_filter_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    def __repr__(self) -> str:
        return f"<AlertConfig id={self.id}>"
