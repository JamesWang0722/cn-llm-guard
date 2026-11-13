"""审计日志存储：SQLite 单文件，记录每次检测的完整上下文。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    input       TEXT    NOT NULL,
    verdict     TEXT    NOT NULL,
    risk_type   TEXT,
    score       REAL,
    hit_rules   TEXT,
    latency_ms  REAL,
    stage       TEXT    DEFAULT 'input',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_verdict ON audit_log(verdict);
"""


class AuditDB:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def insert(
        self,
        text: str,
        verdict: str,
        risk_type: str = "",
        score: float = 0.0,
        hit_rules: list[str] | None = None,
        latency_ms: float = 0.0,
        stage: str = "input",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_log
                    (input, verdict, risk_type, score, hit_rules, latency_ms, stage, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text,
                    verdict,
                    risk_type,
                    score,
                    json.dumps(hit_rules or [], ensure_ascii=False),
                    round(latency_ms, 2),
                    stage,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return int(cur.lastrowid)

    def query(self, limit: int = 50, verdict: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_log"
        params: list[Any] = []
        if verdict:
            sql += " WHERE verdict = ?"
            params.append(verdict)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            blocked = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE verdict = 'block'"
            ).fetchone()[0]
            avg_latency = conn.execute(
                "SELECT AVG(latency_ms) FROM audit_log"
            ).fetchone()[0]
        return {
            "total": total,
            "blocked": blocked,
            "pass_rate": round(1 - blocked / total, 3) if total else 0.0,
            "avg_latency_ms": round(avg_latency or 0, 2),
        }
