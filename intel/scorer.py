"""
Scorer — LLM-based 4-dimension opportunity evaluation.
demand × feasibility × competition × monetization → composite.
Caches scores so we don't re-score the same opportunity twice.
"""
from __future__ import annotations
import json
import hashlib
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

    def to_goal(self) -> str:
        return self.raw.title


def _opp_id(opp: RawOpportunity) -> str:
    return hashlib.md5(opp.title.encode()).hexdigest()[:12]


class Scorer:
    def score(self, opp: RawOpportunity) -> ScoredOpportunity | None:
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
            # Extract JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            data = json.loads(content[start:end])
            d = float(data.get("demand", 0))
            f = float(data.get("feasibility", 0))
            c = float(data.get("competition", 0))
            m = float(data.get("monetization", 0))
            composite = (d + f + c + m) / 4

            COLD.store_opportunity_score(_opp_id(opp), opp.title, opp.source, d, f, c, m)

            return ScoredOpportunity(
                raw=opp, demand=d, feasibility=f, competition=c,
                monetization=m, composite=composite,
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning(f"Scoring failed for '{opp.title[:50]}': {e}")
            return None

    def pick_best(self, opportunities: list[RawOpportunity], min_score: float | None = None) -> ScoredOpportunity | None:
        if min_score is None:
            min_score = CFG.min_opportunity_score

        scored = []
        for opp in opportunities[:30]:  # Cap at 30 to save compute
            s = self.score(opp)
            if s and s.composite >= min_score:
                scored.append(s)

        if not scored:
            logger.warning("No opportunities met minimum score threshold")
            return None

        best = max(scored, key=lambda x: x.composite)
        logger.success(f"Best opportunity: '{best.raw.title[:60]}' (score={best.composite:.2f})")
        return best


SCORER = Scorer()
