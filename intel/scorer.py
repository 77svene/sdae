"""
Scorer — LLM-based 4-dimension opportunity evaluation.
demand × feasibility × competition × monetization → composite.
FIXED: checks cold cache before calling LLM — no double-scoring same opportunity.
"""
from __future__ import annotations
import json
import hashlib
import sqlite3
from dataclasses import dataclass
from loguru import logger
import ollama
from config import CFG
from intel.scanner import RawOpportunity
from memory.cold import COLD


@dataclass
class ScoredOpportunity:
    raw: RawOpportunity
    demand: float
    feasibility: float
    competition: float
    monetization: float
    composite: float
    reasoning: str
    from_cache: bool = False

    def to_goal(self) -> str:
        return self.raw.title


def _opp_id(opp: RawOpportunity) -> str:
    return hashlib.md5(opp.title.encode()).hexdigest()[:12]


def _load_cached(opp_id: str) -> ScoredOpportunity | None:
    """Check cold storage for existing score."""
    try:
        with sqlite3.connect(COLD.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM opportunity_scores WHERE id=?", (opp_id,)
            ).fetchone()
            if row:
                return row  # raw row, will be converted in score()
    except Exception:
        pass
    return None


class Scorer:
    def score(self, opp: RawOpportunity) -> ScoredOpportunity | None:
        oid = _opp_id(opp)

        # Cache check — skip LLM if already scored
        cached_row = _load_cached(oid)
        if cached_row:
            logger.debug(f"Cache hit: '{opp.title[:40]}' (score={cached_row['composite']:.2f})")
            return ScoredOpportunity(
                raw=opp,
                demand=cached_row["demand"],
                feasibility=cached_row["feasibility"],
                competition=cached_row["competition"],
                monetization=cached_row["monetization"],
                composite=cached_row["composite"],
                reasoning="(from cache)",
                from_cache=True,
            )

        prompt = (
            f"Opportunity: {opp.title}\nSource: {opp.source}\n\n"
            "Score this software opportunity. Return ONLY this JSON:\n"
            '{"demand": 0.0, "feasibility": 0.0, "competition": 0.0, "monetization": 0.0, "reasoning": "..."}\n'
            "Scores 0.0-1.0. competition: 0=saturated, 1=blue ocean. Be honest. Most score below 0.6."
        )
        try:
            resp = ollama.chat(
                model=CFG.ollama_model,
                messages=[
                    {"role": "system", "content": "You are a ruthless opportunity evaluator. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.0, "num_ctx": 2048},
            )
            content = resp["message"]["content"].strip()
            start = content.find("{")
            end = content.rfind("}") + 1
            if start < 0 or end <= start:
                logger.warning(f"No JSON in scorer response for: {opp.title[:40]}")
                return None
            data = json.loads(content[start:end])
            d = max(0.0, min(1.0, float(data.get("demand", 0))))
            f = max(0.0, min(1.0, float(data.get("feasibility", 0))))
            c = max(0.0, min(1.0, float(data.get("competition", 0))))
            m = max(0.0, min(1.0, float(data.get("monetization", 0))))
            composite = (d + f + c + m) / 4

            # Persist to cold cache
            COLD.store_opportunity_score(oid, opp.title, opp.source, d, f, c, m)

            return ScoredOpportunity(
                raw=opp, demand=d, feasibility=f, competition=c,
                monetization=m, composite=composite,
                reasoning=data.get("reasoning", ""),
                from_cache=False,
            )
        except Exception as e:
            logger.warning(f"Scoring failed for '{opp.title[:50]}': {e}")
            return None

    def pick_best(self, opportunities: list[RawOpportunity], min_score: float | None = None) -> ScoredOpportunity | None:
        if min_score is None:
            min_score = CFG.min_opportunity_score

        scored = []
        cache_hits = 0
        for opp in opportunities[:40]:  # cap at 40
            s = self.score(opp)
            if s:
                if s.from_cache:
                    cache_hits += 1
                if s.composite >= min_score:
                    scored.append(s)

        logger.info(f"Scored {len(scored)} qualifying opps ({cache_hits} from cache)")

        if not scored:
            # Relax threshold if nothing qualifies
            all_scored = [s for opp in opportunities[:40] if (s := self.score(opp)) is not None]
            if all_scored:
                best = max(all_scored, key=lambda x: x.composite)
                logger.warning(f"Relaxed threshold — best available: {best.composite:.2f}")
                return best
            return None

        best = max(scored, key=lambda x: x.composite)
        logger.success(f"Best: '{best.raw.title[:60]}' score={best.composite:.2f} cache={best.from_cache}")
        return best


SCORER = Scorer()
