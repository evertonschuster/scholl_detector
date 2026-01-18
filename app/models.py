from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from .database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String, default=lambda: str(uuid.uuid4()), unique=True, index=True)
    room_id = Column(String, index=True)
    camera_id = Column(String, index=True)
    timestamp_utc = Column(DateTime, index=True, default=datetime.utcnow)
    event_type = Column(String, index=True)
    severity = Column(Integer, default=1)
    confidence = Column(Float, default=0.0)
    zone_id = Column(String)
    counts_persons = Column(Integer, default=0)
    motion_level = Column(Float, default=0.0)
    track_id = Column(String)
    requires_review = Column(Boolean, default=False)
    privacy_faces_blurred = Column(Boolean, default=True)
    privacy_frame_stored = Column(Boolean, default=False)
    schema_version = Column(String, default="1.0")
    payload_json = Column(Text)


class MetricAggregate(Base):
    __tablename__ = "metric_aggregates"

    id = Column(Integer, primary_key=True)
    room_id = Column(String, index=True)
    camera_id = Column(String, index=True)
    zone_id = Column(String)
    ts_minute = Column(DateTime, index=True)
    person_count = Column(Float, default=0.0)
    motion_level = Column(Float, default=0.0)
    event_counts_json = Column(Text)
