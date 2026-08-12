# SEBI Mutual Fund Swing Pricing & Outflow Stress Engine
## Executive Presentation & Live Demo Script

---

## 1. 30-Second Executive Pitch
"During sudden market dislocations or massive redemption runs in Indian debt mutual funds, first-mover redeeming investors receive un-swung NAV while leaving remaining long-term unit holders to bear the heavy liquidation slippage and bid-ask transaction costs. SEBI's Swing Pricing circulars mandate that Asset Management Companies (AMCs) dynamically compute and apply swing factors during market stress. 

This enterprise solution implements a multi-agent risk surveillance and liquidation simulation engine. Powered by Google Cloud's Vertex AI and sub-millisecond Common Expression Language (CEL) statutory guardrails, the engine models real-time Kyle's lambda market impact, evaluates SEBI Potential Risk Class (PRC) matrices, and enforces strict DPDP 2023 Aadhaar/PAN masking before sensitive portfolio data enters model contexts."

---

## 2. 2-Minute Live Meeting Walkthrough Script

### Hook & Context (0:00 - 0:30)
- **Presenter Action**: Open the cockpit at `https://120-ui.localhost` or `http://localhost:3120`.
- **Speaker**: "Welcome to the SEBI Mutual Fund Swing Pricing & Outflow Stress Engine. Notice the top masthead: we have our Cloud Design System console operating in dual-mode (MOCK vs. Live GCP ADC connected to Vertex AI Mumbai `asia-south1`). On the screen, we see Step 1: the AMC Scheme Parameter Configuration."

### Step 1: Onboarding & Policy Parameter Setup (0:30 - 0:50)
- **Presenter Action**: Point to the Scheme Category selector, AUM input, and Market Dislocation toggle.
- **Speaker**: "Here, risk managers configure their debt scheme parameters: Credit Risk Fund with ₹1,000 Crore AUM, Potential Risk Class B-III, and a 5.0% discretionary swing threshold. If SEBI officially declares a market-wide dislocation, the engine enforces mandatory minimum swing factors according to the SEBI PRC Matrix (1.50% for B-III). Let us proceed to the Simulation Cockpit."
- **Presenter Action**: Click **Proceed to Simulation Cockpit**.

### Step 2: Split-Screen Execution & Preset Scenarios (0:50 - 1:30)
- **Presenter Action**: Click **SCEN-A (Golden Path - Compliant)**.
- **Speaker**: "In the split-screen workspace, we have Indian BFSI test scenarios on the left and the 4-Step Walkthrough Storyboard on the right. Let us click Run Outflow Stress Simulation."
- **Presenter Action**: Click **Run Outflow Stress Simulation**.
- **Speaker**: "Watch the real-time execution across our 4 inspection tabs:
  1. **Data Protection (PII Masking)**: Notice how Vikram Malhotra's 12-digit Aadhaar (`123456789012`) and PAN (`VIKRA1234M`) were masked on the gateway in under 1ms before any analytics or LLMs touched the data.
  2. **Statutory Guardrails**: The Common Expression Language (CEL) engine evaluated `pii_protection.cel`, `portfolio_compliance.cel`, and `swing_pricing_triggers.cel` in just 0.38ms.
  3. **Stress Liquidation & Swing Calculation**: Our mathematical model computed the liquidation waterfall across liquid, semi-liquid, and illiquid holdings, calculated Kyle's lambda price impact, and adjusted the NAV.
  4. **Multi-Agent Narrative Explanation**: Gemini 3.5 Flash synthesized an executive-ready explanation of the transaction costs and regulatory basis."

### Step 3: Regulatory Stress Test & Negative Flow (1:30 - 2:00)
- **Presenter Action**: Click **SCEN-C (Discretionary Breach)** and click **Run Outflow Stress Simulation**.
- **Speaker**: "When redemption outflow reaches 12% of AUM—breaching the 5% threshold—the engine deterministically triggers swing pricing. The base NAV drops from ₹100.00 to the swung NAV of ₹98.75, protecting remaining unit holders by ₹1.25 Crore. Every transaction is appended to our immutable JSONL audit ledger."

---

## 3. Preset Scenarios Guide

| Scenario ID | Name | Outflow % | Market Dislocation | Expected Result | Statutory Basis |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SCEN-A** | Golden Path (Normal Market) | 3.0% | `false` | `CLEARED` (No Swing) | Outflow below 5% discretionary threshold; unswung NAV ₹100.00. |
| **SCEN-B** | Retail Exemption Limit | 0.5% | `true` | `EXEMPT` | Small retail redemption (< ₹2 Lakhs) exempt from swing deductions during stress. |
| **SCEN-C** | Discretionary Outflow Breach | 12.0% | `false` | `SWING TRIGGERED` (1.25%) | 12% outflow > 5% threshold; partial swing applied to offset market impact. |
| **SCEN-D** | Mandatory Market Dislocation | 8.0% | `true` | `MANDATORY SWING` (1.50%) | SEBI declared stress; PRC Cell B-III mandates 1.50% minimum swing factor. |
| **SCEN-SAFE** | Compliant Low-Risk Gilt | 2.0% | `false` | `EXEMPT_SCHEME` | Liquid / Gilt debt schemes are exempt from mandatory swing pricing framework. |

---

## 4. Google Cloud AI Differentiators
- **Sub-millisecond Deterministic Guardrails**: CEL policy rules run in <1ms, avoiding model latency and non-deterministic hallucination on statutory thresholds.
- **Vertex AI Agent Platform in `asia-south1`**: Meets Indian data residency mandates by keeping inference within Google Cloud's Mumbai region.
- **Zero PII Exposure**: Gateway DPDP Act 2023 masking guarantees 0 bytes of plain-text investor PAN or Aadhaar reach external LLM contexts.
