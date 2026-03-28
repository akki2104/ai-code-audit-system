import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path


def generate_audit_id() -> str:
    return str(uuid.uuid4())


def extract_zip(zip_path: str, extract_to: str) -> str:
    """Extract a zip file to the target directory. Returns the extraction path."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Security: validate no path traversal in zip entries
        for member in zf.namelist():
            member_path = os.path.normpath(member)
            if member_path.startswith("..") or os.path.isabs(member_path):
                raise ValueError(f"Unsafe path in zip: {member}")
        zf.extractall(extract_to)

    # If zip contains a single root directory, return that
    entries = os.listdir(extract_to)
    if len(entries) == 1:
        single_entry = os.path.join(extract_to, entries[0])
        if os.path.isdir(single_entry):
            return single_entry
    return extract_to


def clone_github_repo(repo_url: str, target_dir: str) -> str:
    """Clone a GitHub repo to target directory."""
    try:
        import git
    except ImportError:
        raise RuntimeError("gitpython is required for GitHub cloning. Install with: pip install gitpython")

    # Validate URL format
    if not (repo_url.startswith("https://github.com/") or repo_url.startswith("https://gitlab.com/")):
        raise ValueError("Only GitHub and GitLab HTTPS URLs are supported")

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = os.path.join(target_dir, repo_name)

    git.Repo.clone_from(repo_url, clone_path, depth=1)
    return clone_path


def create_temp_directory() -> str:
    """Create a temporary directory for file processing."""
    return tempfile.mkdtemp(prefix="code_audit_")


def cleanup_directory(path: str) -> None:
    """Remove a directory and all its contents."""
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def save_upload_file(file_content: bytes, filename: str, target_dir: str) -> str:
    """Save uploaded file bytes to the target directory."""
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path
