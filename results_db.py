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
    # Add columns if not exists (for DB migrations)
    for col, default in [
        ("judge_model", "''"),
        ("dag_pct", "NULL"),
        ("consolidated_pct", "NULL"),
        ("consolidated_grade", "''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE eval_runs ADD COLUMN {col} {default}")
        except Exception:
            pass
    # Calibration history table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            judge_model TEXT,
            accuracy    REAL,
            discrimination REAL,
            avg_deviation REAL,
            total_tests INTEGER,
            passed      INTEGER,
            failed      INTEGER,
            issues_count INTEGER,
            avg_excellent REAL,
            avg_adequate REAL,
            avg_poor    REAL,
            avg_misleading REAL,
            details     TEXT,
            report_path TEXT
        )
    """)
    # Migration for existing calibration tables
    try:
        conn.execute("ALTER TABLE calibration_runs ADD COLUMN report_path TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()


def log_calibration(result: dict, judge_model: str = "", report_path: str = "") -> int:
    """Log a calibration run."""
    init_db()
    conn = _get_conn()
    try:
        bq = result.get("by_quality", {})
        cursor = conn.execute("""
            INSERT INTO calibration_runs (
                timestamp, judge_model, accuracy, discrimination, avg_deviation,
                total_tests, passed, failed, issues_count,
                avg_excellent, avg_adequate, avg_poor, avg_misleading, details, report_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            judge_model,
            result.get("overall_accuracy", 0),
            result.get("discrimination", 0),
            result.get("avg_deviation", 0),
            result.get("total_tests", 0),
            result.get("passed", 0),
            result.get("failed", 0),
            len(result.get("consistency_issues", [])),
            bq.get("excellent", {}).get("avg_geval", 0),
            bq.get("adequate", {}).get("avg_geval", 0),
            bq.get("poor", {}).get("avg_geval", 0),
            bq.get("misleading", {}).get("avg_geval", 0),
            json.dumps(result.get("consistency_issues", [])),
            report_path,
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_calibration_runs(limit: int = 20) -> list[dict]:
    """Get recent calibration runs."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM calibration_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def log_run(
    report: EvalReport,
    role: str,
    model: str = "",
    judge_model: str = "",
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
                timestamp, role, prompt_name, prompt_version, model, judge_model, provider, mode,
                prompt_source, overall_pct, dag_pct, consolidated_pct, grade, consolidated_grade,
                num_tests, num_criteria, category_scores, avg_latency, p95_latency, total_tokens,
                estimated_cost, total_elapsed, report_path, run_type, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            role,
            report.prompt_name,
            report.prompt_version,
            model,
            judge_model,
            provider,
            mode,
            prompt_source,
            report.overall_pct,
            report.overall_dag_pct,
            report.consolidated_pct,
            report.grade,
            report.consolidated_grade,
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


def log_red_team_run(
    results: dict,
    role: str,
    model: str = "",
    provider: str = "",
    mode: str = "",
    prompt_source: str = "",
    report_path: str = "",
) -> int:
    """Log a red team run to the same history table."""
    init_db()
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
            "Red Team Assessment",
            "1.0",
            model,
            provider,
            mode,
            prompt_source,
            results.get("overall_pass_rate", 0),
            "PASS" if results.get("overall_pass_rate", 0) >= 90 else "WARN" if results.get("overall_pass_rate", 0) >= 70 else "FAIL",
            results.get("total_attacks", 0),
            0,
            json.dumps(results.get("overview", {})),
            0,
            0,
            0,
            0,
            0,
            report_path,
            "red_team",
            f"Pass rate: {results.get('overall_pass_rate', 0)}% | {results.get('total_attacks', 0)} attacks",
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
