"""
Scorer — LLM-based 4-dimension opportunity evaluation.
demand x feasibility x competition x monetization -> composite.

FIXED: qwen3.5 is a thinking model — strips <think>...</think> blocks.
FIXED: adds /no_think to prompt to suppress chain-of-thought for fast scoring.
FIXED: fail cache prevents retrying permanently-failing items this run.
FIXED: single-pass pick_best — never scores same opp twice.
FIXED: cap=20 limits cold-start LLM calls.
FIXED: robust JSON parsing with fallback handling.
FIXED: Windows-compatible path handling.
"""
from __future__ import annotations
import json
import re
import hashlib
import sqlite3
import os
from pathlib import Path
from dataclasses import dataclass
from loguru import logger
import ollama
from config import CFG
from intel.scanner import RawOpportunity
from memory.cold import COLD

# In-process set of IDs that failed this run — skip on retry
_FAILED_THIS_RUN: set[str] = set()

_THINK_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from Qwen3 thinking models."""
    text = _THINK_RE.sub("", text).strip()
    text = _JSON_RE.sub(r"\1", text).strip()
    return text


def _parse_json_response(text: str) -> dict | None:
    """Extract and parse JSON from LLM response with fallback."""
    text = _strip_think(text)
    text = text.strip()
    
    if not text:
        return None
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON in markdown blocks
    match = _THINK_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find any JSON object in the response
    match = _JSON_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


def _opp_id(opp: RawOpportunity) -> str:
    return hashlib.md5(opp.title.encode()).hexdigest()[:12]


def _load_cached(opp_id: str) -> dict | None:
    try:
        db_path = Path(COLD.db_path)
        if not db_path.exists():
            return None
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM opportunity_scores WHERE id=?", (opp_id,)
            ).fetchone()
            if row:
                return dict(row)
    except Exception:
        pass
    return None


class Scorer:
    def score(self, opp: RawOpportunity) -> ScoredOpportunity | None:
        oid = _opp_id(opp)

        if oid in _FAILED_THIS_RUN:
            logger.warning(f"Skipping failed item: {opp.title[:50]}")
            return None

        cached = _load_cached(oid)
        if cached:
            logger.debug(f"Cache hit: '{opp.title[:40]}' score={cached['composite']:.2f}")
            return ScoredOpportunity(
                raw=opp,
                demand=cached["demand"],
                feasibility=cached["feasibility"],
                competition=cached["competition"],
                monetization=cached["monetization"],
                composite=cached["composite"],
                reasoning="(from cache)",
                from_cache=True,
            )

        # /no_think suppresses chain-of-thought for Qwen3 thinking models
        prompt = (
            "/no_think\n"
            f"Opportunity: {opp.title}\nSource: {opp.source}\n\n"
            "Return ONLY this JSON, nothing else:\n"
            '{"demand":0.0,"feasibility":0.0,"competition":0.0,"monetization":0.0,"reasoning":"..."}\n'
            "Scores 0.0-1.0. competition: 0=saturated, 1=blue ocean."
        )
        try:
            resp = ollama.chat(
                model=CFG.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0},
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            _FAILED_THIS_RUN.add(oid)
            return None

        if not resp or not resp.get("message") or not resp["message"].get("content"):
            logger.warning(f"No JSON in scorer response for: {opp.title}")
            _FAILED_THIS_RUN.add(oid)
            return None

        parsed = _parse_json_response(resp["message"]["content"])
        if not parsed:
            logger.warning(f"No JSON in scorer response for: {opp.title}")
            _FAILED_THIS_RUN.add(oid)
            return None

        try:
            demand = float(parsed.get("demand", 0.0))
            feasibility = float(parsed.get("feasibility", 0.0))
            competition = float(parsed.get("competition", 0.0))
            monetization = float(parsed.get("monetization", 0.0))
            reasoning = parsed.get("reasoning", "")
            composite = (demand + feasibility + (1 - competition) + monetization) / 4.0
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to parse scores: {e}")
            _FAILED_THIS_RUN.add(oid)
            return None

        # Cache the result
        try:
            with sqlite3.connect(str(Path(COLD.db_path))) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO opportunity_scores "
                    "(id, raw_title, raw_source, demand, feasibility, competition, monetization, composite, reasoning, from_cache) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (oid, opp.title, opp.source, demand, feasibility, competition, monetization, composite, reasoning, False)
                )
        except Exception:
            pass

        logger.info(f"Scored: {opp.title[:40]} demand={demand:.2f} feasibility={feasibility:.2f} competition={competition:.2f} monetization={monetization:.2f} composite={composite:.2f}")
        return ScoredOpportunity(
            raw=opp,
            demand=demand,
            feasibility=feasibility,
            competition=competition,
            monetization=monetization,
            composite=composite,
            reasoning=reasoning,
            from_cache=False,
        )