from __future__ import annotations

import importlib
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict, Iterable, List, Optional, Tuple

import numpy as np

from .config import AppConfig, CameraConfig, RoomConfig
from .models import Event, MetricAggregate
from .queue import EventPublisher

if importlib.util.find_spec("cv2"):
    import cv2  # type: ignore
else:  # pragma: no cover - optional dependency
    cv2 = None

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]
    confidence: float


@dataclass
class Track:
    track_id: str
    bbox: Tuple[int, int, int, int]
    last_seen: datetime


class PersonDetector:
    def __init__(self):
        self._model = None
        if importlib.util.find_spec("ultralytics"):
            from ultralytics import YOLO  # type: ignore

            try:
                self._model = YOLO("yolov8n.pt")
                logger.info("Loaded YOLOv8n model")
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("YOLOv8n load failed, using stub detector: %s", exc)
        else:  # pragma: no cover - optional dependency
            logger.warning("YOLOv8 not available, using stub detector")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self._model is None:
            return []
        results = self._model.predict(source=frame, verbose=False)
        detections = []
        for result in results:
            for box in result.boxes:
                if int(box.cls[0]) != 0:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append(Detection(bbox=(x1, y1, x2, y2), confidence=float(box.conf[0])))
        return detections


class SimpleTracker:
    def __init__(self, max_distance: float = 80.0, max_age_seconds: int = 3):
        self._tracks: Dict[str, Track] = {}
        self._max_distance = max_distance
        self._max_age = timedelta(seconds=max_age_seconds)

    def update(self, detections: List[Detection]) -> List[Track]:
        now = datetime.utcnow()
        updated_tracks: Dict[str, Track] = {}

        unmatched = detections.copy()
        for track_id, track in self._tracks.items():
            if now - track.last_seen > self._max_age:
                continue
            matched_detection = None
            for detection in unmatched:
                if self._distance(track.bbox, detection.bbox) < self._max_distance:
                    matched_detection = detection
                    break
            if matched_detection:
                unmatched.remove(matched_detection)
                updated_tracks[track_id] = Track(
                    track_id=track_id,
                    bbox=matched_detection.bbox,
                    last_seen=now,
                )

        for detection in unmatched:
            track_id = str(uuid.uuid4())
            updated_tracks[track_id] = Track(track_id=track_id, bbox=detection.bbox, last_seen=now)

        self._tracks = updated_tracks
        return list(updated_tracks.values())

    @staticmethod
    def _distance(bbox_a: Tuple[int, int, int, int], bbox_b: Tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b
        acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
        return float(np.hypot(acx - bcx, acy - bcy))


def point_in_polygon(point: Tuple[float, float], polygon: Iterable[Iterable[float]]) -> bool:
    x, y = point
    inside = False
    poly = list(polygon)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-6) + x1):
            inside = not inside
    return inside


