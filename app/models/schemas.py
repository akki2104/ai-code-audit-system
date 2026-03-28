from typing import Optional
from pydantic import BaseModel


class FileInfo(BaseModel):
    path: str
    language: str
    content: str
    is_entry_point: bool
    imports: list[str]


class SecurityFinding(BaseModel):
    id: str
    severity: str  # Critical, High, Medium, Low
    category: str  # SQL Injection, XSS, Hardcoded Secret, etc.
    file_path: str
    line_number: Optional[int] = None
    code_snippet: str
    description: str
    fix_suggestion: str
    confidence: float  # 0.0 to 1.0


class QualityFinding(BaseModel):
    id: str
    category: str  # Anti-pattern, Performance, Error Handling, etc.
    file_path: str
    description: str
    suggestion: str


class AuditReport(BaseModel):
    summary: str
    health_score: int  # 0-100
    total_critical: int
    total_high: int
    total_medium: int
    total_low: int
    security_findings: list[SecurityFinding]
    quality_findings: list[QualityFinding]
    files_analyzed: int


class AuditRequest(BaseModel):
    repo_url: str


class AuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    error: Optional[str] = None


class GraphState(dict):
    """LangGraph state for the audit pipeline."""
    pass
