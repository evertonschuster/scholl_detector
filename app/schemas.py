from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class EventOut(BaseModel):
    event_id: str
    room_id: str
    camera_id: str
    timestamp_utc: datetime
    event_type: str
    severity: int
    confidence: float
    zone_id: Optional[str]
    counts: Dict[str, int] = Field(default_factory=dict)
    activity: Dict[str, float] = Field(default_factory=dict)
    track: Dict[str, str] = Field(default_factory=dict)
    requires_review: bool
    privacy: Dict[str, bool] = Field(default_factory=dict)


class SummaryOut(BaseModel):
    room_id: str
    from_ts: datetime
    to_ts: datetime
    total_events: int
    avg_person_count: float
    avg_motion_level: float


class TimeseriesPoint(BaseModel):
    ts_minute: datetime
    value: float