class StreamProcessor:
    def __init__(
        self,
        room: RoomConfig,
        camera: CameraConfig,
        app_config: AppConfig,
        session_factory,
        publisher: EventPublisher,
    ):
        self.room = room
        self.camera = camera
        self.app_config = app_config
        self.session_factory = session_factory
        self.publisher = publisher
        self.detector = PersonDetector()
        self.tracker = SimpleTracker()
        self._last_frame = None
        self._last_flow_ts = None
        self._activity_window: Deque[float] = deque(maxlen=30)
        self._count_window: Deque[int] = deque(maxlen=30)
        self._track_window: Dict[str, Deque[Tuple[datetime, Tuple[int, int, int, int]]]] = defaultdict(
            lambda: deque(maxlen=15)
        )
        self._session_start = datetime.utcnow()

    def run(self) -> None:
        if cv2 is None:
            raise RuntimeError("opencv-python is required for stream processing")
        cap = cv2.VideoCapture(self.camera.rtsp_url)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open stream {self.camera.rtsp_url}")

        interval = 1.0 / max(1, self.camera.fps)
        while True:
            start = time.time()
            ret, frame = cap.read()
            if not ret:
                logger.warning("Stream read failed for %s, reconnecting", self.camera.camera_id)
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(self.camera.rtsp_url)
                continue
            self.process_frame(frame)
            elapsed = time.time() - start
            time.sleep(max(0.0, interval - elapsed))

    def process_frame(self, frame: np.ndarray) -> None:
        now = datetime.utcnow()
        if now - self._session_start >= timedelta(minutes=self.app_config.track_reset_minutes):
            self.tracker = SimpleTracker()
            self._track_window.clear()
            self._session_start = now
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections)
        motion_level = self._compute_motion(frame, now)
        self._activity_window.append(motion_level)
        self._count_window.append(len(tracks))

        per_zone_counts = self._count_by_zone(tracks)
        self._emit_metrics(now, per_zone_counts, motion_level)
        self._emit_events(now, tracks, per_zone_counts, motion_level)

    def _compute_motion(self, frame: np.ndarray, now: datetime) -> float:
        if cv2 is None:
            return 0.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._last_frame is None:
            self._last_frame = gray
            self._last_flow_ts = now
            return 0.0
        flow = cv2.calcOpticalFlowFarneback(
            self._last_frame,
            gray,
            None,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )
        magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        motion_level = float(np.mean(magnitude))
        self._last_frame = gray
        self._last_flow_ts = now
        return motion_level

    def _count_by_zone(self, tracks: List[Track]) -> Dict[str, int]:
        counts = {zone.zone_id: 0 for zone in self.camera.zones}
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            for zone in self.camera.zones:
                if point_in_polygon((cx, cy), zone.polygon):
                    counts[zone.zone_id] += 1
        return counts

    def _emit_metrics(self, now: datetime, counts: Dict[str, int], motion_level: float) -> None:
        minute_ts = now.replace(second=0, microsecond=0)
        with self.session_factory() as session:
            for zone_id, count in counts.items():
                existing = (
                    session.query(MetricAggregate)
                    .filter_by(
                        room_id=self.room.room_id,
                        camera_id=self.camera.camera_id,
                        zone_id=zone_id,
                        ts_minute=minute_ts,
                    )
                    .first()
                )
                if existing:
                    existing.person_count = (existing.person_count + count) / 2
                    existing.motion_level = (existing.motion_level + motion_level) / 2
                else:
                    self._publish_metric_event(
                        now,
                        zone_id,
                        count,
                        motion_level,
                        event_type="person_count",
                    )
                    self._publish_metric_event(
                        now,
                        zone_id,
                        count,
                        motion_level,
                        event_type="activity_level",
                    )
                    session.add(
                        MetricAggregate(
                            room_id=self.room.room_id,
                            camera_id=self.camera.camera_id,
                            zone_id=zone_id,
                            ts_minute=minute_ts,
                            person_count=float(count),
                            motion_level=motion_level,
                            event_counts_json=json.dumps({}),
                        )
                    )
            session.commit()

    def _publish_metric_event(
        self,
        now: datetime,
        zone_id: str,
        count: int,
        motion_level: float,
        event_type: str,
    ) -> None:
        payload = {
            "schema_version": "1.0",
            "event_id": str(uuid.uuid4()),
            "room_id": self.room.room_id,
            "camera_id": self.camera.camera_id,
            "timestamp_utc": now.isoformat(),
            "event_type": event_type,
            "severity": 1,
            "confidence": 1.0,
            "zone_id": zone_id,
            "counts": {"persons": count},
            "activity": {"motion_level": motion_level},
            "track": {"ephemeral_track_id": "", "persist_scope": "session_only"},
            "requires_review": False,
            "privacy": {"faces_blurred": True, "frame_stored": False},
            "debug": {"model_versions": {"detector": "yolov8n" if self.detector else "stub"}},
        }
        routing_key = f"classroom.{self.room.room_id}.{event_type}"
        self.publisher.publish(routing_key, payload)

    def _emit_events(
        self,
        now: datetime,
        tracks: List[Track],
        counts: Dict[str, int],
        motion_level: float,
    ) -> None:
        if not tracks:
            return

        avg_motion = float(np.mean(self._activity_window)) if self._activity_window else 0.0
        avg_count = float(np.mean(self._count_window)) if self._count_window else 0.0
        possible_crowd = avg_count > 0 and len(tracks) > avg_count * 1.6 and motion_level > avg_motion * 1.5

        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            width = max(1, x2 - x1)
            height = max(1, y2 - y1)
            aspect_ratio = height / width
            track_history = self._track_window[track.track_id]
            track_history.append((now, track.bbox))

            fall_detected = aspect_ratio < 0.8 and motion_level > avg_motion * 1.2
            conflict_risk = self._detect_conflict_risk(track, tracks)

            zone_id = self._zone_for_track(track)
            if fall_detected:
                self._persist_event(
                    now,
                    track,
                    "fall",
                    severity=4,
                    confidence=0.6,
                    zone_id=zone_id,
                    counts=counts,
                    motion_level=motion_level,
                    requires_review=True,
                )
            if conflict_risk:
                self._persist_event(
                    now,
                    track,
                    "physical_conflict_risk",
                    severity=3,
                    confidence=0.5,
                    zone_id=zone_id,
                    counts=counts,
                    motion_level=motion_level,
                    requires_review=True,
                )
            if possible_crowd:
                self._persist_event(
                    now,
                    track,
                    "crowd_surge",
                    severity=3,
                    confidence=0.5,
                    zone_id=zone_id,
                    counts=counts,
                    motion_level=motion_level,
                    requires_review=True,
                )

    def _detect_conflict_risk(self, track: Track, tracks: List[Track]) -> bool:
        if len(tracks) < 2:
            return False
        x1, y1, x2, y2 = track.bbox
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        for other in tracks:
            if other.track_id == track.track_id:
                continue
            ox1, oy1, ox2, oy2 = other.bbox
            ocx, ocy = (ox1 + ox2) / 2, (oy1 + oy2) / 2
            distance = float(np.hypot(cx - ocx, cy - ocy))
            if distance < 50:
                return True
        return False

    def _zone_for_track(self, track: Track) -> Optional[str]:
        x1, y1, x2, y2 = track.bbox
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        for zone in self.camera.zones:
            if point_in_polygon((cx, cy), zone.polygon):
                return zone.zone_id
        return None

    def _persist_event(
        self,
        now: datetime,
        track: Track,
        event_type: str,
        severity: int,
        confidence: float,
        zone_id: Optional[str],
        counts: Dict[str, int],
        motion_level: float,
        requires_review: bool,
    ) -> None:
        payload = {
            "schema_version": "1.0",
            "event_id": str(uuid.uuid4()),
            "room_id": self.room.room_id,
            "camera_id": self.camera.camera_id,
            "timestamp_utc": now.isoformat(),
            "event_type": event_type,
            "severity": severity,
            "confidence": confidence,
            "zone_id": zone_id,
            "counts": {"persons": counts.get(zone_id, 0) if zone_id else sum(counts.values())},
            "activity": {"motion_level": motion_level},
            "track": {"ephemeral_track_id": track.track_id, "persist_scope": "session_only"},
            "requires_review": requires_review,
            "privacy": {"faces_blurred": True, "frame_stored": False},
            "debug": {"model_versions": {"detector": "yolov8n" if self.detector else "stub"}},
        }

        with self.session_factory() as session:
            session.add(
                Event(
                    event_id=payload["event_id"],
                    room_id=self.room.room_id,
                    camera_id=self.camera.camera_id,
                    timestamp_utc=now,
                    event_type=event_type,
                    severity=severity,
                    confidence=confidence,
                    zone_id=zone_id,
                    counts_persons=payload["counts"]["persons"],
                    motion_level=motion_level,
                    track_id=track.track_id,
                    requires_review=requires_review,
                    privacy_faces_blurred=True,
                    privacy_frame_stored=False,
                    schema_version="1.0",
                    payload_json=json.dumps(payload),
                )
            )
            session.commit()

        routing_key = f"classroom.{self.room.room_id}.{event_type}"
        self.publisher.publish(routing_key, payload)
