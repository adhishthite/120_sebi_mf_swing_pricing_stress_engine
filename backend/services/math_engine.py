def calculate_transaction_cost(
    asset_class: str, amount: float, cost_params: dict, market_dislocation_active: bool
) -> tuple[float, float]:
    """
    Computes bid-ask spread and price impact for an asset class liquidation.
    - Stressed Spread = base_spread_pct * (2.0 if market_dislocation_active else 1.0)
    - Power-law Price Impact = price_impact_coefficient * (amount / market_depth_limit) ** 0.5
    Returns (cost_inr, cost_pct).
    """
    if amount <= 0:
        return 0.0, 0.0

    params = cost_params.get(f"{asset_class}_asset")
    if not params:
        # Fallback default parameters if not found
        params = {"base_spread_pct": 0.5, "price_impact_coefficient": 0.5, "market_depth_limit_inr": 1000000000.0}

    base_spread = params["base_spread_pct"]
    price_impact_coef = params["price_impact_coefficient"]
    depth_limit = params["market_depth_limit_inr"]

    # Bid-ask spread widening under stress
    spread_multiplier = 2.0 if market_dislocation_active else 1.0
    spread_pct = base_spread * spread_multiplier

    # Power-law price impact (Kyle's lambda style square-root law)
    ratio = amount / depth_limit
    impact_pct = price_impact_coef * (ratio**0.5)

    total_cost_pct = spread_pct + impact_pct
    total_cost_inr = amount * (total_cost_pct / 100.0)

    return total_cost_inr, total_cost_pct


