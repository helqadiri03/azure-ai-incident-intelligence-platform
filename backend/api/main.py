"""
main.py — Phase 11 + Phase 3: FastAPI REST API + LangGraph Multi-Agent
───────────────────────────────────────────────────────────────────────
POST /chat     → Multi-agent pipeline: Retriever → RCA → Recommendation → Summary
POST /feedback → Save helpful/unhelpful feedback
GET  /metrics  → Expose latency metrics
GET  /health   → Health check
"""

import sys
import time
import json
import uuid
from pathlib import Path
from pydantic import BaseModel
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge

# Make the rag/ directory importable
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from graph import run_analysis

try:
    from retriever import retrieve as _retrieve
    from pipeline import build_context
    RETRIEVER_AVAILABLE = True
except Exception:
    RETRIEVER_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory State & Mock Data
# ─────────────────────────────────────────────────────────────────────────────

MOCK_CHUNKS = [
    {
        "id": "mock_chunk_1", "incident_id": "1523", "service": "AKS", "severity": "Critical",
        "chunk_type": "Symptoms", "date": "2026-05-02", "region": "francecentral", "environment": "production",
        "content": "Symptoms:\nPods restarting repeatedly due to OOM kill events across multiple node pools."
    },
    {
        "id": "mock_chunk_2", "incident_id": "1523", "service": "AKS", "severity": "Critical",
        "chunk_type": "Root Cause", "date": "2026-05-02", "region": "francecentral", "environment": "production",
        "content": "Root Cause:\nNode memory pressure caused Kubernetes to evict low-priority pods, triggering a restart loop."
    },
    {
        "id": "mock_chunk_3", "incident_id": "1523", "service": "AKS", "severity": "Critical",
        "chunk_type": "Resolution", "date": "2026-05-02", "region": "francecentral", "environment": "production",
        "content": "Resolution:\nScaled the node pool from 3 to 5 nodes and enabled the Cluster Autoscaler. Incident resolved in 18 minutes."
    }
]

# In-memory session store (dictionary of session_id -> list of dicts)
# Cleared to avoid mismatch with new JSON history format
SESSIONS: dict[str, list[dict]] = {}

# Prometheus Metrics
RAG_REQUESTS = Counter('rag_total_requests', 'Total RAG requests')
RAG_TOKENS = Counter('rag_total_tokens_approx', 'Approximate total tokens used')
SEARCH_LATENCY = Gauge('rag_avg_search_latency_ms', 'Moving average of search latency')
LLM_LATENCY = Gauge('rag_avg_llm_latency_ms', 'Moving average of LLM latency')
RAG_CONFIDENCE = Gauge('rag_avg_confidence_score', 'Moving average of agent confidence')
HELPFUL_FEEDBACK = Counter('rag_helpful_feedback_total', 'Total helpful feedback')
UNHELPFUL_FEEDBACK = Counter('rag_unhelpful_feedback_total', 'Total unhelpful feedback')

# Keep old dict for UI metrics panel compatibility
METRICS = {
    "total_requests": 0,
    "avg_search_latency_ms": 0.0,
    "avg_llm_latency_ms": 0.0,
    "total_tokens_approx": 0,
}

LOGS_DIR = Path("backend/logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_LOG = LOGS_DIR / "feedback.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str | None = None
    question: str
    filter_service: str | None = None
    filter_severity: str | None = None
    top_k: int = 5

class SourceChunk(BaseModel):
    id: str
    incident_id: str
    service: str
    severity: str
    chunk_type: str
    content: str
    date: str = ""
    environment: str = ""
    resource_group: str = ""
    region: str = ""

class AnalysisResult(BaseModel):
    # RCA Agent
    root_cause_analysis: str
    confidence: float = 0.0
    evidence: list[str] = []
    # Recommendation Agent
    immediate_actions: list[str] = []
    long_term_fixes: list[str] = []
    preventive_recommendations: list[str] = []
    # Summary Agent
    executive_summary: str = ""
    severity: str = ""
    business_impact: str = ""
    timeline: str = ""

class ChatResponse(BaseModel):
    session_id: str
    analysis: AnalysisResult
    sources: list[SourceChunk]
    related_incidents: list[str]
    confidence: float
    retriever_mode: str
    metrics: dict

class FeedbackRequest(BaseModel):
    session_id: str
    question: str
    rating: str  # "helpful" | "not_helpful"


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Azure Incident Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "retriever": "live" if RETRIEVER_AVAILABLE else "mock",
        "llm_model": "llama-3.3-70b-versatile"
    }


