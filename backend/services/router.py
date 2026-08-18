"""
Strategic Model Router for Project 120.
Maps agentic tasks to optimal Gemini models based on cognitive complexity,
reasoning depth, latency budgets, and cost profiles.
"""

from enum import Enum
from typing import ClassVar


class AgentTaskType(str, Enum):
    TRIAGE_INTENT = "triage_intent"
    TOOL_EXECUTION = "tool_execution"
    LIQUIDATION_OPTIMIZATION = "liquidation_optimization"
    REGULATORY_ADJUDICATION = "regulatory_adjudication"
    MAKER_CHECKER_REVIEW = "maker_checker_review"
    SYNTHESIS_EXPLANATION = "synthesis_explanation"


class ModelTier(str, Enum):
    FLASH_LITE = "gemini-2.5-flash-lite"
    FLASH = "gemini-2.5-flash"
    PRO = "gemini-2.5-pro"


class ModelRouter:
    """
    Directs agent workloads to appropriate Gemini models.
    - Fast Intent Classification / Triage: gemini-2.5-flash-lite
    - Tool Execution & Liquidation Optimization: gemini-2.5-flash
    - Deep Regulatory & Stress Adjudication Review: gemini-2.5-pro
    """

    # Routing matrix
    ROUTING_MAP: ClassVar[dict[AgentTaskType, str]] = {
        AgentTaskType.TRIAGE_INTENT: ModelTier.FLASH_LITE.value,
        AgentTaskType.TOOL_EXECUTION: ModelTier.FLASH.value,
        AgentTaskType.LIQUIDATION_OPTIMIZATION: ModelTier.FLASH.value,
        AgentTaskType.REGULATORY_ADJUDICATION: ModelTier.PRO.value,
        AgentTaskType.MAKER_CHECKER_REVIEW: ModelTier.PRO.value,
        AgentTaskType.SYNTHESIS_EXPLANATION: ModelTier.FLASH.value,
    }

    LATENCY_BUDGET_MS: ClassVar[dict[AgentTaskType, float]] = {
        AgentTaskType.TRIAGE_INTENT: 150.0,
        AgentTaskType.TOOL_EXECUTION: 400.0,
        AgentTaskType.LIQUIDATION_OPTIMIZATION: 500.0,
        AgentTaskType.REGULATORY_ADJUDICATION: 1200.0,
        AgentTaskType.MAKER_CHECKER_REVIEW: 1000.0,
        AgentTaskType.SYNTHESIS_EXPLANATION: 600.0,
    }

    @classmethod
    def get_model_for_task(
        cls,
        task_type: AgentTaskType | str,
        complexity_override: str | None = None,
    ) -> str:
        """
        Resolves the appropriate Gemini model for a given task.

        Args:
            task_type: Type of agent task.
            complexity_override: Optional override ('simple', 'standard', 'deep').

        Returns:
            Model identifier string (e.g. 'gemini-2.5-flash', 'gemini-2.5-pro').
        """
        if complexity_override == "deep":
            return ModelTier.PRO.value
        elif complexity_override == "simple":
            return ModelTier.FLASH_LITE.value

        if isinstance(task_type, str):
            try:
                task_type = AgentTaskType(task_type)
            except ValueError:
                return ModelTier.FLASH.value

        selected_model = cls.ROUTING_MAP.get(task_type, ModelTier.FLASH.value)
        return selected_model

    @classmethod
    def get_latency_budget(cls, task_type: AgentTaskType | str) -> float:
        """Returns the latency budget in milliseconds for a task type."""
        if isinstance(task_type, str):
            try:
                task_type = AgentTaskType(task_type)
            except ValueError:
                return 500.0
        return cls.LATENCY_BUDGET_MS.get(task_type, 500.0)
