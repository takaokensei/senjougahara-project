"""
brain/personality/learner.py

Learns user style preferences (verbosity, formality) dynamically from conversation signals.

Inspired by the personality learning pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_style_signals(user_message: str) -> list[dict[str, Any]]:
    """
    Extract preference signals from user text using keyword and regex heuristics (PT + EN).
    Returns list of dicts: [{"preference": "verbosity"|"formality", "direction": -1.0|1.0}]
    """
    if not user_message:
        return []

    text = user_message.lower().strip()
    signals: list[dict[str, Any]] = []

    # ── Verbosity signals ───────────────────────────────────────────────────
    # Shorter / Concise (-1)
    if re.search(r"\b(mais curto|seja breve|resumido|resuma|resumo|direto ao ponto|sem enrola[çc][aã]o|shorter|tldr|tl;dr|be brief|concise|keep it short)\b", text):
        signals.append({"preference": "verbosity", "direction": -1.0})
    # More detailed (+1)
    elif re.search(r"\b(mais detalh(?:e|es|ado)|explica(?:r)? melhor|mais a fundo|aprofunde|elaborate|more details?|in depth|explain more|expand on this)\b", text):
        signals.append({"preference": "verbosity", "direction": 1.0})

    # ── Formality signals ────────────────────────────────────────────────────
    # More formal (+1)
    if re.search(r"\b(mais formal|fale formalmente|tom formal|profissional|trate por senhor|more formal|formal tone)\b", text):
        signals.append({"preference": "formality", "direction": 1.0})
    # More casual / informal (-1)
    elif re.search(r"\b(mais informal|casual|descontra[ií]do|menos formal|pode falar na boa|more casual|informal tone)\b", text):
        signals.append({"preference": "formality", "direction": -1.0})

    return signals


class PersonalityModel:
    """
    Tracks and persists continuous style preference scores between -1.0 and 1.0.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path
        self._preferences: dict[str, float] = {
            "verbosity": 0.0,
            "formality": 0.0,
        }
        if self.db_path and self.db_path.exists():
            self._load_sync()

    def _get_conn(self) -> sqlite3.Connection | None:
        if not self.db_path:
            return None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _load_sync(self) -> None:
        conn = self._get_conn()
        if not conn:
            return
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM preferences WHERE key IN ('verbosity', 'formality')")
            for k, v in cursor.fetchall():
                try:
                    self._preferences[k] = max(-1.0, min(1.0, float(v)))
                except ValueError:
                    pass

    def get_preference(self, key: str) -> float:
        return self._preferences.get(key, 0.0)

    def apply_signals_sync(self, signals: list[dict[str, Any]], step: float = 0.25) -> None:
        """Apply style adjustment signals with smooth step updates and persist."""
        if not signals:
            return

        for signal in signals:
            pref = signal.get("preference")
            direction = float(signal.get("direction", 0.0))
            if pref in self._preferences:
                curr = self._preferences[pref]
                new_val = max(-1.0, min(1.0, curr + direction * step))
                self._preferences[pref] = round(new_val, 3)
                logger.info("[PERSONALITY] Adjusted %s: %.2f -> %.2f", pref, curr, new_val)

        conn = self._get_conn()
        if conn:
            with conn:
                cursor = conn.cursor()
                for k, v in self._preferences.items():
                    cursor.execute(
                        """
                        INSERT INTO preferences (key, value, updated_at)
                        VALUES (?, ?, datetime('now'))
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = datetime('now')
                        """,
                        (k, str(v)),
                    )
                conn.commit()

    async def apply_signals(self, signals: list[dict[str, Any]], step: float = 0.25) -> None:
        await asyncio.to_thread(self.apply_signals_sync, signals, step)

    def get_style_prompt_context(self) -> str:
        """Generate short system prompt context based on current preference scores."""
        directives: list[str] = []
        verb = self._preferences.get("verbosity", 0.0)
        form = self._preferences.get("formality", 0.0)

        if verb <= -0.3:
            directives.append("O usuário prefere respostas extremamente diretas, concisas e objetivas (evite rodeios).")
        elif verb >= 0.3:
            directives.append("O usuário prefere explicações detalhadas, ricas em contexto e aprofundadas.")

        if form <= -0.3:
            directives.append("Adote um tom informal, descontraído e próximo.")
        elif form >= 0.3:
            directives.append("Adote um tom cortês, polido e formal.")

        return " ".join(directives)
