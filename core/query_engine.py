"""
StreamingQueryEngine — the inner loop.
Pattern extracted from Claude Code's QueryEngine.
Runs tool-call cycles until the model stops calling tools or hits the limit.
Max 3 tool calls per turn (Qwen2.5:9b constraint).
"""
from __future__ import annotations
import json
from typing import Any, Callable
from dataclasses import dataclass
import ollama
from loguru import logger
from config import CFG
from core.router import ROUTER
from core.context_mgr import CTX_MGR
from core.permission import PERMISSIONS


@dataclass
class ToolResult:
    tool_name: str
    output: str
    error: bool = False


@dataclass
class TurnResult:
    content: str
    tool_results: list[ToolResult]
    tool_calls_made: int
    forced_completion: bool = False


class StreamingQueryEngine:
    def __init__(self, tools: list[dict], tool_handlers: dict[str, Callable]):
        self.tools = tools
        self.tool_handlers = tool_handlers

    def run(
        self,
        messages: list[dict],
        task_type: str = "default",
        system_override: str | None = None,
    ) -> TurnResult:
        system_prompt = system_override or ROUTER.get_system_prompt(task_type)
        temperature = ROUTER.get_temperature(task_type)

        full_messages = [{"role": "system", "content": system_prompt}] + messages
        full_messages = CTX_MGR.maybe_compress(full_messages)

        tool_results: list[ToolResult] = []
        tool_call_count = 0
        forced = False
        final_content = ""

        while True:
            try:
                response = ollama.chat(
                    model=CFG.ollama_model,
                    messages=full_messages,
                    tools=self.tools if self.tools else None,
                    options={
                        "temperature": temperature,
                        "num_ctx": CFG.ollama_ctx,
                    },
                )
            except Exception as e:
                logger.error(f"Ollama call failed: {e}")
                return TurnResult(
                    content=f"LLM error: {e}",
                    tool_results=tool_results,
                    tool_calls_made=tool_call_count,
                    forced_completion=True,
                )

            msg = response["message"]
            final_content = msg.get("content", "") or ""

            calls = msg.get("tool_calls") or []
            if not calls:
                break  # Model is done

            if tool_call_count >= CFG.max_tool_calls_per_turn:
                forced = True
                logger.debug(f"Tool call limit ({CFG.max_tool_calls_per_turn}) reached — forcing completion")
                break

            # Execute tool calls — enforce limit WITHIN the batch too
            tool_messages = []
            remaining = CFG.max_tool_calls_per_turn - tool_call_count
            calls_to_run = calls[:remaining]  # slice the batch to stay within budget
            if len(calls) > remaining:
                forced = True
                logger.debug(f"Batch of {len(calls)} trimmed to {remaining} (limit={CFG.max_tool_calls_per_turn})")

            for call in calls_to_run:
                if tool_call_count >= CFG.max_tool_calls_per_turn:
                    break

                fn_name = call["function"]["name"]
                fn_args = call["function"].get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except Exception:
                        fn_args = {}

                if not PERMISSIONS.check(fn_name, fn_args):
                    result_str = f"[BLOCKED by permission mode: {PERMISSIONS.mode}]"
                    tr = ToolResult(fn_name, result_str, error=False)
                else:
                    handler = self.tool_handlers.get(fn_name)
                    if handler is None:
                        result_str = f"[ERROR] Unknown tool: {fn_name}"
                        tr = ToolResult(fn_name, result_str, error=True)
                    else:
                        try:
                            out = handler(**fn_args)
                            result_str = str(out) if not isinstance(out, str) else out
                            tr = ToolResult(fn_name, result_str)
                        except Exception as e:
                            result_str = f"[ERROR] {fn_name} raised: {e}"
                            tr = ToolResult(fn_name, result_str, error=True)
                            logger.warning(result_str)

                tool_results.append(tr)
                tool_call_count += 1
                tool_messages.append({
                    "role": "tool",
                    "content": result_str,
                    "name": fn_name,
                })
                logger.debug(f"Tool {fn_name} → {result_str[:120]}")

            # Append assistant turn + tool results to history
            # Use only the calls we actually ran (Ollama expects matching pairs)
            full_messages.append({"role": "assistant", "content": final_content or "", "tool_calls": calls_to_run})
            full_messages.extend(tool_messages)

        return TurnResult(
            content=final_content,
            tool_results=tool_results,
            tool_calls_made=tool_call_count,
            forced_completion=forced,
        )
