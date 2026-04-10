"""
Memory Engine — unified interface over hot/warm/cold.
Read: hot → warm → cold. Write: all three.
One interface, three tiers.
"""
from __future__ import annotations
from loguru import logger
from memory.hot import HOT
from memory.warm import WARM
from memory.cold import COLD


class MemoryEngine:
    def store(self, key: str, value: str, category: str = "general"):
        HOT.set(key, value)
        WARM.store(key, value, metadata={"category": category})
        COLD.store_memory(key, value, category=category)

    def recall(self, key: str) -> str | None:
        # Try hot first
        val = HOT.get(key)
        if val:
            return val
        # Try cold
        val = COLD.get_memory(key)
        if val:
            HOT.set(key, val)  # promote to hot
            return val
        return None

    def search(self, query: str, n: int = 5) -> list[dict]:
        return WARM.search(query, n)

    def get_context_for_task(self, task_description: str) -> str:
        results = WARM.search(task_description, n=5)
        if not results:
            return ""
        lines = [f"- {r['text'][:200]}" for r in results]
        return "Relevant memory:\n" + "\n".join(lines)

    def record_outcome(self, **kwargs):
        COLD.record_outcome(**kwargs)

    def get_stats(self) -> dict:
        cold_stats = COLD.get_stats()
        return {
            **cold_stats,
            "hot_cache_size": HOT.size(),
            "warm_count": WARM.count(),
        }


MEMORY = MemoryEngine()
