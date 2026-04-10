"""
Router — typed prompt templates per task type.
No model switching. One model, many prompts.
Temperature varies by task: planning needs creativity, scoring needs precision.
"""
from __future__ import annotations
from config import CFG

SYSTEM_PROMPTS: dict[str, str] = {
    "plan": (
        "You are a strategic software planner. Given a goal or opportunity, "
        "decompose it into a concrete DAG of executable steps. Be specific about "
        "file names, commands, and dependencies. Think in terms of: what exists, "
        "what to build, how to verify it works, how to ship it."
    ),
    "build": (
        "You are a senior Python engineer. Write clean, minimal, working code. "
        "No placeholders, no TODOs. Every function must be implementable as-is. "
        "Prefer stdlib over dependencies. If a dependency is needed, name it explicitly."
    ),
    "research": (
        "You are a research analyst. Extract the key facts, patterns, and signals "
        "from the provided content. Be concise. Prioritize actionable intelligence "
        "over comprehensive coverage. What would a builder need to know?"
    ),
    "score": (
        "You are a ruthless opportunity evaluator. Score on: demand (0-1), "
        "feasibility (0-1), competition (0=saturated, 1=blue ocean), monetization (0-1). "
        "Return only a JSON object with these four keys and a 'reasoning' string. "
        "Be honest. Most ideas score below 0.5."
    ),
    "decide": (
        "You are a decision engine. Given options and context, output the single best "
        "choice as a JSON object with 'choice' and 'reason' keys. No hedging."
    ),
    "extract": (
        "You are a memory extractor. From the provided session log or outcome, "
        "extract 3-7 concrete learnings as a JSON array of strings. Each learning "
        "must be specific enough to change future behaviour."
    ),
    "default": (
        "You are SDAE — a fully autonomous software-building entity. "
        "You find opportunities, build software, ship it, and track revenue. "
        "You use tools efficiently (max 3 per turn). You learn from outcomes. "
        "You operate without human intervention."
    ),
}

TEMPERATURES: dict[str, float] = {
    "plan": 0.3,
    "build": 0.1,
    "research": 0.2,
    "score": 0.0,
    "decide": 0.0,
    "extract": 0.1,
    "default": 0.2,
}


class Router:
    def get_system_prompt(self, task_type: str) -> str:
        return SYSTEM_PROMPTS.get(task_type, SYSTEM_PROMPTS["default"])

    def get_temperature(self, task_type: str) -> float:
        return TEMPERATURES.get(task_type, CFG.temperature)


ROUTER = Router()
