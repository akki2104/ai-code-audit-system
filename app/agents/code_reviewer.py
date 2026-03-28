"""Code Quality Reviewer Agent — Checks for anti-patterns and code quality issues."""

import json
import logging
import re

from app.agents.llm import get_llm, is_llm_available, invoke_with_timeout
from app.agents.pattern_scanner import scan_quality_patterns
from app.models.schemas import QualityFinding
from app.prompts.templates import CODE_REVIEWER_SYSTEM, CODE_REVIEWER_USER

logger = logging.getLogger("audit.quality")

MAX_CONTEXT_CHARS = 30000
MAX_LLM_CHUNKS = 3


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

    # Remove markdown code block wrappers
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

    # Try to find individual JSON objects
    objects = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
        try:
            obj = json.loads(m.group())
            if any(k in obj for k in ("id", "issue", "category", "file", "description")):
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    if objects:
        return objects

    logger.warning(f"Failed to parse quality findings JSON from LLM response (len={len(text)})")
    logger.debug(f"LLM raw response: {text[:500]}")
    return []


def code_reviewer_node(state: dict) -> dict:
    """Analyze code for quality issues using LLM or pattern fallback."""
    import time
    files = state.get("files", [])
    logger.info(f"🔧 CODE REVIEWER started | files={len(files)}")
    start = time.time()

    if not files:
        logger.info("🔧 CODE REVIEWER skipped (no files)")
        return {"quality_findings": [], "status": "generating"}

    # Always run pattern-based scan first
    logger.info("🔧 Running pattern-based quality scan...")
    all_findings: list[dict] = []
    for f in files:
        findings = scan_quality_patterns(
            f.get("path", ""), f.get("content", ""), f.get("language", "")
        )
        if findings:
            logger.info(f"   🔍 Pattern scan {f.get('path', '?')}: {len(findings)} quality issues")
        all_findings.extend([finding.model_dump() for finding in findings])
    logger.info(f"🔧 Pattern scan found {len(all_findings)} quality issues")

    # Try LLM for enhanced analysis
    if is_llm_available():
        try:
            llm = get_llm()
            chunks = _build_code_context(files)
            if len(chunks) > MAX_LLM_CHUNKS:
                logger.info(f"🔧 Trimming {len(chunks)} chunks to {MAX_LLM_CHUNKS} (prioritizing entry points)")
                chunks = chunks[:MAX_LLM_CHUNKS]
            logger.info(f"🔧 Sending {len(chunks)} chunk(s) to LLM for enhanced review...")
            existing_descs = {f.get("description") for f in all_findings}

            for i, chunk in enumerate(chunks):
                prompt_user = CODE_REVIEWER_USER.format(code_context=chunk)

                try:
                    logger.info(f"🔧 LLM call chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
                    chunk_start = time.time()
                    messages = [
                        {"role": "system", "content": CODE_REVIEWER_SYSTEM},
                        {"role": "user", "content": prompt_user},
                    ]
                    response = invoke_with_timeout(llm, messages)
                    chunk_elapsed = time.time() - chunk_start
                    raw = response.content if hasattr(response, "content") else str(response)
                    logger.info(f"🔧 LLM responded in {chunk_elapsed:.1f}s ({len(raw)} chars)")
                    findings = _parse_findings_json(raw)
                    logger.info(f"🔧 LLM returned {len(findings)} quality findings for chunk {i+1}")

                    for f in findings:
                        try:
                            validated = QualityFinding(**f)
                            if validated.description not in existing_descs:
                                all_findings.append(validated.model_dump())
                                existing_descs.add(validated.description)
                        except Exception:
                            logger.warning(f"Skipping malformed quality finding: {f}")
                except Exception as e:
                    logger.error(f"🔧 LLM call FAILED for chunk {i+1}: {e}")
        except Exception as e:
            logger.warning(f"🔧 LLM unavailable for code review: {e}")
    else:
        logger.info("🔧 LLM not available — using pattern-based code review only")

    elapsed = time.time() - start
    cats = {}
    for f in all_findings:
        c = f.get('category', 'Unknown')
        cats[c] = cats.get(c, 0) + 1
    logger.info(f"🔧 CODE REVIEWER complete in {elapsed:.1f}s | total={len(all_findings)} {cats}")
    return {"quality_findings": all_findings, "status": "generating"}
