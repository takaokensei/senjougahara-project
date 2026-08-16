"""
brain/memory/extractor.py

Automated fact extraction from conversation turns.

Inspired by the vault fact extraction pattern in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python with a minimal key-value scope.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from brain.agent.providers.base import BaseLLMProvider
from brain.memory.facts import FactMemory

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_FIRST_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


def parse_extracted_facts(raw_text: str) -> list[tuple[str, str, float]]:
    """
    Parse a list of (key, value, confidence) facts from an LLM response.
    Expected JSON schema:
      {"facts": [{"key": "user_name", "value": "Cauã", "confidence": 1.0}]}
    """
    raw = raw_text.strip()
    candidate_json = ""

    if raw.startswith("{") and raw.endswith("}"):
        candidate_json = raw
    else:
        m = _JSON_BLOCK_RE.search(raw)
        if m:
            candidate_json = m.group(1).strip()
        else:
            m2 = _FIRST_OBJECT_RE.search(raw)
            if m2:
                candidate_json = m2.group(0).strip()

    if not candidate_json:
        return []

    try:
        data = json.loads(candidate_json)
        facts_list = data.get("facts", [])
        results: list[tuple[str, str, float]] = []
        for item in facts_list:
            if isinstance(item, dict) and "key" in item and "value" in item:
                k = str(item["key"]).strip()
                v = str(item["value"]).strip()
                c = float(item.get("confidence", 1.0))
                if k and v:
                    results.append((k, v, max(0.0, min(1.0, c))))
        return results
    except Exception as exc:
        logger.debug("Failed parsing extracted facts JSON: %s", exc)
        return []


def extract_facts_heuristic(text: str) -> list[tuple[str, str, float]]:
    """
    Lightweight regex-based fallback for extracting common durable facts
    (e.g., name, location, preferences) without requiring an LLM roundtrip.
    """
    facts: list[tuple[str, str, float]] = []
    
    # Name patterns (Portuguese & English)
    m_name = re.search(r"\b(?:me chamo|meu nome [ée]|sou o|sou a|my name is|i am)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)", text, re.IGNORECASE)
    if m_name:
        facts.append(("user_name", m_name.group(1).strip(), 0.95))

    # Location / Residence
    m_loc = re.search(r"\b(?:moro em|vivo em|resido em|i live in)\s+([A-ZÀ-Úa-zà-ú\s]+?)(?:[.,!]| e | mas |$)", text, re.IGNORECASE)
    if m_loc:
        facts.append(("user_location", m_loc.group(1).strip(), 0.90))

    # Birthday
    m_bday = re.search(r"\b(?:meu anivers[aá]rio [ée]|nasci em)\s+([^.,!]+)", text, re.IGNORECASE)
    if m_bday:
        facts.append(("user_birthday", m_bday.group(1).strip(), 0.90))

    return facts


class FactExtractor:
    """
    Extracts durable key-value facts from conversation turns and stores them in FactMemory.
    """

    EXTRACTION_SYSTEM_PROMPT = (
        "You are a memory extractor. Analyze the conversation turn and extract durable facts "
        "about the user (e.g. name, preferences, location, habits, background). "
        "Output ONLY a JSON object matching this schema:\n"
        '{"facts": [{"key": "snake_case_key", "value": "clear description", "confidence": 0.9}]}\n'
        "If no new durable facts are mentioned, return: {\"facts\": []}\n"
        "Never output markdown commentary outside the JSON object."
    )

    def __init__(self, provider: BaseLLMProvider | None = None) -> None:
        self._provider = provider

    async def extract_and_save(
        self,
        user_message: str,
        assistant_response: str,
        memory: FactMemory,
    ) -> list[str]:
        """
        Extract facts from a conversation exchange and commit them to SQLite memory.

        Returns:
            List of fact keys saved.
        """
        extracted: list[tuple[str, str, float]] = []

        # 1. LLM extraction if provider is present
        if self._provider is not None:
            try:
                turn_text = f"User: {user_message}\nAssistant: {assistant_response}"
                response = await self._provider.complete(
                    messages=[{"role": "user", "content": turn_text}],
                    system_prompt=self.EXTRACTION_SYSTEM_PROMPT,
                )
                if response.text:
                    extracted = parse_extracted_facts(response.text)
            except Exception as exc:
                logger.warning("LLM fact extraction failed: %s", exc)

        # 2. Fallback / supplement with heuristics
        heuristics = extract_facts_heuristic(user_message)
        existing_keys = {f[0] for f in extracted}
        for h in heuristics:
            if h[0] not in existing_keys:
                extracted.append(h)

        saved_keys: list[str] = []
        for key, value, conf in extracted:
            try:
                await memory.set_fact(key, value, confidence=conf)
                saved_keys.append(key)
            except Exception as exc:
                logger.error("Failed saving fact %s: %s", key, exc)

        return saved_keys
