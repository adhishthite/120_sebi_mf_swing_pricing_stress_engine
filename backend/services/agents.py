import json
import re
from typing import Any

from google import genai

from config import get_current_config
from services.cel_engine import evaluate_pii_protection, evaluate_portfolio_compliance, evaluate_swing_pricing_triggers
from services.math_engine import calculate_swing_factor, evaluate_nav_impact, simulate_liquidation


class PIIRedactor:
    """Utility to redact and mask PII (Aadhaar, PAN, Name) to ensure compliance."""

    @staticmethod
    def redact_payload(input_data: dict[str, Any]) -> dict[str, Any]:
        redacted = input_data.copy()

        # Redact Aadhaar: e.g., 123456789012 -> XXXXXXXX9012
        aadhaar = redacted.get("investor_aadhaar", "")
        if aadhaar and re.match(r"^[0-9]{12}$", str(aadhaar)):
            redacted["investor_aadhaar"] = f"XXXXXXXX{str(aadhaar)[-4:]}"
        elif aadhaar and not (
            re.match(r"^XXXX-XXXX-[0-9]{4}$", str(aadhaar)) or re.match(r"^XXXXXXXX[0-9]{4}$", str(aadhaar))
        ):
            redacted["investor_aadhaar"] = "XXXXXXXX0000"  # Default fallback mask

        # Redact PAN: e.g., ABCDE1234F -> XXXXX1234F
        pan = redacted.get("investor_pan", "")
        if pan and re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", str(pan)):
            redacted["investor_pan"] = f"XXXXX{str(pan)[5:]}"
        elif pan and not re.match(r"^XXXXX[0-9]{4}[A-Z]$", str(pan)):
            redacted["investor_pan"] = "XXXXX0000X"  # Default fallback mask

        # Redact Name
        name = redacted.get("investor_name", "")
        if name and not (name.startswith("***") or "MASKED" in name):
            redacted["investor_name"] = f"***MASKED_INVESTOR_{name[:2].upper()}***"

        return redacted


class ComplianceEvaluator:
    """Evaluates policies against CEL engine."""

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


