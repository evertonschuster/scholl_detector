from __future__ import annotations

import argparse
import logging
import threading

from .api import app
from .config import load_settings
from .database import Base, get_engine, get_session_factory
from .pipeline import StreamProcessor
from .queue import EventPublisher

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    settings = load_settings()
    engine = get_engine(settings.database.url)
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(settings.database.url)
    publisher = EventPublisher(settings.queue)

    threads = []
    for room in settings.app.rooms:
        for camera in room.cameras:
            processor = StreamProcessor(
                room=room,
                camera=camera,
                app_config=settings.app,
                session_factory=session_factory,
                publisher=publisher,
            )
            thread = threading.Thread(target=processor.run, daemon=True)
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Classroom observables MVP")
    parser.add_argument(
        "command",
        choices=["api", "pipeline"],
        help="Run API server or pipeline",
    )
    args = parser.parse_args()

    if args.command == "api":
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8000)
    if args.command == "pipeline":
        run_pipeline()


if __name__ == "__main__":
    main()
