import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Base directories
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SCHEMA_PATH = PROJECT_ROOT / "config_schema.json"
CONFIG_OVERRIDE_PATH = BASE_DIR / "config.json"


def load_defaults_from_schema(schema_path: Path) -> dict[str, Any]:
    """Dynamically parses defaults from the JSON schema."""
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")

    with open(schema_path, "r") as f:
        schema = json.load(f)

    def _extract(node: Any) -> Any:
        if not isinstance(node, dict):
            return None
        if "default" in node:
            return node["default"]
        if node.get("type") == "object" and "properties" in node:
            res = {}
            for k, v in node["properties"].items():
                val = _extract(v)
                if val is not None:
                    res[k] = val
            return res
        return None

    defaults = _extract(schema)
    if not defaults:
        raise ValueError("Could not extract defaults from schema.")
    return defaults


# Load the defaults
DEFAULTS = load_defaults_from_schema(SCHEMA_PATH)


# Define Pydantic models for validation and typing
class PortfolioDefaults(BaseModel):
    liquid_ratio: float = DEFAULTS["portfolio_defaults"]["liquid_ratio"]
    semi_liquid_ratio: float = DEFAULTS["portfolio_defaults"]["semi_liquid_ratio"]
    illiquid_ratio: float = DEFAULTS["portfolio_defaults"]["illiquid_ratio"]


class PrcMatrixSwingFactors(BaseModel):
    A_I: float = DEFAULTS["prc_matrix_swing_factors"]["A_I"]
    A_II: float = DEFAULTS["prc_matrix_swing_factors"]["A_II"]
    A_III: float = DEFAULTS["prc_matrix_swing_factors"]["A_III"]
    B_I: float = DEFAULTS["prc_matrix_swing_factors"]["B_I"]
    B_II: float = DEFAULTS["prc_matrix_swing_factors"]["B_II"]
    B_III: float = DEFAULTS["prc_matrix_swing_factors"]["B_III"]
    C_I: float = DEFAULTS["prc_matrix_swing_factors"]["C_I"]
    C_II: float = DEFAULTS["prc_matrix_swing_factors"]["C_II"]
    C_III: float = DEFAULTS["prc_matrix_swing_factors"]["C_III"]


class AssetCostParams(BaseModel):
    base_spread_pct: float
    price_impact_coefficient: float
    market_depth_limit_inr: float


class TransactionCostParameters(BaseModel):
    liquid_asset: AssetCostParams = Field(
        default_factory=lambda: AssetCostParams(**DEFAULTS["transaction_cost_parameters"]["liquid_asset"])
    )
    semi_liquid_asset: AssetCostParams = Field(
        default_factory=lambda: AssetCostParams(**DEFAULTS["transaction_cost_parameters"]["semi_liquid_asset"])
    )
    illiquid_asset: AssetCostParams = Field(
        default_factory=lambda: AssetCostParams(**DEFAULTS["transaction_cost_parameters"]["illiquid_asset"])
    )


class ComplianceLimits(BaseModel):
    max_illiquid_exposure_pct: float = DEFAULTS["compliance_limits"]["max_illiquid_exposure_pct"]
    pan_regex: str = DEFAULTS["compliance_limits"]["pan_regex"]
    aadhaar_regex: str = DEFAULTS["compliance_limits"]["aadhaar_regex"]


class AppConfig(BaseModel):
    system_mode: str = DEFAULTS["system_mode"]
    market_dislocation_active: bool = DEFAULTS["market_dislocation_active"]
    partial_swing_threshold_pct: float = DEFAULTS["partial_swing_threshold_pct"]
    portfolio_defaults: PortfolioDefaults = Field(default_factory=PortfolioDefaults)
    prc_matrix_swing_factors: PrcMatrixSwingFactors = Field(default_factory=PrcMatrixSwingFactors)
    transaction_cost_parameters: TransactionCostParameters = Field(default_factory=TransactionCostParameters)
    pii_masking_enabled: bool = DEFAULTS["pii_masking_enabled"]
    compliance_limits: ComplianceLimits = Field(default_factory=ComplianceLimits)


class ConfigManager:
    """Manages reading and writing application configurations."""

    def __init__(self, override_path: Path = CONFIG_OVERRIDE_PATH):
        self.override_path = override_path
        self._config: AppConfig = self.load_config()

    def load_config(self) -> AppConfig:
        # Load from file if it exists, otherwise use defaults
        config_data = DEFAULTS.copy()
        if self.override_path.exists():
            try:
                with open(self.override_path, "r") as f:
                    overrides = json.load(f)
                    # Recursively update config_data
                    self._update_dict_recursive(config_data, overrides)
            except Exception as e:
                print(f"Error loading config overrides: {e}. Using defaults.")

        # Override with environment variable if present
        system_mode_env = os.getenv("SYSTEM_MODE")
        if system_mode_env in ["MOCK", "LIVE_GCP"]:
            config_data["system_mode"] = system_mode_env

        market_dislocation_env = os.getenv("MARKET_DISLOCATION_ACTIVE")
        if market_dislocation_env is not None:
            config_data["market_dislocation_active"] = market_dislocation_env.lower() in ("true", "1", "yes")

        return AppConfig(**config_data)

    def _update_dict_recursive(self, target: dict, source: dict):
        for k, v in source.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                self._update_dict_recursive(target[k], v)
            else:
                target[k] = v

    def get_config(self) -> AppConfig:
        return self._config

    def update_config(self, new_config: AppConfig) -> AppConfig:
        self._config = new_config
        # Save to config.json
        try:
            with open(self.override_path, "w") as f:
                json.dump(self._config.model_dump(), f, indent=2)
        except Exception as e:
            print(f"Error saving config overrides: {e}")
        return self._config


# Global configuration instance
config_manager = ConfigManager()


def get_current_config() -> AppConfig:
    return config_manager.get_config()
