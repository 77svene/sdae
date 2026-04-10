"""
SDAE Self-Upgrader — continuous self-improvement loop.

Every cycle:
  1. Read recent log output for errors/warnings
  2. Audit each source module for known anti-patterns & Windows gaps
  3. Ask Ollama to propose targeted patches
  4. Apply patches, run smoke tests
  5. If tests pass → write to disk (hot-patch live codebase)
  6. Log what changed and why
  7. Sleep N minutes, repeat forever

Run alongside the daemon:
  python self_upgrader.py
"""
from __future__ import annotations
import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from loguru import logger

import ollama

# ─────────────────────────────── config ──────────────────────────────────────
SDAE_ROOT     = Path(__file__).parent
LOG_FILE      = Path.home() / ".sdae" / "logs" / "sdae.log"
TESTS_CMD     = [sys.executable, "-m", "pytest", "tests/test_smoke.py", "-q", "--tb=short"]
AUDIT_INTERVAL = 300          # seconds between audit passes
MODEL          = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")

# Files audited each pass (in priority order)
AUDIT_TARGETS = [
    "intel/world_model.py",
    "intel/scorer.py",
    "intel/scanner.py",
    "core/query_engine.py",
    "core/daemon.py",
    "exec/builder.py",
    "exec/deployer.py",
    "memory/warm.py",
    "memory/cold.py",
    "memory/compressor.py",
    "outcomes/fitness.py",
    "outcomes/learner.py",
    "agents/coordinator.py",
    "main.py",
]

# Known anti-patterns to always check
ANTIPATTERNS = [
    ("disk_usage(\"/\")",   'disk_usage("/") fails on Windows — use shutil.disk_usage(Path.home().anchor)'),
    ("time.sleep(60)",      "Long fixed sleep in daemon — should use configurable interval"),
    ("except Exception:\n        continue", "Bare except+continue swallows all errors silently"),
    ("requests.get(",       "requests.get without timeout can hang forever"),
    ("print(",              "Use logger.* instead of print() for consistent output"),
]

# ─────────────────────────────── helpers ─────────────────────────────────────

def _tail_log(n: int = 60) -> str:
    """Return last N lines of sdae.log."""
    if not LOG_FILE.exists():
        return ""
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def _read_module(rel: str) -> str | None:
    p = SDAE_ROOT / rel
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _write_module(rel: str, content: str) -> None:
    p = SDAE_ROOT / rel
    p.write_text(content, encoding="utf-8")
    logger.success(f"Patched: {rel}")


def _run_tests() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            TESTS_CMD,
            capture_output=True, text=True, timeout=120,
            cwd=SDAE_ROOT,
        )
        ok = result.returncode == 0
        out = (result.stdout + result.stderr)[-2000:]
        return ok, out
    except Exception as e:
        return False, str(e)


def _check_antipatterns(code: str, module: str) -> list[str]:
    issues = []
    for pattern, message in ANTIPATTERNS:
        if pattern in code:
            issues.append(f"ANTIPATTERN in {module}: {message}")
    return issues


def _is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _ask_llm_for_patch(module: str, code: str, issues: list[str], log_tail: str) -> str | None:
    """Ask Ollama to produce a patched version of the module."""
    issue_text = "\n".join(f"- {i}" for i in issues)
    prompt = f"""You are a senior Python engineer. You MUST improve this module.

Module: {module}
Issues found:
{issue_text}

Recent log output (errors/warnings only):
{log_tail[-800:]}

Current code:
```python
{code[:3000]}
```

Return ONLY the complete improved Python file. No explanation. No markdown fences.
Fix all issues. Do not remove functionality. Keep all imports. Make it Windows-compatible.
Improvements should be minimal, targeted, safe. Return valid Python only."""

    try:
        resp = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a Python expert. Return only valid Python code. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1, "num_ctx": 4096},
        )
        raw = resp["message"]["content"].strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"^```python\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^```\s*", "", raw, flags=re.MULTILINE)
        return raw.strip()
    except Exception as e:
        logger.warning(f"LLM patch request failed: {e}")
        return None


# ─────────────────────────────── audit pass ──────────────────────────────────

