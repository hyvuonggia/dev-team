"""
General file system tools using LangChain tool framework.

These are low-level file operations that can be used by any agent.
Safety checks: path validation, sandboxing, protected paths.
"""

import os
import pathlib
import hashlib
from typing import List, Tuple
from langchain.tools import tool


class FileToolError(Exception):
    """Error raised by file tools."""

    pass


WORKSPACE_ROOT = pathlib.Path(os.environ.get("WORKSPACE_ROOT", "workspace")).resolve()


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
    protected = [".git", ".github", ".env", "docker-compose.yml"]
    for p in protected:
        if str(target).startswith(str((project_root / p).resolve())):
            raise FileToolError(f"Writes to protected path '{p}' are forbidden")
    return target


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
    target = _resolve_and_validate(path, project_id)
    if not target.exists():
        raise FileToolError("File not found")
    return target.read_text(encoding="utf-8")


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
def read_directory_structure(project_id: str) -> List[str]:
    """
    Get the complete directory structure of the project.

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


def _checksum(s: str) -> str:
    """Generate SHA256 checksum of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@tool
def write_file(
    path: str, content: str, project_id: str, dry_run: bool = False
) -> Tuple[str, int, str]:
    """
    Write file into project workspace safely.

    Args:
        path: Relative path to the file
        content: File content to write
        project_id: Project identifier
        dry_run: If True, don't actually write the file

    Returns:
        Tuple of (relative_path, bytes_written, sha256_checksum)
    """
    target = _resolve_and_validate(path, project_id)
    rel = target.relative_to(WORKSPACE_ROOT / project_id)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 5 * 1024 * 1024:
        raise FileToolError("File too large")
    checksum = _checksum(content)
    if dry_run:
        return (str(rel), len(content_bytes), checksum)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return (str(rel), len(content_bytes), checksum)


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
