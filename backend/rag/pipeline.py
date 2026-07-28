"""
pipeline.py — Modular In-Memory RAG Pipeline
──────────────────────────────────────────────
Replaces the disk-based chain:
    exporter.py → .txt → chunker.py → .json → indexer.py

New flow (entirely in RAM):
    Synapse SQL
        ↓  fetch_incidents()
    list[dict]
        ↓  chunk_incident()
    list[IncidentChunk]   (format + split in one step)
        ↓  embed_chunks()
    list[IncidentChunk]   (.embedding populated)
        ↓  upsert_to_search() / delete_from_search()
    Azure AI Search
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ── Embedding model ────────────────────────────────────────────────────────────
EMBEDDING_MODEL = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
EMBEDDING_DIMS  = 1536   # text-embedding-3-small and ada-002 both use 1536


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IncidentChunk:
    """
    A single searchable unit in the Azure AI Search index.

    Each incident is split into 3 chunks (Symptoms / Root Cause / Resolution).
    Every chunk carries the full incident metadata so a retrieved chunk is
    self-contained — no secondary lookup needed.
    """
    id:             str
    incident_id:    str
    service:        str
    severity:       str
    chunk_type:     str       # "Symptoms" | "Root Cause" | "Resolution"
    content:        str       # The text that gets embedded
    date:           str       # YYYY-MM-DD
    environment:    str = "production"
    resource_group: str = "rg-aiip-dev"
    region:         str = "francecentral"
    embedding:      list[float] = field(default_factory=list)

    def to_search_doc(self) -> dict:
        """Serialize to the Azure AI Search document format."""
        return {
            "id":             self.id,
            "incident_id":    self.incident_id,
            "service":        self.service,
            "severity":       self.severity,
            "chunk_type":     self.chunk_type,
            "content":        self.content,
            "date":           self.date,
            "environment":    self.environment,
            "resource_group": self.resource_group,
            "region":         self.region,
            "embedding":      self.embedding,
        }

    def to_display_dict(self) -> dict:
        """Serialize without the embedding vector (for API responses / logging)."""
        d = self.to_search_doc()
        d.pop("embedding", None)
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Fetch from Synapse
# ─────────────────────────────────────────────────────────────────────────────

def fetch_incidents(conn, since: str = "1970-01-01 00:00:00") -> list[dict]:
    """
    Fetch incidents from the Synapse mart layer.

    Pass `since` for incremental mode — only rows updated after that
    timestamp are returned, keeping the pipeline efficient.
    """
    query = """
    SELECT
        incident_id,
        service_name,
        severity,
        initial_symptom,
        primary_root_cause_category AS root_cause,
        duration_minutes,
        incident_start_time,
        updated_at
    FROM dbo.mart_incident_summary
    WHERE updated_at > ?
    ORDER BY updated_at ASC
    """
    cursor = conn.cursor()
    cursor.execute(query, since)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_all_incident_ids(conn) -> set[str]:
    """Return the set of all incident_ids currently in Synapse (for deletion sync)."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT CAST(incident_id AS VARCHAR) FROM dbo.mart_incident_summary")
    return {str(row[0]) for row in cursor.fetchall()}


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Format + Chunk (in memory)
# ─────────────────────────────────────────────────────────────────────────────

def chunk_incident(incident: dict) -> list[IncidentChunk]:
    """
    Convert a single incident dict into 3 semantic chunks.

    Each section (Symptoms / Root Cause / Resolution) becomes an independent
    searchable document. The incident metadata is embedded in every chunk so
    the LLM can cite it precisely: 'According to Incident 1523 (AKS, Critical)…'

    No disk I/O — everything stays in RAM.
    """
    iid  = str(incident.get("incident_id", "unknown"))
    svc  = str(incident.get("service_name",  "Unknown"))
    sev  = str(incident.get("severity",       "Unknown"))
    date = str(incident.get("incident_start_time", ""))[:10]  # YYYY-MM-DD
    dur  = incident.get("duration_minutes", 0)

    # Citation footer appended to every chunk so the LLM can always reference it
    citation = (
        f"\n\n[Source: Incident {iid} | Service: {svc} | "
        f"Severity: {sev} | Date: {date}]"
    )

    sections = [
        (
            "Symptoms",
            f"Symptoms:\n{incident.get('initial_symptom', 'No symptom data available.')}"
            + citation
        ),
        (
            "Root Cause",
            f"Root Cause:\n{incident.get('root_cause', 'Root cause not determined.')}"
            + citation
        ),
        (
            "Resolution",
            f"Resolution:\n"
            f"The incident was resolved in {dur} minutes."
            + citation
        ),
    ]

    return [
        IncidentChunk(
            id=f"incident_{iid}_chunk_{i + 1}",
            incident_id=iid,
            service=svc,
            severity=sev,
            chunk_type=chunk_type,
            content=content,
            date=date,
        )
        for i, (chunk_type, content) in enumerate(sections)
    ]


