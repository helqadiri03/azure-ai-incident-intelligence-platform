"""
ingestion/github_puller.py
──────────────────────────
Pulls GitHub Actions workflow runs for a given repository and normalises
each run into the canonical AIIP deployment-event schema.

Phase-1 output  : local JSON file  (ingestion/output/github_runs_<timestamp>.json)
Phase-1.3 output: Azure Event Hub  (wire-up stub already in place — see send_to_event_hub())

Dependencies (install via ingestion/requirements.txt):
    azure-identity
    azure-keyvault-secrets
    requests
    python-dotenv        # optional – for local .env fallback

Usage
-----
# With Azure Key Vault (requires az login / managed identity):
    python ingestion/github_puller.py

# Fully local (no Key Vault), using .env or env-var:
    GITHUB_PAT=<your_token> python ingestion/github_puller.py
    GITHUB_PAT=<your_token> python ingestion/github_puller.py --repo helqadiri03/azure-ai-incident-intelligence-platform

CLI flags
---------
  --repo     OWNER/REPO   GitHub repository slug (overrides env GITHUB_REPO)
  --runs     N            Max workflow runs to fetch per page  [default: 30]
  --dry-run               Print events to stdout only; skip writing to file / Event Hub
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Optional: load .env for local dev ────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not required in production

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("aiip.github_puller")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Key Vault settings — match your Terraform output
KEY_VAULT_NAME    = os.getenv("KEY_VAULT_NAME", "kv-aiip-dev-frc-001")
KEY_VAULT_SECRET  = os.getenv("KEY_VAULT_SECRET_NAME", "github-pat")  # name of the secret in KV

# GitHub defaults (override via env or --repo flag)
DEFAULT_REPO      = os.getenv("GITHUB_REPO", "helqadiri03/azure-ai-incident-intelligence-platform")
GITHUB_API_BASE   = "https://api.github.com"
MAX_PAGES         = 5          # safety cap – each page = up to 100 runs
RUNS_PER_PAGE     = 30

# Output directory (relative to repo root)
OUTPUT_DIR        = Path(__file__).parent / "output"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 – Retrieve PAT from Azure Key Vault
# ─────────────────────────────────────────────────────────────────────────────

def get_pat_from_key_vault(vault_name: str, secret_name: str) -> str:
    """
    Fetch the GitHub PAT stored in Azure Key Vault.

    Authentication order (DefaultAzureCredential):
      1. Environment variables (AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID)
      2. Azure CLI  (az login)
      3. Managed Identity (when running inside Azure)
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise SystemExit(
            "azure-identity / azure-keyvault-secrets not installed.\n"
            "Run: pip install azure-identity azure-keyvault-secrets"
        ) from exc

    vault_url = f"https://{vault_name}.vault.azure.net"
    logger.info("Fetching PAT from Key Vault: %s / secret: %s", vault_url, secret_name)

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    logger.info("PAT retrieved successfully from Key Vault.")
    return secret.value


