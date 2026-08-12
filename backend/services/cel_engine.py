import re
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
POLICIES_DIR = PROJECT_ROOT / "policies"


def load_policy_source(filename: str) -> str:
    """Reads the CEL policy file contents."""
    path = POLICIES_DIR / filename
    if not path.exists():
        # Try fallback to parent directory context
        path = Path(__file__).resolve().parent.parent / "policies" / filename
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {filename}")
    with open(path, "r") as f:
        return f.read()


def evaluate_swing_pricing_triggers(input_data: dict, config_data: dict) -> tuple[bool, str, dict]:
    """
    Evaluates: swing_pricing_triggers.cel
    Returns (is_compliant, cel_source, details_dict).
    """
    cel_source = load_policy_source("swing_pricing_triggers.cel")

    market_dislocation_active = config_data.get("market_dislocation_active", False)
    risk_o_meter = input_data.get("risk_o_meter", "LOW")
    swing_pricing_active = input_data.get("swing_pricing_active", False)
    applied_swing_factor_pct = input_data.get("applied_swing_factor_pct", 0.0)
    prc_cell = input_data.get("prc_cell", "")
    net_outflow_pct = input_data.get("net_outflow_pct", 0.0)

    # Defaults and matrices
    prc_matrix_swing_factors = config_data.get("prc_matrix_swing_factors", {})
    partial_swing_threshold_pct = config_data.get("partial_swing_threshold_pct", 5.0)

    details = {
        "market_dislocation_active": market_dislocation_active,
        "risk_o_meter": risk_o_meter,
        "swing_pricing_active": swing_pricing_active,
        "applied_swing_factor_pct": applied_swing_factor_pct,
        "prc_cell": prc_cell,
        "net_outflow_pct": net_outflow_pct,
        "rules_evaluated": [],
    }

    # Rule 1: Mandatory Full Swing during Market Dislocation for High-Risk Schemes
    rule1_applies = market_dislocation_active and (risk_o_meter in ["HIGH", "VERY_HIGH"])
    rule1_passed = True

    if rule1_applies:
        min_required_factor = 1.00  # default
        if prc_cell in prc_matrix_swing_factors:
            min_required_factor = prc_matrix_swing_factors[prc_cell]

        rule1_passed = swing_pricing_active == True and applied_swing_factor_pct >= min_required_factor
        details["rules_evaluated"].append(
            {
                "name": "Mandatory Full Swing during Market Dislocation",
                "applies": True,
                "passed": rule1_passed,
                "min_required_factor": min_required_factor,
                "applied_swing_factor_pct": applied_swing_factor_pct,
                "swing_pricing_active": swing_pricing_active,
            }
        )
    else:
        details["rules_evaluated"].append(
            {"name": "Mandatory Full Swing during Market Dislocation", "applies": False, "passed": True}
        )

    # Rule 2: Partial Swing Trigger during Normal Market Conditions (Dislocation Inactive)
    rule2_applies = (not market_dislocation_active) and (net_outflow_pct >= partial_swing_threshold_pct)
    rule2_passed = True

    if rule2_applies:
        rule2_passed = swing_pricing_active == True and applied_swing_factor_pct > 0.0
        details["rules_evaluated"].append(
            {
                "name": "Partial Swing Trigger during Normal Conditions",
                "applies": True,
                "passed": rule2_passed,
                "threshold_pct": partial_swing_threshold_pct,
                "net_outflow_pct": net_outflow_pct,
                "swing_pricing_active": swing_pricing_active,
                "applied_swing_factor_pct": applied_swing_factor_pct,
            }
        )
    else:
        details["rules_evaluated"].append(
            {"name": "Partial Swing Trigger during Normal Conditions", "applies": False, "passed": True}
        )

    is_compliant = rule1_passed and rule2_passed
    return is_compliant, cel_source, details


