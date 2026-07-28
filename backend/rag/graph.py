"""
graph.py — LangGraph StateGraph for incident analysis
──────────────────────────────────────────────────────
Orchestrates the multi-agent pipeline:

  RetrieverAgent (in main.py)
        │
        ▼
    [rca_agent]    ← Root Cause Analysis
        │
        ▼
  [recommendation_agent]  ← Remediation
        │
        ▼
  [summary_agent]   ← Executive Briefing
        │
        ▼
       END

Usage:
    from graph import run_analysis
    result = run_analysis(question, context, raw_chunks, history)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import StateGraph, END
from agents import AgentState, rca_agent, recommendation_agent, summary_agent


# ─────────────────────────────────────────────────────────────────────────────
# Build Graph
# ─────────────────────────────────────────────────────────────────────────────

def _build_graph():
    graph = StateGraph(AgentState)

    # Register agent nodes
    graph.add_node("rca", rca_agent)
    graph.add_node("recommendation", recommendation_agent)
    graph.add_node("summary", summary_agent)

    # Wire sequential edges
    graph.set_entry_point("rca")
    graph.add_edge("rca", "recommendation")
    graph.add_edge("recommendation", "summary")
    graph.add_edge("summary", END)

    return graph.compile()


# Compiled graph — imported by main.py
_graph = _build_graph()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(
    question: str,
    context: str,
    raw_chunks: list[dict],
    history: list[dict] | None = None,
) -> AgentState:
    """
    Run the full multi-agent pipeline and return the final state.

    Args:
        question:   The user's question.
        context:    Pre-formatted string of retrieved chunks.
        raw_chunks: Raw list of chunk dicts (metadata for citations).
        history:    Optional conversation history.

    Returns:
        The final AgentState dict with all agent outputs populated.
    """
    initial_state: AgentState = {
        "question": question,
        "context": context,
        "history": history or [],
        "raw_chunks": raw_chunks,
        # Pre-initialize output fields (LangGraph requires all keys to exist)
        "root_cause": "",
        "confidence": 0.0,
        "evidence": [],
        "immediate_actions": [],
        "long_term_fixes": [],
        "preventive_recommendations": [],
        "executive_summary": "",
        "severity": "",
        "business_impact": "",
        "timeline": "",
    }

    return _graph.invoke(initial_state)
