"""
Learner — uses past outcomes to bias future opportunity selection.
Identifies what types of projects succeed and updates scoring weights.
Pattern: look at wins, extract patterns, store as weighted preferences.
"""
from __future__ import annotations
from loguru import logger
from memory.cold import COLD
from memory.engine import MEMORY


class Learner:
    def analyze_success_patterns(self) -> dict:
        outcomes = COLD.get_outcomes(limit=200)
        if len(outcomes) < 3:
            return {}

        wins = [o for o in outcomes if o["success"]]
        losses = [o for o in outcomes if not o["success"]]

        if not wins:
            return {}

        # Extract common words in winning goals
        from collections import Counter
        win_words = Counter()
        for o in wins:
            for word in (o.get("goal") or "").lower().split():
                if len(word) > 4:
                    win_words[word] += 1

        loss_words = Counter()
        for o in losses:
            for word in (o.get("goal") or "").lower().split():
                if len(word) > 4:
                    loss_words[word] += 1

        # Words that appear in wins but not losses = positive signals
        positive_signals = {
            w: c for w, c in win_words.items()
            if loss_words.get(w, 0) < c
        }

        patterns = {
            "win_rate": len(wins) / len(outcomes),
            "avg_revenue_per_win": sum(o["revenue"] or 0 for o in wins) / len(wins),
            "positive_signals": sorted(positive_signals, key=positive_signals.get, reverse=True)[:10],
        }

        logger.info(f"Patterns: win_rate={patterns['win_rate']:.1%}, signals={patterns['positive_signals'][:5]}")
        return patterns

    def update_weights(self, patterns: dict):
        if not patterns:
            return
        summary = (
            f"Win rate: {patterns.get('win_rate', 0):.1%}. "
            f"Positive signals: {', '.join(patterns.get('positive_signals', [])[:5])}. "
            f"Avg revenue per win: ${patterns.get('avg_revenue_per_win', 0):.2f}."
        )
        MEMORY.store("learner_patterns", summary, category="meta")
        logger.info(f"Updated weights: {summary}")

    def get_preferred_types(self) -> list[str]:
        val = MEMORY.recall("learner_patterns")
        if not val:
            return []
        # Extract signal words from stored pattern summary
        import re
        match = re.search(r"signals: ([^.]+)", val)
        if match:
            return [w.strip() for w in match.group(1).split(",")]
        return []

    def run(self):
        patterns = self.analyze_success_patterns()
        self.update_weights(patterns)
        return patterns


LEARNER = Learner()