def evaluate_portfolio_compliance(input_data: dict, config_data: dict) -> tuple[bool, str, dict]:
    """
    Evaluates: portfolio_compliance.cel
    Returns (is_compliant, cel_source, details_dict).
    """
    cel_source = load_policy_source("portfolio_compliance.cel")

    portfolio_exposure = input_data.get("portfolio_exposure", {})
    illiquid_ratio = portfolio_exposure.get("illiquid_ratio", 0.0)
    risk_o_meter = input_data.get("risk_o_meter", "LOW")

    compliance_limits = config_data.get("compliance_limits", {})
    max_illiquid_exposure_pct = compliance_limits.get("max_illiquid_exposure_pct", 35.0)

    illiquid_pct = illiquid_ratio * 100.0

    # Rule 1: If illiquid assets exceed 30%, Risk-o-meter must be High or Very High
    rule1_passed = True
    if illiquid_pct > 30.0:
        rule1_passed = risk_o_meter in ["HIGH", "VERY_HIGH"]

    # Rule 2: Illiquid exposure must never exceed the compliance limit (e.g., 35.0%)
    rule2_passed = illiquid_pct <= max_illiquid_exposure_pct

    details = {
        "illiquid_ratio_pct": illiquid_pct,
        "risk_o_meter": risk_o_meter,
        "max_illiquid_exposure_pct": max_illiquid_exposure_pct,
        "rules": [
            {
                "name": "High Risk-o-meter for High Illiquidity (>30%)",
                "passed": rule1_passed,
                "illiquid_pct": illiquid_pct,
                "risk_o_meter": risk_o_meter,
            },
            {
                "name": "Maximum Illiquid Exposure Limit",
                "passed": rule2_passed,
                "illiquid_pct": illiquid_pct,
                "limit_pct": max_illiquid_exposure_pct,
            },
        ],
    }

    is_compliant = rule1_passed and rule2_passed
    return is_compliant, cel_source, details


def evaluate_pii_protection(input_data: dict, config_data: dict) -> tuple[bool, str, dict]:
    """
    Evaluates: pii_protection.cel
    Returns (is_compliant, cel_source, details_dict).
    """
    cel_source = load_policy_source("pii_protection.cel")

    investor_aadhaar = input_data.get("investor_aadhaar", "")
    investor_pan = input_data.get("investor_pan", "")
    investor_name = input_data.get("investor_name", "")

    aadhaar_valid = True
    pan_valid = True
    name_valid = True

    # Aadhaar checks: If present and not empty, it must not be a raw 12-digit number and must match masked pattern
    if investor_aadhaar:
        is_raw_aadhaar = bool(re.match(r"^[0-9]{12}$", investor_aadhaar))
        is_masked_aadhaar = bool(
            re.match(r"^XXXX-XXXX-[0-9]{4}$", investor_aadhaar) or re.match(r"^XXXXXXXX[0-9]{4}$", investor_aadhaar)
        )
        aadhaar_valid = (not is_raw_aadhaar) and is_masked_aadhaar

    # PAN checks: If present and not empty, must not match raw PAN, and must match masked pattern.
    # Exclude masked PAN starting with XXXXX from triggering is_raw_pan since X is a valid letter in [A-Z].
    if investor_pan:
        is_raw_pan = bool(
            re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", investor_pan.upper())
        ) and not investor_pan.upper().startswith("XXXXX")
        is_masked_pan = bool(re.match(r"^XXXXX[0-9]{4}[A-Z]$", investor_pan.upper()))
        pan_valid = (not is_raw_pan) and is_masked_pan

    # Name checks: If present and not empty, must start with *** or contain MASKED
    if investor_name:
        name_valid = investor_name.startswith("***") or "MASKED" in investor_name

    is_compliant = aadhaar_valid and pan_valid and name_valid

    details = {
        "aadhaar_checked": bool(investor_aadhaar),
        "aadhaar_valid": aadhaar_valid,
        "pan_checked": bool(investor_pan),
        "pan_valid": pan_valid,
        "name_checked": bool(investor_name),
        "name_valid": name_valid,
    }

    return is_compliant, cel_source, details
