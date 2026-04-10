"""
Builder — iterative test-fix loop.
generate_code → write → install_deps → run → fix (up to max_retries)
FIXED: supports multi-file output, always checks engine is set before use.
"""
from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass, field
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
    files_written: list[str] = field(default_factory=list)


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Returns list of (filename, code) tuples.
    Handles:
      - ```python\n# filename: foo.py\n...```
      - ```python:foo.py\n...```
      - plain ```python\n...``` → defaults to main.py
    """
    results = []

    # Pattern: ```python:filename.py
    for match in re.finditer(r"```(?:python)?:(\S+)\n(.*?)```", text, re.DOTALL):
        results.append((match.group(1), match.group(2).strip()))

    if results:
        return results

    # Pattern: filename comment on first line
    for match in re.finditer(r"```(?:python)?\n#\s*(?:filename|file):\s*(\S+)\n(.*?)```", text, re.DOTALL):
        results.append((match.group(1), match.group(2).strip()))

    if results:
        return results

    # Pattern: plain python block(s) → assign as main.py, app.py, etc.
    blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    default_names = ["main.py", "app.py", "script.py", "solution.py"]
    for i, block in enumerate(blocks):
        name = default_names[i] if i < len(default_names) else f"module_{i}.py"
        results.append((name, block.strip()))

    return results


def _extract_packages(text: str) -> list[str]:
    pkgs = []
    for line in text.splitlines():
        if "pip install" in line:
            parts = line.split("pip install")[-1].strip().split()
            pkgs.extend(p for p in parts if not p.startswith("-") and p)
    return list(set(pkgs))  # deduplicate


class Builder:
    def __init__(self, query_engine=None):
        self._qe = query_engine

    def set_engine(self, qe):
        self._qe = qe

    def _require_engine(self):
        if self._qe is None:
            raise RuntimeError(
                "Builder has no query engine. Call set_engine() before build()."
            )

    def build(self, goal: str, project_dir: Path) -> BuildResult:
        if self._qe is None:
            return BuildResult(success=False, project_path=None, error="No query engine set")

        project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Building: {goal[:80]}")

        # Step 1: Generate initial code
        messages = [{
            "role": "user",
            "content": (
                f"Write a complete, working Python solution that: {goal}\n\n"
                "Rules:\n"
                "- No placeholders, no TODOs, no '...' in code\n"
                "- Use ```python code blocks\n"
                "- If multiple files needed, use ```python:filename.py format\n"
                "- List any pip dependencies on lines starting with 'pip install'"
            ),
        }]
        result = self._qe.run(messages, task_type="build")
        code_blocks = _extract_code_blocks(result.content)

        if not code_blocks:
            return BuildResult(success=False, project_path=project_dir, error="LLM returned no code blocks")

        # Write all files
        files_written = []
        for filename, code in code_blocks:
            path = project_dir / filename
            EXECUTOR.write_file(path, code)
            files_written.append(filename)

        # Install deps
        pkgs = _extract_packages(result.content)
        for pkg in pkgs:
            EXECUTOR.install_package(pkg)

        # Entry point: prefer main.py, else first file
        entry = project_dir / "main.py"
        if not entry.exists():
            entry = project_dir / files_written[0]

        # Step 2: Iterative test-fix loop
        main_code = (project_dir / files_written[0]).read_text()
        for attempt in range(CFG.max_build_retries):
            run_result = EXECUTOR.run_python_file(entry, cwd=project_dir)

            if run_result.success:
                logger.success(f"Build succeeded on attempt {attempt + 1}")
                return BuildResult(
                    success=True,
                    project_path=project_dir,
                    iterations=attempt + 1,
                    test_output=run_result.stdout,
                    files_written=files_written,
                )

            if not run_result.stdout and not run_result.stderr:
                # Empty output from a script that exits 0-ish — consider success
                if run_result.returncode == 0:
                    return BuildResult(success=True, project_path=project_dir,
                                       iterations=attempt + 1, files_written=files_written)

            logger.info(f"Attempt {attempt + 1} failed (rc={run_result.returncode}) — asking LLM to fix")
            fix_messages = [
                {"role": "user", "content": f"Goal: {goal}"},
                {"role": "assistant", "content": f"```python\n{main_code}\n```"},
                {
                    "role": "user",
                    "content": (
                        f"Running produced:\nSTDOUT: {run_result.stdout[:600]}\n"
                        f"STDERR: {run_result.stderr[:600]}\n\n"
                        "Fix the code. Return only the corrected ```python block. No explanations."
                    ),
                },
            ]
            fix_result = self._qe.run(fix_messages, task_type="build")
            new_blocks = _extract_code_blocks(fix_result.content)
            if new_blocks:
                main_code = new_blocks[0][1]
                EXECUTOR.write_file(entry, main_code)

        return BuildResult(
            success=False,
            project_path=project_dir,
            error=f"Failed after {CFG.max_build_retries} attempts",
            iterations=CFG.max_build_retries,
            files_written=files_written,
        )


BUILDER = Builder()
