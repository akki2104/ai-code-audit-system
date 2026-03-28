"""LangGraph workflow — wires all 4 agents into a state machine with conditional edges."""

import logging
from typing import Any, TypedDict, Optional
from langgraph.graph import StateGraph, END

from app.agents.scanner import scanner_node
from app.agents.security_auditor import security_auditor_node, re_audit_node
from app.agents.code_reviewer import code_reviewer_node
from app.agents.report_generator import report_generator_node

logger = logging.getLogger("audit.graph")


class GraphState(TypedDict):
    source_path: str
    files: list[dict]
    security_findings: list[dict]
    quality_findings: list[dict]
    report: Optional[dict]
    status: str
    error: Optional[str]


def should_re_audit(state: GraphState) -> str:
    """Conditional edge: route to re_audit if >3 critical findings."""
    security_findings = state.get("security_findings", [])
    critical_count = sum(
        1 for f in security_findings if f.get("severity") == "Critical"
    )
    if critical_count > 3:
        logger.info(f"⚡ Routing to RE-AUDIT (critical_count={critical_count} > 3)")
        return "re_audit"
    logger.info(f"⚡ Skipping re-audit (critical_count={critical_count} <= 3) → report_generator")
    return "report_generator"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("scanner", scanner_node)
    workflow.add_node("security_auditor", security_auditor_node)
    workflow.add_node("code_reviewer", code_reviewer_node)
    workflow.add_node("re_audit", re_audit_node)
    workflow.add_node("report_generator", report_generator_node)

    # Set entry point
    workflow.set_entry_point("scanner")

    # Add edges
    workflow.add_edge("scanner", "security_auditor")
    workflow.add_edge("security_auditor", "code_reviewer")

    # Conditional edge after code_reviewer
    workflow.add_conditional_edges(
        "code_reviewer",
        should_re_audit,
        {
            "re_audit": "re_audit",
            "report_generator": "report_generator",
        },
    )

    workflow.add_edge("re_audit", "report_generator")
    workflow.add_edge("report_generator", END)

    return workflow.compile()


# Singleton compiled graph
audit_graph = build_graph()


def run_audit(source_path: str) -> dict:
    """Run the full audit pipeline on a source directory."""
    logger.info(f"{'='*60}")
    logger.info(f"🚀 AUDIT PIPELINE STARTING | source={source_path}")
    logger.info(f"{'='*60}")
    initial_state: GraphState = {
        "source_path": source_path,
        "files": [],
        "security_findings": [],
        "quality_findings": [],
        "report": None,
        "status": "scanning",
        "error": None,
    }

    result = audit_graph.invoke(initial_state)
    logger.info(f"{'='*60}")
    logger.info(f"✅ AUDIT PIPELINE FINISHED | status={result.get('status')}")
    logger.info(f"{'='*60}")
    return result
