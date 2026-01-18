from __future__ import annotations

import json
import logging
from typing import Dict

import pika

from .config import QueueConfig

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, config: QueueConfig):
        self._config = config
        self._connection = None
        self._channel = None

    def connect(self) -> None:
        credentials = pika.PlainCredentials(self._config.username, self._config.password)
        params = pika.ConnectionParameters(
            host=self._config.host,
            port=self._config.port,
            credentials=credentials,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._config.exchange,
            exchange_type=self._config.exchange_type,
            durable=True,
        )

    def publish(self, routing_key: str, payload: Dict) -> None:
        if not self._channel:
            self.connect()
        body = json.dumps(payload, ensure_ascii=False)
        self._channel.basic_publish(
            exchange=self._config.exchange,
            routing_key=routing_key,
            body=body,
        )
        logger.debug("Published event %s", routing_key)

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
            self._channel = None
