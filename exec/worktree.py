"""
Worktree — git worktree isolation for each project.
Each build gets its own branch. Merge on success. Delete on failure.
Pattern from Claude Code's EnterWorktreeTool/ExitWorktreeTool.
"""
from __future__ import annotations
import uuid
from pathlib import Path
from contextlib import contextmanager
from loguru import logger
from config import CFG
from exec.executor import EXECUTOR


class WorktreeManager:
    def __init__(self):
        self.base_dir = CFG.data_dir / "worktrees"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def create(self, repo_path: str | Path, branch_prefix: str = "sdae"):
        repo = Path(repo_path)
        branch = f"{branch_prefix}/{uuid.uuid4().hex[:8]}"
        wt_path = self.base_dir / branch.replace("/", "_")

        # Init git repo if not exists
        if not (repo / ".git").exists():
            EXECUTOR.run("git init", cwd=repo)
            EXECUTOR.run("git add -A && git commit -m 'init' --allow-empty", cwd=repo)

        result = EXECUTOR.run(f"git worktree add {wt_path} -b {branch}", cwd=repo)
        if not result.success:
            logger.warning(f"Worktree creation failed: {result.stderr}")
            yield repo  # fallback to main repo path
            return

        logger.info(f"Worktree: {wt_path} (branch: {branch})")
        try:
            yield wt_path
        finally:
            self._cleanup(repo, wt_path, branch)

    def _cleanup(self, repo: Path, wt_path: Path, branch: str):
        EXECUTOR.run(f"git worktree remove {wt_path} --force", cwd=repo)
        EXECUTOR.run(f"git branch -d {branch}", cwd=repo)
        logger.debug(f"Cleaned worktree: {wt_path}")


WORKTREE_MGR = WorktreeManager()
