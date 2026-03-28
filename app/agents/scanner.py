"""Scanner Agent — Traverses file tree and extracts code for analysis."""

import logging
import time
from app.parsers.file_parser import parse_file_tree
from app.models.schemas import FileInfo

logger = logging.getLogger("audit.scanner")


def scanner_node(state: dict) -> dict:
    """Scan the source directory and extract file information."""
    source_path = state["source_path"]
    logger.info(f"📂 SCANNER started | path: {source_path}")
    start = time.time()

    files: list[FileInfo] = parse_file_tree(source_path)

    # Sort: entry points first, then by path
    files.sort(key=lambda f: (not f.is_entry_point, f.path))

    elapsed = time.time() - start
    entry_points = [f.path for f in files if f.is_entry_point]
    languages = set(f.language for f in files)
    logger.info(
        f"📂 SCANNER complete in {elapsed:.2f}s | "
        f"files={len(files)} languages={languages} "
        f"entry_points={entry_points}"
    )
    for f in files:
        logger.info(f"   📄 {f.path} ({f.language}, {len(f.content)} chars, imports={len(f.imports)})")

    return {
        "files": [f.model_dump() for f in files],
        "status": "auditing",
    }
