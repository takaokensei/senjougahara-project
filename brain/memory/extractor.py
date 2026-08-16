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
from typing import Any, NamedTuple

from brain.agent.providers.base import BaseLLMProvider
from brain.memory.facts import FactMemory

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_FIRST_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class ExtractedFact(NamedTuple):
    key: str
    value: str
    confidence: float = 1.0
    category: str = "general"
    expires_at: str | None = None


def _normalize_expires_at(val: Any) -> str | None:
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    # Accept standard ISO 8601 patterns (e.g. 2026-08-20, 2026-08-20T23:59:59)
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?", val):
        return val
    return None


def parse_extracted_facts(raw_text: str) -> list[ExtractedFact]:
    """
    Parse a list of ExtractedFact from an LLM response.
    Expected JSON schema:
      {"facts": [{"key": "exam_date", "value": "2026-08-20", "confidence": 0.9, "category": "event", "expires_at": "2026-08-20T23:59:59"}]}
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
        results: list[ExtractedFact] = []
        for item in facts_list:
            if isinstance(item, dict) and "key" in item and "value" in item:
                k = str(item["key"]).strip()
                v = str(item["value"]).strip()
                try:
                    c = float(item.get("confidence", 1.0))
                except (ValueError, TypeError):
                    c = 1.0
                cat = str(item.get("category", "general")).strip().lower() or "general"
                exp = _normalize_expires_at(item.get("expires_at"))
                if k and v:
                    results.append(ExtractedFact(
                        key=k,
                        value=v,
                        confidence=max(0.0, min(1.0, c)),
                        category=cat,
                        expires_at=exp,
                    ))
        return results
    except Exception as exc:
        logger.debug("Failed parsing extracted facts JSON: %s", exc)
        return []


def extract_facts_heuristic(text: str) -> list[ExtractedFact]:
    """
    Lightweight regex-based fallback for extracting common durable facts
    (e.g., name, location, preferences) without requiring an LLM roundtrip.
    """
    facts: list[ExtractedFact] = []
    
    # Name patterns (Portuguese & English)
    m_name = re.search(r"\b(?:me chamo|meu nome [ée]|sou o|sou a|my name is|i am)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)", text, re.IGNORECASE)
    if m_name:
        facts.append(ExtractedFact(
            key="user_name",
            value=m_name.group(1).strip(),
            confidence=0.95,
            category="general",
            expires_at=None,
        ))

    # Location / Residence
    m_loc = re.search(r"\b(?:moro em|vivo em|resido em|i live in)\s+([A-ZÀ-Úa-zà-ú\s]+?)(?:[.,!]| e | mas |$)", text, re.IGNORECASE)
    if m_loc:
        facts.append(ExtractedFact(
            key="user_location",
            value=m_loc.group(1).strip(),
            confidence=0.90,
            category="general",
            expires_at=None,
        ))

    # Birthday
    m_bday = re.search(r"\b(?:meu anivers[aá]rio [ée]|nasci em)\s+([^.,!]+)", text, re.IGNORECASE)
    if m_bday:
        facts.append(ExtractedFact(
            key="user_birthday",
            value=m_bday.group(1).strip(),
            confidence=0.90,
            category="general",
            expires_at=None,
        ))

    return facts


class FactExtractor:
    """
    Extracts durable key-value facts from conversation turns and stores them in FactMemory.
    """

    EXTRACTION_SYSTEM_PROMPT = (
        "You are a memory extractor. Analyze the conversation turn and extract durable facts "
        "about the user (e.g. name, preferences, location, habits, background, temporary events/commitments). "
        "Categories: general | interest | preference | event | relationship.\n"
        "For temporary events/dates, set 'expires_at' to an ISO 8601 timestamp (e.g. '2026-08-20T23:59:59'). "
        "For permanent facts, omit expires_at or set to null.\n"
        "Output ONLY a JSON object matching this schema:\n"
        '{"facts": [{"key": "snake_case_key", "value": "description", "confidence": 0.9, "category": "general", "expires_at": null}]}\n'
        "If no new facts are mentioned, return: {\"facts\": []}\n"
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
        extracted: list[ExtractedFact] = []

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
        existing_keys = {f.key for f in extracted}
        for h in heuristics:
            if h.key not in existing_keys:
                extracted.append(h)

        saved_keys: list[str] = []
        for fact in extracted:
            try:
                await memory.set_fact(
                    key=fact.key,
                    value=fact.value,
                    confidence=fact.confidence,
                    category=fact.category,
                    expires_at=fact.expires_at,
                )
                saved_keys.append(fact.key)
            except Exception as exc:
                logger.error("Failed saving fact %s: %s", fact.key, exc)

        return saved_keys

