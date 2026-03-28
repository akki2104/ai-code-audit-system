"""Security Auditor Agent — Analyzes code for OWASP Top 10 vulnerabilities."""

import json
import logging
import re

from app.agents.llm import get_llm, is_llm_available, invoke_with_timeout
from app.agents.pattern_scanner import scan_security_patterns
from app.models.schemas import SecurityFinding
from app.prompts.templates import (
    SECURITY_AUDITOR_SYSTEM,
    SECURITY_AUDITOR_USER,
    RE_AUDIT_SYSTEM,
    RE_AUDIT_USER,
)

logger = logging.getLogger("audit.security")

MAX_CONTEXT_CHARS = 30000
MAX_LLM_CHUNKS = 3  # Limit chunks sent to LLM to avoid very long waits


def _build_code_context(files: list[dict]) -> list[str]:
    """Build code context chunks that fit within token limits."""
    chunks = []
    current_chunk = ""

    for f in files:
        file_block = f"\n--- File: {f['path']} (Language: {f['language']}) ---\n{f['content']}\n"
        if len(current_chunk) + len(file_block) > MAX_CONTEXT_CHARS:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = file_block
        else:
            current_chunk += file_block

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _parse_findings_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown code blocks and extra text."""
    text = text.strip()

    # Remove markdown code block wrappers (possibly multiple)
    text = re.sub(r"```(?:json)?\s*\n?", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "findings" in result:
            return result["findings"]
        return [result] if isinstance(result, dict) else []
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array anywhere in the text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to find individual JSON objects and collect them
    objects = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
        try:
            obj = json.loads(m.group())
            if any(k in obj for k in ("id", "vulnerability", "severity", "file", "description")):
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    if objects:
        return objects

    logger.warning(f"Failed to parse security findings JSON from LLM response (len={len(text)})")
    logger.debug(f"LLM raw response: {text[:500]}")
    return []


def _pattern_based_audit(files: list[dict]) -> list[dict]:
    """Fallback: pattern-based security scanning without LLM."""
    all_findings = []
    for f in files:
        findings = scan_security_patterns(f.get("path", ""), f.get("content", ""))
        if findings:
            logger.info(f"   🔍 Pattern scan {f.get('path', '?')}: {len(findings)} findings")
        all_findings.extend([finding.model_dump() for finding in findings])
    return all_findings


def security_auditor_node(state: dict) -> dict:
    """Analyze code for security vulnerabilities using LLM or pattern fallback."""
    import time
    files = state.get("files", [])
    logger.info(f"🔒 SECURITY AUDITOR started | files={len(files)}")
    start = time.time()

    if not files:
        logger.info("🔒 SECURITY AUDITOR skipped (no files)")
        return {"security_findings": [], "status": "reviewing"}

    # Always run pattern-based scan first
    logger.info("🔒 Running pattern-based security scan...")
    all_findings = _pattern_based_audit(files)
    logger.info(f"🔒 Pattern scan found {len(all_findings)} issues")

    # Try LLM for enhanced analysis
    if is_llm_available():
        try:
            llm = get_llm()
            chunks = _build_code_context(files)
            if len(chunks) > MAX_LLM_CHUNKS:
                logger.info(f"🔒 Trimming {len(chunks)} chunks to {MAX_LLM_CHUNKS} (prioritizing entry points)")
                chunks = chunks[:MAX_LLM_CHUNKS]
            logger.info(f"🔒 Sending {len(chunks)} chunk(s) to LLM for enhanced analysis...")
            existing_ids = {f.get("id") for f in all_findings}

            for i, chunk in enumerate(chunks):
                prompt_user = SECURITY_AUDITOR_USER.format(code_context=chunk)
                try:
                    logger.info(f"🔒 LLM call chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
                    chunk_start = time.time()
                    messages = [
                        {"role": "system", "content": SECURITY_AUDITOR_SYSTEM},
                        {"role": "user", "content": prompt_user},
                    ]
                    response = invoke_with_timeout(llm, messages)
                    chunk_elapsed = time.time() - chunk_start
                    raw = response.content if hasattr(response, "content") else str(response)
                    logger.info(f"🔒 LLM responded in {chunk_elapsed:.1f}s ({len(raw)} chars)")
                    findings = _parse_findings_json(raw)
                    logger.info(f"🔒 LLM returned {len(findings)} findings for chunk {i+1}")

                    for f in findings:
                        try:
                            validated = SecurityFinding(**f)
                            if validated.id not in existing_ids:
                                all_findings.append(validated.model_dump())
                                existing_ids.add(validated.id)
                        except Exception:
                            logger.warning(f"Skipping malformed security finding: {f}")
                except Exception as e:
                    logger.error(f"🔒 LLM call FAILED for chunk {i+1}: {e}")
        except Exception as e:
            logger.warning(f"🔒 LLM unavailable, using pattern-based results only: {e}")
    else:
        logger.info("🔒 LLM not available — using pattern-based security scan only")

    elapsed = time.time() - start
    sev_counts = {}
    for f in all_findings:
        s = f.get('severity', 'Unknown')
        sev_counts[s] = sev_counts.get(s, 0) + 1
    logger.info(f"🔒 SECURITY AUDITOR complete in {elapsed:.1f}s | total={len(all_findings)} {sev_counts}")
    return {"security_findings": all_findings, "status": "reviewing"}


def re_audit_node(state: dict) -> dict:
    """Deep re-audit on files with critical findings."""
    import time
    logger.info("🔄 RE-AUDIT (deep scan) started")
    start = time.time()
    files = state.get("files", [])
    security_findings = state.get("security_findings", [])

    # Get files with critical findings
    critical_files = set()
    critical_findings_text = []
    for f in security_findings:
        if f.get("severity") == "Critical":
            critical_files.add(f.get("file_path", ""))
            critical_findings_text.append(
                f"- [{f.get('category')}] {f.get('file_path')}: {f.get('description')}"
            )

    logger.info(f"🔄 Critical files to re-audit: {critical_files}")
    target_files = [f for f in files if f.get("path") in critical_files]
    if not target_files:
        logger.info("🔄 RE-AUDIT skipped (no target files)")
        return {"status": "generating"}

    if not is_llm_available():
        logger.info("🔄 RE-AUDIT skipped (LLM not available)")
        return {"security_findings": security_findings, "status": "generating"}

    try:
        llm = get_llm()
        code_context = ""
        for f in target_files:
            code_context += f"\n--- File: {f['path']} ---\n{f['content']}\n"

        prompt_user = RE_AUDIT_USER.format(
            code_context=code_context[:MAX_CONTEXT_CHARS],
            previous_findings="\n".join(critical_findings_text),
        )

        messages = [
            {"role": "system", "content": RE_AUDIT_SYSTEM},
            {"role": "user", "content": prompt_user},
        ]
        logger.info("🔄 Calling LLM for deep re-audit...")
        reaudit_start = time.time()
        response = invoke_with_timeout(llm, messages)
        reaudit_elapsed = time.time() - reaudit_start
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info(f"🔄 RE-AUDIT LLM responded in {reaudit_elapsed:.1f}s ({len(raw)} chars)")
        new_findings = _parse_findings_json(raw)
        logger.info(f"🔄 RE-AUDIT found {len(new_findings)} additional findings")

        existing_ids = {f.get("id") for f in security_findings}
        for f in new_findings:
            try:
                validated = SecurityFinding(**f)
                if validated.id not in existing_ids:
                    security_findings.append(validated.model_dump())
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Re-audit LLM call failed: {e}")

    return {"security_findings": security_findings, "status": "generating"}
