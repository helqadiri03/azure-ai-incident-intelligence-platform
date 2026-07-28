#!/usr/bin/env python3
"""
seed_index.py — One-time ingestion of incident data into Azure AI Search
───────────────────────────────────────────────────────────────────────────
Ingests a rich set of synthetic incident documents covering common Azure
failure scenarios. Uses BM25 keyword search (no Azure OpenAI needed).

Run with:
    cd backend && rag/.venv/bin/python rag/seed_index.py
"""

import os
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

SEARCH_ENDPOINT   = os.environ.get("SEARCH_ENDPOINT") or os.environ.get("AZURE_SEARCH_ENDPOINT")
SEARCH_API_KEY    = os.environ.get("SEARCH_API_KEY")   or os.environ.get("AZURE_SEARCH_KEY")
SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "incident-chunks-index")

# ─────────────────────────────────────────────────────────────────────────────
# Seed Incidents (diverse Azure failure scenarios)
# ─────────────────────────────────────────────────────────────────────────────

INCIDENTS = [
    # ── AKS ──────────────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1523",
        "service": "AKS",
        "severity": "Critical",
        "date": "2026-05-02",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Pods restarting repeatedly due to OOM kill events across multiple node pools. Node memory utilization above 95%.",
        "root_cause": "Node memory pressure caused Kubernetes to evict low-priority pods, triggering a restart loop. Misconfigured resource requests allowed pods to exceed node capacity.",
        "resolution": "Scaled up node pool from D4s_v3 to D8s_v3. Enabled Cluster Autoscaler with min=3, max=10. Added resource limits to all deployments. Configured PodDisruptionBudgets.",
    },
    {
        "incident_id": "INC-1601",
        "service": "AKS",
        "severity": "High",
        "date": "2026-05-15",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Pod scheduling failures: 'Insufficient CPU'. New deployments stuck in Pending state for over 30 minutes.",
        "root_cause": "CPU over-provisioning — sum of all pod CPU requests exceeded cluster capacity. Horizontal Pod Autoscaler triggered a burst of new replicas during peak hours.",
        "resolution": "Adjusted HPA min/max replica counts. Added node auto-provisioning. Set cluster-wide LimitRange defaults. Optimized Java heap settings to reduce CPU footprint.",
    },
    # ── Azure SQL / SQL Database ──────────────────────────────────────────────
    {
        "incident_id": "INC-1545",
        "service": "SQL Database",
        "severity": "Critical",
        "date": "2026-05-05",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Connection timeouts reported by all backend services. DTU utilization at 100%. Query execution times increased from 20ms to 45s.",
        "root_cause": "A missing index on the fct_incidents table caused full table scans on every analytical query. Coincided with a report generation job that runs at 02:00 UTC.",
        "resolution": "Added composite index on (incident_date, service_name, severity). Rescheduled report job to 04:00 UTC. Upgraded from S3 (100 DTU) to P1 (125 DTU) tier.",
    },
    {
        "incident_id": "INC-1612",
        "service": "SQL Database",
        "severity": "High",
        "date": "2026-05-18",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Deadlock alerts from SQL Insights. Intermittent transaction rollbacks causing data integrity errors in the incident management API.",
        "root_cause": "Two background jobs were updating the same rows in opposite order, creating a deadlock cycle. Missing retry logic in the application layer.",
        "resolution": "Refactored both jobs to use consistent row access ordering. Added exponential backoff retry with jitter in the application. Enabled deadlock trace flag 1222 for monitoring.",
    },
    # ── Event Hub ─────────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1560",
        "service": "Event Hub",
        "severity": "High",
        "date": "2026-05-08",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Event consumer lag growing. GitHub and deployment events not appearing in the incident pipeline. Consumer group offset 1.2M messages behind.",
        "root_cause": "Consumer application crashed due to unhandled JSON deserialization error on a malformed event payload. Without dead-letter queue, the consumer stopped processing entirely.",
        "resolution": "Added try/except around deserialization with dead-letter queue for malformed messages. Restarted consumer from last committed offset. Implemented schema validation on producers.",
    },
    # ── Storage Account ───────────────────────────────────────────────────────
    {
        "incident_id": "INC-1575",
        "service": "Storage Account",
        "severity": "High",
        "date": "2026-05-10",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "Delta Lake reads failing from ADLS Gen2. Databricks jobs returning 403 Forbidden. dbt models unable to query raw incident data.",
        "root_cause": "Storage account firewall rules updated by automated policy compliance scan, which removed the Databricks and Synapse service principal exceptions. Network ACL rollback was not applied.",
        "resolution": "Re-added Synapse managed identity and Databricks SP to storage firewall allowlist. Implemented Terraform drift detection to alert on unauthorized firewall changes.",
    },
    # ── Key Vault ─────────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1588",
        "service": "Key Vault",
        "severity": "Critical",
        "date": "2026-05-12",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "All services returning 401 Unauthorized. API keys, database passwords, and connection strings suddenly inaccessible. Full platform outage.",
        "root_cause": "Key Vault access policies were accidentally deleted during a Terraform apply that used an outdated state file. The apply removed all access policy blocks, locking out all service identities.",
        "resolution": "Restored access policies from Terraform state backup. Added lifecycle { prevent_destroy = true } to the Key Vault resource. Implemented policy-based alerting for access policy changes.",
    },
    # ── Databricks ────────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1592",
        "service": "Databricks",
        "severity": "Medium",
        "date": "2026-05-14",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "event_hub_to_delta Databricks job failing with SparkException. Delta files not landing in ADLS. Incident pipeline stale.",
        "root_cause": "Databricks runtime 13.3 LTS auto-updated to 14.0, introducing a breaking change in the Delta Lake merge API. The job used a deprecated parameter that was removed.",
        "resolution": "Pinned cluster runtime to 13.3 LTS. Updated merge syntax to use new API. Added runtime version check in CI pipeline to prevent unplanned upgrades.",
    },
    # ── Synapse ───────────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1608",
        "service": "Synapse",
        "severity": "Medium",
        "date": "2026-05-17",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "dbt models failing with 'External table is not accessible because location does not exist'. mart_incident_summary returning empty results.",
        "root_cause": "Delta files path in ADLS was renamed from /raw/incidents/ to /raw/incident-events/ during a storage refactoring. Synapse external tables and views were not updated to match.",
        "resolution": "Updated all Synapse view definitions to point to new ADLS path. Added path alias (symlink) for backward compatibility. Documented storage path conventions in ADR.",
    },
    # ── Data Factory ─────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1619",
        "service": "Data Factory",
        "severity": "High",
        "date": "2026-05-20",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "ADF pipeline github_to_blob silently failing. No new incident JSON files landing in ADLS. Alert: 0 files processed in 6 hours.",
        "root_cause": "GitHub Personal Access Token stored in Key Vault expired. ADF pipeline was using a cached token and failing silently without triggering the alert threshold.",
        "resolution": "Rotated GitHub PAT and updated Key Vault secret. Added PAT expiry monitoring via Azure Monitor alert. Configured ADF activity failure alerts with < 1 file threshold.",
    },
    # ── Container Apps ────────────────────────────────────────────────────────
    {
        "incident_id": "INC-1625",
        "service": "Container Apps",
        "severity": "High",
        "date": "2026-05-22",
        "environment": "production",
        "region": "francecentral",
        "resource_group": "rg-aiip-dev-frc-001",
        "symptoms": "RAG backend API returning 502 Bad Gateway. Health endpoint /health unreachable. Container app shows 0 running replicas.",
        "root_cause": "New Docker image pushed with a broken dependency (langchain version conflict). Container failed health check on startup and was terminated. Min replica count was 0, so no fallback existed.",
        "resolution": "Rolled back to previous image tag. Fixed langchain dependency pinning in requirements.txt. Set minReplicas=1 to prevent zero-replica state. Added integration test in CI pipeline before push.",
    },
]


