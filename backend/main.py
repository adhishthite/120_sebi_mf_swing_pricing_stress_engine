"""
FastAPI Backend Application Entrypoint for Project 120:
SEBI Mutual Fund Swing Pricing & Liquidation Stress Simulation Engine.
"""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from config import AppConfig, config_manager
from services.agents import Orchestrator, PIIRedactor
from services.database import (
    get_all_traces,
    get_session_state,
    init_db,
    list_hitl_approvals,
    load_session_history,
    update_hitl_approval,
)
from services.logger import engine_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database schema and OpenTelemetry instrumentation on startup."""
    engine_logger.info("Initializing SQLite database engine and tracing...")
    await init_db()
    yield
    engine_logger.info("Shutting down engine service...")


app = FastAPI(
    title="SEBI Mutual Fund Swing Pricing and Stress Simulation Engine",
    description="Backend API for portfolio liquidation stress testing, compliance checks, swing pricing, and HITL adjudication.",
    version="2.0.0",
    lifespan=lifespan,
)

# OpenTelemetry FastAPI automatic request instrumentation
FastAPIInstrumentor.instrument_app(app)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIT_TRAIL_FILE = Path(__file__).resolve().parent / "audit_trail.json"


def load_audit_trail() -> list[dict[str, Any]]:
    if AUDIT_TRAIL_FILE.exists():
        try:
            with open(AUDIT_TRAIL_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_to_audit_trail(entry: dict[str, Any]):
    trail = load_audit_trail()
    trail.insert(0, entry)
    trail = trail[:100]
    try:
        with open(AUDIT_TRAIL_FILE, "w") as f:
            json.dump(trail, f, indent=2)
    except Exception as e:
        engine_logger.warning(f"Failed to write to audit trail file: {e}")


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------


class RedactRequest(BaseModel):
    investor_name: str = ""
    investor_pan: str = ""
    investor_aadhaar: str = ""


class ApprovalDecisionRequest(BaseModel):
    decision: str = "APPROVED"  # APPROVED or REJECTED
    reviewed_by: str = "Chief Risk Officer"
    comments: str = "Approved by Risk & Compliance Committee under Para 7.1 guidelines."


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/redact")
def redact_pii(payload: dict[str, Any] = Body(...)):
    """Masks investor PII (PAN, Aadhaar, and Name) using DPDP 2023 compliant policies."""
    try:
        redacted = PIIRedactor.redact_payload(payload)
        return redacted
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate-stress")
async def simulate_stress(payload: dict[str, Any] = Body(...)):
    """
    Simulates a portfolio stress scenario using autonomous multi-agent coordination.
    Optimizes liquidation, evaluates CEL compliance rules, computes swung NAV, and checks HITL code stops.
    """
    try:
        result = await Orchestrator.run_simulation_async(payload)

        # Append to legacy JSON audit trail for backwards-compatibility
        audit_entry = {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": result.get("session_id"),
            "session_status": result.get("session_status"),
            "request_payload": result.get("redacted_input_payload", {}),
            "optimal_strategy": result.get("optimal_strategy"),
            "optimal_strategy_details": result.get("optimal_strategy_details"),
            "nav_impact": result.get("nav_impact"),
            "compliance_status": result.get("compliance_status"),
            "explanation": result.get("explanation"),
            "trace_id": result.get("trace_id"),
        }
        save_to_audit_trail(audit_entry)

        return result
    except Exception as e:
        engine_logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}")


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieves session state and message history from SQLite."""
    session = await get_session_state(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    messages = await load_session_history(session_id)
    return {
        "session": session,
        "messages": messages,
    }


@app.post("/api/sessions/{session_id}/approve")
async def approve_session(
    session_id: str,
    req: ApprovalDecisionRequest = Body(default_factory=ApprovalDecisionRequest),
):
    """
    Approves or rejects a paused HELD session under Human-in-the-Loop review.
    """
    approvals = await list_hitl_approvals(session_id=session_id)
    if not approvals:
        raise HTTPException(status_code=404, detail=f"No pending approval ticket found for session {session_id}.")

    latest_appr = approvals[0]
    updated = await update_hitl_approval(
        approval_id=latest_appr["approval_id"],
        status=req.decision.upper(),
        approved_by=req.reviewed_by,
        comments=req.comments,
    )
    return {
        "message": f"Session {session_id} decision recorded as {req.decision.upper()}.",
        "approval": updated,
    }


@app.get("/api/approvals")
async def get_approvals(
    session_id: str | None = Query(None),
    status: str | None = Query(None),
):
    """Lists Human-in-the-Loop approval tickets."""
    return await list_hitl_approvals(session_id=session_id, status=status)


@app.post("/api/approvals/{approval_id}/decision")
async def record_approval_decision(
    approval_id: str,
    req: ApprovalDecisionRequest = Body(...),
):
    """Submits a maker-checker approval decision for an approval ticket."""
    updated = await update_hitl_approval(
        approval_id=approval_id,
        status=req.decision.upper(),
        approved_by=req.reviewed_by,
        comments=req.comments,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Approval ID {approval_id} not found.")
    return updated


@app.get("/api/traces")
async def get_traces(
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieves OpenTelemetry agent execution traces and latency metrics."""
    return await get_all_traces(session_id=session_id, limit=limit)


@app.get("/api/config", response_model=AppConfig)
def get_config():
    """Retrieves the current active configuration."""
    return config_manager.get_config()


@app.post("/api/config", response_model=AppConfig)
def update_config(new_config: AppConfig):
    """Updates the active configuration and saves it to config.json."""
    try:
        updated = config_manager.update_config(new_config)
        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")


@app.get("/api/audit-trail")
def get_audit_trail():
    """Retrieves the list of past simulation runs."""
    return load_audit_trail()


@app.get("/api/health")
def health_check():
    """Checks service health."""
    return {"status": "healthy", "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