def simulate_liquidation(
    aum: float,
    portfolio_ratios: dict[str, float],
    redemption_amount: float,
    strategy: str,
    cost_params: dict,
    market_dislocation_active: bool,
) -> dict:
    """
    Simulates asset liquidation under a chosen strategy:
    - PRO_RATA: Liquidate proportional to current asset holdings.
    - WATERFALL: Liquidate liquid first, then semi-liquid, then illiquid.
    - OPTIMIZED: (Placeholder/simplistic rule for compliance-preservation)

    Returns details on amount liquidated per asset, cost incurred, and post-liquidation exposure.
    """
    liquid_ratio = portfolio_ratios.get("liquid_ratio", 0.4)
    semi_liquid_ratio = portfolio_ratios.get("semi_liquid_ratio", 0.35)
    illiquid_ratio = portfolio_ratios.get("illiquid_ratio", 0.25)

    liquid_holding = aum * liquid_ratio
    semi_liquid_holding = aum * semi_liquid_ratio
    illiquid_holding = aum * illiquid_ratio

    liquidated_liquid = 0.0
    liquidated_semi = 0.0
    liquidated_illiquid = 0.0

    rem_to_liquidate = redemption_amount

    if strategy == "PRO_RATA":
        # Pro-rata liquidation
        if aum > 0:
            liquidated_liquid = min(liquid_holding, rem_to_liquidate * liquid_ratio)
            liquidated_semi = min(semi_liquid_holding, rem_to_liquidate * semi_liquid_ratio)
            liquidated_illiquid = min(illiquid_holding, rem_to_liquidate * illiquid_ratio)

    elif strategy == "WATERFALL":
        # Waterfall liquidation: Liquid -> Semi-liquid -> Illiquid
        liquidated_liquid = min(liquid_holding, rem_to_liquidate)
        rem_to_liquidate -= liquidated_liquid

        if rem_to_liquidate > 0:
            liquidated_semi = min(semi_liquid_holding, rem_to_liquidate)
            rem_to_liquidate -= liquidated_semi

        if rem_to_liquidate > 0:
            liquidated_illiquid = min(illiquid_holding, rem_to_liquidate)
            rem_to_liquidate -= liquidated_illiquid

    elif strategy == "OPTIMIZED":
        # Simple optimizer: raise cash while trying to keep illiquid ratio <= 30%.
        # If we do pro-rata, illiquid ratio stays constant.
        # To reduce illiquid ratio, we liquidate more illiquid.
        # But illiquid has high liquidation cost.
        # Let's write a simple rule-based approach:
        # Liquidate semi-liquid first, then liquid, keeping illiquid untouched unless necessary,
        # OR if illiquid exceeds 30%, we prioritize liquidating illiquid first to restore compliance.
        # Let's calculate target illiquid ratio:
        remaining_aum_estimate = aum - redemption_amount
        target_max_illiquid = remaining_aum_estimate * 0.30

        if illiquid_holding > target_max_illiquid and remaining_aum_estimate > 0:
            # We must liquidate illiquid to bring it down to 30% of remaining AUM
            excess_illiquid = illiquid_holding - target_max_illiquid
            liquidated_illiquid = min(illiquid_holding, excess_illiquid, rem_to_liquidate)
            rem_to_liquidate -= liquidated_illiquid

        # The rest is done waterfall style: liquid first, then semi-liquid, then any remaining illiquid.
        if rem_to_liquidate > 0:
            liquidated_liquid = min(liquid_holding, rem_to_liquidate)
            rem_to_liquidate -= liquidated_liquid

        if rem_to_liquidate > 0:
            liquidated_semi = min(semi_liquid_holding, rem_to_liquidate)
            rem_to_liquidate -= liquidated_semi

        if rem_to_liquidate > 0:
            liquidated_illiquid += min(illiquid_holding - liquidated_illiquid, rem_to_liquidate)
            rem_to_liquidate -= liquidated_illiquid
    else:
        # Default pro-rata
        if aum > 0:
            liquidated_liquid = min(liquid_holding, rem_to_liquidate * liquid_ratio)
            liquidated_semi = min(semi_liquid_holding, rem_to_liquidate * semi_liquid_ratio)
            liquidated_illiquid = min(illiquid_holding, rem_to_liquidate * illiquid_ratio)

    # Compute transaction costs
    cost_liq_inr, cost_liq_pct = calculate_transaction_cost(
        "liquid", liquidated_liquid, cost_params, market_dislocation_active
    )
    cost_semi_inr, cost_semi_pct = calculate_transaction_cost(
        "semi_liquid", liquidated_semi, cost_params, market_dislocation_active
    )
    cost_ill_inr, cost_ill_pct = calculate_transaction_cost(
        "illiquid", liquidated_illiquid, cost_params, market_dislocation_active
    )

    total_cost_inr = cost_liq_inr + cost_semi_inr + cost_ill_inr
    total_liquidated = liquidated_liquid + liquidated_semi + liquidated_illiquid

    # Post-liquidation portfolio exposure
    post_liquid_holding = max(0.0, liquid_holding - liquidated_liquid)
    post_semi_holding = max(0.0, semi_liquid_holding - liquidated_semi)
    post_illiquid_holding = max(0.0, illiquid_holding - liquidated_illiquid)
    post_aum = post_liquid_holding + post_semi_holding + post_illiquid_holding

    if post_aum > 0:
        post_liquid_ratio = post_liquid_holding / post_aum
        post_semi_ratio = post_semi_holding / post_aum
        post_illiquid_ratio = post_illiquid_holding / post_aum
    else:
        post_liquid_ratio = 0.0
        post_semi_ratio = 0.0
        post_illiquid_ratio = 0.0

    return {
        "strategy": strategy,
        "liquidated_amounts": {
            "liquid": liquidated_liquid,
            "semi_liquid": liquidated_semi,
            "illiquid": liquidated_illiquid,
            "total": total_liquidated,
        },
        "transaction_costs": {
            "liquid": {"inr": cost_liq_inr, "pct": cost_liq_pct},
            "semi_liquid": {"inr": cost_semi_inr, "pct": cost_semi_pct},
            "illiquid": {"inr": cost_ill_inr, "pct": cost_ill_pct},
            "total_inr": total_cost_inr,
            "total_pct": (total_cost_inr / total_liquidated * 100.0) if total_liquidated > 0 else 0.0,
        },
        "post_liquidation_exposure": {
            "liquid_ratio": post_liquid_ratio,
            "semi_liquid_ratio": post_semi_ratio,
            "illiquid_ratio": post_illiquid_ratio,
            "aum": post_aum,
        },
    }


