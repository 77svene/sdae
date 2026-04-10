"""
Daemon — the outer loop.
Runs forever: scan → score → build → deploy → monetize → learn → repeat.
Signal handlers for graceful shutdown (SIGINT, SIGTERM).
State snapshot every 60s so crashes don't lose work.
"""
from __future__ import annotations
import signal
import time
import json
from pathlib import Path
from datetime import datetime
from loguru import logger
from config import CFG
from core.scheduler import SCHEDULER


class Daemon:
    def __init__(self):
        self._running = False
        self._state_file = CFG.data_dir / "daemon_state.json"
        self._cycle_count = 0
        self._agent_loop_fn = None  # injected from main.py

    def set_loop(self, fn):
        """Inject the main agent loop function."""
        self._agent_loop_fn = fn

    def start(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._running = True
        logger.info("SDAE Daemon started")
        self._restore_state()

        SCHEDULER.add_job("main_cycle", self._run_cycle, CFG.scan_interval_seconds)
        SCHEDULER.add_daily_job("weekly_report", self._weekly_report, at="08:00")
        SCHEDULER.start()

        # Run immediately on start
        self._run_cycle()

        while self._running:
            time.sleep(60)
            self._snapshot_state()

        logger.info("Daemon stopped cleanly")

    def _run_cycle(self):
        if self._agent_loop_fn is None:
            logger.warning("No agent loop injected — skipping cycle")
            return
        self._cycle_count += 1
        logger.info(f"=== CYCLE {self._cycle_count} START ===")
        try:
            self._agent_loop_fn()
        except Exception as e:
            logger.error(f"Cycle {self._cycle_count} failed: {e}")
        logger.info(f"=== CYCLE {self._cycle_count} END ===")

    def _snapshot_state(self):
        state = {
            "cycle_count": self._cycle_count,
            "last_snapshot": datetime.utcnow().isoformat(),
            "running": self._running,
        }
        try:
            self._state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.warning(f"State snapshot failed: {e}")

    def _restore_state(self):
        if self._state_file.exists():
            try:
                state = json.loads(self._state_file.read_text())
                self._cycle_count = state.get("cycle_count", 0)
                logger.info(f"Restored state: cycle_count={self._cycle_count}")
            except Exception:
                pass

    def _weekly_report(self):
        logger.info("Weekly report triggered (wire to reporter)")

    def _handle_signal(self, sig, frame):
        logger.info(f"Signal {sig} received — shutting down")
        self._running = False
        SCHEDULER.stop()
        self._snapshot_state()


DAEMON = Daemon()
