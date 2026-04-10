"""
Executor — the ONE way to run shell commands.
Wraps subprocess with timeout, rollback journal, and structured output.
All agent actions flow through here.
"""
from __future__ import annotations
import subprocess
import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
from config import CFG


@dataclass
class ExecutionResult:
    command: str
    stdout: str
    stderr: str
    returncode: int
    duration: float
    success: bool = field(init=False)

    def __post_init__(self):
        self.success = self.returncode == 0

    def __str__(self):
        out = self.stdout.strip()
        err = self.stderr.strip()
        return f"[rc={self.returncode}]\n{out}" + (f"\nSTDERR: {err}" if err else "")


class RollbackJournal:
    def __init__(self, path: Path):
        self.path = path
        self._entries: list[dict] = []

    def record(self, action: str, details: dict):
        entry = {"action": action, "details": details, "ts": time.time()}
        self._entries.append(entry)
        self.path.write_text(json.dumps(self._entries, indent=2))

    def get_entries(self) -> list[dict]:
        return list(self._entries)


class Executor:
    def __init__(self):
        self.journal = RollbackJournal(CFG.data_dir / "rollback_journal.json")

    def run(self, command: str, cwd: str | Path | None = None, timeout: int = 120) -> ExecutionResult:
        logger.debug(f"EXEC: {command[:120]}")
        start = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(cwd) if cwd else None,
                timeout=timeout,
            )
            duration = time.time() - start
            result = ExecutionResult(
                command=command,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                duration=duration,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            result = ExecutionResult(command=command, stdout="", stderr="TIMEOUT", returncode=-1, duration=duration)
        except Exception as e:
            duration = time.time() - start
            result = ExecutionResult(command=command, stdout="", stderr=str(e), returncode=-1, duration=duration)

        self.journal.record("exec", {"cmd": command, "rc": result.returncode, "dur": result.duration})
        if not result.success:
            logger.warning(f"Command failed (rc={result.returncode}): {command[:80]}")
        return result

    def run_python_file(self, path: str | Path, cwd: str | Path | None = None) -> ExecutionResult:
        return self.run(f"{sys.executable} {path}", cwd=cwd)

    def install_package(self, package: str) -> ExecutionResult:
        return self.run(f"{sys.executable} -m pip install {package} -q")

    def run_tests(self, test_dir: str | Path) -> ExecutionResult:
        return self.run(f"{sys.executable} -m pytest {test_dir} -x -q --tb=short", timeout=60)

    def write_file(self, path: str | Path, content: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.journal.record("write_file", {"path": str(p)})
        logger.debug(f"Wrote {p}")
        return f"Written: {p}"

    def read_file(self, path: str | Path) -> str:
        p = Path(path)
        if not p.exists():
            return f"[ERROR] File not found: {p}"
        return p.read_text()


EXECUTOR = Executor()