class LiquidationOptimizer:
    """Compares different liquidation strategies and selects the optimal one."""

    @staticmethod
    def optimize(
        aum: float,
        portfolio_ratios: dict[str, float],
        redemption_amount: float,
        cost_params: dict[str, Any],
        market_dislocation_active: bool,
        config_data: dict[str, Any],
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        strategies = ["PRO_RATA", "WATERFALL", "OPTIMIZED"]
        results = []

        best_strategy = "PRO_RATA"
        min_cost = float("inf")
        best_details = {}

        for strat in strategies:
            details = simulate_liquidation(
                aum=aum,
                portfolio_ratios=portfolio_ratios,
                redemption_amount=redemption_amount,
                strategy=strat,
                cost_params=cost_params,
                market_dislocation_active=market_dislocation_active,
            )

            # Check compliance of post-liquidation exposure
            post_exposure = details["post_liquidation_exposure"]
            compliance_input = {
                "portfolio_exposure": {"illiquid_ratio": post_exposure["illiquid_ratio"]},
                "risk_o_meter": "VERY_HIGH",  # Pessimistic/default check
            }
            port_ok, _, _ = evaluate_portfolio_compliance(compliance_input, config_data)

            details["post_liquidation_compliant"] = port_ok
            results.append(details)

            cost = details["transaction_costs"]["total_inr"]

            # Selection criteria: must be compliant if possible, and have the lowest cost.
            # If a strategy is compliant, it is strongly preferred over non-compliant.
            if port_ok:
                if cost < min_cost:
                    min_cost = cost
                    best_strategy = strat
                    best_details = details
            else:
                # If no compliant strategy found yet, or this is cheaper but also non-compliant,
                # keep track of it but prioritize compliant ones.
                if min_cost == float("inf") or (
                    not best_details.get("post_liquidation_compliant", False) and cost < min_cost
                ):
                    min_cost = cost
                    best_strategy = strat
                    best_details = details

        return best_strategy, best_details, results


class MarketImpactSimulator:
    """Evaluates the market price impact and NAV drag."""

    @staticmethod
    def simulate(
        aum: float, initial_nav: float, redemption_amount: float, swing_factor_pct: float, liquidation_cost_inr: float
    ) -> dict[str, Any]:
        return evaluate_nav_impact(
            aum=aum,
            initial_nav=initial_nav,
            redemption_amount=redemption_amount,
            swing_factor_pct=swing_factor_pct,
            liquidation_cost_inr=liquidation_cost_inr,
        )


class GeminiSynthesizer:
    """Generates natural language explanations using the Google GenAI SDK or local mock fallback."""

    @staticmethod
    def synthesize(quantitative_summary: dict[str, Any], system_mode: str) -> str:
        prompt = f"""
        You are the SEBI Compliance & Risk Advisor AI.
        Generate a professional compliance executive summary based on the following stress-test results:
        
        {json.dumps(quantitative_summary, indent=2)}
        
        Please cover the following in your response:
        1. Whether the scheme complies with portfolio risk and swing pricing policies.
        2. Analyze the math: Explain how the liquidation strategy (e.g. PRO_RATA vs WATERFALL vs OPTIMIZED) affected transaction costs and compliance.
        3. Explain the NAV protection in basis points achieved by applying swing pricing.
        4. Give clear recommendations to the AMC Board on portfolio rebalancing or risk mitigation.
        
        Write in a concise, authoritative financial tone. Keep the explanation under 350 words.
        """

        if system_mode == "LIVE_GCP":
            try:
                # Initialize Google GenAI client
                # Standard env variables GEMINI_API_KEY or GCP credentials will configure this client
                client = genai.Client()
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                # Fallback to Mock explanation if API call fails
                return (
                    f"[API Fallback] Gemini API Error ({type(e).__name__}): {e}\n\n"
                    + GeminiSynthesizer._mock_explanation(quantitative_summary)
                )

        return GeminiSynthesizer._mock_explanation(quantitative_summary)

    @staticmethod
    def _mock_explanation(summary: dict[str, Any]) -> str:
        best_strat = summary.get("optimal_strategy", "PRO_RATA")
        swing_triggered = summary.get("swing_pricing_triggered", False)
        swing_factor = summary.get("applied_swing_factor_pct", 0.0)
        nav_impact = summary.get("nav_impact", {})
        protection_bps = nav_impact.get("protection_bps", 0.0)
        overall_compliant = summary.get("compliance_status", {}).get("overall_compliant", False)
        post_illiquid = (
            summary.get("optimal_strategy_details", {}).get("post_liquidation_exposure", {}).get("illiquid_ratio", 0.0)
            * 100
        )

        compliance_status_str = "COMPLIANT" if overall_compliant else "NON-COMPLIANT"

        text = "### Executive Summary: SEBI Compliance & Swing Pricing Analysis\n\n"
        text += f"**Overall Status:** {compliance_status_str}\n\n"
        text += "**1. Compliance Evaluation:**\n"
        if overall_compliant:
            text += "The portfolio currently complies with SEBI risk requirements. "
        else:
            text += "The portfolio violates compliance limits. "
            if post_illiquid > 35.0:
                text += f"Specifically, the post-liquidation illiquid asset ratio stands at {post_illiquid:.2f}%, exceeding the statutory limit of 35%."

        text += "\n\n**2. Liquidation Strategy & Costs:**\n"
        text += f"The system analyzed multiple liquidation routes. **{best_strat}** was determined to be the optimal strategy. "
        costs = summary.get("optimal_strategy_details", {}).get("transaction_costs", {})
        text += f"The total transaction cost incurred under this strategy is INR {costs.get('total_inr', 0):,.2f} ({costs.get('total_pct', 0.0):.4f}% of liquidated amount). "

        text += "\n\n**3. Swing Pricing and NAV Impact:**\n"
        if swing_triggered:
            text += f"Swing pricing was successfully triggered at a rate of **{swing_factor:.2f}%**. "
            text += f"This adjustment provided **{protection_bps:.2f} basis points** of NAV protection for the remaining unit holders. "
            text += f"By charging the redeeming investors the swung NAV (INR {nav_impact.get('swung_nav', 10.0):.4f}), the fund generated an overlay savings of INR {nav_impact.get('swing_savings_inr', 0):,.2f}."
        else:
            text += "Swing pricing was not triggered as redemption flows did not exceed thresholds and market dislocation was inactive."

        text += "\n\n**4. Board Recommendations:**\n"
        text += "- Maintain high liquid buffers (G-Secs/T-Bills) to buffer against redemption stress.\n"
        text += "- Since illiquid assets currently represent a significant risk, reduce high-yield lower-rated corporate debt holdings if they approach the 35% threshold."

        return text


class Orchestrator:
    """Main Orchestrator managing the feedback loop."""

    @staticmethod
    def run_simulation(input_payload: dict[str, Any]) -> dict[str, Any]:
        config = get_current_config()
        config_dict = config.model_dump()

        # 1. Mask PII if enabled
        if config.pii_masking_enabled:
            processed_input = PIIRedactor.redact_payload(input_payload)
        else:
            processed_input = input_payload.copy()

        # Extract stress parameters
        aum = processed_input.get("aum", 1000000000.0)  # 1 Billion INR default
        initial_nav = processed_input.get("initial_nav", 10.0)
        net_outflow_pct = processed_input.get("net_outflow_pct", 0.0)
        redemption_amount = aum * (net_outflow_pct / 100.0)

        portfolio_exposure = processed_input.get("portfolio_exposure", {})
        if not portfolio_exposure:
            portfolio_exposure = {
                "liquid_ratio": config.portfolio_defaults.liquid_ratio,
                "semi_liquid_ratio": config.portfolio_defaults.semi_liquid_ratio,
                "illiquid_ratio": config.portfolio_defaults.illiquid_ratio,
            }

        risk_o_meter = processed_input.get("risk_o_meter", "VERY_HIGH")
        prc_cell = processed_input.get("prc_cell", "C-III")

        # 2. Determine swing pricing factor
        swing_factor_pct, swing_reason = calculate_swing_factor(
            input_data={"risk_o_meter": risk_o_meter, "prc_cell": prc_cell, "net_outflow_pct": net_outflow_pct},
            config_data=config_dict,
        )

        # 3. Optimize liquidation
        best_strategy, best_details, all_strategies = LiquidationOptimizer.optimize(
            aum=aum,
            portfolio_ratios=portfolio_exposure,
            redemption_amount=redemption_amount,
            cost_params=config_dict["transaction_cost_parameters"],
            market_dislocation_active=config.market_dislocation_active,
            config_data=config_dict,
        )

        # 4. Market impact simulation on the optimal strategy
        liquidation_cost_inr = best_details["transaction_costs"]["total_inr"]
        nav_impact = MarketImpactSimulator.simulate(
            aum=aum,
            initial_nav=initial_nav,
            redemption_amount=redemption_amount,
            swing_factor_pct=swing_factor_pct,
            liquidation_cost_inr=liquidation_cost_inr,
        )

        # 5. Evaluate compliance on final state
        compliance_input = {
            "portfolio_exposure": {"illiquid_ratio": best_details["post_liquidation_exposure"]["illiquid_ratio"]},
            "risk_o_meter": risk_o_meter,
            "swing_pricing_active": swing_factor_pct > 0,
            "applied_swing_factor_pct": swing_factor_pct,
            "prc_cell": prc_cell,
            "net_outflow_pct": net_outflow_pct,
            "investor_aadhaar": processed_input.get("investor_aadhaar", ""),
            "investor_pan": processed_input.get("investor_pan", ""),
            "investor_name": processed_input.get("investor_name", ""),
        }

        compliance_status = ComplianceEvaluator.evaluate_all(compliance_input, config_dict)

        # Assemble quantitative results
        result = {
            "initial_aum": aum,
            "initial_nav": initial_nav,
            "net_outflow_pct": net_outflow_pct,
            "redemption_amount_inr": redemption_amount,
            "risk_o_meter": risk_o_meter,
            "prc_cell": prc_cell,
            "swing_pricing_triggered": swing_factor_pct > 0.0,
            "applied_swing_factor_pct": swing_factor_pct,
            "swing_reason": swing_reason,
            "optimal_strategy": best_strategy,
            "optimal_strategy_details": best_details,
            "all_strategies": all_strategies,
            "nav_impact": nav_impact,
            "compliance_status": compliance_status,
            "redacted_input_payload": processed_input,
        }

        # 6. Generate natural language explanation
        explanation = GeminiSynthesizer.synthesize(result, config.system_mode)
        result["explanation"] = explanation

        return result
