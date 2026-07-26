"""
ingestion/event_hub_producer.py
────────────────────────────────
Shared Event Hub producer used by both github_puller.py and synthetic_generator.py.

Design
──────
- Retrieves the Event Hub connection string from Azure Key Vault at startup
  (same DefaultAzureCredential chain as the puller — env vars → CLI → MSI).
- Routes events to the correct hub based on event_type:
    "deployment"  → aiip-deployment-events
    everything else (log, k8s_event, metric, trace) → aiip-incident-events
- Batches efficiently: fills an EventDataBatch until it's full, then sends and
  starts a new one — never exceeds the 1 MB per-batch AMQP limit.
- Emits structured log lines for every batch sent so ADF / monitor can track
  throughput.

Usage (from ingestion scripts)
──────────────────────────────
    from event_hub_producer import EventHubProducer

    producer = EventHubProducer()          # resolves credentials once
    producer.send(events)                  # list[dict] — any mix of event_types
    producer.close()                       # flush + close AMQP connection

    # Or use as a context manager:
    with EventHubProducer() as producer:
        producer.send(events)

Dependencies (ingestion/requirements.txt):
    azure-eventhub>=5.11.0
    azure-identity>=1.17.0
    azure-keyvault-secrets>=4.8.0
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable

logger = logging.getLogger("aiip.event_hub_producer")

# ── Configuration ─────────────────────────────────────────────────────────────
KEY_VAULT_NAME   = os.getenv("KEY_VAULT_NAME",         "kv-aiip-dev-frc-001")
KV_SECRET_NAME   = os.getenv("KEY_VAULT_SECRET_NAME",  "eventhub-connection-string")

HUB_DEPLOYMENT   = os.getenv("EVENTHUB_DEPLOYMENT_HUB", "aiip-deployment-events")
HUB_INCIDENT     = os.getenv("EVENTHUB_INCIDENT_HUB",   "aiip-incident-events")

# event_types that go to the deployment hub; everything else → incident hub
_DEPLOYMENT_TYPES = {"deployment"}


def _get_connection_string() -> str:
    """
    Resolve the Event Hub connection string.
    Priority:
      1. EVENTHUB_CONNECTION_STRING env var  (fast local dev)
      2. Azure Key Vault secret              (production)
    """
    conn = os.getenv("EVENTHUB_CONNECTION_STRING")
    if conn:
        logger.info("Using Event Hub connection string from env var.")
        return conn

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise SystemExit(
            "azure-identity / azure-keyvault-secrets not installed.\n"
            "Run: pip install azure-identity azure-keyvault-secrets"
        ) from exc

    vault_url = f"https://{KEY_VAULT_NAME}.vault.azure.net"
    logger.info("Fetching Event Hub connection string from Key Vault: %s", vault_url)
    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    secret = client.get_secret(KV_SECRET_NAME)
    logger.info("Connection string retrieved successfully.")
    return secret.value


class EventHubProducer:
    """
    Thin wrapper around azure-eventhub that routes and batches AIIP events.

    Parameters
    ----------
    connection_string : str, optional
        Override the connection string (for unit testing). If omitted, resolved
        via env var / Key Vault (see _get_connection_string).
    """

    def __init__(self, connection_string: str | None = None) -> None:
        try:
            from azure.eventhub import EventHubProducerClient
        except ImportError as exc:
            raise SystemExit(
                "azure-eventhub is not installed.\n"
                "Run: pip install azure-eventhub"
            ) from exc

        self._conn = connection_string or _get_connection_string()
        self._EventHubProducerClient = EventHubProducerClient

        # Lazily-created producer clients keyed by hub name
        self._producers: dict[str, object] = {}

    # ── Context-manager support ───────────────────────────────────────────────

    def __enter__(self) -> "EventHubProducer":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _hub_for(self, event: dict) -> str:
        event_type = event.get("event_type", "")
        return HUB_DEPLOYMENT if event_type in _DEPLOYMENT_TYPES else HUB_INCIDENT

    def _producer_for(self, hub_name: str):
        if hub_name not in self._producers:
            self._producers[hub_name] = self._EventHubProducerClient.from_connection_string(
                conn_str=self._conn,
                eventhub_name=hub_name,
            )
            logger.info("Created producer for hub: %s", hub_name)
        return self._producers[hub_name]

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, events: Iterable[dict]) -> dict[str, int]:
        """
        Send a list of AIIP events to Event Hub.

        Events are automatically routed:
          • event_type == "deployment"          → aiip-deployment-events
          • event_type in {log, k8s_event,      → aiip-incident-events
                           metric, trace}

        They are batched efficiently — a new batch is started whenever the
        current one would exceed the AMQP 1 MB limit.

        Returns
        -------
        dict[hub_name, messages_sent]
        """
        from azure.eventhub import EventData

        # Group events by destination hub
        buckets: dict[str, list[dict]] = {}
        for ev in events:
            hub = self._hub_for(ev)
            buckets.setdefault(hub, []).append(ev)

        totals: dict[str, int] = {}

        for hub_name, hub_events in buckets.items():
            producer = self._producer_for(hub_name)
            sent = 0
            batch = producer.create_batch()

            for ev in hub_events:
                data = EventData(json.dumps(ev, ensure_ascii=False))
                try:
                    batch.add(data)
                except ValueError:
                    # Batch is full — flush and start a new one
                    producer.send_batch(batch)
                    logger.info(
                        "Sent batch of %d events → %s", len(batch), hub_name
                    )
                    sent += len(batch)
                    batch = producer.create_batch()
                    batch.add(data)

            # Flush final (possibly partial) batch
            if len(batch) > 0:
                producer.send_batch(batch)
                sent += len(batch)

            logger.info("Total sent to %s: %d events", hub_name, len(hub_events))
            totals[hub_name] = len(hub_events)

        return totals

    def close(self) -> None:
        """Close all open AMQP producer connections."""
        for hub_name, producer in self._producers.items():
            producer.close()
            logger.info("Closed producer for hub: %s", hub_name)
        self._producers.clear()
