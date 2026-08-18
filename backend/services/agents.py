"""
Multi-Agent Orchestration Framework for Project 120.
Coordinates TriageRouterAgent, LiquidationOptimizerAgent, ComplianceAuditorAgent,
and MakerCheckerReviewerAgent with non-blocking SQLite persistence, OpenTelemetry
distributed tracing, Intent vs Outcome logging, and Human-In-The-Loop code stops.
"""

import asyncio
import json
import re
import time
import uuid
from typing import Any

from google import genai

from config import get_current_config
from services.cel_engine import (
    evaluate_pii_protection,
    evaluate_portfolio_compliance,
    evaluate_swing_pricing_triggers,
)
from services.database import (
    init_db,
    save_agent_trace,
    save_hitl_approval,
    save_session_turn,
    update_session_state,
)
from services.logger import engine_logger, log_agent_intent, log_agent_outcome
from services.math_engine import calculate_swing_factor, evaluate_nav_impact, simulate_liquidation
from services.router import AgentTaskType, ModelRouter
from services.telemetry import (
    get_current_span_id,
    get_current_trace_id,
    trace_span,
)
from services.tools import calculate_almgren_chriss_market_impact


class PIIRedactor:
    """Utility to redact and mask PII (Aadhaar, PAN, Name) ensuring DPDP 2023 compliance."""

    @staticmethod
    def redact_payload(input_data: dict[str, Any]) -> dict[str, Any]:
        redacted = input_data.copy()

        # Redact Aadhaar: 12-digit number -> XXXXXXXX9012
        aadhaar = redacted.get("investor_aadhaar", "")
        if aadhaar and re.match(r"^[0-9]{12}$", str(aadhaar)):
            redacted["investor_aadhaar"] = f"XXXXXXXX{str(aadhaar)[-4:]}"
        elif aadhaar and not (
            re.match(r"^XXXX-XXXX-[0-9]{4}$", str(aadhaar)) or re.match(r"^XXXXXXXX[0-9]{4}$", str(aadhaar))
        ):
            redacted["investor_aadhaar"] = "XXXXXXXX0000"

        # Redact PAN: e.g., ABCDE1234F -> XXXXX1234F
        pan = redacted.get("investor_pan", "")
        if pan and re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", str(pan)):
            redacted["investor_pan"] = f"XXXXX{str(pan)[5:]}"
        elif pan and not re.match(r"^XXXXX[0-9]{4}[A-Z]$", str(pan)):
            redacted["investor_pan"] = "XXXXX0000X"

        # Redact Name
        name = redacted.get("investor_name", "")
        if name and not (name.startswith("***") or "MASKED" in name):
            redacted["investor_name"] = f"***MASKED_INVESTOR_{name[:2].upper()}***"

        return redacted


