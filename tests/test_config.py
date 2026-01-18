from pathlib import Path

from app.config import load_settings


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
app:
  retention_days: 10
queue:
  host: localhost
rooms:
  - room_id: sala-test
    cameras:
      - camera_id: cam-1
        rtsp_url: rtsp://example/stream
        fps: 6
        zones:
          - zone_id: front
            polygon:
              - [0, 0]
              - [1, 0]
              - [1, 1]
              - [0, 1]
"""
    )

    settings = load_settings(config_path)
    assert settings.app.retention_days == 10
    assert settings.queue.host == "localhost"
    assert settings.app.rooms[0].room_id == "sala-test"
    assert settings.app.rooms[0].cameras[0].fps == 6
    assert settings.app.rooms[0].cameras[0].zones[0].zone_id == "front"
