from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class ZoneConfig:
    zone_id: str
    polygon: List[List[float]]


@dataclass
class CameraConfig:
    camera_id: str
    rtsp_url: str
    fps: int = 5
    zones: List[ZoneConfig] = field(default_factory=list)


@dataclass
class RoomConfig:
    room_id: str
    cameras: List[CameraConfig] = field(default_factory=list)


@dataclass
class AppConfig:
    rooms: List[RoomConfig] = field(default_factory=list)
    retention_days: int = 30
    track_reset_minutes: int = 15
    event_review_threshold: int = 3


@dataclass
class QueueConfig:
    host: str = "rabbitmq"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    exchange: str = "classroom.events"
    exchange_type: str = "topic"


@dataclass
class DatabaseConfig:
    url: str = "sqlite:///./mvp.db"


@dataclass
class Settings:
    app: AppConfig = field(default_factory=AppConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


DEFAULT_CONFIG_PATH = Path("config.yml")


def load_settings(path: Optional[Path] = None) -> Settings:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        settings = Settings()
        settings.database.url = os.getenv("DATABASE_URL", settings.database.url)
        settings.queue.host = os.getenv("RABBITMQ_HOST", settings.queue.host)
        settings.queue.port = int(os.getenv("RABBITMQ_PORT", settings.queue.port))
        settings.queue.username = os.getenv("RABBITMQ_USER", settings.queue.username)
        settings.queue.password = os.getenv("RABBITMQ_PASS", settings.queue.password)
        return settings

    raw = yaml.safe_load(config_path.read_text()) or {}

    rooms = []
    for room_data in raw.get("rooms", []):
        cameras = []
        for cam_data in room_data.get("cameras", []):
            zones = [
                ZoneConfig(zone_id=zone["zone_id"], polygon=zone["polygon"])
                for zone in cam_data.get("zones", [])
            ]
            cameras.append(
                CameraConfig(
                    camera_id=cam_data["camera_id"],
                    rtsp_url=cam_data["rtsp_url"],
                    fps=cam_data.get("fps", 5),
                    zones=zones,
                )
            )
        rooms.append(RoomConfig(room_id=room_data["room_id"], cameras=cameras))

    app_cfg = raw.get("app", {})
    queue_cfg = raw.get("queue", {})
    db_cfg = raw.get("database", {})

    settings = Settings(
        app=AppConfig(
            rooms=rooms,
            retention_days=app_cfg.get("retention_days", 30),
            track_reset_minutes=app_cfg.get("track_reset_minutes", 15),
            event_review_threshold=app_cfg.get("event_review_threshold", 3),
        ),
        queue=QueueConfig(
            host=queue_cfg.get("host", "rabbitmq"),
            port=queue_cfg.get("port", 5672),
            username=queue_cfg.get("username", "guest"),
            password=queue_cfg.get("password", "guest"),
            exchange=queue_cfg.get("exchange", "classroom.events"),
            exchange_type=queue_cfg.get("exchange_type", "topic"),
        ),
        database=DatabaseConfig(url=db_cfg.get("url", "sqlite:///./mvp.db")),
    )

    settings.database.url = os.getenv("DATABASE_URL", settings.database.url)
    settings.queue.host = os.getenv("RABBITMQ_HOST", settings.queue.host)
    settings.queue.port = int(os.getenv("RABBITMQ_PORT", settings.queue.port))
    settings.queue.username = os.getenv("RABBITMQ_USER", settings.queue.username)
    settings.queue.password = os.getenv("RABBITMQ_PASS", settings.queue.password)
    return settings
