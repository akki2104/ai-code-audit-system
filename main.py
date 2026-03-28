"""FastAPI application — API endpoints for code audit system."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.graph import run_audit
from app.models.schemas import AuditRequest, AuditReport
from app.utils.helpers import (
    create_temp_directory,
    extract_zip,
    clone_github_repo,
    save_upload_file,
    cleanup_directory,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("audit.api")

# In-memory store for audit results
audit_store: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Cleanup temp directories on shutdown
    for audit_id, data in audit_store.items():
        temp_dir = data.get("temp_dir")
        if temp_dir:
            cleanup_directory(temp_dir)


app = FastAPI(
    title="AI Code Audit System",
    description="Multi-Agent Code Review & Security Audit System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for hosted deployment
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _run_audit_pipeline(audit_id: str, source_path: str, temp_dir: str):
    """Run the audit pipeline and store results."""
    import time
    start_time = time.time()
    logger.info(f"[{audit_id[:8]}] ▶ Pipeline STARTED | source: {source_path}")
    try:
        audit_store[audit_id]["status"] = "scanning"
        result = run_audit(source_path)
        audit_store[audit_id]["status"] = result.get("status", "complete")
        audit_store[audit_id]["report"] = result.get("report")
        audit_store[audit_id]["files_count"] = len(result.get("files", []))
        elapsed = time.time() - start_time
        report = result.get("report", {})
        logger.info(
            f"[{audit_id[:8]}] ✔ Pipeline COMPLETE in {elapsed:.1f}s | "
            f"files={len(result.get('files', []))} "
            f"security={len(result.get('security_findings', []))} "
            f"quality={len(result.get('quality_findings', []))} "
            f"score={report.get('health_score', '?')}"
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{audit_id[:8]}] ✘ Pipeline FAILED after {elapsed:.1f}s: {e}")
        audit_store[audit_id]["status"] = "error"
        audit_store[audit_id]["error"] = str(e)


@app.post("/api/audit/upload")
async def upload_audit(file: UploadFile = File(...)):
    """Upload a zip file for code audit."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    audit_id = str(uuid4())
    temp_dir = create_temp_directory()

    try:
        content = await file.read()
        zip_path = save_upload_file(content, file.filename, temp_dir)
        source_path = extract_zip(zip_path, os.path.join(temp_dir, "extracted"))
    except ValueError as e:
        cleanup_directory(temp_dir)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        cleanup_directory(temp_dir)
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {e}")

    audit_store[audit_id] = {
        "status": "queued",
        "report": None,
        "error": None,
        "temp_dir": temp_dir,
    }

    # Run audit in background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_audit_pipeline, audit_id, source_path, temp_dir)

    return {"audit_id": audit_id, "status": "queued"}


@app.post("/api/audit/github")
async def github_audit(request: AuditRequest):
    """Clone a GitHub repo and run code audit."""
    repo_url = request.repo_url.strip()

    if not repo_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Only HTTPS URLs are supported")

    audit_id = str(uuid4())
    temp_dir = create_temp_directory()

    try:
        source_path = clone_github_repo(repo_url, temp_dir)
    except ValueError as e:
        cleanup_directory(temp_dir)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        cleanup_directory(temp_dir)
        raise HTTPException(status_code=500, detail=f"Failed to clone repo: {e}")

    audit_store[audit_id] = {
        "status": "queued",
        "report": None,
        "error": None,
        "temp_dir": temp_dir,
    }

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_audit_pipeline, audit_id, source_path, temp_dir)

    return {"audit_id": audit_id, "status": "queued"}


@app.get("/api/audit/{audit_id}/status")
async def get_audit_status(audit_id: str):
    """Get the current status of an audit."""
    if audit_id not in audit_store:
        raise HTTPException(status_code=404, detail="Audit not found")

    data = audit_store[audit_id]
    return {
        "audit_id": audit_id,
        "status": data["status"],
        "error": data.get("error"),
    }


@app.get("/api/audit/{audit_id}/report")
async def get_audit_report(audit_id: str):
    """Get the final audit report."""
    if audit_id not in audit_store:
        raise HTTPException(status_code=404, detail="Audit not found")

    data = audit_store[audit_id]
    if data["status"] == "error":
        raise HTTPException(status_code=500, detail=data.get("error", "Audit failed"))
    if data["status"] != "complete":
        raise HTTPException(status_code=202, detail="Audit still in progress")
    if not data.get("report"):
        raise HTTPException(status_code=500, detail="Report not available")

    return data["report"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