def resolve_pat() -> str:
    """
    Returns the GitHub PAT.  Priority:
      1. GITHUB_PAT environment variable  (fast local dev / CI)
      2. Azure Key Vault                  (production)
    """
    pat = os.getenv("GITHUB_PAT")
    if pat:
        logger.info("Using PAT from environment variable GITHUB_PAT.")
        return pat

    return get_pat_from_key_vault(KEY_VAULT_NAME, KEY_VAULT_SECRET)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – Fetch workflow runs from GitHub API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_workflow_runs(
    repo: str,
    pat: str,
    per_page: int = RUNS_PER_PAGE,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """
    GET /repos/{owner}/{repo}/actions/runs
    Returns raw run objects from the GitHub API (all pages up to max_pages).
    """
    owner, repo_name = repo.split("/", 1)
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/actions/runs"

    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_runs: list[dict] = []
    page = 1

    while page <= max_pages:
        params = {"per_page": per_page, "page": page}
        logger.info("Fetching runs page %d (per_page=%d) from %s", page, per_page, url)

        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 401:
            raise SystemExit("GitHub API returned 401 Unauthorized – check your PAT.")
        if resp.status_code == 404:
            raise SystemExit(f"Repository '{repo}' not found or PAT lacks access.")
        resp.raise_for_status()

        data = resp.json()
        runs = data.get("workflow_runs", [])
        logger.info("  → received %d runs on page %d", len(runs), page)

        if not runs:
            break

        all_runs.extend(runs)

        # GitHub pagination: stop when we got fewer results than requested
        if len(runs) < per_page:
            break

        page += 1

    logger.info("Total raw runs fetched: %d", len(all_runs))
    return all_runs


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – Normalise into the canonical AIIP deployment-event schema
# ─────────────────────────────────────────────────────────────────────────────

def _duration_seconds(started_at: str | None, updated_at: str | None) -> int | None:
    """Return wall-clock duration in seconds between two ISO-8601 timestamps."""
    if not started_at or not updated_at:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        start = datetime.strptime(started_at, fmt).replace(tzinfo=timezone.utc)
        end   = datetime.strptime(updated_at,  fmt).replace(tzinfo=timezone.utc)
        delta = (end - start).total_seconds()
        return max(0, int(delta))
    except ValueError:
        return None


def normalise_run(run: dict) -> dict:
    """
    Map one raw GitHub Actions run object → canonical AIIP deployment event.

    Schema (v1):
    {
      "event_id":    UUID (deterministic from run id, so re-runs are idempotent),
      "event_type":  "deployment",
      "source":      "github_actions",
      "timestamp":   ISO-8601 UTC  (= updated_at, i.e. when the run *finished*),
      "service_name": workflow name slugified,
      "payload": {
        "deployment_id":   "run_<id>",
        "commit_sha":      head_sha,
        "workflow_name":   name,
        "status":          status,
        "conclusion":      conclusion | null,
        "branch":          head_branch,
        "started_at":      run_started_at | created_at,
        "finished_at":     updated_at,
        "duration_seconds": int | null,
        "triggered_by":    event   (push / pull_request / schedule / workflow_dispatch …)
      }
    }
    """
    run_id     = run.get("id")
    started_at = run.get("run_started_at") or run.get("created_at")
    finished_at = run.get("updated_at")

    # Deterministic UUID v5 (namespace=DNS) so the same run always maps to the
    # same event_id – safe to re-run the puller without producing duplicates.
    event_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"github_actions_run_{run_id}"))

    return {
        "event_id":    event_id,
        "event_type":  "deployment",
        "source":      "github_actions",
        "timestamp":   finished_at,          # "wall-clock" event timestamp
        "service_name": run.get("name", "unknown-workflow"),
        "payload": {
            "deployment_id":   f"run_{run_id}",
            "commit_sha":      run.get("head_sha"),
            "workflow_name":   run.get("name"),
            "status":          run.get("status"),
            "conclusion":      run.get("conclusion"),   # null if still running
            "branch":          run.get("head_branch"),
            "started_at":      started_at,
            "finished_at":     finished_at,
            "duration_seconds": _duration_seconds(started_at, finished_at),
            "triggered_by":    run.get("event"),
        },
    }


def normalise_runs(raw_runs: list[dict]) -> list[dict]:
    events = [normalise_run(r) for r in raw_runs]
    logger.info("Normalised %d runs into deployment events.", len(events))
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Step 4a – Write to local JSON (Phase 1)
# ─────────────────────────────────────────────────────────────────────────────

def write_local_json(events: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out   = OUTPUT_DIR / f"github_runs_{ts}.json"
    out.write_text(json.dumps(events, indent=2, ensure_ascii=False))
    logger.info("Wrote %d events → %s", len(events), out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Step 4b – Send to Event Hub (Phase 1.3 stub)
# ─────────────────────────────────────────────────────────────────────────────

def send_to_event_hub(events: list[dict]) -> None:
    """
    Publish normalised deployment events to the aiip-deployment-events Event Hub.
    Credentials and connection string are resolved via Key Vault automatically.
    """
    from event_hub_producer import EventHubProducer

    with EventHubProducer() as producer:
        totals = producer.send(events)
        for hub, count in totals.items():
            logger.info("Published %d events → Event Hub '%s'", count, hub)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull GitHub Actions runs → AIIP deployment events"
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help="GitHub repository slug (owner/repo).  Default: %(default)s",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS_PER_PAGE,
        dest="per_page",
        help="Workflow runs per page (max 100).  Default: %(default)s",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print events to stdout only; skip writing to file / Event Hub.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("=== AIIP GitHub Puller — repo: %s ===", args.repo)

    # 1. Get PAT
    pat = resolve_pat()

    # 2. Fetch raw runs
    raw_runs = fetch_workflow_runs(repo=args.repo, pat=pat, per_page=args.per_page)

    if not raw_runs:
        logger.warning("No workflow runs found. Exiting.")
        sys.exit(0)

    # 3. Normalise
    events = normalise_runs(raw_runs)

    # 4. Output
    if args.dry_run:
        print(json.dumps(events, indent=2))
        logger.info("Dry run – output printed to stdout only.")
    else:
        out_path = write_local_json(events)
        print(f"\n✅  Saved {len(events)} events → {out_path}")

        # Phase 1.3: push to Event Hub
        send_to_event_hub(events)


if __name__ == "__main__":
    main()
