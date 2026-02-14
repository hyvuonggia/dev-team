"""
BA Agent Tools - File operations using LangChain tool framework.

BA has:
- READ access: project docs, conversation history, directory structure
- WRITE access: requirement docs (.md, .yaml files only)
- NO WRITE access: source code files
"""

from __future__ import annotations

import os
import pathlib
import hashlib
from typing import List
from langchain.tools import tool


# Import the underlying logic, not the decorated tools
from app.tools.file_tools import (
    _resolve_and_validate,
    FileToolError,
    WORKSPACE_ROOT,
)


@tool
def ba_read_file(path: str, project_id: str) -> str:
    """
    Read a file from the project workspace.

    BA has read access to all project files including:
    - Documentation files (.md, .txt, .rst)
    - Configuration files (.yaml, .yml, .json, .toml)
    - Source code files (for context only, read-only)

    Args:
        path: Relative path to the file
        project_id: Project identifier

    Returns:
        File contents as string
    """
    try:
        target = _resolve_and_validate(path, project_id)
        if not target.exists():
            return f"Error: File not found at {path}"
        return target.read_text(encoding="utf-8")
    except FileToolError as e:
        return f"Error reading file: {e}"


@tool
def ba_list_files(directory: str, project_id: str) -> str:
    """
    List files in a directory within the project workspace.

    Args:
        directory: Relative directory path
        project_id: Project identifier

    Returns:
        Comma-separated list of file paths
    """
    try:
        target = _resolve_and_validate(directory, project_id)
        if not target.exists():
            return ""
        files = []
        for root, _, filenames in os.walk(target):
            for fn in filenames:
                rel = (
                    pathlib.Path(root)
                    .joinpath(fn)
                    .relative_to(WORKSPACE_ROOT / project_id)
                )
                files.append(str(rel))
        return ", ".join(files)
    except FileToolError as e:
        return f"Error listing files: {e}"


@tool
def ba_read_directory_structure(project_id: str) -> str:
    """
    Get the complete directory structure of the project.

    Args:
        project_id: Project identifier

    Returns:
        Comma-separated list of all paths in the project
    """
    try:
        root = (WORKSPACE_ROOT / project_id).resolve()
        if not root.exists():
            return ""
        paths = []
        for p in root.rglob("*"):
            paths.append(str(p.relative_to(root)))
        return ", ".join(paths)
    except FileToolError as e:
        return f"Error reading directory structure: {e}"


@tool
def ba_write_requirement_doc(
    path: str, content: str, project_id: str, dry_run: bool = False
) -> str:
    """
    Write a requirement document to the project workspace.

    BA can ONLY write requirement documents (.md, .yaml, .yml files).
    Cannot write source code files like .py, .js, .ts, etc.

    Args:
        path: Relative path to the file (must end in .md, .yaml, or .yml)
        content: File content to write
        project_id: Project identifier
        dry_run: If True, don't actually write the file

    Returns:
        JSON string with operation result including path, size, checksum, and dry_run status
    """
    import json

    # Validate file extension
    allowed_extensions = (".md", ".markdown", ".yaml", ".yml")
    path_lower = path.lower()

    if not any(path_lower.endswith(ext) for ext in allowed_extensions):
        return json.dumps(
            {
                "error": f"BA can only write requirement documents with extensions: {allowed_extensions}.",
                "path": path,
            }
        )

    try:
        target = _resolve_and_validate(path, project_id)
        rel = target.relative_to(WORKSPACE_ROOT / project_id)
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > 5 * 1024 * 1024:
            return json.dumps({"error": "File too large"})
        checksum = hashlib.sha256(content_bytes).hexdigest()
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "path": str(rel),
                "size": len(content_bytes),
                "checksum": checksum,
                "dry_run": dry_run,
            }
        )
    except FileToolError as e:
        return json.dumps({"error": f"Cannot write requirement document: {e}"})


@tool
def ba_read_conversation_history(session_id: str) -> str:
    """
    Read conversation history for a session.

    This allows BA to ground analysis in previous conversations.

    Args:
        session_id: Session identifier

    Returns:
        JSON string with list of messages or error
    """
    import json
    from app.chat_memory import get_session_history

    try:
        history = get_session_history(session_id)
        return json.dumps(history)
    except Exception as e:
        return json.dumps({"error": f"Cannot read conversation history: {e}"})


# List of BA tools for agent binding
BA_TOOLS = [
    ba_read_file,
    ba_list_files,
    ba_read_directory_structure,
    ba_write_requirement_doc,
    ba_read_conversation_history,
]


def get_ba_tools() -> list:
    """
    Get the list of BA agent tools for LangChain agent binding.

    Returns:
        List of tool functions decorated with @tool
    """
    return BA_TOOLS.copy()