@app.get("/metrics")
def get_metrics(raw: bool = False):
    if raw:
        return METRICS
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    record = req.model_dump()
    record["timestamp"] = time.time()
    with open(FEEDBACK_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
    if req.rating == "helpful":
        HELPFUL_FEEDBACK.inc()
    else:
        UNHELPFUL_FEEDBACK.inc()
    return {"status": "recorded"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Get or create session
    session_id = request.session_id or str(uuid.uuid4())
    history = SESSIONS.get(session_id, [])

    retriever_mode = "mock"
    raw_chunks = MOCK_CHUNKS
    context = build_context(raw_chunks) if RETRIEVER_AVAILABLE else "Mock Data Error"
    try:
        context = build_context(raw_chunks)
    except NameError:
        # Fallback if build_context wasn't imported correctly
        context = "\n".join([c["content"] for c in raw_chunks])
    
    confidence = 0.85
    search_ms = 0
    llm_ms = 0

    # ── 1: Retrieval ────────────────────────────────────────────────────────
    t0 = time.time()
    if RETRIEVER_AVAILABLE:
        try:
            raw_chunks = _retrieve(
                question=request.question,
                filter_service=request.filter_service,
                filter_severity=request.filter_severity,
                top_k=request.top_k,
            )
            context = build_context(raw_chunks)
            retriever_mode = "live"

            # Use Hybrid / Reranker scores if available, else vector score
            if raw_chunks:
                first = raw_chunks[0]
                if "@search.reranker_score" in first:
                    confidence = round(min(first["@search.reranker_score"] / 4.0, 1.0), 2)
                else:
                    confidence = round(min(first.get("@search.score", 0.85), 1.0), 2)
        except Exception as e:
            print(f"Retrieval error: {e}")
            pass
    search_ms = int((time.time() - t0) * 1000)

    # ── 2: Multi-Agent Pipeline (LangGraph) ──────────────────────────────────
    t1 = time.time()
    try:
        final_state = run_analysis(
            question=request.question,
            context=context,
            raw_chunks=raw_chunks,
            history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent pipeline error: {e}")
    llm_ms = int((time.time() - t1) * 1000)

    # Update session memory (store a summary, not the full state)
    history.append({"role": "user", "content": request.question})
    history.append({"role": "assistant", "content": final_state.get("executive_summary", "")})
    SESSIONS[session_id] = history[-10:]  # Keep last 10 turns

    # Update metrics
    METRICS["total_requests"] += 1
    reqs = METRICS["total_requests"]
    METRICS["avg_search_latency_ms"] = (METRICS["avg_search_latency_ms"] * (reqs - 1) + search_ms) / reqs
    METRICS["avg_llm_latency_ms"]    = (METRICS["avg_llm_latency_ms"] * (reqs - 1) + llm_ms) / reqs
    tokens = (len(context) + len(str(final_state))) // 4
    METRICS["total_tokens_approx"]  += tokens

    # Update Prometheus metrics
    RAG_REQUESTS.inc()
    RAG_TOKENS.inc(tokens)
    SEARCH_LATENCY.set(METRICS["avg_search_latency_ms"])
    LLM_LATENCY.set(METRICS["avg_llm_latency_ms"])
    RAG_CONFIDENCE.set(confidence * 100)

    # Build response
    sources = [
        SourceChunk(
            id=c.get("id", ""),
            incident_id=c.get("incident_id", ""),
            service=c.get("service", "Unknown"),
            severity=c.get("severity", "Unknown"),
            chunk_type=c.get("chunk_type", "Unknown"),
            content=c.get("content", ""),
            date=c.get("date", ""),
            environment=c.get("environment", ""),
            resource_group=c.get("resource_group", ""),
            region=c.get("region", "")
        )
        for c in raw_chunks
    ]

    related_incidents = list(dict.fromkeys(c.get("incident_id", "") for c in raw_chunks if c.get("incident_id")))

    # Use RCA agent confidence if retriever confidence is default
    rca_confidence = final_state.get("confidence", confidence)
    final_confidence = round(max(confidence, rca_confidence), 2)

    return ChatResponse(
        session_id=session_id,
        analysis=AnalysisResult(
            root_cause_analysis=final_state.get("root_cause", ""),
            confidence=final_state.get("confidence", confidence),
            evidence=final_state.get("evidence", []),
            immediate_actions=final_state.get("immediate_actions", []),
            long_term_fixes=final_state.get("long_term_fixes", []),
            preventive_recommendations=final_state.get("preventive_recommendations", []),
            executive_summary=final_state.get("executive_summary", ""),
            severity=final_state.get("severity", ""),
            business_impact=final_state.get("business_impact", ""),
            timeline=final_state.get("timeline", ""),
        ),
        sources=sources,
        related_incidents=related_incidents,
        confidence=final_confidence,
        retriever_mode=retriever_mode,
        metrics={"search_ms": search_ms, "llm_ms": llm_ms}
    )
