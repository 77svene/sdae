"""
Builder — iterative test-fix loop.
generate_code → write → install_deps → run_tests → fix (up to max_retries)
Uses QueryEngine to generate and fix code. Not a one-shot call.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass
from loguru import logger
from config import CFG
from exec.executor import EXECUTOR


@dataclass
class BuildResult:
    success: bool
    project_path: Path | None
    error: str = ""
    iterations: int = 0
    test_output: str = ""


def _extract_code(text: str, lang: str = "python") -> str:
    """Pull code block out of LLM markdown output."""
    pattern = rf"```{lang}\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try generic code block
    match = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_packages(text: str) -> list[str]:
    """Find pip install requirements from LLM output."""
    lines = text.splitlines()
    pkgs = []
    for line in lines:
        if "pip install" in line:
            parts = line.split("pip install")[-1].strip().split()
            pkgs.extend(p for p in parts if not p.startswith("-"))
    return pkgs


class Builder:
    def __init__(self, query_engine=None):
        self._qe = query_engine

    def set_engine(self, qe):
        self._qe = qe

    def build(self, goal: str, project_dir: Path) -> BuildResult:
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Building: {goal[:80]}")

        if self._qe is None:
            return BuildResult(success=False, project_path=None, error="No query engine set")

        # Step 1: Generate initial code
        messages = [{"role": "user", "content": f"Write a complete, working Python script that: {goal}\n\nReturn only the code in a ```python block."}]
        result = self._qe.run(messages, task_type="build")
        code = _extract_code(result.content)

        main_file = project_dir / "main.py"
        EXECUTOR.write_file(main_file, code)

        # Install any dependencies mentioned
        pkgs = _extract_packages(result.content)
        for pkg in pkgs:
            EXECUTOR.install_package(pkg)

        # Step 2: Iterative test-fix loop
        for attempt in range(CFG.max_build_retries):
            run_result = EXECUTOR.run_python_file(main_file, cwd=project_dir)
            if run_result.success:
                logger.success(f"Build succeeded on attempt {attempt + 1}")
                return BuildResult(
                    success=True,
                    project_path=project_dir,
                    iterations=attempt + 1,
                    test_output=run_result.stdout,
                )

            # Fix
            logger.info(f"Attempt {attempt + 1} failed — asking LLM to fix")
            fix_messages = [
                {"role": "user", "content": f"Goal: {goal}"},
                {"role": "assistant", "content": f"```python\n{code}\n```"},
                {"role": "user", "content": f"Running this produced:\nSTDOUT: {run_result.stdout[:500]}\nSTDERR: {run_result.stderr[:500]}\n\nFix the code. Return only the corrected ```python block."},
            ]
            fix_result = self._qe.run(fix_messages, task_type="build")
            code = _extract_code(fix_result.content)
            EXECUTOR.write_file(main_file, code)

        return BuildResult(
            success=False,
            project_path=project_dir,
            error=f"Failed after {CFG.max_build_retries} attempts",
            iterations=CFG.max_build_retries,
        )


BUILDER = Builder()