def build_context(chunks: list) -> str:
    """
    Format a list of IncidentChunk or raw dicts into an LLM-ready context block.
    Works with both IncidentChunk dataclass objects and plain dicts.
    """
    if not chunks:
        return "No relevant incident data found in the knowledge base."

    lines = []
    for i, chunk in enumerate(chunks, start=1):
        # Support both dataclass and dict (from Azure AI Search)
        if isinstance(chunk, IncidentChunk):
            svc, sev, ct, content = chunk.service, chunk.severity, chunk.chunk_type, chunk.content
        else:
            svc  = chunk.get("service",     "Unknown")
            sev  = chunk.get("severity",    "Unknown")
            ct   = chunk.get("chunk_type",  "Unknown")
            content = chunk.get("content",  "")

        lines.append(f"[Chunk {i}] {svc} | {sev} | {ct}")
        lines.append(content)
        lines.append("─" * 44)

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Embed (batch, text-embedding-3-small)
# ─────────────────────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[IncidentChunk], openai_client) -> list[IncidentChunk]:
    """
    Batch-embed all chunks using text-embedding-3-small.

    Batching is more efficient than one API call per chunk.
    Returns the same list with .embedding populated on each item.
    Falls back to zero vectors if the API is unavailable.
    """
    if not chunks:
        return chunks

    texts = [c.content for c in chunks]
    try:
        response = openai_client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL,
        )
        for chunk, emb_obj in zip(chunks, response.data):
            chunk.embedding = emb_obj.embedding
        print(f"  [embed] Generated {len(chunks)} embeddings via {EMBEDDING_MODEL}.")
    except Exception as e:
        print(f"  [embed] Warning — API unavailable ({e}). Using zero vectors.")
        for chunk in chunks:
            chunk.embedding = [0.0] * EMBEDDING_DIMS

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Upsert / Delete in Azure AI Search
# ─────────────────────────────────────────────────────────────────────────────

def upsert_to_search(chunks: list[IncidentChunk], search_client) -> int:
    """
    Upsert embedded chunks to Azure AI Search.

    Uses merge_or_upload_documents so:
    - New chunks are INSERTED.
    - Existing chunks are UPDATED in-place.
    - The index is NEVER rebuilt or cleared.

    Returns the count of successfully processed documents.
    """
    if not chunks:
        return 0
    docs = [c.to_search_doc() for c in chunks]
    results = search_client.merge_or_upload_documents(documents=docs)
    return sum(1 for r in results if r.succeeded)


def delete_from_search(incident_ids: list[str], search_client) -> int:
    """
    Deletion synchronization — remove all chunks for the given incident_ids.

    Called when incidents are detected as deleted from Synapse so the
    Azure AI Search index stays in sync with the source of truth.
    Each incident has 3 chunks (chunk_1, chunk_2, chunk_3).
    """
    if not incident_ids:
        return 0
    keys = [
        {"id": f"incident_{iid}_chunk_{i}"}
        for iid in incident_ids
        for i in range(1, 4)
    ]
    results = search_client.delete_documents(documents=keys)
    return sum(1 for r in results if r.succeeded)


def get_indexed_incident_ids(search_client) -> set[str]:
    """
    Return the set of all incident_ids currently stored in Azure AI Search.
    Used for deletion sync — compare against Synapse to find orphaned chunks.
    """
    results = search_client.search(
        search_text="*",
        select=["incident_id"],
        top=1000
    )
    return {r["incident_id"] for r in results if r.get("incident_id")}
