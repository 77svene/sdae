"""
SDAE — Self-Directed Autonomous Entity
Single source of truth for all configuration.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # LLM
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    ollama_ctx: int = int(os.getenv("OLLAMA_CTX", "8192"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.1"))

    # Paths
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SDAE_DATA", str(Path.home() / ".sdae"))))

    # Agent behaviour
    max_tool_calls_per_turn: int = 3
    max_build_retries: int = 5
    max_context_tokens: int = 5000
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL", "3600"))
    permission_mode: str = os.getenv("PERMISSION_MODE", "auto")  # auto | plan | default | supervised

    # Notifications
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Fitness
    min_opportunity_score: float = 0.55

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "worktrees").mkdir(exist_ok=True)
        (self.data_dir / "projects").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)


# Global singleton
CFG = Config()
