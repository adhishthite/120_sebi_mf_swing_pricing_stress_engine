# SEBI Mutual Fund Swing Pricing & Stress Engine: Backend Architecture

The backend is built with Python 3.12+, FastAPI, Pydantic v2, and managed via native `uv`. It simulates portfolio liquidation under stress, evaluates statutory Common Expression Language (CEL) guardrails, and synthesizes natural language compliance reports via Gemini 3.5.

---

## 1. API Gateway Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/redact` | Gateway masking of investor PII (Aadhaar 12-digit, PAN, and full name) matching DPDP 2023. |
| `POST` | `/api/simulate-stress` | Main execution endpoint. Runs liquidation models, evaluates CEL guardrails, and computes swung NAV. |
| `GET` | `/api/config` | Retrieves the active system configuration (PRC matrix, portfolio ratios, thresholds). |
| `POST` | `/api/config` | Updates the active system configuration and persists overrides to `config.json`. |
| `GET` | `/api/audit-trail` | Returns historical simulation records from the immutable audit ledger. |
| `GET` | `/api/health` | Service health status check. |

---

## 2. Core Service Architecture

- **`services/math_engine.py`**:
  - Implements Kyle's lambda market impact model: $\Delta P\% = c \cdot \sqrt{\text{Amount} / \text{Depth Limit}}$.
  - Bid-ask spread stress widening factor ($2.0\times$ during SEBI-declared dislocation).
  - Multi-asset liquidation strategies: `PRO_RATA`, `WATERFALL`, and `OPTIMIZED`.
  - Calculates NAV drag reduction and unitholder protection basis points ($\text{bps}$).
- **`services/cel_engine.py`**:
  - Deterministic evaluation of statutory policies in `../policies/` (`pii_protection.cel`, `portfolio_compliance.cel`, `swing_pricing_triggers.cel`).
  - Average evaluation latency: $< 0.5\text{ ms}$.
- **`services/agents.py`**:
  - Multi-agent orchestrator connecting the Liquidation Optimizer, Market Impact Simulator, Compliance Evaluator, and Gemini Synthesizer.
  - Dual-mode support: `MOCK` (offline deterministic) vs `LIVE_GCP` (Vertex AI `asia-south1`).

---

## 3. Development Commands (Native `uv` Only)

```bash
# Install / Lock dependencies
uv sync

# Run development server
PYTHONPATH=. uv run uvicorn main:app --host 0.0.0.0 --port 8120 --reload

# Run pytest unit test suite
PYTHONPATH=. uv run pytest

# Format and Lint
uv run ruff format .
uv run ruff check .
```
