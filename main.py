"""
SDAE — Self-Directed Autonomous Entity
Entry point. Assembles all layers. Runs the outer loop.

Usage:
  python main.py --status          # Show current fitness dashboard
  python main.py --goal "..."      # Run one cycle with explicit goal
  python main.py --daemon          # Run indefinitely, scanning every N hours
  python main.py --mode plan       # Change permission mode (auto/plan/default/supervised)
  python main.py --interval 1800   # Scan every 30 minutes
"""
from __future__ import annotations
import sys
import time
import uuid
from pathlib import Path
import typer
from loguru import logger
from rich.console import Console

# ── Config ──────────────────────────────────────────────────────────────────
from config import CFG

# ── Core ────────────────────────────────────────────────────────────────────
from core.query_engine import StreamingQueryEngine
from core.permission import PERMISSIONS
from core.daemon import DAEMON

# ── Exec ────────────────────────────────────────────────────────────────────
from exec.executor import EXECUTOR
from exec.builder import BUILDER
from exec.deployer import DEPLOYER

# ── Memory ──────────────────────────────────────────────────────────────────
from memory.engine import MEMORY
from memory.extractor import EXTRACTOR

# ── Intel ───────────────────────────────────────────────────────────────────
from intel.scanner import SCANNER
from intel.scorer import SCORER
from intel.researcher import RESEARCHER
from intel.world_model import WORLD

# ── Agents ──────────────────────────────────────────────────────────────────
from agents.coordinator import COORDINATOR

# ── Outcomes ────────────────────────────────────────────────────────────────
from outcomes.fitness import FITNESS
from outcomes.revenue import REVENUE
from outcomes.learner import LEARNER
from outcomes.reporter import REPORTER

# ── Setup logging ────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add(CFG.data_dir / "logs" / "sdae.log", level="DEBUG", rotation="50 MB", retention="14 days")

console = Console()
app = typer.Typer(help="SDAE — Self-Directed Autonomous Entity")


# ── Tool definitions for the query engine ─────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command and return stdout/stderr",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Shell command to run"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and return the text content of a URL",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a file and return its content",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "Search agent memory for relevant context",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "bash": lambda command: str(EXECUTOR.run(command)),
    "web_search": lambda query: RESEARCHER.search(query),
    "fetch_url": lambda url: RESEARCHER.fetch(url),
    "file_write": lambda path, content: EXECUTOR.write_file(path, content),
    "file_read": lambda path: EXECUTOR.read_file(path),
    "memory_recall": lambda query: MEMORY.get_context_for_task(query),
}


def build_engine() -> StreamingQueryEngine:
    return StreamingQueryEngine(tools=TOOL_SCHEMAS, tool_handlers=TOOL_HANDLERS)


# ── Main agent cycle ──────────────────────────────────────────────────────

def run_cycle(goal: str | None = None):
    """One full iteration of the outer loop."""
    # Always ensure builder has an engine — safe to call multiple times
    if BUILDER._qe is None:
        BUILDER.set_engine(build_engine())

    start = time.time()
    project_id = uuid.uuid4().hex[:8]

    # 1. World health check
    state = WORLD.get_state()
    if not state.is_healthy():
        logger.warning(f"World unhealthy — skipping cycle: {state.summary()}")
        return

    engine = build_engine()

    # 2. Pick opportunity
    if goal:
        logger.info(f"Explicit goal: {goal}")
        target_goal = goal
    else:
        opps = SCANNER.scan()
        best = SCORER.pick_best(opps)
        if best is None:
            logger.warning("No scoreable opportunity found this cycle")
            return
        target_goal = best.to_goal()
        logger.info(f"Selected: {target_goal}")

    # 3. Research
    context = RESEARCHER.research_topic(target_goal)
    memory_context = MEMORY.get_context_for_task(target_goal)

    # 4. Plan
    plan_messages = [{
        "role": "user",
        "content": (
            f"Goal: {target_goal}\n\n"
            f"Research:\n{context[:1500]}\n\n"
            f"Memory:\n{memory_context}\n\n"
            "Create a concrete build plan. What will you build, what files, what commands?"
        ),
    }]
    plan_result = engine.run(plan_messages, task_type="plan")
    logger.info(f"Plan: {plan_result.content[:200]}")

    # 5. Build
    project_dir = CFG.data_dir / "projects" / project_id
    build_result = BUILDER.build(target_goal, project_dir)

    # 6. Deploy (if build succeeded)
    deploy_url = ""
    deploy_success = False
    if build_result.success:
        deploy_result = DEPLOYER.deploy(project_dir)
        deploy_success = deploy_result.success
        deploy_url = deploy_result.url
        if deploy_success:
            REPORTER.notify(f"✅ Deployed: {target_goal[:60]}\n{deploy_url}")

    # 7. Extract learnings
    compute_hours = (time.time() - start) / 3600
    learnings = EXTRACTOR.extract_from_outcome(
        project_name=project_id,
        goal=target_goal,
        success=build_result.success,
        stdout=build_result.test_output,
        stderr=build_result.error,
    )

    # 8. Record fitness
    FITNESS.record_build(
        project_name=project_id,
        goal=target_goal,
        build_success=build_result.success,
        deploy_success=deploy_success,
        compute_hours=compute_hours,
        revenue=0.0,  # Updated externally when payment comes in
        deploy_url=deploy_url,
    )

    # 9. Learn
    LEARNER.run()

    elapsed = time.time() - start
    logger.info(f"Cycle complete in {elapsed:.1f}s | build={'OK' if build_result.success else 'FAIL'} | deploy={'OK' if deploy_success else 'FAIL'}")


# ── CLI ───────────────────────────────────────────────────────────────────

@app.command()
def main(
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon (continuous loop)"),
    goal: str = typer.Option("", "--goal", "-g", help="Explicit goal for this cycle"),
    status: bool = typer.Option(False, "--status", "-s", help="Show fitness dashboard and exit"),
    mode: str = typer.Option("", "--mode", "-m", help="Permission mode: auto|plan|default|supervised"),
    interval: int = typer.Option(0, "--interval", "-i", help="Scan interval in seconds (daemon mode)"),
):
    if mode:
        PERMISSIONS.set_mode(mode)

    if interval:
        CFG.scan_interval_seconds = interval

    if status:
        FITNESS.print_dashboard()
        stats = MEMORY.get_stats()
        console.print(f"\n[bold]Memory:[/bold] hot={stats['hot_cache_size']}, warm={stats['warm_count']}, memories={stats['memories']}")
        console.print(f"[bold]Total Revenue:[/bold] ${REVENUE.get_total():.2f}")
        return

    if daemon:
        DAEMON.set_loop(lambda: run_cycle(goal or None))
        DAEMON.start()
    else:
        run_cycle(goal or None)


if __name__ == "__main__":
    app()