def calculate_swing_factor(input_data: dict, config_data: dict) -> tuple[float, str]:
    """
    Looks up and calculates the applicable swing factor percent.
    - Market Dislocation: uses the PRC matrix swing factor for high-risk schemes.
    - Normal Times: uses partial swing trigger if outflow exceeds threshold.
    Returns (swing_factor_pct, trigger_reason).
    """
    transaction_type = input_data.get("transaction_type", "redemption")
    amount_inr = input_data.get("amount_inr", 0.0)
    scheme_category = input_data.get("scheme_category", "credit_risk")

    # Statutory exemptions
    if transaction_type == "subscription":
        return 0.0, "Subscriptions are not subject to swing pricing adjustments."

    if amount_inr > 0 and amount_inr <= 200_000.0:
        return 0.0, "Retail transaction <= INR 2 Lakh is statutorily exempt from swing pricing."

    if scheme_category in ["liquid", "overnight", "gilt", "gilt-10yr"]:
        return 0.0, f"Scheme category '{scheme_category}' is statutorily exempt from swing pricing framework."

    market_dislocation_active = config_data.get("market_dislocation_active", False)
    risk_o_meter = input_data.get("risk_o_meter", "LOW")
    prc_cell = input_data.get("prc_cell", "")
    net_outflow_pct = input_data.get("net_outflow_pct", 0.0)

    # Configs
    prc_matrix = config_data.get("prc_matrix_swing_factors", {})
    partial_swing_threshold_pct = config_data.get("partial_swing_threshold_pct", 5.0)

    # Clean PRC key for lookup (support both B-III and B_III)
    prc_key = prc_cell.replace("-", "_") if prc_cell else ""
    
    # High risk cells defined by SEBI: A-III, B-II, B-III, C-I, C-II, C-III
    high_risk_cells = ["A_III", "A-III", "B_II", "B-II", "B_III", "B-III", "C_I", "C-I", "C_II", "C-II", "C_III", "C-III"]
    is_high_risk = (risk_o_meter in ["HIGH", "VERY_HIGH"]) or (prc_cell in high_risk_cells)

    if market_dislocation_active and is_high_risk:
        # Mandatory full swing
        swing_factor = prc_matrix.get(prc_key, prc_matrix.get(prc_cell, 1.00))
        return (
            float(swing_factor),
            f"SEBI mandated full swing pricing triggered due to market dislocation for cell {prc_cell} ({risk_o_meter} risk scheme).",
        )

    if not market_dislocation_active and net_outflow_pct >= partial_swing_threshold_pct:
        # Partial swing trigger
        return (
            0.5,
            f"Partial swing pricing triggered: net outflow {net_outflow_pct}% meets or exceeds trigger threshold of {partial_swing_threshold_pct}%.",
        )

    return 0.0, "Swing pricing not triggered under current conditions."


def evaluate_nav_impact(
    aum: float, initial_nav: float, redemption_amount: float, swing_factor_pct: float, liquidation_cost_inr: float
) -> dict:
    """
    Computes units, NAV changes, and swing pricing overlay savings.
    """
    initial_units = aum / initial_nav if initial_nav > 0 else 0.0
    redemption_units = redemption_amount / initial_nav if initial_nav > 0 else 0.0
    remaining_units = max(0.0, initial_units - redemption_units)

    # Swung NAV at which redeeming investors are paid out
    swung_nav = initial_nav * (1.0 - swing_factor_pct / 100.0)
    actual_cash_paid_out = redemption_units * swung_nav

    # Swing savings kept in the fund to offset liquidation costs
    swing_savings_inr = redemption_amount - actual_cash_paid_out

    # Value of remaining assets in the fund
    remaining_assets_without_swing = max(0.0, aum - redemption_amount - liquidation_cost_inr)
    remaining_assets_with_swing = max(0.0, aum - actual_cash_paid_out - liquidation_cost_inr)

    remaining_nav_without_swing = (remaining_assets_without_swing / remaining_units) if remaining_units > 0 else 0.0
    remaining_nav_with_swing = (remaining_assets_with_swing / remaining_units) if remaining_units > 0 else 0.0

    nav_drag_without_swing_pct = (
        ((initial_nav - remaining_nav_without_swing) / initial_nav * 100.0) if initial_nav > 0 else 0.0
    )
    nav_drag_with_swing_pct = (
        ((initial_nav - remaining_nav_with_swing) / initial_nav * 100.0) if initial_nav > 0 else 0.0
    )

    # Net protection provided by swing pricing (basis points)
    protection_bps = (
        (remaining_nav_with_swing - remaining_nav_without_swing) / initial_nav * 10000.0 if initial_nav > 0 else 0.0
    )

    return {
        "initial_units": initial_units,
        "redemption_units": redemption_units,
        "remaining_units": remaining_units,
        "swung_nav": swung_nav,
        "actual_cash_paid_out_inr": actual_cash_paid_out,
        "swing_savings_inr": swing_savings_inr,
        "remaining_assets_without_swing_inr": remaining_assets_without_swing,
        "remaining_assets_with_swing_inr": remaining_assets_with_swing,
        "remaining_nav_without_swing": remaining_nav_without_swing,
        "remaining_nav_with_swing": remaining_nav_with_swing,
        "nav_drag_without_swing_pct": nav_drag_without_swing_pct,
        "nav_drag_with_swing_pct": nav_drag_with_swing_pct,
        "protection_bps": protection_bps,
    }
