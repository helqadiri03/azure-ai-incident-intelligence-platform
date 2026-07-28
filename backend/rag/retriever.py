import os
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import (
    VectorizedQuery,
    QueryType
)

load_dotenv()

# ── Azure OpenAI (optional — only needed for vector/hybrid search) ────────────
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY  = os.environ.get("AZURE_OPENAI_API_KEY")
EMBEDDING_DEPLOYMENT  = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

# ── Azure AI Search ─────────────────────────────────────────────────────────
# Supports both naming conventions (.env uses SEARCH_*, older code used AZURE_SEARCH_*)
SEARCH_ENDPOINT   = (
    os.environ.get("SEARCH_ENDPOINT")
    or os.environ.get("AZURE_SEARCH_ENDPOINT")
)
SEARCH_API_KEY    = (
    os.environ.get("SEARCH_API_KEY")
    or os.environ.get("AZURE_SEARCH_KEY")
)
SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "incident-chunks-index")

TOP_K = 5
RERANK_TOP_K = 20


def _embed_question(question: str) -> list[float] | None:
    """Generate a vector embedding using Azure OpenAI. Returns None if not configured."""
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT:
        return None
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version="2023-05-15",
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
        )
        response = client.embeddings.create(input=question, model=EMBEDDING_DEPLOYMENT)
        return response.data[0].embedding
    except Exception as e:
        print(f"[Retriever] Embedding failed, will use keyword-only search. ({e})")
        return None


def _keyword_search(
    question: str,
    search_client: SearchClient,
    top_k: int,
    odata_filter: str | None,
) -> list[dict]:
    """BM25 keyword-only search — works without Azure OpenAI."""
    results = search_client.search(
        search_text=question,
        filter=odata_filter,
        select=["id", "content", "service", "severity", "incident_id",
                "chunk_type", "date", "environment", "resource_group", "region"],
        top=top_k,
    )
    return list(results)


def _hybrid_search(
    question: str,
    query_vector: list[float],
    search_client: SearchClient,
    top_k: int,
    odata_filter: str | None,
) -> list[dict]:
    """Hybrid (keyword + vector) search with optional semantic reranking."""
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=RERANK_TOP_K,
        fields="embedding",
    )
    try:
        results = search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            filter=odata_filter,
            select=["id", "content", "service", "severity", "incident_id",
                    "chunk_type", "date", "environment", "resource_group", "region"],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name="mySemanticConfig",
            top=top_k,
        )
        return list(results)
    except Exception as e:
        print(f"[Retriever] Semantic ranking unavailable, using hybrid search. ({e})")
        results = search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            filter=odata_filter,
            select=["id", "content", "service", "severity", "incident_id",
                    "chunk_type", "date", "environment", "resource_group", "region"],
            top=top_k,
        )
        return list(results)


def retrieve(
    question: str,
    filter_service: str = None,
    filter_severity: str = None,
    top_k: int = TOP_K,
) -> list[dict]:
    """
    End-to-end retrieval pipeline.

    Search strategy (auto-selected based on available credentials):
      1. Hybrid + Semantic reranking  — Azure OpenAI + Azure AI Search (Standard)
      2. Hybrid (vector + keyword)    — Azure OpenAI + Azure AI Search (Basic)
      3. Keyword-only (BM25)          — Azure AI Search only (no Azure OpenAI needed)
    """
    if not SEARCH_API_KEY or not SEARCH_ENDPOINT:
        raise ValueError("Missing API keys for Azure OpenAI or Azure AI Search.")

    # Build OData filter
    filters = []
    if filter_service:
        filters.append(f"service eq '{filter_service}'")
    if filter_severity:
        filters.append(f"severity eq '{filter_severity}'")
    odata_filter = " and ".join(filters) if filters else None

    search_client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(SEARCH_API_KEY),
    )

    # Try to get embeddings — if unavailable, fall back to keyword search
    query_vector = _embed_question(question)

    if query_vector:
        return _hybrid_search(question, query_vector, search_client, top_k, odata_filter)
    else:
        print("[Retriever] No Azure OpenAI key configured — using keyword-only (BM25) search.")
        return _keyword_search(question, search_client, top_k, odata_filter)
