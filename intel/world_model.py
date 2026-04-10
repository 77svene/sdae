"""
WorldModel — system state awareness. Disk, memory, CPU, network.
The agent checks health before each cycle. If unhealthy, skips or throttles.
FIXED: disk_usage uses Path.home().anchor for Windows compatibility.
"""
from __future__ import annotations
import shutil
from pathlib import Path
import psutil
import requests
from dataclasses import dataclass
from loguru import logger


@dataclass
class WorldState:
    disk_free_gb: float
    ram_free_gb: float
    cpu_percent: float
    network_ok: bool
    ollama_ok: bool

    def is_healthy(self) -> bool:
        return (
            self.disk_free_gb > 1.0
            and self.ram_free_gb > 0.5
            and self.cpu_percent < 90.0
            and self.ollama_ok
        )

    def summary(self) -> str:
        status = "HEALTHY" if self.is_healthy() else "DEGRADED"
        return (
            f"[{status}] disk={self.disk_free_gb:.1f}GB free, "
            f"ram={self.ram_free_gb:.1f}GB free, cpu={self.cpu_percent:.0f}%, "
            f"network={'OK' if self.network_ok else 'DOWN'}, "
            f"ollama={'OK' if self.ollama_ok else 'DOWN'}"
        )


class WorldModel:
    def __init__(self):
        from config import CFG
        self._ollama_url = CFG.ollama_base_url

    def get_state(self) -> WorldState:
        # Disk — use home drive anchor for Windows/Linux compatibility
        disk = shutil.disk_usage(Path.home().anchor)
        disk_free_gb = disk.free / (1024 ** 3)

        # RAM
        mem = psutil.virtual_memory()
        ram_free_gb = mem.available / (1024 ** 3)

        # CPU (1s sample)
        cpu = psutil.cpu_percent(interval=1)

        # Network
        net_ok = self._check_network()

        # Ollama
        ollama_ok = self._check_ollama()

        state = WorldState(
            disk_free_gb=disk_free_gb,
            ram_free_gb=ram_free_gb,
            cpu_percent=cpu,
            network_ok=net_ok,
            ollama_ok=ollama_ok,
        )
        logger.debug(state.summary())
        return state

    def _check_network(self) -> bool:
        try:
            requests.get("https://1.1.1.1", timeout=3)
            return True
        except Exception:
            return False

    def _check_ollama(self) -> bool:
        try:
            r = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


WORLD = WorldModel()
