"""
Coordinator — dispatches tasks to registered sub-agents.
Pattern from Claude Code's coordinator/ multi-agent system.
Agents are functions. Coordinator tracks them and routes work.
"""
from __future__ import annotations
from typing import Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger


class Coordinator:
    def __init__(self):
        self._agents: dict[str, Callable] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sdae-agent")

    def register(self, name: str, fn: Callable):
        self._agents[name] = fn
        logger.debug(f"Registered agent: {name}")

    def dispatch(self, name: str, **kwargs) -> Any:
        agent = self._agents.get(name)
        if agent is None:
            raise ValueError(f"Unknown agent: {name}")
        logger.info(f"Dispatching → {name}")
        return agent(**kwargs)

    def dispatch_parallel(self, tasks: list[dict]) -> list[Any]:
        """tasks = [{"agent": "name", "kwargs": {...}}, ...]"""
        futures = {}
        for task in tasks:
            name = task["agent"]
            kwargs = task.get("kwargs", {})
            agent = self._agents.get(name)
            if agent is None:
                logger.warning(f"Unknown agent in parallel dispatch: {name}")
                continue
            f = self._executor.submit(agent, **kwargs)
            futures[f] = name

        results = []
        for f in as_completed(futures):
            name = futures[f]
            try:
                result = f.result(timeout=300)
                results.append({"agent": name, "result": result, "error": None})
            except Exception as e:
                logger.error(f"Agent {name} failed: {e}")
                results.append({"agent": name, "result": None, "error": str(e)})

        return results

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())


COORDINATOR = Coordinator()