class TriageRouterAgent:
    """
    Agent 1: Ingests raw stress scenario, executes DPDP 2023 PII scrubbing,
    evaluates statutory exemptions (retail <= 2L, liquid/overnight funds, subscriptions),
    and sets routing parameters for downstream solver agents.
    """

    @classmethod
    @trace_span(name="agent.TriageRouterAgent")
    def run(cls, payload: dict[str, Any], session_id: str, trace_id: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        config = get_current_config()

        log_agent_intent(
            logger=engine_logger,
            agent_name="TriageRouterAgent",
            intent="Scrub PII, evaluate statutory exemptions, and structure scenario parameters.",
            params={"amount_inr": payload.get("amount_inr"), "transaction_type": payload.get("transaction_type")},
            session_id=session_id,
            trace_id=trace_id,
        )

        # 1. PII Redaction
        if config.pii_masking_enabled:
            redacted_payload = PIIRedactor.redact_payload(payload)
        else:
            redacted_payload = payload.copy()

        # 2. Extract and Normalize Parameters
        aum = float(redacted_payload.get("aum", 1_000_000_000.0))
        initial_nav = float(redacted_payload.get("initial_nav", 10.0))
        net_outflow_pct = float(redacted_payload.get("net_outflow_pct", 0.0))
        amount_inr = float(redacted_payload.get("amount_inr", aum * (net_outflow_pct / 100.0)))
        transaction_type = redacted_payload.get("transaction_type", "redemption")
        scheme_category = redacted_payload.get("scheme_category", "credit_risk")
        risk_o_meter = redacted_payload.get("risk_o_meter", "VERY_HIGH")
        prc_cell = redacted_payload.get("prc_cell", "C-III")

        # Check statutory exemptions
        is_retail_exempt = amount_inr > 0 and amount_inr <= 200_000.0 and transaction_type == "redemption"
        is_scheme_exempt = scheme_category in ["liquid", "overnight", "gilt", "gilt-10yr"]
        is_subscription = transaction_type == "subscription"

        exemption_status = {
            "is_exempt": bool(is_retail_exempt or is_scheme_exempt or is_subscription),
            "retail_exempt": is_retail_exempt,
            "scheme_category_exempt": is_scheme_exempt,
            "subscription_exempt": is_subscription,
        }

        portfolio_exposure = redacted_payload.get("portfolio_exposure", {})
        if not portfolio_exposure:
            portfolio_exposure = {
                "liquid_ratio": config.portfolio_defaults.liquid_ratio,
                "semi_liquid_ratio": config.portfolio_defaults.semi_liquid_ratio,
                "illiquid_ratio": config.portfolio_defaults.illiquid_ratio,
            }

        triage_result = {
            "session_id": session_id,
            "redacted_payload": redacted_payload,
            "aum": aum,
            "initial_nav": initial_nav,
            "net_outflow_pct": net_outflow_pct,
            "redemption_amount_inr": amount_inr,
            "transaction_type": transaction_type,
            "scheme_category": scheme_category,
            "risk_o_meter": risk_o_meter,
            "prc_cell": prc_cell,
            "portfolio_exposure": portfolio_exposure,
            "exemption_status": exemption_status,
            "market_dislocation_active": config.market_dislocation_active,
        }

        lat = (time.perf_counter() - t0) * 1000.0
        log_agent_outcome(
            logger=engine_logger,
            agent_name="TriageRouterAgent",
            status="SUCCESS",
            outcome_summary=f"Triage complete. Exemption active: {exemption_status['is_exempt']}",
            latency_ms=lat,
            session_id=session_id,
            trace_id=trace_id,
        )

        return triage_result


class LiquidationOptimizerAgent:
    """
    Agent 2: Simulates multi-tier asset liquidation pathways (PRO_RATA, WATERFALL, OPTIMIZED),
    calculates Almgren-Chriss market impact, and determines minimum-cost compliant allocations.
    """

    @classmethod
    @trace_span(name="agent.LiquidationOptimizerAgent")
    def run(cls, triage_data: dict[str, Any], session_id: str, trace_id: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        config = get_current_config().model_dump()

        aum = triage_data["aum"]
        portfolio_exposure = triage_data["portfolio_exposure"]
        redemption_amount = triage_data["redemption_amount_inr"]
        cost_params = config["transaction_cost_parameters"]
        market_dislocation_active = triage_data["market_dislocation_active"]

        log_agent_intent(
            logger=engine_logger,
            agent_name="LiquidationOptimizerAgent",
            intent="Simulate liquidation routes and select optimal strategy.",
            params={"aum": aum, "redemption_amount": redemption_amount, "dislocation": market_dislocation_active},
            session_id=session_id,
            trace_id=trace_id,
        )

        strategies = ["PRO_RATA", "WATERFALL", "OPTIMIZED"]
        results = []
        best_strategy = "PRO_RATA"
        min_cost = float("inf")
        best_details = {}

        for strat in strategies:
            details = simulate_liquidation(
                aum=aum,
                portfolio_ratios=portfolio_exposure,
                redemption_amount=redemption_amount,
                strategy=strat,
                cost_params=cost_params,
                market_dislocation_active=market_dislocation_active,
            )

            # Check compliance of post-liquidation exposure
            post_exposure = details["post_liquidation_exposure"]
            compliance_input = {
                "portfolio_exposure": {"illiquid_ratio": post_exposure["illiquid_ratio"]},
                "risk_o_meter": triage_data["risk_o_meter"],
            }
            port_ok, _, _ = evaluate_portfolio_compliance(compliance_input, config)
            details["post_liquidation_compliant"] = port_ok
            results.append(details)

            cost = details["transaction_costs"]["total_inr"]
            if port_ok:
                if cost < min_cost:
                    min_cost = cost
                    best_strategy = strat
                    best_details = details
            else:
                if min_cost == float("inf") or (
                    not best_details.get("post_liquidation_compliant", False) and cost < min_cost
                ):
                    min_cost = cost
                    best_strategy = strat
                    best_details = details

        # Compute granular Almgren-Chriss impact breakdown on optimal route
        liquidated_illiquid = best_details["liquidated_amounts"].get("illiquid", 0.0)
        ac_impact = calculate_almgren_chriss_market_impact(
            asset_class="illiquid",
            liquidation_amount=liquidated_illiquid,
            market_dislocation_active=market_dislocation_active,
        )

        lat = (time.perf_counter() - t0) * 1000.0
        log_agent_outcome(
            logger=engine_logger,
            agent_name="LiquidationOptimizerAgent",
            status="SUCCESS",
            outcome_summary=f"Optimal Strategy: {best_strategy} (Total Cost: INR {best_details['transaction_costs']['total_inr']:,.2f})",
            latency_ms=lat,
            session_id=session_id,
            trace_id=trace_id,
        )

        return {
            "optimal_strategy": best_strategy,
            "optimal_strategy_details": best_details,
            "all_strategies": results,
            "almgren_chriss_impact": ac_impact,
        }


class ComplianceAuditorAgent:
    """
    Agent 3: Evaluates statutory CEL policies (PRC matrix swing pricing, illiquid exposure limits,
    DPDP PII protection) and computes swung NAV protection metrics.
    """

    @classmethod
    @trace_span(name="agent.ComplianceAuditorAgent")
    def run(
        cls,
        triage_data: dict[str, Any],
        optimizer_data: dict[str, Any],
        session_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        config = get_current_config().model_dump()

        log_agent_intent(
            logger=engine_logger,
            agent_name="ComplianceAuditorAgent",
            intent="Evaluate CEL statutory policies and compute swung NAV impact.",
            params={"prc_cell": triage_data["prc_cell"], "risk_o_meter": triage_data["risk_o_meter"]},
            session_id=session_id,
            trace_id=trace_id,
        )

        # 1. Determine swing pricing factor
        swing_factor_pct, swing_reason = calculate_swing_factor(
            input_data={
                "risk_o_meter": triage_data["risk_o_meter"],
                "prc_cell": triage_data["prc_cell"],
                "net_outflow_pct": triage_data["net_outflow_pct"],
                "amount_inr": triage_data["redemption_amount_inr"],
                "transaction_type": triage_data["transaction_type"],
                "scheme_category": triage_data["scheme_category"],
            },
            config_data=config,
        )

        # 2. Evaluate NAV impact
        best_details = optimizer_data["optimal_strategy_details"]
        liquidation_cost_inr = best_details["transaction_costs"]["total_inr"]
        nav_impact = evaluate_nav_impact(
            aum=triage_data["aum"],
            initial_nav=triage_data["initial_nav"],
            redemption_amount=triage_data["redemption_amount_inr"],
            swing_factor_pct=swing_factor_pct,
            liquidation_cost_inr=liquidation_cost_inr,
        )

        # 3. Evaluate CEL Policies
        redacted = triage_data["redacted_payload"]
        compliance_input = {
            "portfolio_exposure": {"illiquid_ratio": best_details["post_liquidation_exposure"]["illiquid_ratio"]},
            "risk_o_meter": triage_data["risk_o_meter"],
            "swing_pricing_active": swing_factor_pct > 0,
            "applied_swing_factor_pct": swing_factor_pct,
            "prc_cell": triage_data["prc_cell"],
            "net_outflow_pct": triage_data["net_outflow_pct"],
            "investor_aadhaar": redacted.get("investor_aadhaar", ""),
            "investor_pan": redacted.get("investor_pan", ""),
            "investor_name": redacted.get("investor_name", ""),
        }

        swing_ok, swing_cel, swing_details = evaluate_swing_pricing_triggers(compliance_input, config)
        port_ok, port_cel, port_details = evaluate_portfolio_compliance(compliance_input, config)
        pii_ok, pii_cel, pii_details = evaluate_pii_protection(compliance_input, config)

        compliance_status = {
            "overall_compliant": bool(swing_ok and port_ok and pii_ok),
            "policies": {
                "swing_pricing_triggers": {"compliant": swing_ok, "cel_source": swing_cel, "details": swing_details},
                "portfolio_compliance": {"compliant": port_ok, "cel_source": port_cel, "details": port_details},
                "pii_protection": {"compliant": pii_ok, "cel_source": pii_cel, "details": pii_details},
            },
        }

        lat = (time.perf_counter() - t0) * 1000.0
        log_agent_outcome(
            logger=engine_logger,
            agent_name="ComplianceAuditorAgent",
            status="SUCCESS",
            outcome_summary=f"Swing Factor: {swing_factor_pct}% | Overall Compliant: {compliance_status['overall_compliant']}",
            latency_ms=lat,
            session_id=session_id,
            trace_id=trace_id,
        )

        return {
            "swing_pricing_triggered": swing_factor_pct > 0.0,
            "applied_swing_factor_pct": swing_factor_pct,
            "swing_reason": swing_reason,
            "nav_impact": nav_impact,
            "compliance_status": compliance_status,
        }


class MakerCheckerReviewerAgent:
    """
    Agent 4: Synthesizes final adjudication, inspects thresholds for Human-In-The-Loop (HITL)
    code stops (>150 bps swing factor, >15% net redemption, or >35% illiquid ratio), and produces
    executive summary and audit ledger entries.
    """

    @classmethod
    @trace_span(name="agent.MakerCheckerReviewerAgent")
    def run(
        cls,
        triage_data: dict[str, Any],
        optimizer_data: dict[str, Any],
        auditor_data: dict[str, Any],
        session_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        config = get_current_config()

        swing_factor_pct = auditor_data["applied_swing_factor_pct"]
        swing_factor_bps = swing_factor_pct * 100.0
        net_outflow_pct = triage_data["net_outflow_pct"]
        post_illiquid_ratio = optimizer_data["optimal_strategy_details"]["post_liquidation_exposure"]["illiquid_ratio"]

        log_agent_intent(
            logger=engine_logger,
            agent_name="MakerCheckerReviewerAgent",
            intent="Perform maker-checker inspection, check HITL code stops, and generate executive report.",
            params={"swing_factor_bps": swing_factor_bps, "net_outflow_pct": net_outflow_pct},
            session_id=session_id,
            trace_id=trace_id,
        )

        # HITL Condition Check
        hitl_triggered = False
        hitl_reasons = []

        if swing_factor_bps > 150.0:
            hitl_triggered = True
            hitl_reasons.append(
                f"Applied swing factor ({swing_factor_bps:.1f} bps) exceeds high-impact threshold of 150 bps."
            )

        if net_outflow_pct > 15.0:
            hitl_triggered = True
            hitl_reasons.append(
                f"Net redemption outflow ({net_outflow_pct:.1f}% AUM) exceeds critical stress threshold of 15.0%."
            )

        if post_illiquid_ratio > 0.35:
            hitl_triggered = True
            hitl_reasons.append(
                f"Post-liquidation illiquid asset exposure ({post_illiquid_ratio * 100:.2f}%) breaches statutory ceiling of 35.0%."
            )

        hitl_ticket = None
        session_status = "ACTIVE"
        if hitl_triggered:
            session_status = "HELD"
            approval_id = f"APPR-{uuid.uuid4().hex[:8].upper()}"
            hitl_ticket = {
                "approval_id": approval_id,
                "session_id": session_id,
                "status": "HELD",
                "reason": " | ".join(hitl_reasons),
                "trigger_metrics": {
                    "swing_factor_bps": swing_factor_bps,
                    "net_outflow_pct": net_outflow_pct,
                    "post_illiquid_ratio": post_illiquid_ratio,
                    "initial_nav": triage_data["initial_nav"],
                    "swung_nav": auditor_data["nav_impact"]["swung_nav"],
                },
                "required_roles": ["Chief Risk Officer (CRO)", "Compliance Officer", "Fund Manager"],
            }

        # Generate Natural Language Synthesis
        explanation = cls._generate_explanation(
            triage_data=triage_data,
            optimizer_data=optimizer_data,
            auditor_data=auditor_data,
            hitl_ticket=hitl_ticket,
            system_mode=config.system_mode,
        )

        lat = (time.perf_counter() - t0) * 1000.0
        log_agent_outcome(
            logger=engine_logger,
            agent_name="MakerCheckerReviewerAgent",
            status="HELD" if hitl_triggered else "SUCCESS",
            outcome_summary=f"Review completed. HITL Status: {session_status}",
            latency_ms=lat,
            session_id=session_id,
            trace_id=trace_id,
        )

        return {
            "session_status": session_status,
            "hitl_triggered": hitl_triggered,
            "hitl_ticket": hitl_ticket,
            "explanation": explanation,
        }

    @classmethod
    def _generate_explanation(
        cls,
        triage_data: dict[str, Any],
        optimizer_data: dict[str, Any],
        auditor_data: dict[str, Any],
        hitl_ticket: dict[str, Any] | None,
        system_mode: str,
    ) -> str:
        summary_payload = {
            "triage": {
                "aum": triage_data["aum"],
                "net_outflow_pct": triage_data["net_outflow_pct"],
                "risk_o_meter": triage_data["risk_o_meter"],
                "prc_cell": triage_data["prc_cell"],
            },
            "optimizer": {
                "optimal_strategy": optimizer_data["optimal_strategy"],
                "transaction_costs": optimizer_data["optimal_strategy_details"]["transaction_costs"],
                "post_illiquid_pct": optimizer_data["optimal_strategy_details"]["post_liquidation_exposure"][
                    "illiquid_ratio"
                ]
                * 100,
            },
            "auditor": {
                "swing_pricing_triggered": auditor_data["swing_pricing_triggered"],
                "applied_swing_factor_pct": auditor_data["applied_swing_factor_pct"],
                "protection_bps": auditor_data["nav_impact"]["protection_bps"],
                "swung_nav": auditor_data["nav_impact"]["swung_nav"],
                "compliance_status": auditor_data["compliance_status"]["overall_compliant"],
            },
            "hitl": hitl_ticket,
        }

        if system_mode == "LIVE_GCP":
            try:
                client = genai.Client()
                model_name = ModelRouter.get_model_for_task(AgentTaskType.SYNTHESIS_EXPLANATION)
                prompt = (
                    "You are the SEBI Compliance & Risk Advisor AI.\n"
                    "Generate a concise, professional compliance executive summary for the AMC Board based on the following stress-test results:\n"
                    f"{json.dumps(summary_payload, indent=2)}\n\n"
                    "Cover: 1. Compliance status, 2. Liquidation strategy & costs, 3. Swing pricing NAV protection, 4. Board recommendations.\n"
                    "Write in an authoritative financial tone under 350 words."
                )
                response = client.models.generate_content(model=model_name, contents=prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                engine_logger.warning(f"GenAI synthesis fallback: {e}")

        # Deterministic Mock Explanation
        strat = optimizer_data["optimal_strategy"]
        costs = optimizer_data["optimal_strategy_details"]["transaction_costs"]
        swing_trig = auditor_data["swing_pricing_triggered"]
        swing_factor = auditor_data["applied_swing_factor_pct"]
        protection_bps = auditor_data["nav_impact"]["protection_bps"]
        swung_nav = auditor_data["nav_impact"]["swung_nav"]
        savings = auditor_data["nav_impact"]["swing_savings_inr"]
        overall_comp = auditor_data["compliance_status"]["overall_compliant"]
        post_illiquid = optimizer_data["optimal_strategy_details"]["post_liquidation_exposure"]["illiquid_ratio"] * 100

        text = "### Executive Summary: SEBI Compliance & Swing Pricing Analysis\n\n"
        text += f"**Overall Status:** {'COMPLIANT' if overall_comp else 'NON-COMPLIANT'}\n\n"

        if hitl_ticket:
            text += f"> ⚠️ **HUMAN APPROVAL REQUIRED (HELD):** {hitl_ticket['reason']}\n\n"

        text += "**1. Compliance Evaluation:**\n"
        if overall_comp:
            text += "The portfolio currently complies with SEBI risk requirements. "
        else:
            text += "The portfolio violates compliance limits. "
            if post_illiquid > 35.0:
                text += f"Specifically, the post-liquidation illiquid asset ratio stands at {post_illiquid:.2f}%, exceeding the statutory limit of 35%."

        text += "\n\n**2. Liquidation Strategy & Costs:**\n"
        text += (
            f"The system analyzed multiple liquidation routes. **{strat}** was determined to be the optimal strategy. "
        )
        text += f"The total transaction cost incurred under this strategy is INR {costs.get('total_inr', 0):,.2f} ({costs.get('total_pct', 0.0):.4f}% of liquidated amount). "

        text += "\n\n**3. Swing Pricing and NAV Impact:**\n"
        if swing_trig:
            text += f"Swing pricing was successfully triggered at a rate of **{swing_factor:.2f}%**. "
            text += f"This adjustment provided **{protection_bps:.2f} basis points** of NAV protection for the remaining unit holders. "
            text += f"By charging the redeeming investors the swung NAV (INR {swung_nav:.4f}), the fund generated an overlay savings of INR {savings:,.2f}."
        else:
            text += "Swing pricing was not triggered as redemption flows did not exceed thresholds and market dislocation was inactive."

        text += "\n\n**4. Board Recommendations:**\n"
        text += "- Maintain high liquid buffers (G-Secs/T-Bills) to buffer against redemption stress.\n"
        text += "- Since illiquid assets currently represent a significant risk, reduce high-yield lower-rated corporate debt holdings if they approach the 35% threshold."

        return text


class Orchestrator:
    """
    Main Multi-Agent Orchestrator connecting:
    TriageRouterAgent -> LiquidationOptimizerAgent -> ComplianceAuditorAgent -> MakerCheckerReviewerAgent.
    Handles non-blocking SQLite persistence, memory compaction, OpenTelemetry tracing, and JSON logging.
    """

    @classmethod
    def run_simulation(cls, input_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Synchronous simulation runner (wraps async pipeline for compatibility).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In an already running loop, execute synchronously or create a nested task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, cls.run_simulation_async(input_payload)).result()
            return loop.run_until_complete(cls.run_simulation_async(input_payload))
        except RuntimeError:
            return asyncio.run(cls.run_simulation_async(input_payload))

    @classmethod
    @trace_span(name="orchestrator.run_simulation_async")
    async def run_simulation_async(cls, input_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Asynchronous multi-agent execution pipeline.
        """
        t0 = time.perf_counter()
        session_id = input_payload.get("session_id") or f"sess-{uuid.uuid4().hex[:8]}"
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()

        # Initialize SQLite database if needed
        await init_db()

        log_agent_intent(
            logger=engine_logger,
            agent_name="MultiAgentOrchestrator",
            intent="Initiate full multi-agent stress simulation pipeline.",
            params={"session_id": session_id, "trace_id": trace_id},
            session_id=session_id,
            trace_id=trace_id,
        )

        # 1. TriageRouterAgent
        triage_data = TriageRouterAgent.run(input_payload, session_id=session_id, trace_id=trace_id)
        await save_agent_trace(
            session_id=session_id,
            trace_data={
                "trace_id": trace_id,
                "span_id": span_id,
                "agent_name": "TriageRouterAgent",
                "intent": "Scrub PII and triage stress parameters",
                "outcome": "SUCCESS",
                "latency_ms": 1.5,
                "status": "SUCCESS",
                "details": {"exemption_active": triage_data["exemption_status"]["is_exempt"]},
            },
        )

        # 2. LiquidationOptimizerAgent
        optimizer_data = LiquidationOptimizerAgent.run(triage_data, session_id=session_id, trace_id=trace_id)
        await save_agent_trace(
            session_id=session_id,
            trace_data={
                "trace_id": trace_id,
                "span_id": span_id,
                "agent_name": "LiquidationOptimizerAgent",
                "intent": "Optimize liquidation routes",
                "outcome": f"Selected {optimizer_data['optimal_strategy']}",
                "latency_ms": 2.0,
                "status": "SUCCESS",
                "details": {"optimal_strategy": optimizer_data["optimal_strategy"]},
            },
        )

        # 3. ComplianceAuditorAgent
        auditor_data = ComplianceAuditorAgent.run(triage_data, optimizer_data, session_id=session_id, trace_id=trace_id)
        await save_agent_trace(
            session_id=session_id,
            trace_data={
                "trace_id": trace_id,
                "span_id": span_id,
                "agent_name": "ComplianceAuditorAgent",
                "intent": "Evaluate CEL policies and swung NAV",
                "outcome": f"Swing Factor: {auditor_data['applied_swing_factor_pct']}%",
                "latency_ms": 1.8,
                "status": "SUCCESS",
                "details": {"swing_factor": auditor_data["applied_swing_factor_pct"]},
            },
        )

        # 4. MakerCheckerReviewerAgent
        reviewer_data = MakerCheckerReviewerAgent.run(
            triage_data=triage_data,
            optimizer_data=optimizer_data,
            auditor_data=auditor_data,
            session_id=session_id,
            trace_id=trace_id,
        )
        await save_agent_trace(
            session_id=session_id,
            trace_data={
                "trace_id": trace_id,
                "span_id": span_id,
                "agent_name": "MakerCheckerReviewerAgent",
                "intent": "Review decisions and check HITL stops",
                "outcome": f"Session Status: {reviewer_data['session_status']}",
                "latency_ms": 2.5,
                "status": reviewer_data["session_status"],
                "details": {"hitl_triggered": reviewer_data["hitl_triggered"]},
            },
        )

        # Save HITL ticket if triggered
        if reviewer_data["hitl_ticket"]:
            ticket = reviewer_data["hitl_ticket"]
            await save_hitl_approval(
                approval_id=ticket["approval_id"],
                session_id=session_id,
                status="HELD",
                payload=ticket["trigger_metrics"],
                reason=ticket["reason"],
            )

        # Assemble Final Response
        result = {
            "session_id": session_id,
            "session_status": reviewer_data["session_status"],
            "hitl_triggered": reviewer_data["hitl_triggered"],
            "hitl_ticket": reviewer_data["hitl_ticket"],
            "initial_aum": triage_data["aum"],
            "initial_nav": triage_data["initial_nav"],
            "net_outflow_pct": triage_data["net_outflow_pct"],
            "redemption_amount_inr": triage_data["redemption_amount_inr"],
            "risk_o_meter": triage_data["risk_o_meter"],
            "prc_cell": triage_data["prc_cell"],
            "swing_pricing_triggered": auditor_data["swing_pricing_triggered"],
            "applied_swing_factor_pct": auditor_data["applied_swing_factor_pct"],
            "swing_reason": auditor_data["swing_reason"],
            "optimal_strategy": optimizer_data["optimal_strategy"],
            "optimal_strategy_details": optimizer_data["optimal_strategy_details"],
            "all_strategies": optimizer_data["all_strategies"],
            "nav_impact": auditor_data["nav_impact"],
            "compliance_status": auditor_data["compliance_status"],
            "redacted_input_payload": triage_data["redacted_payload"],
            "explanation": reviewer_data["explanation"],
            "trace_id": trace_id,
        }

        # Persist session state and conversational turns to SQLite
        await update_session_state(
            session_id=session_id,
            state_update=result,
            status=reviewer_data["session_status"],
            summary=f"Optimal Strategy: {optimizer_data['optimal_strategy']}, Swing: {auditor_data['applied_swing_factor_pct']}%",
        )

        # Save turn to message history
        await save_session_turn(
            session_id=session_id,
            role="user",
            content=f"Simulate stress scenario: outflow={triage_data['net_outflow_pct']}%, prc={triage_data['prc_cell']}",
            metadata={"type": "simulation_request"},
        )
        await save_session_turn(
            session_id=session_id,
            role="assistant",
            content=reviewer_data["explanation"],
            metadata={
                "compliance_status": "COMPLIANT"
                if auditor_data["compliance_status"]["overall_compliant"]
                else "NON-COMPLIANT",
                "optimal_strategy": optimizer_data["optimal_strategy"],
                "applied_swing_factor_pct": auditor_data["applied_swing_factor_pct"],
            },
        )

        total_lat = (time.perf_counter() - t0) * 1000.0
        log_agent_outcome(
            logger=engine_logger,
            agent_name="MultiAgentOrchestrator",
            status=reviewer_data["session_status"],
            outcome_summary=f"Completed full multi-agent simulation in {total_lat:.2f}ms.",
            latency_ms=total_lat,
            session_id=session_id,
            trace_id=trace_id,
        )

        return result


class LiquidationOptimizer:
    """Backwards-compatible helper wrapping LiquidationOptimizerAgent."""

    @staticmethod
    def optimize(
        aum: float,
        portfolio_ratios: dict[str, float],
        redemption_amount: float,
        cost_params: dict[str, Any],
        market_dislocation_active: bool,
        config_data: dict[str, Any],
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        triage_data = {
            "aum": aum,
            "portfolio_exposure": portfolio_ratios,
            "redemption_amount_inr": redemption_amount,
            "market_dislocation_active": market_dislocation_active,
            "risk_o_meter": "VERY_HIGH",
        }
        res = LiquidationOptimizerAgent.run(triage_data, session_id="compat", trace_id="compat-trc")
        return res["optimal_strategy"], res["optimal_strategy_details"], res["all_strategies"]


class MarketImpactSimulator:
    """Backwards-compatible helper wrapping evaluate_nav_impact."""

    @staticmethod
    def simulate(
        aum: float,
        initial_nav: float,
        redemption_amount: float,
        swing_factor_pct: float,
        liquidation_cost_inr: float,
    ) -> dict[str, Any]:
        return evaluate_nav_impact(
            aum=aum,
            initial_nav=initial_nav,
            redemption_amount=redemption_amount,
            swing_factor_pct=swing_factor_pct,
            liquidation_cost_inr=liquidation_cost_inr,
        )


class ComplianceEvaluator:
    """Backwards-compatible helper wrapping evaluate_all."""

    @staticmethod
    def evaluate_all(input_data: dict[str, Any], config_data: dict[str, Any]) -> dict[str, Any]:
        swing_ok, swing_cel, swing_details = evaluate_swing_pricing_triggers(input_data, config_data)
        port_ok, port_cel, port_details = evaluate_portfolio_compliance(input_data, config_data)
        pii_ok, pii_cel, pii_details = evaluate_pii_protection(input_data, config_data)

        return {
            "overall_compliant": bool(swing_ok and port_ok and pii_ok),
            "policies": {
                "swing_pricing_triggers": {"compliant": swing_ok, "cel_source": swing_cel, "details": swing_details},
                "portfolio_compliance": {"compliant": port_ok, "cel_source": port_cel, "details": port_details},
                "pii_protection": {"compliant": pii_ok, "cel_source": pii_cel, "details": pii_details},
            },
        }
