"""
brain/tools/filesystem.py

Filesystem tools: read files, list directories, search.

Risk tiers:
  LOW:  Reading files, listing directories, searching
  MEDIUM: Writing/creating files
  HIGH: Deleting files (not exposed in Phase 1 — add in Phase 3 with care)
"""

from __future__ import annotations

import logging
from pathlib import Path

from brain.tools.registry import RISK_LOW, RISK_MEDIUM, tool

logger = logging.getLogger(__name__)

# Maximum file size to read in one call (prevents accidentally reading huge files)
_MAX_READ_BYTES = 100_000  # 100 KB


@tool(
    name="read_file",
    description="Read the contents of a text file. Returns the content as a string.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file.",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (default: utf-8).",
                "default": "utf-8",
            },
        },
        "required": ["path"],
    },
)
async def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read a text file and return its contents."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Path is not a file: {path}")

    size = p.stat().st_size
    if size > _MAX_READ_BYTES:
        # Read only the first N bytes and note the truncation
        content = p.read_bytes()[:_MAX_READ_BYTES].decode(encoding, errors="replace")
        return content + f"\n\n[... truncated: file is {size} bytes, showing first {_MAX_READ_BYTES}]"

    content = p.read_text(encoding=encoding, errors="replace")
    logger.info("Read file: %s (%d bytes)", path, size)
    return content


@tool(
    name="list_directory",
    description="List the contents of a directory. Returns a list of file/folder names.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the directory.",
            },
            "show_hidden": {
                "type": "boolean",
                "description": "Include hidden files/directories (starting with . or marked hidden on Windows).",
                "default": False,
            },
        },
        "required": ["path"],
    },
)
async def list_directory(path: str, show_hidden: bool = False) -> list[str]:
    """List directory contents."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not p.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    entries = []
    for entry in sorted(p.iterdir()):
        if not show_hidden and entry.name.startswith("."):
            continue
        suffix = "/" if entry.is_dir() else ""
        entries.append(f"{entry.name}{suffix}")

    logger.info("Listed directory: %s (%d entries)", path, len(entries))
    return entries


@tool(
    name="write_file",
    description="Write or overwrite a text file with the given content.",
    risk=RISK_MEDIUM,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path where the file will be written.",
            },
            "content": {
                "type": "string",
                "description": "Text content to write.",
            },
            "encoding": {
                "type": "string",
                "default": "utf-8",
            },
        },
        "required": ["path", "content"],
    },
)
async def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
    """Write content to a file, creating parent directories if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    logger.info("Wrote file: %s (%d bytes)", path, len(content.encode(encoding)))
    return f"Wrote {len(content)} characters to '{path}'."


@tool(
    name="search_files",
    description="Search for files matching a glob pattern under a directory.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Root directory to search under.",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '*.py' or '**/*.txt'.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 50,
            },
        },
        "required": ["directory", "pattern"],
    },
)
async def search_files(directory: str, pattern: str, max_results: int = 50) -> list[str]:
    """Search for files matching a glob pattern."""
    p = Path(directory)
    if not p.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    results = [str(f) for f in p.glob(pattern) if f.is_file()]
    results = results[:max_results]
    logger.info("Search '%s' in %s: %d results", pattern, directory, len(results))
    return results