def build_documents(incidents: list[dict]) -> list[dict]:
    """Convert structured incidents into 3 searchable chunks per incident."""
    docs = []
    for inc in incidents:
        base = {
            "incident_id": inc["incident_id"],
            "service":      inc["service"],
            "severity":     inc["severity"],
            "date":         inc["date"],
            "environment":  inc["environment"],
            "region":       inc.get("region", ""),
            "resource_group": inc.get("resource_group", ""),
        }
        for chunk_type, text_key in [
            ("Symptoms",   "symptoms"),
            ("Root Cause", "root_cause"),
            ("Resolution", "resolution"),
        ]:
            content = f"{chunk_type}:\n{inc[text_key]}"
            docs.append({
                **base,
                "id":         f"{inc['incident_id']}-{chunk_type.replace(' ', '_').lower()}",
                "chunk_type": chunk_type,
                "content":    content,
            })
    return docs


def main():
    if not SEARCH_API_KEY or not SEARCH_ENDPOINT:
        print("❌ SEARCH_ENDPOINT and SEARCH_API_KEY must be set in your .env file.")
        sys.exit(1)

    print(f"📡 Connecting to: {SEARCH_ENDPOINT}")
    print(f"📑 Index: {SEARCH_INDEX_NAME}")

    client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    docs = build_documents(INCIDENTS)
    print(f"📦 Upserting {len(docs)} documents ({len(INCIDENTS)} incidents × 3 chunks)...")

    result = client.upload_documents(documents=docs)
    succeeded = sum(1 for r in result if r.succeeded)
    failed    = len(result) - succeeded

    print(f"✅ Ingested: {succeeded} documents")
    if failed:
        print(f"⚠️  Failed:   {failed} documents")

    print("\n🎉 Done! Your AI Search index is ready. Restart the backend container and test with questions like:")
    print("  - 'Why are my SQL databases slow?'")
    print("  - 'Show me all Event Hub failures'")
    print("  - 'What caused the Key Vault outage?'")
    print("  - 'AKS CPU scheduling problems'")


if __name__ == "__main__":
    main()
