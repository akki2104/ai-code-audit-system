"""Pattern-based security and quality analysis — works without any LLM.
Used as a fallback when no LLM provider is available, or as a first-pass scanner."""

import re
import ast
import logging
from typing import Optional
from app.models.schemas import SecurityFinding, QualityFinding

logger = logging.getLogger(__name__)

# ─── Security Patterns ───

HARDCODED_SECRET_PATTERNS = [
    (r'(?:API_KEY|SECRET_KEY|API_SECRET|PRIVATE_KEY|ACCESS_KEY|AWS_SECRET)\s*=\s*["\'][^"\']{8,}["\']',
     "Hardcoded Secret", "Critical"),
    (r'(?:PASSWORD|DB_PASSWORD|REDIS_PASSWORD|DB_PASS)\s*=\s*["\'][^"\']+["\']',
     "Hardcoded Password", "Critical"),
    (r'(?:TOKEN|AUTH_TOKEN|JWT_SECRET|ENCRYPTION_KEY)\s*=\s*["\'][^"\']{8,}["\']',
     "Hardcoded Token/Key", "Critical"),
    (r'(?:DATABASE_URL|REDIS_URL|MONGODB_URI)\s*=\s*["\'][^"\']*(?:password|secret|key)[^"\']*["\']',
     "Hardcoded Database Credential", "Critical"),
    (r'sk-[a-zA-Z0-9]{20,}', "Hardcoded OpenAI Key", "Critical"),
    (r'AKIA[0-9A-Z]{16}', "Hardcoded AWS Access Key", "Critical"),
]

SQL_INJECTION_PATTERNS = [
    (r'execute\s*\(\s*["\'].*?\'\s*\+\s*\w+', "SQL Injection via String Concatenation", "Critical"),
    (r'execute\s*\(\s*f["\']', "SQL Injection via F-String", "Critical"),
    (r'execute\s*\(\s*["\'].*?%s.*?["\']\s*%', "SQL Injection via % Formatting", "High"),
    (r'\.format\(.*?\).*?execute', "SQL Injection via .format()", "Critical"),
    (r'cursor\.execute\s*\(\s*["\'].*?\+', "SQL Injection in Cursor Execute", "Critical"),
]

XSS_PATTERNS = [
    (r'return\s+f["\']<.*?\{.*?request\.\w+', "XSS via Unescaped User Input in HTML", "High"),
    (r'return\s+["\']<.*?\+\s*request\.\w+', "XSS via String Concatenation", "High"),
    (r'innerHTML\s*=\s*.*?request', "XSS via innerHTML Assignment", "High"),
]

AUTH_PATTERNS = [
    (r'@app\.route\s*\(\s*["\']\/admin.*?["\']', "Admin Route (check for auth)", "Medium"),
    (r'def\s+delete_\w+.*?:.*?(?!auth|login|permission)', "Destructive Action Without Auth Check", "High"),
]

MISC_SECURITY_PATTERNS = [
    (r'DEBUG\s*=\s*True', "Debug Mode Enabled", "Medium", "Security Misconfiguration"),
    (r'app\.run\s*\(.*?debug\s*=\s*True', "Debug Mode in Production", "Medium", "Security Misconfiguration"),
    (r'host\s*=\s*["\']0\.0\.0\.0["\']', "Binding to All Interfaces", "Medium", "Security Misconfiguration"),
    (r'Access-Control-Allow-Origin.*?\*', "Permissive CORS Configuration", "Medium", "Security Misconfiguration"),
    (r'CORS_ORIGINS\s*=\s*\[\s*["\']\*["\']', "Permissive CORS Configuration", "Medium", "Security Misconfiguration"),
    (r'pickle\.loads?\s*\(', "Insecure Deserialization (pickle)", "High", "Insecure Deserialization"),
    (r'yaml\.load\s*\((?!.*Loader\s*=\s*yaml\.SafeLoader)', "Insecure YAML Deserialization", "High", "Insecure Deserialization"),
    (r'eval\s*\(', "Use of eval()", "High", "Code Injection"),
    (r'exec\s*\(', "Use of exec()", "High", "Code Injection"),
    (r'subprocess\.(?:run|call|Popen)\s*\(.*?shell\s*=\s*True', "Command Injection Risk (shell=True)", "High", "Command Injection"),
    (r'os\.system\s*\(', "Command Injection Risk (os.system)", "High", "Command Injection"),
    (r'os\.path\.join\s*\(.*?request\.', "Potential Directory Traversal", "High", "Directory Traversal"),
    (r'open\s*\(.*?request\.\w+', "File Access with User Input", "High", "Directory Traversal"),
    (r'hashlib\.md5\s*\(', "Weak Hash Algorithm (MD5)", "Medium", "Cryptographic Weakness"),
    (r'hashlib\.sha1\s*\(', "Weak Hash Algorithm (SHA1)", "Medium", "Cryptographic Weakness"),
    (r'SESSION_COOKIE_SECURE\s*=\s*False', "Insecure Session Cookie", "Medium", "Security Misconfiguration"),
    (r'SESSION_COOKIE_HTTPONLY\s*=\s*False', "HTTPOnly Cookie Disabled", "Medium", "Security Misconfiguration"),
    (r'RATE_LIMIT_ENABLED\s*=\s*False', "Rate Limiting Disabled", "Medium", "Security Misconfiguration"),
    (r'password.*?==\s*', "Plaintext Password Comparison", "High", "Broken Authentication"),
]

