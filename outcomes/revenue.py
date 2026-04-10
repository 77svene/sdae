"""
RevenueTracker — tracks actual money.
SQLite table: revenue_events.
Ko-fi donation link setup (no code required, just generates the URL).
"""
from __future__ import annotations
import sqlite3
import time
import uuid
from pathlib import Path
from loguru import logger
from config import CFG


class RevenueTracker:
    def __init__(self):
        self.db_path = CFG.data_dir / "revenue.db"
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS revenue_events (
                    id TEXT PRIMARY KEY,
                    project_name TEXT,
                    amount REAL,
                    currency TEXT DEFAULT 'USD',
                    source TEXT,
                    note TEXT,
                    created_at REAL
                )
            """)

    def record(self, project_name: str, amount: float, source: str = "manual", note: str = ""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO revenue_events VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), project_name, amount, "USD", source, note, time.time()),
            )
        logger.info(f"Revenue: +${amount:.2f} from {project_name} ({source})")

    def get_total(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT SUM(amount) FROM revenue_events").fetchone()
            return float(row[0] or 0)

    def get_by_project(self, project_name: str) -> float:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT SUM(amount) FROM revenue_events WHERE project_name=?",
                (project_name,),
            ).fetchone()
            return float(row[0] or 0)

    def get_recent(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM revenue_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def setup_donation_link(self, username: str) -> str:
        """Ko-fi requires zero code. Just a URL."""
        url = f"https://ko-fi.com/{username}"
        logger.info(f"Donation link: {url}")
        return url

    def setup_gumroad_product(self, title: str, price: float, description: str) -> str:
        """Returns instructions — actual Gumroad setup requires browser."""
        return (
            f"Create Gumroad product:\n"
            f"  Title: {title}\n"
            f"  Price: ${price}\n"
            f"  Description: {description}\n"
            f"  → https://app.gumroad.com/products/new"
        )


REVENUE = RevenueTracker()
