"""
rag.py — Master RAG Pipeline
─────────────────────────────
End-to-end entry point. Wires all phases together:

  Phase 8  → retriever.py  (embed question → vector search → top-K chunks)
  Phase 9  → generator.py  (build grounded prompt)
  Phase 10 → generator.py  (llama-3.3-70b via AIHubMix → answer)

Usage:
    python backend/rag/rag.py "Why are my AKS pods restarting?"
"""

import sys
from retriever import retrieve
from generator import generate_answer


def answer(
    question: str,
    filter_service: str = None,
    filter_severity: str = None,
    top_k: int = 5
) -> dict:
    """
    Full RAG pipeline.

    Args:
        question:        User's natural language question.
        filter_service:  Optional — scope search to a specific Azure service.
        filter_severity: Optional — scope search to a specific severity level.
        top_k:           Number of chunks to retrieve from Azure AI Search.

    Returns:
        dict with keys:
            'question'  — the original question
            'context'   — the formatted retrieved chunks (for transparency/citations)
            'answer'    — the LLM-generated response
    """
    print(f"\n[RAG] Question received: {question}")

    # ── Phase 8: Retrieve relevant chunks ─────────────────────────────────────
    print("[RAG] Running vector search against Azure AI Search...")
    context, raw_chunks = retrieve(
        question=question,
        filter_service=filter_service,
        filter_severity=filter_severity,
        top_k=top_k
    )
    print(f"[RAG] Retrieved {len(raw_chunks)} chunks.")

    # ── Phase 9 + 10: Build prompt and get LLM answer ─────────────────────────
    print("[RAG] Sending prompt to llama-3.3-70b-versatile via Groq...")
    llm_answer = generate_answer(question, context)
    print("[RAG] Answer received.\n")

    return {
        "question": question,
        "context":  context,
        "answer":   llm_answer
    }


if __name__ == "__main__":
    # Allow running directly: python rag.py "your question here"
    if len(sys.argv) > 1:
        user_question = " ".join(sys.argv[1:])
    else:
        user_question = "Why are my AKS pods restarting?"

    result = answer(user_question)

    print("=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(result["answer"])
    print()
    print("─" * 60)
    print("RETRIEVED CONTEXT (sources)")
    print("─" * 60)
    print(result["context"])
