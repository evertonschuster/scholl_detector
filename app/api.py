from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import load_settings
from .database import Base, get_engine, get_session_factory
from .models import Event, MetricAggregate
from .schemas import EventOut, SummaryOut, TimeseriesPoint

settings = load_settings()
engine = get_engine(settings.database.url)
SessionLocal = get_session_factory(settings.database.url)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Classroom Observables MVP")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/rooms/{room_id}/summary", response_model=SummaryOut)
async def room_summary(
    room_id: str,
    from_ts: datetime = Query(..., alias="from"),
    to_ts: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
) -> SummaryOut:
    events_query = db.query(Event).filter(
        Event.room_id == room_id,
        Event.timestamp_utc >= from_ts,
        Event.timestamp_utc <= to_ts,
    )
    total_events = events_query.count()

    metrics_query = db.query(
        func.avg(MetricAggregate.person_count),
        func.avg(MetricAggregate.motion_level),
    ).filter(
        MetricAggregate.room_id == room_id,
        MetricAggregate.ts_minute >= from_ts,
        MetricAggregate.ts_minute <= to_ts,
    )
    avg_person_count, avg_motion_level = metrics_query.one()

    return SummaryOut(
        room_id=room_id,
        from_ts=from_ts,
        to_ts=to_ts,
        total_events=total_events,
        avg_person_count=avg_person_count or 0.0,
        avg_motion_level=avg_motion_level or 0.0,
    )


@app.get("/rooms/{room_id}/events", response_model=List[EventOut])
async def room_events(
    room_id: str,
    from_ts: datetime = Query(..., alias="from"),
    to_ts: datetime = Query(..., alias="to"),
    event_type: Optional[str] = Query(None, alias="type"),
    db: Session = Depends(get_db),
) -> List[EventOut]:
    query = db.query(Event).filter(
        Event.room_id == room_id,
        Event.timestamp_utc >= from_ts,
        Event.timestamp_utc <= to_ts,
    )
    if event_type:
        query = query.filter(Event.event_type == event_type)

    results = []
    for event in query.order_by(Event.timestamp_utc.desc()).all():
        payload = json.loads(event.payload_json or "{}")
        results.append(
            EventOut(
                event_id=event.event_id,
                room_id=event.room_id,
                camera_id=event.camera_id,
                timestamp_utc=event.timestamp_utc,
                event_type=event.event_type,
                severity=event.severity,
                confidence=event.confidence,
                zone_id=event.zone_id,
                counts=payload.get("counts", {}),
                activity=payload.get("activity", {}),
                track=payload.get("track", {}),
                requires_review=event.requires_review,
                privacy=payload.get("privacy", {}),
            )
        )
    return results


@app.get("/rooms/{room_id}/timeseries", response_model=List[TimeseriesPoint])
async def room_timeseries(
    room_id: str,
    metric: str,
    from_ts: datetime = Query(..., alias="from"),
    to_ts: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
) -> List[TimeseriesPoint]:
    if metric not in {"person_count", "motion_level"}:
        return []
    column = MetricAggregate.person_count if metric == "person_count" else MetricAggregate.motion_level
    query = db.query(MetricAggregate.ts_minute, column).filter(
        MetricAggregate.room_id == room_id,
        MetricAggregate.ts_minute >= from_ts,
        MetricAggregate.ts_minute <= to_ts,
    )
    return [TimeseriesPoint(ts_minute=ts, value=value or 0.0) for ts, value in query.all()]
