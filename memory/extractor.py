"""
MemoryExtractor — pulls learnings from session logs and outcomes.
Pattern from Claude Code's extractMemories/.
Runs after each cycle to update cold memory.
"""
from __future__ import annotations
import json
from loguru import logger
import ollama
from config import CFG
from memory.cold import COLD


class MemoryExtractor:
    def extract_from_outcome(self, project_name: str, goal: str, success: bool,
                              stdout: str, stderr: str) -> list[str]:
        outcome_text = (
            f"Project: {project_name}\nGoal: {goal}\n"
            f"Success: {success}\nOutput: {stdout[:800]}\nErrors: {stderr[:400]}"
        )
        try:
            resp = ollama.chat(
                model=CFG.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract 3-7 concrete learnings from this build outcome. "
                            "Each learning must be specific enough to change future behaviour. "
                            "Return a JSON array of strings only."
                        ),
                    },
                    {"role": "user", "content": outcome_text},
                ],
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            content = resp["message"]["content"].strip()
            # Extract JSON array
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                learnings = json.loads(content[start:end])
                self._store(learnings, project_name)
                return learnings
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
        return []

    def _store(self, learnings: list[str], project_name: str):
        for i, learning in enumerate(learnings):
            key = f"learning_{project_name}_{i}"
            COLD.store_memory(key, learning, category="learning", confidence=0.8)
        logger.info(f"Stored {len(learnings)} learnings from {project_name}")

    def get_relevant_learnings(self, goal: str, limit: int = 5) -> list[str]:
        mems = COLD.get_recent_memories(category="learning", limit=50)
        # Simple relevance: shared words
        goal_words = set(goal.lower().split())
        scored = []
        for m in mems:
            content = m["content"]
            words = set(content.lower().split())
            overlap = len(goal_words & words)
            scored.append((overlap, content))
        scored.sort(reverse=True)
        return [c for _, c in scored[:limit]]


EXTRACTOR = MemoryExtractor()
