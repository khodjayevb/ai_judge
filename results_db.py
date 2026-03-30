"""
SQLite results store — logs every evaluation run for historical tracking.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from evaluators.scorer import EvalReport

DB_PATH = Path(__file__).parent / "results.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            role        TEXT NOT NULL,
            prompt_name TEXT,
            prompt_version TEXT,
            model       TEXT,
            provider    TEXT,
            mode        TEXT,
            prompt_source TEXT,
            overall_pct REAL,
            grade       TEXT,
            num_tests   INTEGER,
            num_criteria INTEGER,
            category_scores TEXT,
            avg_latency REAL,
            p95_latency REAL,
            total_tokens INTEGER,
            estimated_cost REAL,
            total_elapsed REAL,
            report_path TEXT,
            run_type    TEXT DEFAULT 'evaluation',
            notes       TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_run(
    report: EvalReport,
    role: str,
    model: str = "",
    provider: str = "",
    mode: str = "",
    prompt_source: str = "",
    report_path: str = "",
    run_type: str = "evaluation",
    notes: str = "",
) -> int:
    """Log an evaluation run and return the run ID."""
    init_db()
    perf = report.perf_summary()
    conn = _get_conn()
    try:
        cursor = conn.execute("""
            INSERT INTO eval_runs (
                timestamp, role, prompt_name, prompt_version, model, provider, mode,
                prompt_source, overall_pct, grade, num_tests, num_criteria,
                category_scores, avg_latency, p95_latency, total_tokens,
                estimated_cost, total_elapsed, report_path, run_type, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            role,
            report.prompt_name,
            report.prompt_version,
            model,
            provider,
            mode,
            prompt_source,
            report.overall_pct,
            report.grade,
            len(report.test_results),
            sum(len(r.criteria_results) for r in report.test_results),
            json.dumps(report.category_scores()),
            perf.get("avg_latency", 0),
            perf.get("p95_latency", 0),
            perf.get("total_tokens", 0),
            perf.get("estimated_cost_usd", 0),
            report.total_elapsed,
            report_path,
            run_type,
            notes,
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_runs(limit: int = 100, role: str = None) -> list[dict]:
    """Get recent evaluation runs."""
    init_db()
    conn = _get_conn()
    try:
        query = "SELECT * FROM eval_runs"
        params = []
        if role:
            query += " WHERE role = ?"
            params.append(role)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_run(run_id: int) -> dict | None:
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
