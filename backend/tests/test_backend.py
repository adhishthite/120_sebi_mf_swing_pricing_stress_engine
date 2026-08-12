import pytest
from fastapi.testclient import TestClient

from main import app
from services.cel_engine import evaluate_pii_protection, evaluate_portfolio_compliance
from services.math_engine import (
    calculate_swing_factor,
    calculate_transaction_cost,
    evaluate_nav_impact,
    simulate_liquidation,
)

client = TestClient(app)

# ----------------- Math Model Tests -----------------


def test_calculate_transaction_cost():
    # Normal spread parameter
    cost_params = {
        "liquid_asset": {"base_spread_pct": 0.1, "price_impact_coefficient": 0.2, "market_depth_limit_inr": 1000000.0}
    }

    # 0 amount = 0 cost
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 0, cost_params, False)
    assert cost_inr == 0
    assert cost_pct == 0

    # Normal market
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 1000000.0, cost_params, False)
    # base_spread_pct = 0.1
    # price_impact = 0.2 * (1000000 / 1000000) ** 0.5 = 0.2
    # total_pct = 0.3%
    # total_inr = 1000000 * 0.003 = 3000.0
    assert pytest.approx(cost_pct) == 0.3
    assert pytest.approx(cost_inr) == 3000.0

    # Stressed market (market dislocation) -> spread doubles to 0.2%
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 1000000.0, cost_params, True)
    # base_spread_pct = 0.1 * 2 = 0.2
    # price_impact = 0.2
    # total_pct = 0.4%
    # total_inr = 1000000 * 0.004 = 4000.0
    assert pytest.approx(cost_pct) == 0.4
    assert pytest.approx(cost_inr) == 4000.0


def test_simulate_liquidation():
    portfolio = {"liquid_ratio": 0.5, "semi_liquid_ratio": 0.3, "illiquid_ratio": 0.2}
    cost_params = {
        "liquid_asset": {"base_spread_pct": 0.1, "price_impact_coefficient": 0.1, "market_depth_limit_inr": 1000000.0},
        "semi_liquid_asset": {
            "base_spread_pct": 0.3,
            "price_impact_coefficient": 0.3,
            "market_depth_limit_inr": 1000000.0,
        },
        "illiquid_asset": {
            "base_spread_pct": 1.0,
            "price_impact_coefficient": 1.0,
            "market_depth_limit_inr": 1000000.0,
        },
    }
    aum = 10000000.0  # 10 Million
    redemption = 2000000.0  # 2 Million (20% of AUM)

    # Pro-rata strategy
    res_pro = simulate_liquidation(aum, portfolio, redemption, "PRO_RATA", cost_params, False)
    assert res_pro["strategy"] == "PRO_RATA"
    assert res_pro["liquidated_amounts"]["liquid"] == 1000000.0  # 2M * 0.5
    assert res_pro["liquidated_amounts"]["semi_liquid"] == 600000.0  # 2M * 0.3
    assert res_pro["liquidated_amounts"]["illiquid"] == 400000.0  # 2M * 0.2

    # Waterfall strategy (2M: all from liquid since liquid holding = 5M)
    res_water = simulate_liquidation(aum, portfolio, redemption, "WATERFALL", cost_params, False)
    assert res_water["strategy"] == "WATERFALL"
    assert res_water["liquidated_amounts"]["liquid"] == 2000000.0
    assert res_water["liquidated_amounts"]["semi_liquid"] == 0.0
    assert res_water["liquidated_amounts"]["illiquid"] == 0.0


def test_calculate_swing_factor():
    config = {
        "market_dislocation_active": True,
        "prc_matrix_swing_factors": {"C-III": 2.00, "B-II": 1.25},
        "partial_swing_threshold_pct": 5.0,
    }

    # Under dislocation, very high risk scheme -> triggers matrix
    factor, reason = calculate_swing_factor(
        {"risk_o_meter": "VERY_HIGH", "prc_cell": "C-III", "net_outflow_pct": 1.0}, config
    )
    assert factor == 2.00
    assert "C-III" in reason

    # Normal times, flow below threshold -> no swing
    config["market_dislocation_active"] = False
    factor, reason = calculate_swing_factor(
        {"risk_o_meter": "VERY_HIGH", "prc_cell": "C-III", "net_outflow_pct": 3.0}, config
    )
    assert factor == 0.0

    # Normal times, flow exceeds threshold -> partial swing
    factor, reason = calculate_swing_factor(
        {"risk_o_meter": "VERY_HIGH", "prc_cell": "C-III", "net_outflow_pct": 8.0}, config
    )
    assert factor == 0.5
    assert "Partial" in reason


