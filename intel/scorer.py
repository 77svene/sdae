"""
Scorer — LLM-based 4-dimension opportunity evaluation.
demand × feasibility × competition × monetization → composite.
FIXED: checks cold cache before calling LLM — no double-scoring same opportunity.
FIXED: pick_best reuses already-scored list — no second LLM pass.
FIXED: caps individual score calls at 20 (not 40) to limit cold-start time.
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


def _load_cached(opp_id: str) -> dict | None:
    """Check cold storage for existing score. Returns dict or None."""
    try:
        with sqlite3.connect(COLD.db_path) as conn:
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

        # Cache check — skip LLM if already scored
        cached = _load_cached(oid)
        if cached:
            logger.debug(f"Cache hit: '{opp.title[:40]}' (score={cached['composite']:.2f})")
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

    def pick_best(
        self,
        opportunities: list[RawOpportunity],
        min_score: float | None = None,
        cap: int = 20,
    ) -> ScoredOpportunity | None:
        if min_score is None:
            min_score = CFG.min_opportunity_score

        # Score up to `cap` opps — reuse this list, never score twice
        all_scored: list[ScoredOpportunity] = []
        cache_hits = 0
        for opp in opportunities[:cap]:
            s = self.score(opp)
            if s is None:
                continue
            if s.from_cache:
                cache_hits += 1
            all_scored.append(s)

        qualifying = [s for s in all_scored if s.composite >= min_score]
        logger.info(
            f"Scored {len(all_scored)} opps | "
            f"{len(qualifying)} qualify (>={min_score:.2f}) | "
            f"{cache_hits} from cache"
        )

        if qualifying:
            best = max(qualifying, key=lambda x: x.composite)
        elif all_scored:
            best = max(all_scored, key=lambda x: x.composite)
            logger.warning(f"Relaxed threshold — best available: {best.composite:.2f}")
        else:
            return None

        logger.success(
            f"Best: '{best.raw.title[:60]}' "
            f"score={best.composite:.2f} cache={best.from_cache}"
        )
        return best


SCORER = Scorer()
