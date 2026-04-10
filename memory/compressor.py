"""
ContextCompressor — standalone compressor for arbitrary message lists.
Used by the QueryEngine (via ContextManager) and any component
that needs to shrink a message list before an LLM call.
"""
from __future__ import annotations
import ollama
from loguru import logger
from config import CFG


def _token_estimate(text: str) -> int:
    return len(text) // 4


def _messages_tokens(messages: list[dict]) -> int:
    return sum(_token_estimate(str(m.get("content", ""))) for m in messages)


class ContextCompressor:
    """
    Compress a message list to stay under a token budget.
    Strategy: keep system + last N messages verbatim, summarize the middle.
    """

    def __init__(self, max_tokens: int | None = None, keep_recent: int = 6):
        self.max_tokens = max_tokens or CFG.max_context_tokens
        self.keep_recent = keep_recent

    def compress(self, messages: list[dict]) -> list[dict]:
        if _messages_tokens(messages) <= self.max_tokens:
            return messages

        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        if len(non_system) <= self.keep_recent + 1:
            return messages

        middle = non_system[:-self.keep_recent]
        recent = non_system[-self.keep_recent:]

        summary = self._summarize(middle)
        logger.debug(
            f"Compressed {len(middle)} messages ({_messages_tokens(middle)} tok) "
            f"→ summary ({_token_estimate(summary)} tok)"
        )
        return system + [{"role": "assistant", "content": f"[CONTEXT SUMMARY]\n{summary}"}] + recent

    def _summarize(self, messages: list[dict]) -> str:
        text = "\n".join(
            f"{m['role'].upper()}: {str(m.get('content', ''))[:600]}"
            for m in messages
        )
        if not text.strip():
            return "[empty context]"
        try:
            resp = ollama.chat(
                model=CFG.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize this conversation concisely. "
                            "Preserve: key decisions, code filenames, error messages, outcomes. "
                            "Output under 250 words."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                options={"temperature": 0.0, "num_ctx": 4096},
            )
            return resp["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return f"[{len(messages)} messages — summary unavailable]"

    def fits(self, messages: list[dict]) -> bool:
        return _messages_tokens(messages) <= self.max_tokens


COMPRESSOR = ContextCompressor()
