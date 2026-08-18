"""
Structured JSON Logger & Intent/Outcome Logging for Project 120.
Enforces machine-readable JSON log emissions and agentic telemetry.
"""

import json
import logging
import sys
import time
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Formats standard Python LogRecord objects into structured JSON lines.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach custom contextual attributes if present
        for key in ("trace_id", "span_id", "session_id", "agent_name", "event_type", "latency_ms", "payload"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def get_structured_logger(name: str = "sebi_mf_engine") -> logging.Logger:
    """
    Returns or configures a structured JSON logger.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


# Default engine logger
engine_logger = get_structured_logger("sebi_mf_engine")


def log_agent_intent(
    logger: logging.Logger,
    agent_name: str,
    intent: str,
    params: dict[str, Any],
    session_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """
    Logs structured intent before an agent or tool step execution.
    """
    extra = {
        "event_type": "agent.intent",
        "agent_name": agent_name,
        "session_id": session_id or "default",
        "trace_id": trace_id or f"trace-{int(time.time() * 1000)}",
        "payload": {
            "intent": intent,
            "parameters": params,
        },
    }
    logger.info(f"[{agent_name}] Intent: {intent}", extra=extra)


def log_agent_outcome(
    logger: logging.Logger,
    agent_name: str,
    status: str,
    outcome_summary: str,
    latency_ms: float,
    session_id: str | None = None,
    trace_id: str | None = None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """
    Logs structured outcome after an agent or tool step execution.
    """
    extra = {
        "event_type": "agent.outcome",
        "agent_name": agent_name,
        "session_id": session_id or "default",
        "trace_id": trace_id or f"trace-{int(time.time() * 1000)}",
        "latency_ms": round(latency_ms, 3),
        "payload": {
            "status": status,
            "outcome_summary": outcome_summary,
            **(extra_data or {}),
        },
    }
    logger.info(
        f"[{agent_name}] Outcome: {status} ({latency_ms:.2f}ms) - {outcome_summary}",
        extra=extra,
    )
