import os
import ast
from pathlib import Path

from app.config import settings
from app.models.schemas import FileInfo


ENTRY_POINT_PATTERNS = {
    "main.py", "app.py", "server.py", "index.py", "manage.py",
    "wsgi.py", "asgi.py", "index.js", "index.ts", "server.js",
    "server.ts", "main.go", "Main.java",
}

ROUTE_INDICATORS = {
    "@app.route", "@router.", "app.get", "app.post", "app.put",
    "app.delete", "app.patch", "@api_view", "router.get", "router.post",
    "express()", "FastAPI", "APIRouter",
}


def is_supported_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in settings.SUPPORTED_EXTENSIONS


def should_skip_dir(dir_name: str) -> bool:
    return dir_name in settings.SKIP_DIRS


def extract_python_imports(content: str) -> list[str]:
    imports = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
    except SyntaxError:
        # Fallback: regex-like line parsing
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("import "):
                imports.append(line.split("import ")[1].split(",")[0].strip())
            elif line.startswith("from "):
                parts = line.split("import")
                if parts:
                    imports.append(parts[0].replace("from ", "").strip())
    return imports


def extract_js_imports(content: str) -> list[str]:
    imports = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("import ") or "require(" in line:
            imports.append(line)
    return imports


def detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".go": "go", ".rb": "ruby",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "unknown")


def is_entry_point(file_path: str, content: str) -> bool:
    filename = Path(file_path).name
    if filename in ENTRY_POINT_PATTERNS:
        return True
    for indicator in ROUTE_INDICATORS:
        if indicator in content:
            return True
    if '__name__' in content and '__main__' in content:
        return True
    return False


def parse_file_tree(root_path: str) -> list[FileInfo]:
    """Traverse directory tree and extract file information."""
    files: list[FileInfo] = []
    root = Path(root_path)

    if not root.exists():
        return files

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out directories to skip (in-place modification)
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for filename in filenames:
            file_path = os.path.join(dirpath, filename)

            if not is_supported_file(file_path):
                continue

            # Skip large files
            try:
                file_size = os.path.getsize(file_path)
                if file_size > settings.MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            rel_path = os.path.relpath(file_path, root_path)
            language = detect_language(file_path)

            if language == "python":
                imports = extract_python_imports(content)
            elif language in ("javascript", "typescript"):
                imports = extract_js_imports(content)
            else:
                imports = []

            files.append(FileInfo(
                path=rel_path,
                language=language,
                content=content,
                is_entry_point=is_entry_point(file_path, content),
                imports=imports,
            ))

    return files
