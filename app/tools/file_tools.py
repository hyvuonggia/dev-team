"""
General file system tools using LangChain tool framework.

These are low-level file operations that can be used by any agent.
Safety checks: path validation, sandboxing, protected paths.
"""

import os
import pathlib
import hashlib
import re
from typing import List, Tuple, Any, Dict
from langchain.tools import tool
import json
import logging
from datetime import datetime
import difflib


PROTECTED_PATTERNS = [
    ".git",
    ".github",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".env",
    "secrets.json",
    "config.yaml",
    "docker-compose.yml",
    ".dockerignore",
]


class FileToolError(Exception):
    """Error raised by file tools."""

    pass


WORKSPACE_ROOT = pathlib.Path(os.environ.get("WORKSPACE_ROOT", "workspace")).resolve()

logger = logging.getLogger(__name__)


def _resolve_and_validate(path: str, project_id: str) -> pathlib.Path:
    """Resolve and validate a path within the project workspace."""
    if os.path.isabs(path):
        raise FileToolError("Absolute paths are not allowed")
    if ".." in pathlib.Path(path).parts:
        raise FileToolError("Parent traversal is not allowed")
    project_root = WORKSPACE_ROOT / project_id
    project_root.mkdir(parents=True, exist_ok=True)
    target = (project_root / path).resolve()
    try:
        target.relative_to(project_root.resolve())
    except Exception:
        raise FileToolError("Path escapes project workspace")
    rel_path = str(target.relative_to(project_root))
    for pattern in PROTECTED_PATTERNS:
        if pattern in rel_path.lower():
            raise FileToolError(
                f"Protected pattern '{pattern}' matched in path {rel_path}"
            )
    return target


def _read_file_impl(path: str, project_id: str) -> str:
    """
    Core implementation to read a file from the project workspace.

    Args:
        path: Relative path to the file within the project
        project_id: Project identifier for workspace isolation

    Returns:
        File contents as string
    """
    target = _resolve_and_validate(path, project_id)
    if not target.exists():
        raise FileToolError("File not found")
    return target.read_text(encoding="utf-8")


@tool
def read_file(path: str, project_id: str) -> str:
    """
    Read a file from the project workspace.

    Args:
        path: Relative path to the file within the project
        project_id: Project identifier for workspace isolation

    Returns:
        File contents as string
    """
    return _read_file_impl(path, project_id)


def _list_files_impl(directory: str, project_id: str) -> List[str]:
    """
    Core implementation to list files in a directory within the project workspace.

    Args:
        directory: Relative directory path
        project_id: Project identifier

    Returns:
        List of relative file paths
    """
    target = _resolve_and_validate(directory, project_id)
    if not target.exists():
        return []
    files = []
    for root, _, filenames in os.walk(target):
        for fn in filenames:
            rel = (
                pathlib.Path(root).joinpath(fn).relative_to(WORKSPACE_ROOT / project_id)
            )
            files.append(str(rel))
    return files


@tool
def list_files(directory: str, project_id: str) -> List[str]:
    """
    List files in a directory within the project workspace.

    Args:
        directory: Relative directory path
        project_id: Project identifier

    Returns:
        List of relative file paths
    """
    return _list_files_impl(directory, project_id)


def _read_directory_structure_impl(project_id: str) -> List[str]:
    """
    Core implementation to get the complete directory structure of the project.

    Args:
        project_id: Project identifier

    Returns:
        List of all paths in the project
    """
    root = (WORKSPACE_ROOT / project_id).resolve()
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*"):
        out.append(str(p.relative_to(root)))
    return out


@tool
def read_directory_structure(project_id: str) -> List[str]:
    """
    Get the complete directory structure of the project.

    Args:
        project_id: Project identifier

    Returns:
        List of all paths in the project
    """
    return _read_directory_structure_impl(project_id)


def _checksum(s: str) -> str:
    """Generate SHA256 checksum of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _write_file_impl(
    path: str, content: str, project_id: str, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Core implementation to write file into project workspace safely with full safety checks.

    Args:
        path: Relative path to the file
        content: File content to write
        project_id: Project identifier
        dry_run: If True, validate/log but don't write; returns diff if file exists

    Returns:
        Dict with success, path, size, checksum, diff (dry_run), message
    """
    target = _resolve_and_validate(path, project_id)
    rel = target.relative_to(WORKSPACE_ROOT / project_id)
    content_bytes = content.encode("utf-8")

    # Size limit 1MB
    if len(content_bytes) > 1024 * 1024:
        raise FileToolError("File size exceeds 1MB limit")

    checksum = _checksum(content)

    # Basic content validation
    suspicious_patterns = [r"__import__\(\'os\'\)", r"exec\(", r"eval\(", r"compile\("]
    if rel.suffix.lower() == ".py" and any(
        re.search(pattern, content) for pattern in suspicious_patterns
    ):
        raise FileToolError(
            "Suspicious code detected in Python file (exec/eval/os import)"
        )

    # Audit log BEFORE any write
    project_root = WORKSPACE_ROOT / project_id
    audit_path = project_root / "audit.log"
    project_root.mkdir(parents=True, exist_ok=True)

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "write_file",
        "project_id": project_id,
        "path": str(rel),
        "size_bytes": len(content_bytes),
        "checksum": checksum,
        "dry_run": dry_run,
    }

    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry) + "\n")

    logger.info(
        f"Write audit logged: project={project_id}, path={rel}, size={len(content_bytes)}, checksum={checksum[:8]}..., dry_run={dry_run}"
    )

    if dry_run:
        diff = None
        diff_size = 0
        if target.exists():
            try:
                old_content = target.read_text(encoding="utf-8")
                diff_lines = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    n=3,
                )
                diff = "".join(diff_lines)
                diff_size = len(diff)
            except Exception as e:
                logger.warning(f"Dry-run diff failed for {rel}: {e}")
                diff = "diff computation failed"

        message = (
            "dry_run new file"
            if diff is None
            else f"dry_run modified (diff {diff_size} chars)"
        )
        logger.info(f"Dry-run complete: {rel} - {message}")

        return {
            "success": True,
            "path": str(rel),
            "size": len(content_bytes),
            "checksum": checksum,
            "diff": diff,
            "message": message,
        }

    # Perform write
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    logger.info(f"File written successfully: {rel}")

    # Update audit with success
    audit_entry["success"] = True
    audit_entry["message"] = "written"
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry) + "\n")

    return {
        "success": True,
        "path": str(rel),
        "size": len(content_bytes),
        "checksum": checksum,
        "diff": None,
        "message": "written successfully",
    }


@tool
def write_file(
    path: str, content: str, project_id: str, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Write file into project workspace safely with full safety checks.

    Args:
        path: Relative path to the file
        content: File content to write
        project_id: Project identifier
        dry_run: If True, validate/log but don't write; returns diff if file exists

    Returns:
        Dict with success, path, size, checksum, diff (dry_run), message
    """
    return _write_file_impl(path, content, project_id, dry_run)


# List of all file tools for agent binding
FILE_TOOLS = [
    read_file,
    list_files,
    read_directory_structure,
    write_file,
]


def get_file_tools() -> List:
    """
    Get the list of file tools for LangChain agent binding.

    Returns:
        List of tool functions decorated with @tool
    """
    return FILE_TOOLS.copy()
