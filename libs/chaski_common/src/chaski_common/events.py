"""Publishes transaction events to Fabric Eventstream (Event Hubs-compatible endpoint).

Disabled unless EVENTSTREAM_CONNECTION_STRING is set. Events carry no PII: ids, amounts,
channel, merchant and city only. Failures are logged and never break the transaction.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any

from chaski_common.logging import get_logger
from chaski_common.models import Transaction
from chaski_common.settings import get_common_settings

log = get_logger(__name__)


def transaction_event(tx: Transaction, customer_id: uuid.UUID, alerts: list[str]) -> dict[str, Any]:
    return {
        "event_type": "transaction.created",
        "transaction_id": str(tx.id),
        "account_id": str(tx.account_id),
        "customer_id": str(customer_id),
        "card_id": str(tx.card_id) if tx.card_id else None,
        "type": tx.type,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "channel": tx.channel,
        "merchant": tx.merchant,
        "city": tx.city,
        "created_at": tx.created_at.isoformat(),
        "rules_triggered": alerts,
    }


class EventPublisher:
    def __init__(self, connection_string: str, eventhub_name: str | None) -> None:
        from azure.eventhub import EventHubProducerClient

        kwargs: dict[str, Any] = {"eventhub_name": eventhub_name} if eventhub_name else {}
        self._producer = EventHubProducerClient.from_connection_string(connection_string, **kwargs)

    def publish(self, events: list[dict[str, Any]]) -> None:
        from azure.eventhub import EventData

        try:
            batch = self._producer.create_batch()
            for event in events:
                batch.add(EventData(json.dumps(event, ensure_ascii=False)))
            self._producer.send_batch(batch)
        except Exception as exc:
            log.warning(
                "eventstream_publish_failed", error_type=type(exc).__name__, count=len(events)
            )


@lru_cache
def get_publisher() -> EventPublisher | None:
    settings = get_common_settings()
    if not settings.eventstream_connection_string:
        return None
    return EventPublisher(settings.eventstream_connection_string, settings.eventstream_name)


def publish(events: list[dict[str, Any]]) -> None:
    publisher = get_publisher()
    if publisher is not None and events:
        publisher.publish(events)
