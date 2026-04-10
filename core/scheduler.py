"""
Scheduler — background thread running periodic jobs.
Wraps the `schedule` library. Add jobs by name, run in daemon thread.
"""
from __future__ import annotations
import threading
import time
from typing import Callable
import schedule
from loguru import logger


class Scheduler:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._running = False
        self._jobs: dict[str, schedule.Job] = {}

    def add_job(self, name: str, fn: Callable, interval_seconds: int):
        job = schedule.every(interval_seconds).seconds.do(self._wrap(name, fn))
        self._jobs[name] = job
        logger.info(f"Scheduled '{name}' every {interval_seconds}s")

    def add_daily_job(self, name: str, fn: Callable, at: str = "09:00"):
        job = schedule.every().day.at(at).do(self._wrap(name, fn))
        self._jobs[name] = job
        logger.info(f"Scheduled '{name}' daily at {at}")

    def run_now(self, name: str):
        job = self._jobs.get(name)
        if job:
            job.run()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sdae-scheduler")
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            schedule.run_pending()
            time.sleep(1)

    def _wrap(self, name: str, fn: Callable) -> Callable:
        def _inner():
            logger.info(f"Running scheduled job: {name}")
            try:
                fn()
            except Exception as e:
                logger.error(f"Job '{name}' failed: {e}")
        return _inner


SCHEDULER = Scheduler()
