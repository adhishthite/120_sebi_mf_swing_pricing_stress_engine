# SEBI Mutual Fund Swing Pricing & Outflow Stress Engine
### India BFSI Solution Factory · Project ID `120`

[![Status: Production Ready](https://img.shields.io/badge/Status-Production_Ready-emerald.svg)](#)
[![SEBI Regulatory Compliance](https://img.shields.io/badge/Compliance-SEBI_Circular_2021-blue.svg)](#)
[![Google Cloud Vertex AI](https://img.shields.io/badge/AI-Vertex_AI_Agent_Platform-blue.svg)](#)
[![Deterministic Guardrails](https://img.shields.io/badge/Guardrails-CEL_<1ms-indigo.svg)](#)

An enterprise-grade risk surveillance and liquidity stress simulation engine modeling the **SEBI Mandated Mutual Fund Swing Pricing Framework** (SEBI/HO/IMD/IMD-II DOF3/P/CIR/2021/631) for Indian Asset Management Companies (AMCs).

---

## 1. Executive Summary & Problem Context
During sudden bond market dislocation periods or severe liquidity runs, mutual fund redemption volumes surge. Selling semi-liquid commercial papers or illiquid corporate bonds incurs substantial bid-ask spreads and market impact slippage. Under standard valuation, exiting unitholders receive un-swung NAV, transferring the liquidation penalty entirely onto remaining long-term unitholders.

SEBI mandates that AMCs implement dynamic swing pricing mechanisms:
1. **Mandatory Full Swing Pricing**: Enforced during SEBI-declared market dislocation across high-risk Potential Risk Class (PRC) debt schemes (Cells A-III, B-II, B-III, C-I, C-II, C-III).
2. **Discretionary / Partial Swing Pricing**: Triggered during normal market conditions when net outflow exceeds AMC-defined thresholds (typically 5.0% of AUM).
3. **Retail Investor Protection**: Retail redemptions up to ₹2 Lakhs per investor are exempted from downward swing adjustments.

This solution provides AMCs and institutional custodians with a real-time simulation cockpit, combining Kyle's lambda market impact mathematics, statutory Common Expression Language (CEL) policy enforcement, and Gemini 3.5 multi-agent synthesis.

---

## 2. Technical Architecture & Component Flow

```
+----------------------------------------------------------------------------------------------------+
|                                     INCOMING TRANSACTION REQUEST                                   |
|                        (Investor Name, 12-digit Aadhaar, 10-char PAN, Outflow Amount)              |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         LAYER 1: GATEWAY DATA PROTECTION (DPDP ACT 2023)                            |
|             Regex Masking: Aadhaar -> XXXXXXXX9012 | PAN -> XXXXX1234F | Name -> ***ish Thite      |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         LAYER 2: STATUTORY CEL GUARDRAIL ENGINE (< 1ms)                            |
|  * pii_protection.cel         -> Enforce Zero PII leakage across context payloads                  |
|  * portfolio_compliance.cel   -> Validate Scheme Risk-o-meter vs Illiquid Asset Exposure           |
|  * swing_pricing_triggers.cel -> SEBI PRC Matrix (A-I to C-III) & Outflow Threshold Validation      |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         LAYER 3: FINANCIAL MATHEMATICS & LIQUIDATION ENGINE                        |
|  * Kyle's Lambda Price Impact : Impact% = C * (Liquidation_Amount / Depth_Limit) ^ 0.5             |
|  * Bid-Ask Spread Widening   : Stressed Spread = Base_Spread * (2.0 if Dislocation else 1.0)      |
|  * Strategy Optimizer        : PRO_RATA vs WATERFALL vs OPTIMIZED Liquidation                      |
|  * NAV Impact Calculation    : Adjusted NAV = Unswung NAV * (1 - Swing_Factor%)                    |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         LAYER 4: GEMINI 3.5 MULTI-AGENT EXPLAINER                                  |
|         Natural Language Narrative Synthesis of Liquidation Waterfall & Compliance Basis           |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         LAYER 5: IMMUTABLE AUDIT TRAIL (JSONL TELEMETRY)                           |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. UI Design System & Dials

```
Reading this as: B2B regulatory debt compliance workspace for fund risk managers, with a serious, technical, and high-density visual language, leaning toward Cloud Design System (CDS / Pantheon) archetype with IBM Plex Sans/Mono typography.
```

- **`DESIGN_VARIANCE: 4`**: Predictable 4px grid alignment, zero-shadow borders, structured data cockpit.
- **`MOTION_INTENSITY: 2`**: Restrained transitions, micro-feedback on active state changes.
- **`VISUAL_DENSITY: 8`**: Compact information density, monospaced figures, data tables, and live telemetry feeds.

---

## 4. Project Directory Structure

```
120_sebi_mf_swing_pricing_stress_engine/
├── 0-spec/                          # Formal OpenAPI and CEL policy specifications
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   ├── api_schemas.json
│   └── cel_rules.json
├── backend/                         # FastAPI Python Backend (native uv)
│   ├── config.py                    # AppConfig & Dynamic schema loader
│   ├── main.py                      # REST endpoints & CORS configuration
│   ├── pyproject.toml               # Locked uv dependencies
│   ├── services/
│   │   ├── agents.py                # Multi-agent orchestrator & Gemini explainer
│   │   ├── cel_engine.py            # Local CEL policy evaluator
│   │   └── math_engine.py           # Liquidation models & Kyle's lambda math
│   └── tests/
│       └── test_backend.py          # Pytest unit & integration test suite
├── frontend/                        # Next.js 16 + React 19 Client (pnpm)
│   ├── src/app/page.tsx             # 2-step onboarding & split-screen cockpit
│   ├── src/components/ui/           # ShadCN UI component primitives
│   └── package.json                 # pnpm configuration bound to port 3120
├── evals/                           # Multi-agent benchmark evaluation harness
│   ├── eval_dataset.json            # 10 test scenarios (golden, guardrail, adversarial)
│   ├── eval_report.md               # Auto-generated benchmark metrics report
│   └── run_evals.py                 # Automated evaluation runner
├── policies/                        # Common Expression Language (CEL) statutory files
│   ├── pii_protection.cel
│   ├── portfolio_compliance.cel
│   └── swing_pricing_triggers.cel
├── screenshots/                     # 10 High-resolution verification captures
├── DEMO_SCRIPT.md                   # 30s executive pitch & live demo walkthrough
├── Makefile                         # Root orchestration targets
└── config_schema.json               # Master schema configuration
```

---

## 5. Quick Start & Execution

### Prerequisites
- Python 3.12+ with `uv`
- Node.js 20+ with `pnpm`

### Start Development Server
```bash
# Start backend on :8120 and frontend on :3120 concurrently
make dev
```

### Run Test Suites
```bash
# Run backend pytest suite
make test

# Run multi-agent evaluations
PYTHONPATH=backend uv run python evals/run_evals.py
```

### Access Dashboard
- **Frontend Cockpit**: `http://localhost:3120` or `https://120-ui.localhost`
- **Backend API Gateway**: `http://localhost:8120/docs` or `https://120-api.localhost`
