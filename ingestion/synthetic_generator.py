"""
ingestion/synthetic_generator.py
─────────────────────────────────
Generates realistic synthetic incident telemetry for the AIIP platform.

Covers four signal types (all share the same top-level envelope as
github_puller.py, so dbt treats every source identically):

  • app_logs   – structured application log lines (ERROR / WARN / INFO)
  • k8s_logs   – Kubernetes pod events (OOMKilled, CrashLoopBackOff, Evicted …)
  • metrics    – Prometheus-style scalar samples (CPU, memory, latency, error-rate)
  • traces     – OpenTelemetry distributed trace spans (with parent/child linkage)

Incident scenarios
──────────────────
The generator can emit plain random events OR a correlated incident scenario
(--scenario flag).  A scenario is a realistic burst:

  deploy → latency spike → error-rate climb → OOM kill → pod restart

This gives dbt / ML models something meaningful to detect correlations on.

Phase-1 output  : local JSON  (ingestion/output/synthetic_<type>_<ts>.json)
Phase-1.3 output: Azure Event Hub stub (send_to_event_hub) — same pattern as puller

Dependencies (already in ingestion/requirements.txt — no new packages needed):
    python-dotenv  (optional)

Usage
─────
  # 200 random events, all types mixed:
  python3 ingestion/synthetic_generator.py

  # 50 events per type, dry-run to stdout:
  python3 ingestion/synthetic_generator.py --count 50 --dry-run

  # Correlated incident scenario (~120 events), saved to file:
  python3 ingestion/synthetic_generator.py --scenario

  # One type only:
  python3 ingestion/synthetic_generator.py --type metrics --count 100

CLI flags
─────────
  --type      app_logs | k8s_logs | metrics | traces | all  [default: all]
  --count     N   events per enabled type                   [default: 50]
  --scenario      emit a correlated incident scenario instead of random events
  --seed      N   random seed for reproducible output       [default: 42]
  --dry-run       print to stdout only; skip writing file / Event Hub
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Optional .env loader ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("aiip.synthetic_generator")

# ── Output directory (mirrors github_puller.py) ───────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "output"


# ─────────────────────────────────────────────────────────────────────────────
# Shared catalogue — realistic AIIP microservices & infrastructure
# ─────────────────────────────────────────────────────────────────────────────

SERVICES = [
    "aiip-api-gateway",
    "aiip-ingestion-worker",
    "aiip-rag-service",
    "aiip-ml-scorer",
    "aiip-alert-router",
    "aiip-dashboard-backend",
    "aiip-event-processor",
    "aiip-data-normaliser",
    "aiip-notification-svc",
    "aiip-auth-service",
]

NAMESPACES = ["aiip-prod", "aiip-dev", "monitoring", "kube-system"]

PODS = {svc: [f"{svc}-{sfx}" for sfx in ["7d9f8b-xk2pq", "7d9f8b-mnjr4", "6c4a1d-wqtl7"]]
        for svc in SERVICES}

BRANCHES = ["main", "release/1.2", "hotfix/oom-fix", "feat/rag-v2"]

COMMIT_SHAS = [uuid.uuid4().hex[:40] for _ in range(20)]

# ── ISO-8601 helpers ──────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rand_ts(base: datetime, jitter_seconds: int = 3600) -> str:
    """Random timestamp within ±jitter_seconds of base."""
    delta = random.randint(-jitter_seconds, 0)
    return _iso(base + timedelta(seconds=delta))


def _new_event_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Generator 1 – Application Logs
# ─────────────────────────────────────────────────────────────────────────────

_LOG_LEVELS = ["ERROR", "ERROR", "WARN", "WARN", "INFO", "INFO", "INFO", "DEBUG"]

_ERROR_MESSAGES = [
    ("ConnectionRefusedError", "Failed to connect to upstream service after 3 retries",
     "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='aiip-ml-scorer', port=443): Max retries exceeded"),
    ("TimeoutError", "Request to /api/v1/score timed out after 30s",
     "concurrent.futures.TimeoutError: operation timed out after 30000ms"),
    ("MemoryError", "Out of memory while loading embedding model",
     "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.50 GiB"),
    ("ValueError", "Invalid event schema: missing required field 'service_name'",
     "pydantic.ValidationError: 1 validation error for DeploymentEvent\nservice_name\n  field required"),
    ("DatabaseError", "pgpool: connection pool exhausted (max=50)",
     "psycopg2.OperationalError: FATAL: remaining connection slots are reserved"),
    ("KafkaError", "Failed to produce event to topic aiip-deployment-events",
     "kafka.errors.KafkaTimeoutError: Failed to update metadata after 60.0 secs"),
]

_WARN_MESSAGES = [
    "Slow query detected: 4.2s on incidents table (expected <500ms)",
    "Retry 2/3 connecting to Event Hub endpoint",
    "Cache miss rate above threshold: 78% (threshold: 60%)",
    "Heap usage at 82% — approaching GC pressure threshold",
    "Rate limit approaching: 4800/5000 requests used in current window",
    "Circuit breaker HALF_OPEN for aiip-ml-scorer",
    "Stale pod detected: last heartbeat 95s ago (threshold: 60s)",
]

_INFO_MESSAGES = [
    "HTTP 200 GET /api/v1/incidents?limit=25 — 42ms",
    "Event batch of 50 normalised and written to output/",
    "Health check passed — all 3 dependencies reachable",
    "Background job completed: scored 1200 alerts in 8.3s",
    "Feature flag 'rag-v2-enabled' evaluated → True for tenant aiip-prod",
    "Token refreshed via DefaultAzureCredential (AzureCliCredential)",
    "Startup complete — listening on 0.0.0.0:8080",
]


def generate_app_log_event(base_ts: datetime, level: str | None = None) -> dict:
    svc  = random.choice(SERVICES)
    lvl  = level or random.choice(_LOG_LEVELS)
    ts   = _rand_ts(base_ts, jitter_seconds=1800)

    if lvl == "ERROR":
        exc, msg, trace = random.choice(_ERROR_MESSAGES)
        payload = {
            "level":       "ERROR",
            "logger":      f"com.aiip.{svc.replace('-', '.')}",
            "message":     msg,
            "exception":   exc,
            "stack_trace": trace,
            "request_id":  str(uuid.uuid4()),
            "trace_id":    uuid.uuid4().hex[:32],
            "thread":      f"worker-{random.randint(1, 16)}",
            "host":        random.choice(PODS[svc]),
            "namespace":   "aiip-prod",
        }
    elif lvl == "WARN":
        payload = {
            "level":      "WARN",
            "logger":     f"com.aiip.{svc.replace('-', '.')}",
            "message":    random.choice(_WARN_MESSAGES),
            "request_id": str(uuid.uuid4()),
            "trace_id":   uuid.uuid4().hex[:32],
            "thread":     f"worker-{random.randint(1, 16)}",
            "host":       random.choice(PODS[svc]),
            "namespace":  "aiip-prod",
        }
    else:
        payload = {
            "level":     lvl,
            "logger":    f"com.aiip.{svc.replace('-', '.')}",
            "message":   random.choice(_INFO_MESSAGES),
            "trace_id":  uuid.uuid4().hex[:32],
            "host":      random.choice(PODS[svc]),
            "namespace": "aiip-prod",
        }

    return {
        "event_id":    _new_event_id(),
        "event_type":  "log",
        "source":      "app_logs",
        "timestamp":   ts,
        "service_name": svc,
        "payload":     payload,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generator 2 – Kubernetes Events / Logs
# ─────────────────────────────────────────────────────────────────────────────

_K8S_REASONS = [
    ("OOMKilled",        "Warning", "Container aiip-ml-scorer was OOMKilled — memory limit 2Gi exceeded"),
    ("CrashLoopBackOff", "Warning", "Back-off restarting failed container; last exit code: 137"),
    ("Evicted",          "Warning", "Pod evicted due to node memory pressure (threshold: 95%)"),
    ("Pulled",           "Normal",  "Successfully pulled image aiip-ingestion-worker:1.4.2 in 8.3s"),
    ("Started",          "Normal",  "Started container aiip-api-gateway"),
    ("Killing",          "Normal",  "Stopping container aiip-event-processor (graceful shutdown)"),
    ("FailedMount",      "Warning", "Unable to attach volume 'aiip-data-pvc': timeout after 120s"),
    ("Unhealthy",        "Warning", "Liveness probe failed: HTTP probe failed with statuscode: 503"),
    ("NodeNotReady",     "Warning", "Node aks-nodepool1-12345-vmss000002 condition is NotReady"),
    ("Scheduled",        "Normal",  "Successfully assigned aiip-prod/aiip-rag-service-7d9f8b-xk2pq to node aks-nodepool1-12345-vmss000001"),
    ("ScalingReplicaSet","Normal",  "Scaled up replica set aiip-ingestion-worker-7d9f8b to 5"),
    ("FailedCreate",     "Warning", "Error creating: pods quota exceeded. Limited to 20, used 20"),
]


def generate_k8s_event(base_ts: datetime, reason: str | None = None) -> dict:
    svc  = random.choice(SERVICES)
    pod  = random.choice(PODS[svc])
    ns   = "aiip-prod"
    ts   = _rand_ts(base_ts, jitter_seconds=1800)

    if reason:
        match = next((r for r in _K8S_REASONS if r[0] == reason), None)
        k8s_reason, k8s_type, k8s_message = match or random.choice(_K8S_REASONS)
    else:
        k8s_reason, k8s_type, k8s_message = random.choice(_K8S_REASONS)

    count = random.randint(1, 12) if k8s_type == "Warning" else 1

    return {
        "event_id":    _new_event_id(),
        "event_type":  "k8s_event",
        "source":      "k8s_logs",
        "timestamp":   ts,
        "service_name": svc,
        "payload": {
            "namespace":        ns,
            "pod_name":         pod,
            "container_name":   svc,
            "node":             f"aks-nodepool1-12345-vmss{random.randint(0, 4):06d}",
            "reason":           k8s_reason,
            "type":             k8s_type,
            "message":          k8s_message,
            "count":            count,
            "first_timestamp":  _rand_ts(base_ts, jitter_seconds=7200),
            "last_timestamp":   ts,
            "involved_object": {
                "kind":      "Pod",
                "name":      pod,
                "namespace": ns,
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generator 3 – Prometheus Metrics
# ─────────────────────────────────────────────────────────────────────────────

_METRIC_CATALOGUE = [
    # (metric_name, unit, normal_range, spike_range)
    ("cpu_usage_percent",            "percent",      (5.0,  40.0),  (70.0,  99.0)),
    ("memory_rss_bytes",             "bytes",        (2e8,  8e8),   (1.8e9, 2.1e9)),
    ("http_requests_per_second",     "rps",          (20.0, 200.0), (500.0, 1200.0)),
    ("http_error_rate_percent",      "percent",      (0.1,  1.0),   (8.0,   45.0)),
    ("http_request_duration_p50_ms", "milliseconds", (10.0, 80.0),  (200.0, 800.0)),
    ("http_request_duration_p99_ms", "milliseconds", (80.0, 300.0), (1000.0,5000.0)),
    ("event_hub_lag_messages",       "messages",     (0.0,  100.0), (5000.0,50000.0)),
    ("db_query_duration_p95_ms",     "milliseconds", (5.0,  50.0),  (500.0, 3000.0)),
    ("pod_restarts_total",           "count",        (0.0,  1.0),   (5.0,   30.0)),
    ("gc_pause_duration_ms",         "milliseconds", (5.0,  30.0),  (200.0, 800.0)),
    ("cache_hit_ratio",              "ratio",        (0.7,  0.95),  (0.1,   0.35)),
    ("open_file_descriptors",        "count",        (100,  500),   (900,   1024)),
]


def generate_metric_event(base_ts: datetime, spike: bool = False) -> dict:
    svc   = random.choice(SERVICES)
    pod   = random.choice(PODS[svc])
    ts    = _rand_ts(base_ts, jitter_seconds=900)
    name, unit, normal, spk = random.choice(_METRIC_CATALOGUE)
    lo, hi = spk if spike else normal
    value  = round(random.uniform(lo, hi), 4)

    return {
        "event_id":    _new_event_id(),
        "event_type":  "metric",
        "source":      "prometheus",
        "timestamp":   ts,
        "service_name": svc,
        "payload": {
            "metric_name":        name,
            "value":              value,
            "unit":               unit,
            "is_anomalous":       spike,
            "aggregation_window": "1m",
            "labels": {
                "service":   svc,
                "pod":       pod,
                "namespace": "aiip-prod",
                "env":       "dev",
                "region":    "francecentral",
            },
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generator 4 – Distributed Traces (OpenTelemetry)
# ─────────────────────────────────────────────────────────────────────────────

_OPERATIONS = [
    ("POST", "/api/v1/incidents",          [50,  400]),
    ("GET",  "/api/v1/incidents/{id}",     [10,  80]),
    ("POST", "/api/v1/score",              [200, 2000]),
    ("GET",  "/api/v1/health",             [2,   15]),
    ("POST", "/internal/normalise",        [30,  300]),
    ("GET",  "/internal/embed",            [100, 900]),
    ("PUT",  "/api/v1/alerts/{id}/ack",    [20,  150]),
    ("POST", "/api/v1/events/batch",       [80,  600]),
]

_SPAN_STATUS = ["OK", "OK", "OK", "ERROR", "UNSET"]


def _make_span(
    trace_id: str,
    parent_span_id: str | None,
    service: str,
    base_ts: datetime,
    start_offset_ms: int = 0,
    slow: bool = False,
) -> dict:
    method, op, (lo, hi) = random.choice(_OPERATIONS)
    dur_ms    = random.randint(hi // 2, hi * 3) if slow else random.randint(lo, hi)
    start_dt  = base_ts + timedelta(milliseconds=start_offset_ms)
    end_dt    = start_dt + timedelta(milliseconds=dur_ms)
    status    = "ERROR" if (slow and random.random() < 0.4) else random.choice(_SPAN_STATUS)

    span: dict = {
        "trace_id":      trace_id,
        "span_id":       uuid.uuid4().hex[:16],
        "parent_span_id": parent_span_id,
        "service_name":  service,
        "operation_name": f"{method} {op}",
        "start_time":    _iso(start_dt),
        "end_time":      _iso(end_dt),
        "duration_ms":   dur_ms,
        "status":        status,
        "tags": {
            "http.method":      method,
            "http.url":         f"https://{service}.aiip-prod.svc.cluster.local{op}",
            "http.status_code": 500 if status == "ERROR" else 200,
            "net.peer.name":    service,
            "component":        "http",
        },
    }
    if status == "ERROR":
        span["logs"] = [{"timestamp": _iso(start_dt), "event": "exception",
                         "message": "upstream connection refused or timed out"}]
    return span


def generate_trace_event(base_ts: datetime, slow: bool = False) -> dict:
    """
    Emit one logical trace as a single AIIP event.
    The payload contains a list of spans (root + up to 4 child spans) so that
    dbt can explode them into a spans table for waterfall analysis.
    """
    root_svc  = random.choice(SERVICES)
    trace_id  = uuid.uuid4().hex[:32]
    ts        = _rand_ts(base_ts, jitter_seconds=1800)
    base_dt   = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    root_span = _make_span(trace_id, None, root_svc, base_dt, slow=slow)
    root_sid  = root_span["span_id"]
    n_children = random.randint(1, 4)
    spans = [root_span]
    offset = 5
    for _ in range(n_children):
        child_svc = random.choice([s for s in SERVICES if s != root_svc])
        child     = _make_span(trace_id, root_sid, child_svc, base_dt,
                               start_offset_ms=offset, slow=slow)
        offset   += child["duration_ms"] + random.randint(1, 20)
        spans.append(child)

    total_dur = sum(s["duration_ms"] for s in spans)
    has_error = any(s["status"] == "ERROR" for s in spans)

    return {
        "event_id":    _new_event_id(),
        "event_type":  "trace",
        "source":      "opentelemetry",
        "timestamp":   ts,
        "service_name": root_svc,
        "payload": {
            "trace_id":       trace_id,
            "root_service":   root_svc,
            "root_operation": root_span["operation_name"],
            "total_duration_ms": total_dur,
            "span_count":     len(spans),
            "has_error":      has_error,
            "is_slow":        slow,
            "spans":          spans,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scenario: correlated incident burst
# ─────────────────────────────────────────────────────────────────────────────

def generate_incident_scenario() -> list[dict]:
    """
    Emit a realistic correlated incident sequence:

    T+0  – deploy event triggers push (github_puller would produce this; we
            emit a synthetic deployment log here for completeness)
    T+2m – latency spikes (traces)
    T+4m – error-rate climbs (metrics + app-log ERRORs)
    T+6m – OOMKilled (k8s_event)
    T+8m – pod restarts + CrashLoopBackOff
    T+10m– partial recovery (metrics normalise)

    Returns ~120 events, chronologically ordered.
    """
    logger.info("Generating correlated incident scenario …")
    base = _now_utc() - timedelta(hours=1)
    events: list[dict] = []

    def ts_at(minutes: int) -> datetime:
        return base + timedelta(minutes=minutes)

    # T+0: deploy starts
    for _ in range(3):
        ev = generate_app_log_event(ts_at(0), level="INFO")
        ev["payload"]["message"] = "Deployment aiip-ml-scorer:1.5.0 started — rolling update"
        ev["service_name"] = "aiip-ml-scorer"
        events.append(ev)

    # T+2: latency spikes appear in traces
    for _ in range(20):
        events.append(generate_trace_event(ts_at(2), slow=True))

    # T+3: normal metrics start showing anomalies
    for _ in range(15):
        events.append(generate_metric_event(ts_at(3), spike=True))

    # T+4: error logs flood in
    for _ in range(25):
        events.append(generate_app_log_event(ts_at(4), level="ERROR"))

    # T+4.5: warn logs
    for _ in range(10):
        events.append(generate_app_log_event(ts_at(4), level="WARN"))

    # T+6: OOMKilled
    for _ in range(4):
        ev = generate_k8s_event(ts_at(6), reason="OOMKilled")
        ev["service_name"] = "aiip-ml-scorer"
        events.append(ev)

    # T+7: Liveness probe failures → CrashLoopBackOff
    for _ in range(5):
        events.append(generate_k8s_event(ts_at(7), reason="Unhealthy"))
    for _ in range(3):
        events.append(generate_k8s_event(ts_at(7), reason="CrashLoopBackOff"))

    # T+8: metrics still spiking
    for _ in range(10):
        events.append(generate_metric_event(ts_at(8), spike=True))

    # T+9: pod rescheduled / started
    for _ in range(4):
        events.append(generate_k8s_event(ts_at(9), reason="Scheduled"))
    for _ in range(4):
        events.append(generate_k8s_event(ts_at(9), reason="Started"))

    # T+10: recovery — normal metrics
    for _ in range(10):
        events.append(generate_metric_event(ts_at(10), spike=False))
    for _ in range(5):
        events.append(generate_app_log_event(ts_at(10), level="INFO"))

    # Sort chronologically
    events.sort(key=lambda e: e["timestamp"])
    logger.info("Scenario generated: %d correlated events.", len(events))
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers (mirrors github_puller.py)
# ─────────────────────────────────────────────────────────────────────────────

def write_local_json(events: list[dict], label: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUTPUT_DIR / f"synthetic_{label}_{ts}.json"
    out.write_text(json.dumps(events, indent=2, ensure_ascii=False))
    logger.info("Wrote %d events → %s", len(events), out)
    return out


def send_to_event_hub(events: list[dict]) -> None:
    """
    Publish synthetic incident events to the correct Event Hub.
    deployment events  → aiip-deployment-events
    all other types    → aiip-incident-events
    Routing and batching are handled by EventHubProducer.
    """
    from event_hub_producer import EventHubProducer

    with EventHubProducer() as producer:
        totals = producer.send(events)
        for hub, count in totals.items():
            logger.info("Published %d events → Event Hub '%s'", count, hub)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic AIIP incident telemetry (app_logs, k8s_logs, metrics, traces)"
    )
    parser.add_argument(
        "--type",
        choices=["app_logs", "k8s_logs", "metrics", "traces", "all"],
        default="all",
        help="Signal type to generate.  Default: all",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Events to generate per enabled type.  Default: 50",
    )
    parser.add_argument(
        "--scenario",
        action="store_true",
        help="Emit a correlated incident scenario instead of random events.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible output.  Default: 42",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print events to stdout only; skip writing file / Event Hub.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    base = _now_utc()

    logger.info("=== AIIP Synthetic Generator — type=%s count=%d scenario=%s ===",
                args.type, args.count, args.scenario)

    # ── Generate ──────────────────────────────────────────────────────────────
    if args.scenario:
        all_events = generate_incident_scenario()
        label = "incident_scenario"
    else:
        all_events = []
        generators = {
            "app_logs": lambda: generate_app_log_event(base),
            "k8s_logs": lambda: generate_k8s_event(base),
            "metrics":  lambda: generate_metric_event(base),
            "traces":   lambda: generate_trace_event(base),
        }
        active = list(generators.keys()) if args.type == "all" else [args.type]
        for signal in active:
            batch = [generators[signal]() for _ in range(args.count)]
            logger.info("Generated %d %s events.", len(batch), signal)
            all_events.extend(batch)

        # Sort by timestamp for readability
        all_events.sort(key=lambda e: e["timestamp"])
        label = args.type

    # ── Output ────────────────────────────────────────────────────────────────
    if args.dry_run:
        print(json.dumps(all_events, indent=2))
        logger.info("Dry run – %d events printed to stdout only.", len(all_events))
    else:
        out_path = write_local_json(all_events, label)
        print(f"\n✅  Saved {len(all_events)} events → {out_path}")

        # Phase 1.3: push to Event Hub
        send_to_event_hub(all_events)


if __name__ == "__main__":
    main()