def test_evaluate_nav_impact():
    res = evaluate_nav_impact(
        aum=1000000.0, initial_nav=10.0, redemption_amount=200000.0, swing_factor_pct=2.0, liquidation_cost_inr=5000.0
    )

    assert res["initial_units"] == 100000.0
    assert res["redemption_units"] == 200000.0 / 10.0
    assert res["remaining_units"] == 80000.0

    # Swung NAV = 10 * (1 - 0.02) = 9.8
    assert res["swung_nav"] == 9.8
    # swing savings = 200000 - (20000 units * 9.8) = 4000.0 INR
    assert res["swing_savings_inr"] == 4000.0

    # Remaining NAV without swing = (1000000 - 200000 - 5000) / 80000 = 795000 / 80000 = 9.9375
    assert res["remaining_nav_without_swing"] == 9.9375

    # Remaining NAV with swing = (1000000 - 196000 - 5000) / 80000 = 799000 / 80000 = 9.9875
    assert res["remaining_nav_with_swing"] == 9.9875

    # Protection in basis points = (9.9875 - 9.9375) / 10.0 * 10000 = 0.05 / 10 * 10000 = 50 bps
    assert pytest.approx(res["protection_bps"]) == 50.0


# ----------------- CEL Policy Evaluator Tests -----------------


def test_cel_pii_protection():
    config = {}

    # Fully masked details should pass
    ok, _, details = evaluate_pii_protection(
        {"investor_aadhaar": "XXXX-XXXX-1234", "investor_pan": "XXXXX5544B", "investor_name": "***MASKED_INVESTOR***"},
        config,
    )
    assert ok is True
    assert details["aadhaar_valid"] is True
    assert details["pan_valid"] is True

    # Unmasked details should fail
    ok, _, details = evaluate_pii_protection(
        {"investor_aadhaar": "123456789012", "investor_pan": "ABCDE1234F", "investor_name": "Ramesh Kumar"}, config
    )
    assert ok is False
    assert details["aadhaar_valid"] is False
    assert details["pan_valid"] is False
    assert details["name_valid"] is False


def test_cel_portfolio_compliance():
    config = {"compliance_limits": {"max_illiquid_exposure_pct": 35.0}}

    # Compliant: Illiquid < 30%
    ok, _, _ = evaluate_portfolio_compliance(
        {"portfolio_exposure": {"illiquid_ratio": 0.25}, "risk_o_meter": "LOW"}, config
    )
    assert ok is True

    # High risk meter needed: Illiquid is 32% (>30% rule)
    # Risk-o-meter LOW -> Should fail Rule 1
    ok, _, _ = evaluate_portfolio_compliance(
        {"portfolio_exposure": {"illiquid_ratio": 0.32}, "risk_o_meter": "LOW"}, config
    )
    assert ok is False

    # Risk-o-meter HIGH -> Should pass Rule 1
    ok, _, _ = evaluate_portfolio_compliance(
        {"portfolio_exposure": {"illiquid_ratio": 0.32}, "risk_o_meter": "HIGH"}, config
    )
    assert ok is True

    # Exceeds max compliance limit (38% > 35%) -> Should fail Rule 2
    ok, _, _ = evaluate_portfolio_compliance(
        {"portfolio_exposure": {"illiquid_ratio": 0.38}, "risk_o_meter": "VERY_HIGH"}, config
    )
    assert ok is False


# ----------------- API Route Tests -----------------


def test_api_redact():
    payload = {"investor_name": "Ananya Sharma", "investor_pan": "ABCDE1234F", "investor_aadhaar": "123456789012"}
    response = client.post("/api/redact", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["investor_name"].startswith("***")
    assert data["investor_pan"] == "XXXXX1234F"
    assert data["investor_aadhaar"] == "XXXXXXXX9012"


def test_api_simulate_stress():
    payload = {
        "aum": 1000000000.0,
        "initial_nav": 10.0,
        "net_outflow_pct": 6.0,
        "risk_o_meter": "VERY_HIGH",
        "prc_cell": "C-III",
        "portfolio_exposure": {"liquid_ratio": 0.40, "semi_liquid_ratio": 0.35, "illiquid_ratio": 0.25},
        "investor_name": "Adhish Thite",
        "investor_pan": "ABCDE1234F",
        "investor_aadhaar": "123456789012",
    }

    response = client.post("/api/simulate-stress", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Math outputs
    assert "optimal_strategy" in data
    assert "nav_impact" in data
    assert "compliance_status" in data
    assert "explanation" in data

    # Redacted payload check
    assert data["redacted_input_payload"]["investor_pan"] == "XXXXX1234F"
    assert data["redacted_input_payload"]["investor_name"].startswith("***")


def test_api_config_get_post():
    # GET config
    response = client.get("/api/config")
    assert response.status_code == 200
    config_data = response.json()
    assert config_data["system_mode"] in ["MOCK", "LIVE_GCP"]

    # POST config
    config_data["partial_swing_threshold_pct"] = 8.5
    response = client.post("/api/config", json=config_data)
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["partial_swing_threshold_pct"] == 8.5


def test_api_audit_trail():
    response = client.get("/api/audit-trail")
    assert response.status_code == 200
    trail = response.json()
    assert isinstance(trail, list)
    # Check that it recorded our previous test run
    assert len(trail) > 0
    assert "timestamp" in trail[0]
    assert "optimal_strategy" in trail[0]
