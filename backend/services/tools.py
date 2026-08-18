"""
Typed and Documented Tools for Project 120 Autonomous Agents.
Contains mathematical liquidation solvers, CEL compliance evaluators,
SEBI circular knowledge lookup, and HITL overlimit triggers.
"""

import functools
import inspect
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from config import get_current_config
from services.cel_engine import (
    evaluate_pii_protection,
    evaluate_portfolio_compliance,
    evaluate_swing_pricing_triggers,
)
from services.math_engine import (
    simulate_liquidation,
)
from services.telemetry import trace_span

# Registry of tools available to agent loops
TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(name: str | None = None, description: str | None = None):
    """
    Decorator to register a Python function as an agent tool with metadata and JSON schema.
    """

    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__.strip() if func.__doc__ else f"Tool {tool_name}")

        sig = inspect.signature(func)

        # Build parameter schema
        properties: dict[str, Any] = {}
        required: list[str] = []

        type_map = {
            int: "integer",
            float: "number",
            str: "string",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            p_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
            json_type = type_map.get(p_type, "string")
            param_meta: dict[str, Any] = {"type": json_type, "description": f"Parameter {param_name}"}
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
            else:
                param_meta["default"] = param.default
            properties[param_name] = param_meta

        schema = {
            "name": tool_name,
            "description": tool_desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

        TOOL_REGISTRY[tool_name] = {
            "name": tool_name,
            "function": func,
            "description": tool_desc,
            "schema": schema,
            "signature": sig,
        }

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Pydantic Schemas for Tools
# ---------------------------------------------------------------------------


class AlmgrenChrissImpactInput(BaseModel):
    asset_class: str = Field(..., description="Asset class: 'liquid', 'semi_liquid', or 'illiquid'")
    liquidation_amount: float = Field(..., ge=0, description="INR amount of asset to liquidate")
    market_depth_limit: float = Field(default=1_000_000_000.0, gt=0, description="Daily market volume / depth limit")
    base_spread_pct: float = Field(default=0.5, ge=0, description="Base bid-ask half spread percentage")
    price_impact_coefficient: float = Field(
        default=0.5, ge=0, description="Temporary and permanent price impact factor"
    )
    volatility_pct: float = Field(default=1.5, ge=0, description="Asset daily volatility percentage")
    market_dislocation_active: bool = Field(default=False, description="Whether SEBI market dislocation is active")


class AlmgrenChrissImpactOutput(BaseModel):
    asset_class: str
    liquidation_amount: float
    spread_pct: float
    temporary_impact_pct: float
    permanent_impact_pct: float
    total_cost_pct: float
    total_cost_inr: float
    execution_shortfall_inr: float


class CelComplianceInput(BaseModel):
    policy_name: str = Field(
        ..., description="Policy to check: 'swing_pricing_triggers', 'portfolio_compliance', 'pii_protection', or 'all'"
    )
    payload: dict[str, Any] = Field(..., description="Payload containing scheme and transaction metrics")


class CelComplianceOutput(BaseModel):
    policy_name: str
    is_compliant: bool
    details: dict[str, Any]
    rules_evaluated: list[dict[str, Any]]


class LiquidationStepInput(BaseModel):
    aum: float = Field(..., gt=0, description="Total fund AUM in INR")
    liquid_ratio: float = Field(..., ge=0, le=1, description="Ratio of liquid assets (G-Secs, T-Bills, Cash)")
    semi_liquid_ratio: float = Field(
        ..., ge=0, le=1, description="Ratio of semi-liquid assets (AAA/AA corporate bonds)"
    )
    illiquid_ratio: float = Field(..., ge=0, le=1, description="Ratio of illiquid assets (unrated/A corporate debt)")
    redemption_amount: float = Field(..., ge=0, description="Gross redemption amount in INR")
    strategy: str = Field(
        default="OPTIMIZED", description="Liquidation strategy: 'PRO_RATA', 'WATERFALL', or 'OPTIMIZED'"
    )
    market_dislocation_active: bool = Field(default=False, description="True if market dislocation declared by SEBI")


class LiquidationStepOutput(BaseModel):
    strategy: str
    liquidated_amounts: dict[str, float]
    transaction_costs: dict[str, Any]
    post_liquidation_exposure: dict[str, float]


class CircularQueryInput(BaseModel):
    query_topic: str = Field(
        ...,
        description="Topic: 'prc_matrix', 'exemptions', 'market_dislocation', 'normal_conditions', 'governance', or 'all'",
    )


class CircularQueryOutput(BaseModel):
    circular_reference: str
    query_topic: str
    clauses: list[dict[str, str]]
    applicable_thresholds: dict[str, Any]
    guidelines_summary: str


class HitlApprovalInput(BaseModel):
    session_id: str = Field(..., description="Active session ID requiring HITL escalation")
    reason: str = Field(..., description="Reason for escalation (e.g., swing factor > 150 bps or net redemption > 15%)")
    swing_factor_bps: float = Field(..., ge=0, description="Calculated swing factor in basis points")
    redemption_pct: float = Field(..., ge=0, description="Net outflow as percentage of AUM")
    post_illiquid_ratio: float = Field(..., ge=0, le=1, description="Post-liquidation illiquid asset ratio")
    current_nav: float = Field(..., gt=0, description="Pre-swing NAV in INR")
    swung_nav: float = Field(..., gt=0, description="Adjusted swung NAV in INR")


class HitlApprovalOutput(BaseModel):
    approval_id: str
    session_id: str
    status: str
    reason: str
    trigger_metrics: dict[str, Any]
    required_roles: list[str]
    instructions: str


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------


@tool(
    name="calculate_almgren_chriss_market_impact",
    description="Calculates market price impact and execution shortfall using the Almgren-Chriss / Kyle's lambda optimal execution model under normal and stressed market conditions.",
)
@trace_span(name="tool.calculate_almgren_chriss_market_impact")
def calculate_almgren_chriss_market_impact(
    asset_class: str,
    liquidation_amount: float,
    market_depth_limit: float = 1_000_000_000.0,
    base_spread_pct: float = 0.5,
    price_impact_coefficient: float = 0.5,
    volatility_pct: float = 1.5,
    market_dislocation_active: bool = False,
) -> dict[str, Any]:
    """
    Computes bid-ask spread cost, temporary price impact, and permanent price impact for portfolio liquidation.

    Args:
        asset_class: Asset bucket ('liquid', 'semi_liquid', 'illiquid').
        liquidation_amount: Amount to liquidate in INR.
        market_depth_limit: Daily volume capacity / market depth limit in INR.
        base_spread_pct: Half-spread under normal market conditions.
        price_impact_coefficient: Impact multiplier coefficient.
        volatility_pct: Daily asset volatility.
        market_dislocation_active: Flag indicating if market is under SEBI dislocation stress.

    Returns:
        Dictionary containing spread_pct, temporary_impact_pct, permanent_impact_pct, total_cost_pct, total_cost_inr, and execution_shortfall_inr.
    """
    if liquidation_amount <= 0:
        return {
            "asset_class": asset_class,
            "liquidation_amount": 0.0,
            "spread_pct": 0.0,
            "temporary_impact_pct": 0.0,
            "permanent_impact_pct": 0.0,
            "total_cost_pct": 0.0,
            "total_cost_inr": 0.0,
            "execution_shortfall_inr": 0.0,
        }

    # Bid-ask spread doubles under market dislocation
    spread_multiplier = 2.0 if market_dislocation_active else 1.0
    spread_pct = base_spread_pct * spread_multiplier

    # Almgren-Chriss temporary impact: eta * (amount / depth)^0.5
    participation_ratio = min(10.0, liquidation_amount / max(1.0, market_depth_limit))
    temp_impact_pct = price_impact_coefficient * (participation_ratio**0.5)

    # Permanent impact: gamma * (amount / depth) * volatility
    perm_impact_pct = 0.5 * price_impact_coefficient * participation_ratio * (volatility_pct / 100.0)

    total_cost_pct = spread_pct + temp_impact_pct + perm_impact_pct
    total_cost_inr = liquidation_amount * (total_cost_pct / 100.0)
    execution_shortfall_inr = liquidation_amount * ((temp_impact_pct + perm_impact_pct) / 100.0)

    return {
        "asset_class": asset_class,
        "liquidation_amount": liquidation_amount,
        "spread_pct": round(spread_pct, 4),
        "temporary_impact_pct": round(temp_impact_pct, 4),
        "permanent_impact_pct": round(perm_impact_pct, 4),
        "total_cost_pct": round(total_cost_pct, 4),
        "total_cost_inr": round(total_cost_inr, 2),
        "execution_shortfall_inr": round(execution_shortfall_inr, 2),
    }


@tool(
    name="evaluate_cel_compliance_policy",
    description="Evaluates SEBI regulatory guardrails, portfolio exposure limits, and DPDP PII protection rules using Common Expression Language (CEL) policies.",
)
@trace_span(name="tool.evaluate_cel_compliance_policy")
def evaluate_cel_compliance_policy(policy_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluates policy guardrails for swing pricing triggers, portfolio illiquid exposure, or PII masking.

    Args:
        policy_name: Name of the policy ('swing_pricing_triggers', 'portfolio_compliance', 'pii_protection', or 'all').
        payload: Input metrics dictionary containing risk_o_meter, prc_cell, net_outflow_pct, etc.

    Returns:
        Dictionary with compliance boolean, detailed rule evaluations, and CEL source pointers.
    """
    config = get_current_config().model_dump()

    if policy_name == "swing_pricing_triggers":
        ok, _src, details = evaluate_swing_pricing_triggers(payload, config)
        return {
            "policy_name": policy_name,
            "is_compliant": ok,
            "details": details,
            "rules_evaluated": details.get("rules_evaluated", []),
        }
    elif policy_name == "portfolio_compliance":
        ok, _src, details = evaluate_portfolio_compliance(payload, config)
        return {
            "policy_name": policy_name,
            "is_compliant": ok,
            "details": details,
            "rules_evaluated": details.get("rules", []),
        }
    elif policy_name == "pii_protection":
        ok, _src, details = evaluate_pii_protection(payload, config)
        return {
            "policy_name": policy_name,
            "is_compliant": ok,
            "details": details,
            "rules_evaluated": [
                {"rule": "Aadhaar Masked", "passed": details.get("aadhaar_valid", True)},
                {"rule": "PAN Masked", "passed": details.get("pan_valid", True)},
                {"rule": "Name Masked", "passed": details.get("name_valid", True)},
            ],
        }
    else:
        # Evaluate all policies
        s_ok, _, s_det = evaluate_swing_pricing_triggers(payload, config)
        p_ok, _, p_det = evaluate_portfolio_compliance(payload, config)
        pii_ok, _, pii_det = evaluate_pii_protection(payload, config)
        overall = bool(s_ok and p_ok and pii_ok)
        return {
            "policy_name": "all",
            "is_compliant": overall,
            "details": {
                "swing_pricing_triggers": s_det,
                "portfolio_compliance": p_det,
                "pii_protection": pii_det,
            },
            "rules_evaluated": s_det.get("rules_evaluated", []) + p_det.get("rules", []),
        }


@tool(
    name="execute_portfolio_liquidation_step",
    description="Simulates portfolio liquidation across liquid, semi-liquid, and illiquid buckets using PRO_RATA, WATERFALL, or OPTIMIZED strategies, and computes transaction costs and post-liquidation exposure.",
)
@trace_span(name="tool.execute_portfolio_liquidation_step")
def execute_portfolio_liquidation_step(
    aum: float,
    liquid_ratio: float,
    semi_liquid_ratio: float,
    illiquid_ratio: float,
    redemption_amount: float,
    strategy: str = "OPTIMIZED",
    market_dislocation_active: bool = False,
) -> dict[str, Any]:
    """
    Executes a multi-tier liquidation strategy simulation.

    Args:
        aum: Total scheme AUM in INR.
        liquid_ratio: Proportion in liquid assets.
        semi_liquid_ratio: Proportion in semi-liquid assets.
        illiquid_ratio: Proportion in illiquid assets.
        redemption_amount: Outflow liquidation amount in INR.
        strategy: Strategy archetype ('PRO_RATA', 'WATERFALL', 'OPTIMIZED').
        market_dislocation_active: True if market dislocation is active.

    Returns:
        Dictionary with liquidated amounts, transaction costs, and post-trade exposure ratios.
    """
    config = get_current_config().model_dump()
    cost_params = config.get("transaction_cost_parameters", {})

    portfolio_ratios = {
        "liquid_ratio": liquid_ratio,
        "semi_liquid_ratio": semi_liquid_ratio,
        "illiquid_ratio": illiquid_ratio,
    }

    result = simulate_liquidation(
        aum=aum,
        portfolio_ratios=portfolio_ratios,
        redemption_amount=redemption_amount,
        strategy=strategy,
        cost_params=cost_params,
        market_dislocation_active=market_dislocation_active,
    )
    return result


@tool(
    name="query_sebi_swing_pricing_circular",
    description="Retrieves regulatory clauses, statutory thresholds, and PRC matrix swing factor mandates from SEBI Circular SEBI/HO/IMD/IMD-II DOF3/P/CIR/2021/631.",
)
@trace_span(name="tool.query_sebi_swing_pricing_circular")
def query_sebi_swing_pricing_circular(query_topic: str) -> dict[str, Any]:
    """
    Queries SEBI mutual fund swing pricing regulatory circular clauses and thresholds.

    Args:
        query_topic: Topic of inquiry ('prc_matrix', 'exemptions', 'market_dislocation', 'normal_conditions', 'governance', or 'all').

    Returns:
        Dictionary with regulatory clauses, statutory limits, and reference circular citations.
    """
    clauses_db = {
        "prc_matrix": [
            {
                "clause": "Para 4.2 - Potential Risk Class (PRC) Matrix Mandated Swing Factors",
                "content": "During market dislocation, high-risk open-ended debt schemes must apply mandatory full swing pricing based on the PRC matrix: A-III (1.00%), B-II (1.25%), B-III (1.50%), C-I (1.50%), C-II (1.75%), C-III (2.00%). Schemes in low risk cells (A-I, A-II, B-I) are exempt from mandatory full swing pricing.",
            }
        ],
        "exemptions": [
            {
                "clause": "Para 5.1 - Retail Investor Exemption",
                "content": "Redemptions by retail investors up to INR 2 Lakh per scheme per day are statutorily exempt from swing pricing adjustments to protect small retail unit holders.",
            },
            {
                "clause": "Para 5.2 - Category Exemptions",
                "content": "Liquid schemes, Overnight schemes, and Gilt schemes are statutorily exempt from the mandatory swing pricing framework.",
            },
            {
                "clause": "Para 5.3 - Inflow/Subscription Exemption",
                "content": "Subscription inflows during redemption stress are executed at un-swung NAV or separate inflow pricing to prevent dilution.",
            },
        ],
        "market_dislocation": [
            {
                "clause": "Para 3.1 - Market Dislocation Declaration",
                "content": "SEBI determines and declares market dislocation periods based on systemic liquidity triggers, bond spread widening, or macroeconomic dislocation. Full swing pricing is mandatory for all eligible open-ended debt schemes upon SEBI notification.",
            }
        ],
        "normal_conditions": [
            {
                "clause": "Para 6.1 - Partial Swing Pricing in Normal Times",
                "content": "AMCs are empowered to enforce discretionary/partial swing pricing during normal times if net outflows exceed an AMC-defined threshold (default 5% of scheme AUM) to internalize transaction costs.",
            }
        ],
        "governance": [
            {
                "clause": "Para 7.1 - Governance & Board Oversight",
                "content": "AMCs must institute a dedicated Swing Pricing Committee comprising the CEO, CIO, CRO, and Compliance Officer. All swing activations must be promptly notified to AMFI and SEBI, and published on the AMC website.",
            }
        ],
    }

    thresholds = {
        "retail_exemption_limit_inr": 200_000.0,
        "default_partial_swing_threshold_pct": 5.0,
        "statutory_illiquid_limit_pct": 35.0,
        "prc_matrix_swing_factors": {
            "A-III": 1.00,
            "B-II": 1.25,
            "B-III": 1.50,
            "C-I": 1.50,
            "C-II": 1.75,
            "C-III": 2.00,
        },
    }

    if query_topic in clauses_db:
        selected_clauses = clauses_db[query_topic]
    else:
        selected_clauses = [item for sublist in clauses_db.values() for item in sublist]

    return {
        "circular_reference": "SEBI/HO/IMD/IMD-II DOF3/P/CIR/2021/631",
        "circular_date": "September 29, 2021",
        "query_topic": query_topic,
        "clauses": selected_clauses,
        "applicable_thresholds": thresholds,
        "guidelines_summary": "SEBI framework for swing pricing in mutual fund debt schemes to curb first-mover advantages during redemption stress.",
    }


@tool(
    name="request_human_approval_overlimit",
    description="Registers a Human-in-the-Loop (HITL) maker-checker stop ticket and halts automated trade execution when swing factor exceeds 150 bps or net redemption exceeds 15% of AUM.",
)
@trace_span(name="tool.request_human_approval_overlimit")
def request_human_approval_overlimit(
    session_id: str,
    reason: str,
    swing_factor_bps: float,
    redemption_pct: float,
    post_illiquid_ratio: float,
    current_nav: float,
    swung_nav: float,
) -> dict[str, Any]:
    """
    Creates a Human-in-the-Loop stop ticket for board review.

    Args:
        session_id: Active session identifier.
        reason: Explanation of threshold breach.
        swing_factor_bps: Applied swing factor in basis points.
        redemption_pct: Redemption outflow as percentage of AUM.
        post_illiquid_ratio: Projected illiquid asset ratio post-liquidation.
        current_nav: Standard pre-swing NAV.
        swung_nav: Swung NAV after adjustment.

    Returns:
        Dictionary with approval ticket details, status, and required sign-off roles.
    """
    approval_id = f"APPR-{uuid.uuid4().hex[:8].upper()}"
    trigger_metrics = {
        "swing_factor_bps": swing_factor_bps,
        "redemption_pct": redemption_pct,
        "post_illiquid_ratio": post_illiquid_ratio,
        "current_nav": current_nav,
        "swung_nav": swung_nav,
    }

    return {
        "approval_id": approval_id,
        "session_id": session_id,
        "status": "HELD",
        "reason": reason,
        "trigger_metrics": trigger_metrics,
        "required_roles": [
            "Chief Risk Officer (CRO)",
            "Head of Fixed Income",
            "Compliance Officer",
        ],
        "instructions": f"Execution paused. Requires maker-checker adjudication at /api/sessions/{session_id}/approve or /api/approvals/{approval_id}/decision.",
    }