def audit_pass(pass_num: int) -> dict:
    logger.info(f"=== SELF-UPGRADE PASS {pass_num} ===")
    log_tail  = _tail_log(60)
    upgraded  = []
    skipped   = []
    failed    = []

    # Extract ERROR/WARNING lines from log for context
    error_lines = [l for l in log_tail.splitlines() if "ERROR" in l or "WARNING" in l or "Traceback" in l]
    error_ctx   = "\n".join(error_lines[-20:]) if error_lines else "No recent errors."
    logger.info(f"Recent log issues: {len(error_lines)} lines")

    for rel in AUDIT_TARGETS:
        code = _read_module(rel)
        if code is None:
            skipped.append(rel)
            continue

        issues = _check_antipatterns(code, rel)

        # Also flag any ERROR/WARNING lines that mention this module
        module_name = Path(rel).stem
        module_errors = [l for l in error_lines if module_name in l]
        if module_errors:
            issues.append(f"Runtime errors in this module: {'; '.join(module_errors[:3])}")

        if not issues:
            logger.debug(f"Clean: {rel}")
            skipped.append(rel)
            continue

        logger.warning(f"Issues in {rel}: {len(issues)} problems")
        for iss in issues:
            logger.warning(f"  → {iss}")

        # Ask LLM for patch
        patch = _ask_llm_for_patch(rel, code, issues, error_ctx)
        if not patch:
            failed.append(rel)
            continue

        if not _is_valid_python(patch):
            logger.error(f"LLM returned invalid Python for {rel} — skipping")
            failed.append(rel)
            continue

        if patch.strip() == code.strip():
            logger.info(f"No change proposed for {rel}")
            skipped.append(rel)
            continue

        # Backup original
        backup_path = SDAE_ROOT / f"{rel}.bak"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(code, encoding="utf-8")

        # Apply patch
        _write_module(rel, patch)

        # Validate with tests
        ok, test_out = _run_tests()
        if ok:
            logger.success(f"Tests PASSED after patching {rel}")
            upgraded.append(rel)
        else:
            logger.error(f"Tests FAILED after patching {rel} — reverting")
            _write_module(rel, code)   # revert
            backup_path.unlink(missing_ok=True)
            failed.append(rel)
            logger.info(f"Test output:\n{test_out[-500:]}")

    return {"upgraded": upgraded, "skipped": skipped, "failed": failed}


# ─────────────────────────────── gap scanner ─────────────────────────────────

def scan_structural_gaps() -> list[str]:
    """Detect missing files/modules that should exist based on imports."""
    gaps = []
    for rel in AUDIT_TARGETS:
        p = SDAE_ROOT / rel
        if not p.exists():
            gaps.append(f"MISSING FILE: {rel}")
            continue
        code = p.read_text(encoding="utf-8", errors="replace")
        # Check for TODO/FIXME/HACK/STUB markers
        for i, line in enumerate(code.splitlines(), 1):
            if any(marker in line for marker in ["TODO", "FIXME", "HACK", "STUB", "NotImplemented", "pass  #"]):
                gaps.append(f"{rel}:{i}: {line.strip()}")
    return gaps


def report_gaps(gaps: list[str]) -> None:
    if not gaps:
        logger.info("No structural gaps found")
        return
    logger.warning(f"=== {len(gaps)} GAPS DETECTED ===")
    for g in gaps:
        logger.warning(f"  GAP: {g}")

    # Write gaps to a file for tracking
    gap_file = SDAE_ROOT / "gaps.txt"
    gap_file.write_text("\n".join(gaps), encoding="utf-8")
    logger.info(f"Gaps written to {gap_file}")


# ─────────────────────────────── main loop ───────────────────────────────────

def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<cyan>{time:HH:mm:ss}</cyan> | <level>{level: <8}</level> | UPGRADER | {message}")
    logger.add(SDAE_ROOT / "upgrader.log", level="DEBUG", rotation="10 MB", retention="7 days")

    logger.info("SDAE Self-Upgrader started")
    logger.info(f"Model: {MODEL} | Interval: {AUDIT_INTERVAL}s | Targets: {len(AUDIT_TARGETS)} modules")

    pass_num = 0
    while True:
        pass_num += 1
        try:
            # 1. Scan for structural gaps
            gaps = scan_structural_gaps()
            report_gaps(gaps)

            # 2. Audit and patch
            result = audit_pass(pass_num)
            logger.info(
                f"Pass {pass_num} complete — "
                f"upgraded={len(result['upgraded'])} | "
                f"skipped={len(result['skipped'])} | "
                f"failed={len(result['failed'])}"
            )
            if result["upgraded"]:
                logger.success(f"Patched modules: {result['upgraded']}")

        except KeyboardInterrupt:
            logger.info("Self-upgrader stopped by user")
            break
        except Exception as e:
            logger.error(f"Upgrader pass {pass_num} crashed: {e}")

        logger.info(f"Next audit in {AUDIT_INTERVAL}s...")
        time.sleep(AUDIT_INTERVAL)


if __name__ == "__main__":
    main()
