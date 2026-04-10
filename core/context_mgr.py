"""
ContextManager — keeps the conversation window from exploding.
Compress at 5000 tokens. Keep recent 6 messages verbatim. Summarize the middle.
Token counting is approximate (4 chars ~ 1 token).
"""
from __future__ import annotations
import json
from typing import Any
import ollama
from config import CFG
from loguru import logger


def _approx_tokens(messages: list[dict]) -> int:
    total = sum(len(str(m.get("content", ""))) for m in messages)
    return total // 4


class ContextManager:
    def __init__(self):
        self._compress_threshold = CFG.max_context_tokens
        self._keep_recent = 6

    def maybe_compress(self, messages: list[dict]) -> list[dict]:
        if _approx_tokens(messages) < self._compress_threshold:
            return messages

        if len(messages) <= self._keep_recent + 1:
            return messages

        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        if len(non_system) <= self._keep_recent:
            return messages

        middle = non_system[:-self._keep_recent]
        recent = non_system[-self._keep_recent:]

        summary = self._summarize(middle)
        logger.debug(f"Compressed {len(middle)} messages → summary ({len(summary)} chars)")

        compressed = system + [{"role": "assistant", "content": f"[CONTEXT SUMMARY]\n{summary}"}] + recent
        return compressed

    def _summarize(self, messages: list[dict]) -> str:
        text = "\n".join(f"{m['role'].upper()}: {m.get('content','')[:500]}" for m in messages)
        try:
            resp = ollama.chat(
                model=CFG.ollama_model,
                messages=[
                    {"role": "system", "content": "Summarize this conversation history concisely. Preserve key decisions, code written, and outcomes. Under 300 words."},
                    {"role": "user", "content": text},
                ],
                options={"temperature": 0.0, "num_ctx": 4096},
            )
            return resp["message"]["content"]
        except Exception as e:
            logger.warning(f"Context compression failed: {e}")
            return f"[{len(messages)} messages compressed — summary unavailable]"


CTX_MGR = ContextManager()
