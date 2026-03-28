"""Report Generator Agent — Compiles all findings into a final audit report."""

import json
import logging
import re

from app.agents.llm import get_llm, is_llm_available, invoke_with_timeout
from app.models.schemas import AuditReport
from app.prompts.templates import REPORT_GENERATOR_SYSTEM, REPORT_GENERATOR_USER

logger = logging.getLogger("audit.report")


def _parse_report_json(text: str) -> dict:
    """Extract JSON object from LLM response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


def _calculate_health_score(security_findings: list[dict], quality_findings: list[dict]) -> int:
    """Calculate health score based on findings."""
    score = 100
    for f in security_findings:
        severity = f.get("severity", "Low")
        if severity == "Critical":
            score -= 15
        elif severity == "High":
            score -= 10
        elif severity == "Medium":
            score -= 5
        elif severity == "Low":
            score -= 2

    score -= len(quality_findings) * 2
    return max(0, min(100, score))


def report_generator_node(state: dict) -> dict:
    """Generate the final audit report."""
    import time
    logger.info("📊 REPORT GENERATOR started")
    start = time.time()
    security_findings = state.get("security_findings", [])
    quality_findings = state.get("quality_findings", [])
    files = state.get("files", [])
    logger.info(f"📊 Compiling report: {len(security_findings)} security + {len(quality_findings)} quality findings")

    # Count by severity
    severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for f in security_findings:
        sev = f.get("severity", "Low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Build summary text for LLM
    security_summary = ""
    for f in security_findings:
        security_summary += (
            f"- [{f.get('severity')}] {f.get('category')}: "
            f"{f.get('description')} (File: {f.get('file_path')})\n"
        )
    if not security_summary:
        security_summary = "No security vulnerabilities found."

    quality_summary = ""
    for f in quality_findings:
        quality_summary += (
            f"- [{f.get('category')}] {f.get('description')} "
            f"(File: {f.get('file_path')})\n"
        )
    if not quality_summary:
        quality_summary = "No code quality issues found."

    # Get LLM summary
    health_score = _calculate_health_score(security_findings, quality_findings)

    # Build a default summary
    default_summary = (
        f"Automated code audit analyzed {len(files)} files. "
        f"Found {len(security_findings)} security issues "
        f"({severity_counts['Critical']} Critical, {severity_counts['High']} High, "
        f"{severity_counts['Medium']} Medium, {severity_counts['Low']} Low) "
        f"and {len(quality_findings)} code quality issues. "
    )
    if severity_counts["Critical"] > 0:
        default_summary += (
            f"URGENT: {severity_counts['Critical']} critical vulnerabilities require immediate attention. "
        )
    if health_score >= 80:
        default_summary += "Overall code health is good."
    elif health_score >= 50:
        default_summary += "Code health needs improvement — address high-severity issues first."
    else:
        default_summary += "Code health is poor — significant security and quality issues found."

    summary_text = default_summary

    if is_llm_available():
        try:
            llm = get_llm()
            logger.info("📊 Calling LLM for executive summary...")
            llm_start = time.time()
            prompt_user = REPORT_GENERATOR_USER.format(
                security_count=len(security_findings),
                security_summary=security_summary[:3000],
                quality_count=len(quality_findings),
                quality_summary=quality_summary[:3000],
                files_analyzed=len(files),
            )
            messages = [
                {"role": "system", "content": REPORT_GENERATOR_SYSTEM},
                {"role": "user", "content": prompt_user},
            ]
            response = invoke_with_timeout(llm, messages)
            raw = response.content if hasattr(response, "content") else str(response)
            report_data = _parse_report_json(raw)

            llm_elapsed = time.time() - llm_start
            logger.info(f"📊 LLM summary received in {llm_elapsed:.1f}s")
            if "summary" in report_data:
                summary_text = report_data["summary"]
            if "health_score" in report_data:
                health_score = max(0, min(100, int(report_data["health_score"])))
        except Exception as e:
            logger.error(f"📊 LLM call FAILED, using default summary: {e}")

    report = AuditReport(
        summary=summary_text,
        health_score=health_score,
        total_critical=severity_counts["Critical"],
        total_high=severity_counts["High"],
        total_medium=severity_counts["Medium"],
        total_low=severity_counts["Low"],
        security_findings=security_findings,
        quality_findings=quality_findings,
        files_analyzed=len(files),
    )

    elapsed = time.time() - start
    logger.info(
        f"📊 REPORT GENERATOR complete in {elapsed:.1f}s | "
        f"score={health_score} critical={severity_counts['Critical']} "
        f"high={severity_counts['High']} medium={severity_counts['Medium']} "
        f"low={severity_counts['Low']}"
    )

    return {
        "report": report.model_dump(),
        "status": "complete",
    }
