"""
Spawner — creates specialized sub-agent instances with mutated configs.
Each spawned agent can have different model/temperature/tools.
Enables emergent specialization without hardcoded roles.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Callable
from loguru import logger
from config import CFG


@dataclass
class AgentConfig:
    name: str
    task_type: str = "default"
    model: str = field(default_factory=lambda: CFG.ollama_model)
    temperature: float = field(default_factory=lambda: CFG.temperature)
    max_tool_calls: int = field(default_factory=lambda: CFG.max_tool_calls_per_turn)
    tools: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def mutate(self, **overrides) -> "AgentConfig":
        """Return a new config with overrides applied."""
        import copy
        new = copy.deepcopy(self)
        for k, v in overrides.items():
            setattr(new, k, v)
        new.name = f"{self.name}_mut_{uuid.uuid4().hex[:4]}"
        return new


class Spawner:
    def __init__(self):
        self._active: dict[str, AgentConfig] = {}

    def spawn(self, config: AgentConfig, fn: Callable, **kwargs) -> str:
        agent_id = uuid.uuid4().hex[:8]
        self._active[agent_id] = config
        logger.info(f"Spawned agent {agent_id} ({config.name}, task={config.task_type})")

        import threading
        def _run():
            try:
                fn(config=config, **kwargs)
            except Exception as e:
                logger.error(f"Agent {agent_id} crashed: {e}")
            finally:
                self._active.pop(agent_id, None)
                logger.debug(f"Agent {agent_id} terminated")

        t = threading.Thread(target=_run, daemon=True, name=f"agent-{agent_id}")
        t.start()
        return agent_id

    def terminate(self, agent_id: str):
        # Cooperative termination — agents check a shared flag in practice
        self._active.pop(agent_id, None)
        logger.info(f"Terminated agent {agent_id}")

    def get_active(self) -> dict[str, AgentConfig]:
        return dict(self._active)

    def count(self) -> int:
        return len(self._active)


SPAWNER = Spawner()