# ─── Quality Patterns ───

QUALITY_PATTERNS = [
    (r'except\s*:', "Bare Except Clause", "Error Handling",
     "Use specific exception types instead of bare except"),
    (r'except\s+Exception\s*:', "Broad Exception Catch", "Error Handling",
     "Catch specific exception types rather than generic Exception"),
    (r'#\s*TODO', "TODO Comment Left in Code", "Code Organization",
     "Resolve or track TODO items properly"),
    (r'#\s*FIXME', "FIXME Comment Found", "Code Organization",
     "Address FIXME comments before production"),
    (r'import\s+\*', "Wildcard Import", "Anti-pattern",
     "Import only needed names to improve readability and avoid namespace pollution"),
    (r'global\s+\w+', "Global Variable Usage", "Anti-pattern",
     "Avoid global mutable state; use dependency injection or class attributes"),
    (r'time\.sleep\s*\(', "Synchronous Sleep", "Performance",
     "Use asyncio.sleep() in async code or consider event-based approaches"),
]


def _get_line_number(content: str, match_start: int) -> int:
    """Get 1-based line number from character position."""
    return content[:match_start].count('\n') + 1


def _get_code_snippet(content: str, line_num: int, context: int = 1) -> str:
    """Extract code around a given line."""
    lines = content.split('\n')
    start = max(0, line_num - 1 - context)
    end = min(len(lines), line_num + context)
    return '\n'.join(lines[start:end])


def _check_function_length(content: str, file_path: str) -> list[QualityFinding]:
    """Check for overly long functions using AST."""
    findings = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_length = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                if func_length > 50:
                    findings.append(QualityFinding(
                        id=f"QUA-LONG-{node.lineno}",
                        category="Anti-pattern",
                        file_path=file_path,
                        description=f"Function '{node.name}' is {func_length} lines long (>{50} threshold)",
                        suggestion="Break this function into smaller, focused helper functions",
                    ))
    except SyntaxError:
        pass
    return findings


def _check_nesting_depth(content: str, file_path: str) -> list[QualityFinding]:
    """Check for deeply nested code."""
    findings = []
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped and not stripped.startswith('#'):
            indent = len(line) - len(stripped)
            depth = indent // 4  # Assuming 4-space indentation
            if depth > 4:
                findings.append(QualityFinding(
                    id=f"QUA-NEST-{i}",
                    category="Anti-pattern",
                    file_path=file_path,
                    description=f"Deeply nested code at line {i} (depth: {depth} levels)",
                    suggestion="Refactor using early returns, guard clauses, or extract helper functions",
                ))
                break  # Only report first instance per file
    return findings


def _check_missing_type_hints(content: str, file_path: str) -> list[QualityFinding]:
    """Check for public functions missing type hints."""
    findings = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith('_'):
                    continue
                if node.returns is None:
                    findings.append(QualityFinding(
                        id=f"QUA-TYPE-{node.lineno}",
                        category="Type Safety",
                        file_path=file_path,
                        description=f"Public function '{node.name}' missing return type hint",
                        suggestion=f"Add return type annotation: def {node.name}(...) -> ReturnType:",
                    ))
    except SyntaxError:
        pass
    return findings


