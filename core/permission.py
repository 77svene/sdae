"""
PermissionSystem — 4 modes from Claude Code, adapted for local autonomy.
auto: runs everything, no questions asked (default for daemon mode)
plan: shows plan, asks before executing
default: asks for dangerous ops
supervised: asks for every tool call
"""
from __future__ import annotations
from config import CFG
from loguru import logger

DANGEROUS_TOOLS = {
    "bash",
    "file_delete",
    "deploy",
    "publish",
    "send_telegram",
}


class PermissionSystem:
    def __init__(self):
        self.mode = CFG.permission_mode

    def set_mode(self, mode: str):
        assert mode in ("auto", "plan", "default", "supervised"), f"Unknown mode: {mode}"
        self.mode = mode
        logger.info(f"Permission mode → {mode}")

    def check(self, tool_name: str, args: dict) -> bool:
        """Return True if tool call is allowed to proceed."""
        if self.mode == "auto":
            return True

        if self.mode == "supervised":
            return self._ask(tool_name, args)

        if self.mode == "default":
            if tool_name in DANGEROUS_TOOLS:
                return self._ask(tool_name, args)
            return True

        if self.mode == "plan":
            # plan mode: allow reads/research, block writes/deploys
            if tool_name in DANGEROUS_TOOLS or tool_name in ("file_write", "bash"):
                logger.warning(f"[PLAN MODE] Would call {tool_name}({args}) — blocked")
                return False
            return True

        return True

    def _ask(self, tool_name: str, args: dict) -> bool:
        print(f"\n[PERMISSION] {tool_name}({args})")
        answer = input("Allow? [y/N]: ").strip().lower()
        return answer == "y"


PERMISSIONS = PermissionSystem()
