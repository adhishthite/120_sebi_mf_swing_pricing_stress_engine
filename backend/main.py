import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import AppConfig, config_manager
from services.agents import Orchestrator, PIIRedactor

app = FastAPI(
    title="SEBI Mutual Fund Swing Pricing and Stress Simulation Engine",
    description="Backend API for portfolio liquidation stress testing, compliance checks, and swing pricing.",
    version="1.0.0",
)

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
    trail.insert(0, entry)  # Prepend newest runs
    # Keep only the last 100 entries to prevent infinite growth
    trail = trail[:100]
    try:
        with open(AUDIT_TRAIL_FILE, "w") as f:
            json.dump(trail, f, indent=2)
    except Exception as e:
        print(f"Failed to write to audit trail: {e}")


class RedactRequest(BaseModel):
    investor_name: str = ""
    investor_pan: str = ""
    investor_aadhaar: str = ""


@app.post("/api/redact")
def redact_pii(payload: dict[str, Any] = Body(...)):
    """Masks investor PII (PAN, Aadhaar, and Name) using regex rules defined in policies."""
    try:
        redacted = PIIRedactor.redact_payload(payload)
        return redacted
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate-stress")
def simulate_stress(payload: dict[str, Any] = Body(...)):
    """
    Simulates a portfolio stress scenario.
    Optimizes liquidation, evaluates compliance rules, and generates explanations.
    """
    try:
        # Run orchestrator simulation
        result = Orchestrator.run_simulation(payload)

        # Add to audit trail
        audit_entry = {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_payload": result.get("redacted_input_payload", {}),
            "optimal_strategy": result.get("optimal_strategy"),
            "optimal_strategy_details": result.get("optimal_strategy_details"),
            "nav_impact": result.get("nav_impact"),
            "compliance_status": result.get("compliance_status"),
            "explanation": result.get("explanation"),
        }
        save_to_audit_trail(audit_entry)

        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}")


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