def scan_security_patterns(file_path: str, content: str) -> list[SecurityFinding]:
    """Scan a file for security vulnerabilities using regex patterns."""
    findings: list[SecurityFinding] = []
    finding_id = 0

    # Hardcoded secrets
    for pattern, name, severity in HARDCODED_SECRET_PATTERNS:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            finding_id += 1
            line_num = _get_line_number(content, match.start())
            findings.append(SecurityFinding(
                id=f"SEC-{finding_id:03d}",
                severity=severity,
                category="Hardcoded Secret",
                file_path=file_path,
                line_number=line_num,
                code_snippet=_get_code_snippet(content, line_num),
                description=f"{name} found: sensitive value hardcoded in source code",
                fix_suggestion="Move secrets to environment variables and use os.getenv() or a secrets manager",
                confidence=0.95,
            ))

    # SQL injection
    for pattern, name, severity in SQL_INJECTION_PATTERNS:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            finding_id += 1
            line_num = _get_line_number(content, match.start())
            findings.append(SecurityFinding(
                id=f"SEC-{finding_id:03d}",
                severity=severity,
                category="SQL Injection",
                file_path=file_path,
                line_number=line_num,
                code_snippet=_get_code_snippet(content, line_num),
                description=f"{name}: user input may be directly concatenated into SQL query",
                fix_suggestion="Use parameterized queries: cursor.execute('SELECT * FROM users WHERE name = ?', (name,))",
                confidence=0.9,
            ))

    # XSS
    for pattern, name, severity in XSS_PATTERNS:
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            finding_id += 1
            line_num = _get_line_number(content, match.start())
            findings.append(SecurityFinding(
                id=f"SEC-{finding_id:03d}",
                severity=severity,
                category="XSS",
                file_path=file_path,
                line_number=line_num,
                code_snippet=_get_code_snippet(content, line_num),
                description=f"{name}: user input rendered in HTML response without escaping",
                fix_suggestion="Use a templating engine with auto-escaping (e.g., Jinja2) or markupsafe.escape()",
                confidence=0.85,
            ))

    # Misc security patterns
    for item in MISC_SECURITY_PATTERNS:
        if len(item) == 4:
            pattern, name, severity, category = item
        else:
            pattern, name, severity = item
            category = "Security Misconfiguration"

        for match in re.finditer(pattern, content, re.IGNORECASE):
            finding_id += 1
            line_num = _get_line_number(content, match.start())
            findings.append(SecurityFinding(
                id=f"SEC-{finding_id:03d}",
                severity=severity,
                category=category,
                file_path=file_path,
                line_number=line_num,
                code_snippet=_get_code_snippet(content, line_num),
                description=f"{name} detected",
                fix_suggestion=_get_fix_suggestion(category, name),
                confidence=0.85,
            ))

    # Auth checks on admin routes
    if re.search(r'@app\.route\s*\(\s*["\']\/admin', content):
        if not re.search(r'@login_required|@auth_required|@requires_auth|verify_token|check_auth', content):
            finding_id += 1
            findings.append(SecurityFinding(
                id=f"SEC-{finding_id:03d}",
                severity="High",
                category="Broken Authentication",
                file_path=file_path,
                line_number=None,
                code_snippet="",
                description="Admin routes found without authentication decorators or middleware",
                fix_suggestion="Add authentication middleware: @login_required or implement JWT verification",
                confidence=0.8,
            ))

    return findings


def scan_quality_patterns(file_path: str, content: str, language: str) -> list[QualityFinding]:
    """Scan a file for code quality issues."""
    findings: list[QualityFinding] = []
    finding_id = 0

    # Regex-based patterns
    for pattern, name, category, suggestion in QUALITY_PATTERNS:
        for match in re.finditer(pattern, content):
            finding_id += 1
            line_num = _get_line_number(content, match.start())
            findings.append(QualityFinding(
                id=f"QUA-{finding_id:03d}",
                category=category,
                file_path=file_path,
                description=f"{name} at line {line_num}",
                suggestion=suggestion,
            ))

    # AST-based checks for Python
    if language == "python":
        findings.extend(_check_function_length(content, file_path))
        findings.extend(_check_nesting_depth(content, file_path))
        findings.extend(_check_missing_type_hints(content, file_path))

    return findings


def _get_fix_suggestion(category: str, name: str) -> str:
    """Get contextual fix suggestion based on category."""
    suggestions = {
        "Security Misconfiguration": "Set DEBUG=False in production. Use environment-specific configuration.",
        "Insecure Deserialization": "Use json.loads() instead of pickle. Use yaml.safe_load() instead of yaml.load().",
        "Code Injection": "Avoid eval/exec. Use ast.literal_eval() for safe evaluation of literals.",
        "Command Injection": "Use subprocess.run() with a list of arguments instead of shell=True.",
        "Directory Traversal": "Validate and sanitize file paths. Use os.path.realpath() and verify the path is within the allowed directory.",
        "Cryptographic Weakness": "Use bcrypt, scrypt, or argon2 for password hashing. Use SHA-256+ for general hashing.",
        "Broken Authentication": "Implement proper authentication with password hashing, session management, and rate limiting.",
    }
    return suggestions.get(category, f"Review and fix: {name}")
