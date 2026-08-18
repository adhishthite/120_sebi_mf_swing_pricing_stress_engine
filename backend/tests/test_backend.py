"""
Unit and Integration Test Suite for Project 120:
SEBI Mutual Fund Swing Pricing & Liquidation Stress Engine.
Validates all 5 Architecture Pillars:
1. Tool & Interface Design
2. Context & Memory (Async SQLite + History Compaction)
3. Multi-Agent Orchestration & Strategic Routing
4. Observability & Distributed Tracing
5. HITL Decision Workflow & API Contracts
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from services.agent_loop import AgentLoopRunner
from services.agents import (
    ComplianceAuditorAgent,
    LiquidationOptimizerAgent,
    MakerCheckerReviewerAgent,
    Orchestrator,
    TriageRouterAgent,
)
from services.database import (
    get_all_traces,
    get_hitl_approval,
    get_session_state,
    init_db,
    list_hitl_approvals,
    load_session_history,
    save_agent_trace,
    save_hitl_approval,
    save_session_turn,
    update_hitl_approval,
    update_session_state,
)
from services.logger import get_structured_logger, log_agent_intent, log_agent_outcome
from services.math_engine import (
    calculate_transaction_cost,
)
from services.memory_compactor import compact_conversation_history
from services.router import AgentTaskType, ModelRouter
from services.telemetry import custom_span, get_current_trace_id, trace_span
from services.tools import (
    TOOL_REGISTRY,
    calculate_almgren_chriss_market_impact,
    execute_portfolio_liquidation_step,
    query_sebi_swing_pricing_circular,
    request_human_approval_overlimit,
)

client = TestClient(app)

# ----------------- 1. Mathematical & Almgren-Chriss Tools Tests -----------------


def test_calculate_transaction_cost():
    cost_params = {
        "liquid_asset": {"base_spread_pct": 0.1, "price_impact_coefficient": 0.2, "market_depth_limit_inr": 1000000.0}
    }
    # 0 amount = 0 cost
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 0, cost_params, False)
    assert cost_inr == 0
    assert cost_pct == 0

    # Normal market
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 1000000.0, cost_params, False)
    assert pytest.approx(cost_pct) == 0.3
    assert pytest.approx(cost_inr) == 3000.0

    # Stressed market (market dislocation)
    cost_inr, cost_pct = calculate_transaction_cost("liquid", 1000000.0, cost_params, True)
    assert pytest.approx(cost_pct) == 0.4
    assert pytest.approx(cost_inr) == 4000.0


def test_calculate_almgren_chriss_market_impact_tool():
    # Test zero amount
    zero_res = calculate_almgren_chriss_market_impact("liquid", 0.0)
    assert zero_res["total_cost_inr"] == 0.0

    # Test normal liquidation
    res = calculate_almgren_chriss_market_impact(
        asset_class="illiquid",
        liquidation_amount=50_000_000.0,
        market_depth_limit=500_000_000.0,
        base_spread_pct=0.8,
        price_impact_coefficient=0.6,
        volatility_pct=2.0,
        market_dislocation_active=False,
    )
    assert res["spread_pct"] == 0.8
    assert res["temporary_impact_pct"] > 0
    assert res["permanent_impact_pct"] > 0
    assert res["total_cost_pct"] > 0
    assert res["total_cost_inr"] > 0
    assert res["execution_shortfall_inr"] > 0

    # Test stressed liquidation (spread doubles)
    res_stressed = calculate_almgren_chriss_market_impact(
        asset_class="illiquid",
        liquidation_amount=50_000_000.0,
        market_depth_limit=500_000_000.0,
        base_spread_pct=0.8,
        price_impact_coefficient=0.6,
        volatility_pct=2.0,
        market_dislocation_active=True,
    )
    assert res_stressed["spread_pct"] == 1.6
    assert res_stressed["total_cost_inr"] > res["total_cost_inr"]


def test_execute_portfolio_liquidation_step_tool():
    res = execute_portfolio_liquidation_step(
        aum=1_000_000_000.0,
        liquid_ratio=0.4,
        semi_liquid_ratio=0.35,
        illiquid_ratio=0.25,
        redemption_amount=100_000_000.0,
        strategy="OPTIMIZED",
        market_dislocation_active=False,
    )
    assert res["strategy"] == "OPTIMIZED"
    assert "liquidated_amounts" in res
    assert "transaction_costs" in res
    assert "post_liquidation_exposure" in res
    assert res["post_liquidation_exposure"]["aum"] == 900_000_000.0


def test_query_sebi_swing_pricing_circular_tool():
    prc_res = query_sebi_swing_pricing_circular("prc_matrix")
    assert "SEBI/HO/IMD/IMD-II" in prc_res["circular_reference"]
    assert len(prc_res["clauses"]) > 0
    assert "C-III" in prc_res["applicable_thresholds"]["prc_matrix_swing_factors"]

    exempt_res = query_sebi_swing_pricing_circular("exemptions")
    assert any("Retail" in c["clause"] for c in exempt_res["clauses"])

    all_res = query_sebi_swing_pricing_circular("all")
    assert len(all_res["clauses"]) >= 4


def test_request_human_approval_overlimit_tool():
    appr = request_human_approval_overlimit(
        session_id="sess-test-123",
        reason="Swing factor 175 bps exceeded 150 bps ceiling",
        swing_factor_bps=175.0,
        redemption_pct=18.0,
        post_illiquid_ratio=0.38,
        current_nav=10.0,
        swung_nav=9.825,
    )
    assert appr["status"] == "HELD"
    assert appr["session_id"] == "sess-test-123"
    assert "Chief Risk Officer (CRO)" in appr["required_roles"]
    assert appr["trigger_metrics"]["swing_factor_bps"] == 175.0


def test_tool_registry_integrity():
    required_tools = [
        "calculate_almgren_chriss_market_impact",
        "evaluate_cel_compliance_policy",
        "execute_portfolio_liquidation_step",
        "query_sebi_swing_pricing_circular",
        "request_human_approval_overlimit",
    ]
    for t in required_tools:
        assert t in TOOL_REGISTRY
        assert "schema" in TOOL_REGISTRY[t]
        assert "parameters" in TOOL_REGISTRY[t]["schema"]


# ----------------- 2. Context & Async Memory Tests -----------------


@pytest.mark.asyncio
async def test_async_database_crud(tmp_path):
    test_db = tmp_path / "test_engine.db"
    await init_db(test_db)

    session_id = "sess-async-001"

    # 1. State update
    state = await update_session_state(
        session_id=session_id,
        state_update={"aum": 500_000_000.0, "net_outflow_pct": 8.0},
        status="ACTIVE",
        summary="Test session initialization",
        db_path=test_db,
    )
    assert state["session_id"] == session_id
    assert state["state"]["aum"] == 500_000_000.0

    retrieved = await get_session_state(session_id, db_path=test_db)
    assert retrieved is not None
    assert retrieved["summary"] == "Test session initialization"

    # 2. Message turn persistence
    msg_id1 = await save_session_turn(
        session_id=session_id,
        role="user",
        content="Stress scenario with 8% outflow",
        metadata={"step": 1},
        db_path=test_db,
    )
    msg_id2 = await save_session_turn(
        session_id=session_id,
        role="assistant",
        content="Applied swing factor 1.50%",
        metadata={"step": 2},
        db_path=test_db,
    )
    assert msg_id1 > 0
    assert msg_id2 > msg_id1

    history = await load_session_history(session_id, db_path=test_db)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # 3. Agent trace persistence
    trace_id = "trc-test-trace-999"
    await save_agent_trace(
        session_id=session_id,
        trace_data={
            "trace_id": trace_id,
            "span_id": "spn-001",
            "agent_name": "TriageRouterAgent",
            "intent": "Test intent logging",
            "outcome": "SUCCESS",
            "latency_ms": 1.45,
            "status": "SUCCESS",
            "details": {"verified": True},
        },
        db_path=test_db,
    )
    traces = await get_all_traces(session_id=session_id, db_path=test_db)
    assert len(traces) == 1
    assert traces[0]["trace_id"] == trace_id

    # 4. HITL Approval lifecycle
    appr_id = "APPR-TEST-01"
    appr_created = await save_hitl_approval(
        approval_id=appr_id,
        session_id=session_id,
        status="HELD",
        payload={"swing_factor_bps": 160.0},
        reason="Swing factor exceeded 150 bps",
        db_path=test_db,
    )
    assert appr_created["status"] == "HELD"

    fetched = await get_hitl_approval(appr_id, db_path=test_db)
    assert fetched is not None
    assert fetched["status"] == "HELD"

    updated = await update_hitl_approval(
        approval_id=appr_id,
        status="APPROVED",
        approved_by="Chief Risk Officer",
        comments="Authorized for execution.",
        db_path=test_db,
    )
    assert updated["status"] == "APPROVED"
    assert updated["reviewed_by"] == "Chief Risk Officer"

    all_apprs = await list_hitl_approvals(session_id=session_id, db_path=test_db)
    assert len(all_apprs) == 1
    assert all_apprs[0]["status"] == "APPROVED"


def test_memory_compaction():
    # Under threshold -> no compaction
    short_messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Ready for stress test"},
    ]
    compacted, summary = compact_conversation_history(short_messages, max_turns=6, token_threshold=3000)
    assert len(compacted) == 2
    assert summary == ""

    # Over turn threshold (8 messages with max_turns=4)
    long_messages = [
        {"role": "user", "content": f"Turn {i} request", "metadata": {}}
        if i % 2 == 1
        else {
            "role": "assistant",
            "content": f"Turn {i} response",
            "metadata": {"optimal_strategy": "OPTIMIZED", "applied_swing_factor_pct": 1.5},
        }
        for i in range(1, 9)
    ]
    compacted, summary = compact_conversation_history(long_messages, max_turns=4, token_threshold=3000)
    assert len(compacted) == 5  # 1 summary + 4 recent turns
    assert compacted[0]["role"] == "system"
    assert "Prior Conversation Context Summary" in compacted[0]["content"]
    assert "Optimal Strategy: OPTIMIZED" in summary


# ----------------- 3. Orchestration & Strategic Routing Tests -----------------


def test_model_router():
    # Intent / Triage -> flash-lite
    m_triage = ModelRouter.get_model_for_task(AgentTaskType.TRIAGE_INTENT)
    assert "flash-lite" in m_triage

    # Tool Execution -> flash
    m_tool = ModelRouter.get_model_for_task(AgentTaskType.TOOL_EXECUTION)
    assert "flash" in m_tool

    # Regulatory Adjudication & Review -> pro
    m_adj = ModelRouter.get_model_for_task(AgentTaskType.REGULATORY_ADJUDICATION)
    assert "pro" in m_adj

    m_review = ModelRouter.get_model_for_task(AgentTaskType.MAKER_CHECKER_REVIEW)
    assert "pro" in m_review

    # Latency budgets
    assert ModelRouter.get_latency_budget(AgentTaskType.TRIAGE_INTENT) <= 200.0
    assert ModelRouter.get_latency_budget(AgentTaskType.REGULATORY_ADJUDICATION) >= 1000.0


@pytest.mark.asyncio
async def test_agent_loop_runner_mock_execution():
    context_payload = {
        "aum": 1_000_000_000.0,
        "initial_nav": 10.0,
        "net_outflow_pct": 8.0,
        "risk_o_meter": "VERY_HIGH",
        "prc_cell": "C-III",
        "market_dislocation_active": True,
        "portfolio_exposure": {"liquid_ratio": 0.40, "semi_liquid_ratio": 0.35, "illiquid_ratio": 0.25},
    }

    result = await AgentLoopRunner.run_agent_loop(
        prompt="Simulate stress scenario for C-III scheme under market dislocation",
        session_id="sess-agent-loop-01",
        context_payload=context_payload,
    )

    assert isinstance(result.iterations_count, int)
    assert len(result.tool_calls_executed) >= 3
    assert len(result.steps_trace) >= 3
    assert "Adjudication Summary" in result.final_response
    assert result.status in ["COMPLETED", "HELD"]


def test_multi_agent_pipeline_sync_and_async():
    payload = {
        "aum": 1_000_000_000.0,
        "initial_nav": 10.0,
        "net_outflow_pct": 6.0,
        "risk_o_meter": "VERY_HIGH",
        "prc_cell": "C-III",
        "portfolio_exposure": {"liquid_ratio": 0.40, "semi_liquid_ratio": 0.35, "illiquid_ratio": 0.25},
        "investor_name": "Adhish Thite",
        "investor_pan": "ABCDE1234F",
        "investor_aadhaar": "123456789012",
    }

    # Test TriageRouterAgent
    triage = TriageRouterAgent.run(payload, "sess-multi-01", "trc-01")
    assert triage["redacted_payload"]["investor_pan"] == "XXXXX1234F"
    assert triage["redacted_payload"]["investor_aadhaar"] == "XXXXXXXX9012"

    # Test LiquidationOptimizerAgent
    opt = LiquidationOptimizerAgent.run(triage, "sess-multi-01", "trc-01")
    assert opt["optimal_strategy"] in ["PRO_RATA", "WATERFALL", "OPTIMIZED"]

    # Test ComplianceAuditorAgent
    aud = ComplianceAuditorAgent.run(triage, opt, "sess-multi-01", "trc-01")
    assert "nav_impact" in aud
    assert "applied_swing_factor_pct" in aud

    # Test MakerCheckerReviewerAgent
    rev = MakerCheckerReviewerAgent.run(triage, opt, aud, "sess-multi-01", "trc-01")
    assert rev["session_status"] in ["ACTIVE", "HELD"]
    assert len(rev["explanation"]) > 50

    # Test full Orchestrator
    res = Orchestrator.run_simulation(payload)
    assert res["optimal_strategy"] in ["PRO_RATA", "WATERFALL", "OPTIMIZED"]
    assert res["compliance_status"]["overall_compliant"] in [True, False]


def test_hitl_trigger_and_held_state():
    # Payload with high outflow (>15%) and high swing factor (>150 bps)
    high_stress_payload = {
        "aum": 1_000_000_000.0,
        "initial_nav": 10.0,
        "net_outflow_pct": 20.0,  # >15% triggers HITL
        "risk_o_meter": "VERY_HIGH",
        "prc_cell": "C-III",
        "portfolio_exposure": {"liquid_ratio": 0.20, "semi_liquid_ratio": 0.40, "illiquid_ratio": 0.40},
    }

    res = Orchestrator.run_simulation(high_stress_payload)
    assert res["session_status"] == "HELD"
    assert res["hitl_triggered"] is True
    assert res["hitl_ticket"] is not None
    assert res["hitl_ticket"]["status"] == "HELD"
    assert "15.0%" in res["hitl_ticket"]["reason"] or "35.0%" in res["hitl_ticket"]["reason"]


# ----------------- 4. Observability & Distributed Tracing Tests -----------------


def test_structured_json_logger():
    logger = get_structured_logger("test_structured_logger")
    assert logger is not None

    # Verify intent and outcome helper execution without errors
    log_agent_intent(
        logger=logger,
        agent_name="TestAgent",
        intent="Test intent emission",
        params={"key": "value"},
        session_id="sess-log-01",
        trace_id="trc-log-01",
    )

    log_agent_outcome(
        logger=logger,
        agent_name="TestAgent",
        status="SUCCESS",
        outcome_summary="Test outcome verified",
        latency_ms=1.23,
        session_id="sess-log-01",
        trace_id="trc-log-01",
    )


def test_opentelemetry_custom_spans():
    with custom_span("test.sync_span", {"test_key": "test_val"}) as span:
        assert span is not None
        trace_id = get_current_trace_id()
        assert len(trace_id) > 0

    @trace_span(name="test.decorated_function")
    def decorated():
        return "ok"

    assert decorated() == "ok"


# ----------------- 5. API Endpoints & HITL Decisions Tests -----------------


def test_api_redact():
    payload = {"investor_name": "Ananya Sharma", "investor_pan": "ABCDE1234F", "investor_aadhaar": "123456789012"}
    response = client.post("/api/redact", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["investor_name"].startswith("***")
    assert data["investor_pan"] == "XXXXX1234F"
    assert data["investor_aadhaar"] == "XXXXXXXX9012"


def test_api_simulate_stress_and_session_retrieval():
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

    assert "optimal_strategy" in data
    assert "nav_impact" in data
    assert "compliance_status" in data
    assert "explanation" in data
    assert "session_id" in data

    session_id = data["session_id"]

    # Test GET /api/sessions/{session_id}
    sess_res = client.get(f"/api/sessions/{session_id}")
    assert sess_res.status_code == 200
    sess_data = sess_res.json()
    assert sess_data["session"]["session_id"] == session_id
    assert len(sess_data["messages"]) >= 2


def test_api_hitl_approval_workflow():
    # 1. Trigger a HELD scenario
    payload = {
        "aum": 1_000_000_000.0,
        "initial_nav": 10.0,
        "net_outflow_pct": 18.0,  # >15% triggers HELD
        "risk_o_meter": "VERY_HIGH",
        "prc_cell": "C-III",
        "portfolio_exposure": {"liquid_ratio": 0.20, "semi_liquid_ratio": 0.40, "illiquid_ratio": 0.40},
    }

    sim_res = client.post("/api/simulate-stress", json=payload)
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert sim_data["session_status"] == "HELD"
    assert sim_data["hitl_ticket"] is not None
    appr_id = sim_data["hitl_ticket"]["approval_id"]
    sess_id = sim_data["session_id"]

    # 2. Query /api/approvals
    appr_list_res = client.get("/api/approvals")
    assert appr_list_res.status_code == 200
    appr_list = appr_list_res.json()
    assert any(a["approval_id"] == appr_id for a in appr_list)

    # 3. Approve session via /api/sessions/{session_id}/approve
    appr_res = client.post(
        f"/api/sessions/{sess_id}/approve",
        json={
            "decision": "APPROVED",
            "reviewed_by": "Chief Risk Officer",
            "comments": "Approved after reviewing liquidation impact.",
        },
    )
    assert appr_res.status_code == 200
    appr_out = appr_res.json()
    assert appr_out["approval"]["status"] == "APPROVED"

    # 4. Check session updated to APPROVED
    check_sess = client.get(f"/api/sessions/{sess_id}")
    assert check_sess.status_code == 200
    assert check_sess.json()["session"]["status"] == "APPROVED"


def test_api_traces():
    response = client.get("/api/traces?limit=20")
    assert response.status_code == 200
    traces = response.json()
    assert isinstance(traces, list)
    assert len(traces) > 0
    assert "agent_name" in traces[0]
    assert "latency_ms" in traces[0]


def test_api_config_get_post():
    # GET config
    response = client.get("/api/config")
    assert response.status_code == 200
    config_data = response.json()
    assert config_data["system_mode"] in ["MOCK", "LIVE_GCP"]

    # POST config
    config_data["partial_swing_threshold_pct"] = 7.5
    response = client.post("/api/config", json=config_data)
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["partial_swing_threshold_pct"] == 7.5


def test_api_audit_trail():
    response = client.get("/api/audit-trail")
    assert response.status_code == 200
    trail = response.json()
    assert isinstance(trail, list)
    assert len(trail) > 0
    assert "timestamp" in trail[0]
