"""
brain/tools/screenshot.py

Screen capture tool using mss.
Risk tier: LOW (read-only), but logged for transparency.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path

from brain.tools.registry import RISK_LOW, tool

logger = logging.getLogger(__name__)


@tool(
    name="take_screenshot",
    description="Take a screenshot of the primary monitor and save it to a temporary file. Returns the file path.",
    risk=RISK_LOW,
    parameters={
        "type": "object",
        "properties": {
            "monitor_number": {
                "type": "integer",
                "description": "Monitor index (1 for primary monitor).",
                "default": 1,
            },
        },
        "required": [],
    },
)
async def take_screenshot(monitor_number: int = 1) -> dict[str, str]:
    import mss

    temp_dir = Path(tempfile.gettempdir()) / "senjougahara_screenshots"
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_path = temp_dir / "latest_screenshot.png"

    with mss.mss() as sct:
        monitors = sct.monitors
        idx = monitor_number if monitor_number < len(monitors) else 1
        monitor = monitors[idx]
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(out_path))

    logger.info("Screenshot taken on monitor %d: %s", idx, out_path)
    return {"path": str(out_path), "width": str(sct_img.width), "height": str(sct_img.height)}