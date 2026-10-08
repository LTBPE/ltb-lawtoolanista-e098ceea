"""
Pydantic schemas for API request/response validation.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Court schemas
# ---------------------------------------------------------------------------


class CourtBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=2048)
    court_type: str = Field(default="other")
    state: str | None = Field(default=None, max_length=2)
    category: str = Field(default="all")
    active: bool = True
    js_required: bool = False
    css_selector: str | None = Field(default=None, max_length=500)
    notes: str | None = None

    @field_validator("court_type")
    @classmethod
    def validate_court_type(cls, v: str) -> str:
        allowed = {"state", "federal", "bankruptcy", "appellate", "other"}
        if v not in allowed:
            raise ValueError(f"court_type must be one of {allowed}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = {"civil", "criminal", "family", "probate", "all"}
        if v not in allowed:
            raise ValueError(f"category must be one of {allowed}")
        return v


class CourtCreate(CourtBase):
    pass


class CourtUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    court_type: str | None = None
    state: str | None = Field(default=None, max_length=2)
    category: str | None = None
    active: bool | None = None
    js_required: bool | None = None
    css_selector: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class ScanHistoryOut(BaseModel):
    id: int
    court_id: int
    scanned_at: datetime
    content_hash: str | None
    status: str
    error_message: str | None
    response_time_ms: int | None

    model_config = {"from_attributes": True}


class CourtOut(CourtBase):
    id: int
    last_scanned_at: datetime | None
    last_content_hash: str | None
    last_changed_at: datetime | None
    consecutive_errors: int
    created_at: datetime
    updated_at: datetime | None
    recent_scans: list[ScanHistoryOut] = []

    model_config = {"from_attributes": True}


class CourtListOut(BaseModel):
    items: list[CourtOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Change schemas
# ---------------------------------------------------------------------------


class ChangeStatusUpdate(BaseModel):
    status: str
    reviewed_by: str | None = None
    resolution_notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"new", "in_review", "resolved", "false_positive"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class ChangeOut(BaseModel):
    id: int
    court_id: int
    detected_at: datetime
    old_snapshot_path: str
    new_snapshot_path: str
    diff_text: str | None
    diff_line_count: int
    ai_is_relevant: bool | None
    ai_summary: str | None
    ai_category: str | None
    ai_priority: str | None
    ai_action: str | None
    sharepoint_item_id: str | None
    email_sent: bool
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    resolution_notes: str | None
    court_name: str | None = None
    court_url: str | None = None

    model_config = {"from_attributes": True}


class ChangeListOut(BaseModel):
    items: list[ChangeOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Dashboard schema
# ---------------------------------------------------------------------------


class DashboardOut(BaseModel):
    total_courts: int
    active_courts: int
    scanned_today: int
    scanned_this_week: int
    changes_new: int
    changes_this_week: int
    error_count: int
    last_scan_at: datetime | None


# ---------------------------------------------------------------------------
# AlertConfig schemas
# ---------------------------------------------------------------------------


class AlertConfigOut(BaseModel):
    id: int
    email_recipients: str
    notify_immediately: bool
    notify_digest_time: str | None
    min_priority: str
    ai_filter_enabled: bool

    model_config = {"from_attributes": True}


class AlertConfigUpdate(BaseModel):
    email_recipients: str | None = None
    notify_immediately: bool | None = None
    notify_digest_time: str | None = None
    min_priority: str | None = None
    ai_filter_enabled: bool | None = None

    @field_validator("min_priority")
    @classmethod
    def validate_min_priority(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"low", "medium", "high"}
        if v not in allowed:
            raise ValueError(f"min_priority must be one of {allowed}")
        return v


# ---------------------------------------------------------------------------
# Health check schema
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str
    database: str
    storage: str
    version: str = "1.0.0"
