"""
brain/tools/terminal.py

Terminal/subprocess execution tool.

Risk tiers:
  MEDIUM: Read-only commands (git log, dir, type, echo, where, etc.)
  HIGH:   Commands that can mutate state (git push, del, rm, pip install, etc.)

The command is analyzed against an allowlist of known-safe prefixes to determine
the actual risk tier at call time. The registry tag is HIGH (the worst case)
to ensure the permission engine always checks.

IMPORTANT: This tool executes with the CURRENT USER's privileges. It does not
elevate. Commands requiring admin rights will fail with an access-denied error
(which is the correct safe behavior).
"""

from __future__ import annotations

import asyncio
import logging
import shlex

from brain.tools.registry import RISK_HIGH, RISK_MEDIUM, tool

logger = logging.getLogger(__name__)

# Timeout for command execution
_DEFAULT_TIMEOUT_SECONDS = 30

# Prefixes of commands considered read-only (MEDIUM risk).
# Everything NOT in this list is HIGH risk.
# This list is intentionally conservative.
_READ_ONLY_PREFIXES = (
    "git log", "git status", "git diff", "git branch", "git show",
    "dir", "ls", "echo", "where", "which", "type ", "cat ",
    "python --version", "python -V", "node --version", "npm --version",
    "pip list", "pip show",
    "whoami", "hostname", "ipconfig", "ping ",
    "tasklist",
)


# Operators that chain shell commands. If any of these appear in a command,
# the risk is always HIGH — regardless of what prefix the command starts with.
# This check MUST come before the prefix allowlist: a command like
# "git status; Remove-Item -Recurse -Force C:\Users\..." starts with a safe
# prefix but the second operation is fully destructive.
_CHAIN_OPERATORS = (";", "&&", " & ", "|", "`", "$(", "%(", "\n")


def classify_command_risk(command: str) -> str:
    """Heuristic risk classification for terminal commands.

    Order matters:
    1. Reject any command containing shell chaining / substitution operators
       (HIGH, unconditionally) — these bypass the prefix allowlist.
    2. Only then check whether the single command matches a read-only prefix.
    """
    # Step 1: any chaining operator → immediately HIGH
    for op in _CHAIN_OPERATORS:
        if op in command:
            logger.warning(
                "Command contains chaining operator %r — classified as HIGH risk: %s",
                op, command[:120],
            )
            return RISK_HIGH

    # Step 2: single command — safe prefix → MEDIUM, otherwise HIGH
    cmd_lower = command.strip().lower()
    for prefix in _READ_ONLY_PREFIXES:
        if cmd_lower.startswith(prefix):
            return RISK_MEDIUM
    return RISK_HIGH


@tool(
    name="run_command",
    description=(
        "Run a shell command and return its output. "
        "Read-only commands (git log, dir, etc.) are MEDIUM risk. "
        "State-mutating commands (git push, del, pip install, etc.) are HIGH risk and require confirmation."
    ),
    risk=RISK_HIGH,  # Worst-case tag; actual tier determined by classify_command_risk at runtime
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run (PowerShell on Windows).",
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for the command. Defaults to user home directory.",
                "default": None,
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Maximum time to wait for the command to complete.",
                "default": 30,
            },
        },
        "required": ["command"],
    },
)
async def run_command(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, str | int]:
    """
    Execute a shell command via PowerShell and return stdout/stderr/returncode.
    Always runs as the current user (no elevation).
    """
    logger.info("Executing command: %s (cwd=%s)", command, working_directory)

    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NonInteractive",
            "-NoProfile",
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_directory,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds}s and was killed.",
                "returncode": -1,
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        returncode = proc.returncode

        logger.info("Command returned %d (stdout=%d chars)", returncode, len(stdout))
        return {"stdout": stdout, "stderr": stderr, "returncode": returncode}

    except Exception as exc:
        logger.error("Command execution failed: %s", exc)
        raise RuntimeError(f"Command execution failed: {exc}") from exc