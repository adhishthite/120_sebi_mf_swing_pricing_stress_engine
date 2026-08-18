"""
Memory Compaction & Sliding Window Algorithm for Project 120.
Condenses long multi-turn agent conversations into structured state summaries
when approaching token or turn thresholds to optimize LLM context window usage.
"""

import json
from typing import Any


def estimate_tokens(text: str) -> int:
    """
    Heuristic token estimator (approx 4 characters per token).
    """
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """
    Calculates cumulative token estimate across all messages in a session.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens(content)
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            total += estimate_tokens(json.dumps(tool_calls))
        tool_responses = msg.get("tool_responses", [])
        if tool_responses:
            total += estimate_tokens(json.dumps(tool_responses))
    return total


def summarize_older_turns(older_messages: list[dict[str, Any]]) -> str:
    """
    Synthesizes a structured deterministic summary of older conversational turns.
    Preserves stress scenario decisions, liquidation strategies, and compliance outcomes.
    """
    if not older_messages:
        return ""

    key_points = []
    for idx, msg in enumerate(older_messages, 1):
        role = msg.get("role", "unknown").upper()
        metadata = msg.get("metadata", {})

        if role == "USER":
            # Extract key request parameters if present
            key_points.append(f"- Turn {idx} ({role}): User requested scenario simulation or parameter evaluation.")
        elif role == "ASSISTANT":
            # Check for compliance status, swing factor, strategy
            status = metadata.get("compliance_status", "Evaluated")
            strategy = metadata.get("optimal_strategy", "")
            swing_factor = metadata.get("applied_swing_factor_pct", None)

            summary_item = f"- Turn {idx} ({role}): System completed simulation."
            if strategy:
                summary_item += f" Optimal Strategy: {strategy}."
            if swing_factor is not None:
                summary_item += f" Swing Factor: {swing_factor}%."
            if status:
                summary_item += f" Compliance: {status}."
            key_points.append(summary_item)
        elif role == "TOOL" or role == "FUNCTION":
            key_points.append(f"- Turn {idx} ({role}): Executed tool call for regulatory or liquidation calculation.")

    summary_text = (
        "### Prior Conversation Context Summary:\n"
        + "\n".join(key_points)
        + "\n*Context window compacted to preserve regulatory bounds and low latency.*"
    )
    return summary_text


def compact_conversation_history(
    messages: list[dict[str, Any]],
    max_turns: int = 6,
    token_threshold: int = 3000,
) -> tuple[list[dict[str, Any]], str]:
    """
    Compacts conversation history when exceeding maximum turn count or token threshold.
    Preserves recent N turns verbatim and prepends a structured summary of preceding turns.

    Args:
        messages: List of message dictionaries with 'role', 'content', etc.
        max_turns: Number of recent turns to retain verbatim.
        token_threshold: Maximum approximate token budget before triggering compaction.

    Returns:
        tuple[list[dict[str, Any]], str]: (compacted_messages_list, summary_string)
    """
    if not messages:
        return [], ""

    total_tokens = estimate_messages_tokens(messages)
    total_turns = len(messages)

    if total_turns <= max_turns and total_tokens <= token_threshold:
        return messages, ""

    # Split into older messages to compact and recent messages to keep
    split_index = max(0, total_turns - max_turns)
    older_messages = messages[:split_index]
    recent_messages = messages[split_index:]

    summary = summarize_older_turns(older_messages)

    summary_message = {
        "role": "system",
        "content": summary,
        "tool_calls": [],
        "tool_responses": [],
        "metadata": {"type": "compacted_memory_summary", "compacted_turns_count": len(older_messages)},
    }

    compacted = [summary_message] + recent_messages
    return compacted, summary
