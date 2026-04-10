"""
ColdMemory — SQLite persistence. Survives restarts.
Tables: memories, outcomes, opportunity_scores
"""
from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from loguru import logger
from config import CFG


class ColdMemory:
    def __init__(self):
        self.db_path = CFG.data_dir / "cold.db"
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    id TEXT PRIMARY KEY,
                    project_name TEXT,
                    goal TEXT,
                    success INTEGER,
                    revenue REAL DEFAULT 0.0,
                    compute_hours REAL DEFAULT 0.0,
                    deploy_url TEXT,
                    learnings TEXT,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS opportunity_scores (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    source TEXT,
                    demand REAL,
                    feasibility REAL,
                    competition REAL,
                    monetization REAL,
                    composite REAL,
                    created_at REAL
                );
            """)
        logger.info(f"ColdMemory: {self.db_path}")

    def store_memory(self, key: str, content: str, category: str = "general", confidence: float = 1.0):
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?,?,?)",
                (key, content, category, confidence, now, now, 0),
            )

    def get_memory(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT content FROM memories WHERE id=?", (key,)).fetchone()
            if row:
                conn.execute("UPDATE memories SET accessed_at=?, access_count=access_count+1 WHERE id=?", (time.time(), key))
                return row["content"]
        return None

    def get_recent_memories(self, category: str | None = None, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            if category:
                rows = conn.execute("SELECT * FROM memories WHERE category=? ORDER BY accessed_at DESC LIMIT ?", (category, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM memories ORDER BY accessed_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def record_outcome(self, project_name: str, goal: str, success: bool, revenue: float = 0.0,
                       compute_hours: float = 0.0, deploy_url: str = "", learnings: list[str] | None = None):
        import uuid
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), project_name, goal, int(success),
                    revenue, compute_hours, deploy_url,
                    json.dumps(learnings or []), time.time(),
                ),
            )

    def get_outcomes(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM outcomes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def store_opportunity_score(self, opp_id: str, title: str, source: str,
                                demand: float, feasibility: float, competition: float,
                                monetization: float):
        composite = (demand + feasibility + competition + monetization) / 4
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO opportunity_scores VALUES (?,?,?,?,?,?,?,?,?)",
                (opp_id, title, source, demand, feasibility, competition, monetization, composite, time.time()),
            )
        return composite

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
            wins = conn.execute("SELECT COUNT(*) FROM outcomes WHERE success=1").fetchone()[0]
            rev = conn.execute("SELECT SUM(revenue) FROM outcomes").fetchone()[0] or 0.0
            mems = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"total_projects": total, "wins": wins, "revenue": rev, "memories": mems}


COLD = ColdMemory()
