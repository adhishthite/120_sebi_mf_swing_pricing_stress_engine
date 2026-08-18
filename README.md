# SEBI Mutual Fund Swing Pricing & Outflow Stress Engine
### India BFSI Solution Factory · Project ID `120`

[![Status: Production Ready](https://img.shields.io/badge/Status-Production_Ready-emerald.svg)](#)
[![SEBI Regulatory Compliance](https://img.shields.io/badge/Compliance-SEBI_Circular_2021-blue.svg)](#)
[![Google Cloud Vertex AI](https://img.shields.io/badge/AI-Vertex_AI_Agent_Platform-blue.svg)](#)
[![Deterministic Guardrails](https://img.shields.io/badge/Guardrails-CEL_<1ms-indigo.svg)](#)
[![OpenTelemetry Tracing](https://img.shields.io/badge/Observability-OpenTelemetry-orange.svg)](#)
[![Async SQLite Memory](https://img.shields.io/badge/Persistence-aiosqlite-purple.svg)](#)

An enterprise-grade risk surveillance and liquidity stress simulation engine modeling the **SEBI Mandated Mutual Fund Swing Pricing Framework** (SEBI/HO/IMD/IMD-II DOF3/P/CIR/2021/631) for Indian Asset Management Companies (AMCs) and institutional custodians.

---

## 1. Executive Summary & Problem Context
During sudden bond market dislocation periods or severe liquidity runs, mutual fund redemption volumes surge. Selling semi-liquid commercial papers or illiquid corporate bonds incurs substantial bid-ask spreads and market impact slippage. Under standard valuation, exiting unitholders receive un-swung NAV, transferring the liquidation penalty entirely onto remaining long-term unitholders.

SEBI mandates that AMCs implement dynamic swing pricing mechanisms:
1. **Mandatory Full Swing Pricing**: Enforced during SEBI-declared market dislocation across high-risk Potential Risk Class (PRC) debt schemes (Cells A-III, B-II, B-III, C-I, C-II, C-III).
2. **Discretionary / Partial Swing Pricing**: Triggered during normal market conditions when net outflow exceeds AMC-defined thresholds (typically 5.0% of AUM).
3. **Retail Investor Protection**: Retail redemptions up to ₹2 Lakhs per investor are exempted from downward swing adjustments.
4. **Human-In-The-Loop (HITL) Code Stops**: Mandatory board review and execution pause when applied swing factor > 150 bps or net redemption > 15% AUM.

---

## 2. 5-Pillar Architecture & Capabilities

```
+----------------------------------------------------------------------------------------------------+
|                                     INCOMING TRANSACTION REQUEST                                   |
|                        (Investor Name, 12-digit Aadhaar, 10-char PAN, Outflow Amount)              |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         PILLAR 1: TYPED TOOLS & AGENTIC INTERFACE                                  |
|  * calculate_almgren_chriss_market_impact -> Permanent/temp slippage & spread execution shortfall  |
|  * evaluate_cel_compliance_policy         -> CEL rule engine (<1ms deterministic evaluation)       |
|  * execute_portfolio_liquidation_step     -> Multi-tier asset liquidation solver                    |
|  * query_sebi_swing_pricing_circular      -> RAG / statutory knowledge retriever                    |
|  * request_human_approval_overlimit       -> HITL code stop trigger (>150 bps or >15% AUM)         |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         PILLAR 2: CONTEXT & ASYNC MEMORY                                           |
|  * Non-blocking SQLite persistence (`aiosqlite` schema: sessions, messages, traces, approvals)     |
|  * Sliding window memory compactor (`memory_compactor.py`) for long multi-turn sessions            |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         PILLAR 3: MULTI-AGENT ORCHESTRATION & ROUTING                              |
|  * Strategic Model Router: Flash-Lite (Triage) | Flash (Execution) | Pro (Adjudication & Review)   |
|  * TriageRouterAgent           -> DPDP 2023 PII Masking & Exemption Evaluation                     |
|  * LiquidationOptimizerAgent   -> Almgren-Chriss Optimal Route Analysis                            |
|  * ComplianceAuditorAgent      -> CEL Statutory PRC Matrix & Swung NAV Computation                |
|  * MakerCheckerReviewerAgent   -> HITL Stop Enforcement & Executive Board Synthesis                |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         PILLAR 4: OBSERVABILITY & DISTRIBUTED TRACING                              |
|  * Structured JSON logging with Intent vs Outcome tracking around all agent steps                 |
|  * OpenTelemetry distributed tracing with custom spans, trace IDs, and latency breakdown           |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                         PILLAR 5: INFRASTRUCTURE AS CODE & CI/CD                                   |
|  * Terraform suite (Cloud Run v2, BigQuery audit dataset, Cloud Storage, Vertex AI, IAM)          |
|  * GitHub Actions CI/CD (Ruff, Biome, Pytest, Evals Benchmark, Terraform Validate)                |
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
├── .github/workflows/
│   └── ci.yml                       # CI/CD Quality Pipeline (Lint, Tests, Evals, Terraform)
├── 0-spec/                          # Formal OpenAPI and CEL policy specifications
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   ├── api_schemas.json
│   └── cel_rules.json
├── backend/                         # FastAPI Python Backend (native uv)
│   ├── config.py                    # AppConfig & Dynamic schema loader
│   ├── main.py                      # REST endpoints, Lifespan DB init, OpenTelemetry, HITL
│   ├── pyproject.toml               # Locked uv dependencies
│   ├── services/
│   │   ├── agent_loop.py            # Autonomous tool-calling loop with self-correction
│   │   ├── agents.py                # Multi-agent orchestrator & 4 agent actors
│   │   ├── cel_engine.py            # Local CEL policy evaluator
│   │   ├── database.py              # Async SQLite persistence (sessions, traces, approvals)
│   │   ├── logger.py                # Structured JSON logging & Intent vs Outcome
│   │   ├── math_engine.py           # Liquidation models & Kyle's lambda math
│   │   ├── memory_compactor.py      # Conversation compaction & sliding window
│   │   ├── router.py                # Strategic Model Router (Flash-Lite/Flash/Pro)
│   │   ├── telemetry.py             # OpenTelemetry distributed tracing & custom spans
│   │   └── tools.py                 # Typed & documented agent tools with Pydantic schemas
│   └── tests/
│       └── test_backend.py          # 20 Unit & integration tests
├── terraform/                       # Complete Terraform Suite
│   ├── main.tf                      # Google provider configuration
│   ├── variables.tf                 # Configurable project, region, image variables
│   ├── outputs.tf                   # Service URLs, BigQuery, GCS, Vertex AI outputs
│   ├── vertex_ai.tf                 # Vertex AI endpoint, BigQuery audit dataset, GCS, IAM
│   └── cloud_run.tf                 # Cloud Run v2 services for Backend and Frontend
├── frontend/                        # Next.js 16 + React 19 Client (pnpm)
│   ├── src/app/page.tsx             # 2-step onboarding & split-screen cockpit
│   ├── src/components/ui/           # ShadCN UI component primitives
│   └── package.json                 # pnpm configuration bound to port 3120
├── evals/                           # Multi-agent benchmark evaluation harness
│   ├── eval_dataset.json            # 10 benchmark scenarios (golden, guardrail, adversarial)
│   ├── eval_report.md               # Auto-generated benchmark metrics report
│   └── run_evals.py                 # Automated evaluation runner
├── policies/                        # Common Expression Language (CEL) statutory files
│   ├── pii_protection.cel
│   ├── portfolio_compliance.cel
│   └── swing_pricing_triggers.cel
├── screenshots/                     # 10 High-resolution verification captures
├── DEMO_SCRIPT.md                   # 30s executive pitch & live demo walkthrough
├── Makefile                         # Root orchestration targets (dev, test, format, lint, check)
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

### Run Test Suite & Check Pipeline
```bash
# Run backend pytest suite (20 tests covering all 5 pillars)
make test

# Run full quality check (format, lint, tests)
make check
```

### Run Multi-Agent Benchmark Evaluations
```bash
cd backend && PYTHONPATH=. uv run python ../evals/run_evals.py
```

### Evaluation Scorecard
| Metric | Target Standard | Achieved Score | Status |
| :--- | :--- | :--- | :--- |
| **Task Success Rate** | $\ge 95\%$ | **100.0%** | 🟢 PASS |
| **Statutory Guardrail Precision** | $100\%$ | **100.0%** | 🟢 PASS |
| **Data Protection / Zero PII Leakage** | $0\%$ Leaked ($100\%$ Redacted) | **100.0%** | 🟢 PASS |
| **Groundedness & Tool Calling Accuracy** | $\ge 90\%$ | **100.0%** | 🟢 PASS |
| **Avg Deterministic Policy Latency** | $< 2.0\text{ ms}$ | **0.326 ms** | 🟢 PASS |

---

## 6. API Endpoints
- `POST /api/simulate-stress`: Run multi-agent simulation, Almgren-Chriss liquidation, swung NAV calculation, and HITL check.
- `POST /api/redact`: Mask PII according to DPDP Act 2023.
- `GET /api/sessions/{session_id}`: Load session state and message turn history.
- `POST /api/sessions/{session_id}/approve`: Maker-checker sign-off for HELD sessions.
- `GET /api/approvals`: List all pending and reviewed HITL tickets.
- `POST /api/approvals/{approval_id}/decision`: Submit CRO / Compliance decision.
- `GET /api/traces`: Query OpenTelemetry agent traces and execution latencies.
- `GET|POST /api/config`: Dynamic system configuration overrides.
- `GET /api/audit-trail`: Immutable execution logs.
- `GET /api/health`: Health status.
