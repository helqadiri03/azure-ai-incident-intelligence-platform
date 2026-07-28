"""
agents.py — Four specialized LangGraph agents
─────────────────────────────────────────────
Each agent is a Python function that receives the shared AgentState
and returns a partial state update. Agents run sequentially via LangGraph edges.

State flow:
  RetrieverAgent → RCA Agent → Recommendation Agent → Summary Agent
"""

import os
import json
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

# Module-level default — overridden at call-time by env var
_FALLBACK_KEY = None
MODEL_NAME = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
# Shared State Schema
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Inputs
    question: str
    context: str
    history: list[dict]

    # RetrieverAgent outputs (passed in externally from main.py)
    raw_chunks: list[dict]

    # RCA Agent outputs
    root_cause: str
    confidence: float
    evidence: list[str]

    # Recommendation Agent outputs
    immediate_actions: list[str]
    long_term_fixes: list[str]
    preventive_recommendations: list[str]

    # Summary Agent outputs
    executive_summary: str
    severity: str
    business_impact: str
    timeline: str


# ─────────────────────────────────────────────────────────────────────────────
# LLM Helper
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm(system: str, user: str) -> dict:
    """Call Groq in JSON mode and return a parsed dict."""
    # Read key fresh every call — works both locally (dotenv) and in Docker (env var)
    api_key = os.environ.get("GROQ_API_KEY") or _FALLBACK_KEY
    llm = ChatGroq(
        api_key=api_key,
        model=MODEL_NAME,
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=user),
    ])
    return json.loads(response.content)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — Root Cause Analysis Agent
# ─────────────────────────────────────────────────────────────────────────────

def rca_agent(state: AgentState) -> AgentState:
    """Analyzes logs, symptoms, and similar incidents to determine root cause."""

    system = (
        "You are a Senior Site Reliability Engineer specializing in root cause analysis.\n"
        "Your ONLY job is to analyze the provided incident context and determine the root cause.\n\n"
        "RULES:\n"
        "1. Use ONLY the provided Context. Never hallucinate.\n"
        "2. Cite specific incident IDs as evidence (e.g. 'Incident #1523 shows...').\n"
        "3. Express confidence as a decimal between 0.0 and 1.0.\n"
        "4. Return ONLY valid JSON with these exact keys:\n"
        "   {\n"
        "     \"root_cause\": \"<string: the most likely root cause>\",\n"
        "     \"confidence\": <float: 0.0 to 1.0>,\n"
        "     \"evidence\": [\"<string>\", \"<string>\", ...]\n"
        "   }"
    )

    user = (
        f"[Incident Context]\n{state['context']}\n\n"
        f"[User Question]\n{state['question']}\n\n"
        "Perform root cause analysis and return JSON."
    )

    result = _call_llm(system, user)

    return {
        **state,
        "root_cause": result.get("root_cause", "Unable to determine root cause."),
        "confidence": float(result.get("confidence", 0.5)),
        "evidence": result.get("evidence", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — Recommendation Agent
# ─────────────────────────────────────────────────────────────────────────────

def recommendation_agent(state: AgentState) -> AgentState:
    """Generates immediate actions, long-term fixes, and preventive recommendations."""

    system = (
        "You are an Azure Cloud Architect specializing in incident remediation.\n"
        "You are given the root cause of an incident. Your job is to generate actionable recommendations.\n\n"
        "RULES:\n"
        "1. Keep immediate actions concise and numbered (max 4 items).\n"
        "2. Long-term fixes should address the systemic problem (max 3 items).\n"
        "3. Preventive recommendations should stop recurrence (max 3 items).\n"
        "4. Return ONLY valid JSON:\n"
        "   {\n"
        "     \"immediate_actions\": [\"<string>\", ...],\n"
        "     \"long_term_fixes\": [\"<string>\", ...],\n"
        "     \"preventive_recommendations\": [\"<string>\", ...]\n"
        "   }"
    )

    user = (
        f"[Root Cause Identified]\n{state['root_cause']}\n\n"
        f"[Incident Context]\n{state['context']}\n\n"
        f"[Original Question]\n{state['question']}\n\n"
        "Generate remediation recommendations and return JSON."
    )

    result = _call_llm(system, user)

    return {
        **state,
        "immediate_actions": result.get("immediate_actions", []),
        "long_term_fixes": result.get("long_term_fixes", []),
        "preventive_recommendations": result.get("preventive_recommendations", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — Summary Agent
# ─────────────────────────────────────────────────────────────────────────────

def summary_agent(state: AgentState) -> AgentState:
    """Produces executive summary, severity assessment, business impact, and timeline."""

    system = (
        "You are a Technical Incident Manager preparing an executive briefing.\n"
        "You are given a full incident analysis (root cause + recommendations).\n"
        "Produce a concise executive report.\n\n"
        "RULES:\n"
        "1. Executive summary: 2-3 sentences max.\n"
        "2. Severity: one of [Critical, High, Medium, Low].\n"
        "3. Business impact: 1-2 sentences on user/service impact.\n"
        "4. Timeline: estimated time to resolve with current recommendations.\n"
        "5. Return ONLY valid JSON:\n"
        "   {\n"
        "     \"executive_summary\": \"<string>\",\n"
        "     \"severity\": \"<Critical|High|Medium|Low>\",\n"
        "     \"business_impact\": \"<string>\",\n"
        "     \"timeline\": \"<string>\"\n"
        "   }"
    )

    user = (
        f"[Root Cause]\n{state['root_cause']}\n\n"
        f"[Immediate Actions]\n" + "\n".join(f"- {a}" for a in state["immediate_actions"]) + "\n\n"
        f"[Long-term Fixes]\n" + "\n".join(f"- {f}" for f in state["long_term_fixes"]) + "\n\n"
        f"[Original Question]\n{state['question']}\n\n"
        "Produce executive summary and return JSON."
    )

    result = _call_llm(system, user)

    return {
        **state,
        "executive_summary": result.get("executive_summary", ""),
        "severity": result.get("severity", "Unknown"),
        "business_impact": result.get("business_impact", ""),
        "timeline": result.get("timeline", ""),
    }
