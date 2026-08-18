"""
Asynchronous SQLite Database Engine for Project 120.
Provides state persistence, session history, OpenTelemetry agent trace logging,
and Human-In-The-Loop (HITL) approval records.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

DB_DIR = Path(__file__).resolve().parent.parent
DB_PATH = DB_DIR / "sebi_engine.db"


@asynccontextmanager
async def get_db_connection(db_path: Path = DB_PATH) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Provides an async context manager for SQLite database connection."""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db(db_path: Path = DB_PATH) -> None:
    """
    Initializes database tables and indexes if they do not exist.
    """
    async with get_db_connection(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_json TEXT NOT NULL DEFAULT '{}',
                summary TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE'
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls_json TEXT DEFAULT '[]',
                tool_responses_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                intent TEXT NOT NULL,
                outcome TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS hitl_approvals (
                approval_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'HELD',
                reason TEXT NOT NULL,
                trigger_metrics_json TEXT NOT NULL DEFAULT '{}',
                requested_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by TEXT,
                comments TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
            );
        """)

        # Create indexes for high performance query resolution
        await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_traces_session ON agent_traces(session_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON agent_traces(trace_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_approvals_session ON hitl_approvals(session_id);")
        await db.commit()


async def get_session_state(session_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    """Retrieves session record and parsed state dictionary."""
    async with (
        get_db_connection(db_path) as db,
        db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor,
    ):
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "state": json.loads(row["state_json"]),
            "summary": row["summary"],
            "status": row["status"],
        }


async def update_session_state(
    session_id: str,
    state_update: dict[str, Any],
    status: str | None = None,
    summary: str | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """
    Updates or inserts a session with new state dictionary and timestamp.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    current = await get_session_state(session_id, db_path)

    if current is None:
        merged_state = state_update
        stat = status or "ACTIVE"
        summ = summary or ""
        async with get_db_connection(db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (session_id, created_at, updated_at, state_json, summary, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, json.dumps(merged_state), summ, stat),
            )
            await db.commit()
    else:
        merged_state = {**current["state"], **state_update}
        stat = status or current["status"]
        summ = summary if summary is not None else current["summary"]
        async with get_db_connection(db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET updated_at = ?, state_json = ?, summary = ?, status = ?
                WHERE session_id = ?
                """,
                (now, json.dumps(merged_state), summ, stat, session_id),
            )
            await db.commit()

    return {
        "session_id": session_id,
        "updated_at": now,
        "state": merged_state,
        "summary": summary if summary is not None else (current["summary"] if current else ""),
        "status": status or (current["status"] if current else "ACTIVE"),
    }


async def save_session_turn(
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_responses: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path = DB_PATH,
) -> int:
    """
    Persists a single conversational turn / message to SQLite database.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    await update_session_state(session_id, {}, db_path=db_path)

    async with get_db_connection(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO messages (
                session_id, role, content, tool_calls_json, tool_responses_json, metadata_json, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(tool_calls or []),
                json.dumps(tool_responses or []),
                json.dumps(metadata or {}),
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def load_session_history(session_id: str, limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """
    Retrieves chronological messages for the given session.
    """
    async with (
        get_db_connection(db_path) as db,
        db.execute(
            """
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ) as cursor,
    ):
        rows = await cursor.fetchall()
        history = []
        for r in rows:
            history.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "tool_calls": json.loads(r["tool_calls_json"]),
                    "tool_responses": json.loads(r["tool_responses_json"]),
                    "metadata": json.loads(r["metadata_json"]),
                    "timestamp": r["timestamp"],
                }
            )
        return history


async def save_agent_trace(session_id: str, trace_data: dict[str, Any], db_path: Path = DB_PATH) -> int:
    """
    Persists a fine-grained agent execution trace to SQLite.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with get_db_connection(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO agent_traces (
                session_id, trace_id, span_id, agent_name, intent, outcome, latency_ms, status, details_json, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                trace_data.get("trace_id", "trace-default"),
                trace_data.get("span_id", "span-default"),
                trace_data.get("agent_name", "UnknownAgent"),
                trace_data.get("intent", ""),
                trace_data.get("outcome", ""),
                float(trace_data.get("latency_ms", 0.0)),
                trace_data.get("status", "SUCCESS"),
                json.dumps(trace_data.get("details", {})),
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_all_traces(
    session_id: str | None = None, limit: int = 100, db_path: Path = DB_PATH
) -> list[dict[str, Any]]:
    """
    Fetches agent traces, optionally filtered by session ID.
    """
    async with get_db_connection(db_path) as db:
        if session_id:
            query = "SELECT * FROM agent_traces WHERE session_id = ? ORDER BY id DESC LIMIT ?"
            params = (session_id, limit)
        else:
            query = "SELECT * FROM agent_traces ORDER BY id DESC LIMIT ?"
            params = (limit,)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "trace_id": r["trace_id"],
                    "span_id": r["span_id"],
                    "agent_name": r["agent_name"],
                    "intent": r["intent"],
                    "outcome": r["outcome"],
                    "latency_ms": r["latency_ms"],
                    "status": r["status"],
                    "details": json.loads(r["details_json"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]


async def save_hitl_approval(
    approval_id: str,
    session_id: str,
    status: str,
    payload: dict[str, Any],
    reason: str = "",
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """
    Persists a Human-In-The-Loop approval stop ticket.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with get_db_connection(db_path) as db:
        await db.execute(
            """
            INSERT INTO hitl_approvals (
                approval_id, session_id, status, reason, trigger_metrics_json, requested_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(approval_id) DO UPDATE SET
                status = excluded.status,
                reason = excluded.reason,
                trigger_metrics_json = excluded.trigger_metrics_json
            """,
            (approval_id, session_id, status, reason, json.dumps(payload), now),
        )
        await db.commit()

    return {
        "approval_id": approval_id,
        "session_id": session_id,
        "status": status,
        "reason": reason,
        "trigger_metrics": payload,
        "requested_at": now,
    }


async def update_hitl_approval(
    approval_id: str,
    status: str,
    approved_by: str,
    comments: str = "",
    db_path: Path = DB_PATH,
) -> dict[str, Any] | None:
    """
    Updates status and decision of a Human-In-The-Loop approval ticket.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with get_db_connection(db_path) as db:
        async with db.execute("SELECT * FROM hitl_approvals WHERE approval_id = ?", (approval_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

        await db.execute(
            """
            UPDATE hitl_approvals
            SET status = ?, reviewed_at = ?, reviewed_by = ?, comments = ?
            WHERE approval_id = ?
            """,
            (status, now, approved_by, comments, approval_id),
        )
        await db.commit()

    session_id = row["session_id"]
    new_sess_status = "APPROVED" if status == "APPROVED" else "REJECTED" if status == "REJECTED" else "ACTIVE"
    await update_session_state(
        session_id, {"approval_decision": status, "reviewed_by": approved_by}, status=new_sess_status, db_path=db_path
    )

    return {
        "approval_id": approval_id,
        "session_id": session_id,
        "status": status,
        "reviewed_at": now,
        "reviewed_by": approved_by,
        "comments": comments,
    }


async def get_hitl_approval(approval_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    """Retrieves a single HITL approval ticket by approval ID."""
    async with (
        get_db_connection(db_path) as db,
        db.execute("SELECT * FROM hitl_approvals WHERE approval_id = ?", (approval_id,)) as cursor,
    ):
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "approval_id": row["approval_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "reason": row["reason"],
            "trigger_metrics": json.loads(row["trigger_metrics_json"]),
            "requested_at": row["requested_at"],
            "reviewed_at": row["reviewed_at"],
            "reviewed_by": row["reviewed_by"],
            "comments": row["comments"],
        }


async def list_hitl_approvals(
    session_id: str | None = None, status: str | None = None, db_path: Path = DB_PATH
) -> list[dict[str, Any]]:
    """Lists HITL approval tickets filtered by session ID and/or status."""
    async with get_db_connection(db_path) as db:
        query = "SELECT * FROM hitl_approvals WHERE 1=1"
        params = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY requested_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "approval_id": r["approval_id"],
                    "session_id": r["session_id"],
                    "status": r["status"],
                    "reason": r["reason"],
                    "trigger_metrics": json.loads(r["trigger_metrics_json"]),
                    "requested_at": r["requested_at"],
                    "reviewed_at": r["reviewed_at"],
                    "reviewed_by": r["reviewed_by"],
                    "comments": r["comments"],
                }
                for r in rows
            ]
