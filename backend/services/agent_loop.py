"""
Autonomous Agent Tool-Calling Loop for Project 120.
Uses google-genai SDK with function calling, iterative guided error recovery,
OpenTelemetry distributed tracing, and Intent vs Outcome structured logging.
"""

import os
import time
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from config import get_current_config
from services.logger import engine_logger, log_agent_intent, log_agent_outcome
from services.math_engine import calculate_swing_factor
from services.router import AgentTaskType, ModelRouter
from services.telemetry import custom_span, get_current_trace_id
from services.tools import TOOL_REGISTRY


class AgentStepTrace(BaseModel):
    iteration: int
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    status: str
    latency_ms: float
    error_message: str | None = None


class AgentExecutionResult(BaseModel):
    session_id: str
    status: str
    model_used: str
    iterations_count: int
    final_response: str
    tool_calls_executed: list[dict[str, Any]]
    steps_trace: list[AgentStepTrace]
    total_latency_ms: float


def build_genai_tool_declarations() -> list[types.Tool]:
    """
    Constructs Google GenAI FunctionDeclarations from registered tools.
    """
    declarations = []
    for tool_meta in TOOL_REGISTRY.values():
        schema = tool_meta["schema"]
        decl = types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["parameters"],
        )
        declarations.append(decl)
    return [types.Tool(function_declarations=declarations)]


class AgentLoopRunner:
    """
    Executes autonomous LLM agent tool-calling loops with guided self-correction.
    """

    @classmethod
    async def run_agent_loop(
        cls,
        prompt: str,
        session_id: str = "default-session",
        system_instruction: str | None = None,
        task_type: AgentTaskType | str = AgentTaskType.TOOL_EXECUTION,
        model_override: str | None = None,
        max_iterations: int = 8,
        context_payload: dict[str, Any] | None = None,
    ) -> AgentExecutionResult:
        """
        Executes multi-step agent reasoning with dynamic tool dispatch and error recovery.
        """
        start_time = time.perf_counter()
        trace_id = get_current_trace_id()
        model_name = model_override or ModelRouter.get_model_for_task(task_type)
        config = get_current_config()

        system_prompt = system_instruction or (
            "You are the SEBI Mutual Fund Swing Pricing & Liquidation Engine Agent. "
            "Your objective is to analyze redemption stress scenarios, calculate Almgren-Chriss market impact, "
            "verify CEL policy compliance (PRC matrix and illiquid exposure), and trigger HITL stops if swing factor > 150 bps or net redemption > 15%. "
            "Use the provided tools to calculate impact, evaluate policies, and execute liquidations."
        )

        steps_trace: list[AgentStepTrace] = []
        executed_tool_calls: list[dict[str, Any]] = []

        log_agent_intent(
            logger=engine_logger,
            agent_name="AutonomousAgentLoop",
            intent=f"Execute agentic tool loop for task: {task_type}",
            params={"model": model_name, "max_iterations": max_iterations, "session_id": session_id},
            session_id=session_id,
            trace_id=trace_id,
        )

        with custom_span("agent_loop.execution", {"model": model_name, "session_id": session_id, "trace_id": trace_id}):
            # Check if LIVE_GCP mode is active and API key exists
            api_key = os.getenv("GEMINI_API_KEY")
            use_live_api = config.system_mode == "LIVE_GCP" and (api_key or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))

            if use_live_api:
                try:
                    result = await cls._execute_live_genai_loop(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        model_name=model_name,
                        max_iterations=max_iterations,
                        session_id=session_id,
                        trace_id=trace_id,
                        steps_trace=steps_trace,
                        executed_tool_calls=executed_tool_calls,
                    )
                    total_latency = (time.perf_counter() - start_time) * 1000.0
                    log_agent_outcome(
                        logger=engine_logger,
                        agent_name="AutonomousAgentLoop",
                        status=result.status,
                        outcome_summary=f"Completed {result.iterations_count} iterations with {len(executed_tool_calls)} tool calls.",
                        latency_ms=total_latency,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
                    return result
                except Exception as exc:
                    engine_logger.warning(
                        f"Live GenAI API encountered error: {exc}. Falling back to deterministic agent solver.",
                        extra={"trace_id": trace_id, "session_id": session_id},
                    )

            # Fallback / MOCK mode deterministic agentic loop
            result = cls._execute_mock_agent_loop(
                prompt=prompt,
                context_payload=context_payload or {},
                model_name=model_name,
                session_id=session_id,
                trace_id=trace_id,
                steps_trace=steps_trace,
                executed_tool_calls=executed_tool_calls,
            )
            total_latency = (time.perf_counter() - start_time) * 1000.0
            result.total_latency_ms = total_latency

            log_agent_outcome(
                logger=engine_logger,
                agent_name="AutonomousAgentLoop",
                status=result.status,
                outcome_summary=f"Completed deterministic tool loop ({len(executed_tool_calls)} tools invoked).",
                latency_ms=total_latency,
                session_id=session_id,
                trace_id=trace_id,
            )
            return result

    @classmethod
    async def _execute_live_genai_loop(
        cls,
        prompt: str,
        system_prompt: str,
        model_name: str,
        max_iterations: int,
        session_id: str,
        trace_id: str,
        steps_trace: list[AgentStepTrace],
        executed_tool_calls: list[dict[str, Any]],
    ) -> AgentExecutionResult:
        """
        Executes multi-turn tool calling using Google GenAI SDK Client.
        """
        client = genai.Client()
        genai_tools = build_genai_tool_declarations()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=genai_tools,
            temperature=0.1,
        )

        conversation_contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        final_text = ""
        iteration = 0
        overall_status = "COMPLETED"

        for iteration in range(1, max_iterations + 1):
            iter_start = time.perf_counter()
            with custom_span(f"agent_loop.iteration_{iteration}", {"iteration": iteration}):
                response = client.models.generate_content(
                    model=model_name,
                    contents=conversation_contents,
                    config=config,
                )

                # Check if model made function calls
                function_calls = []
                if response.candidates and response.candidates[0].content:
                    cand_content = response.candidates[0].content
                    conversation_contents.append(cand_content)
                    for part in cand_content.parts:
                        if part.function_call:
                            function_calls.append(part.function_call)
                        if part.text:
                            final_text += part.text + "\n"

                if not function_calls:
                    # Model provided final textual response
                    iter_latency = (time.perf_counter() - iter_start) * 1000.0
                    steps_trace.append(
                        AgentStepTrace(
                            iteration=iteration,
                            status="FINAL_RESPONSE",
                            latency_ms=iter_latency,
                        )
                    )
                    break

                # Dispatch and execute function calls with guided error recovery
                response_parts = []
                for fc in function_calls:
                    fn_name = fc.name
                    fn_args = dict(fc.args) if fc.args else {}
                    t_start = time.perf_counter()

                    log_agent_intent(
                        logger=engine_logger,
                        agent_name="ToolDispatcher",
                        intent=f"Execute tool {fn_name}",
                        params=fn_args,
                        session_id=session_id,
                        trace_id=trace_id,
                    )

                    try:
                        if fn_name not in TOOL_REGISTRY:
                            raise ValueError(f"Tool '{fn_name}' is not registered in TOOL_REGISTRY.")

                        tool_fn = TOOL_REGISTRY[fn_name]["function"]
                        tool_result = tool_fn(**fn_args)
                        status_str = "SUCCESS"
                        err_msg = None

                        if fn_name == "request_human_approval_overlimit":
                            overall_status = "HELD"

                    except Exception as err:
                        # Guided Error Recovery: Provide actionable diagnostic output to LLM for self-correction
                        status_str = "ERROR"
                        err_msg = str(err)
                        tool_result = {
                            "status": "error",
                            "error_type": type(err).__name__,
                            "message": err_msg,
                            "guidance": "Verify schema parameters, check numeric ranges, and re-execute.",
                        }

                    t_lat = (time.perf_counter() - t_start) * 1000.0
                    executed_tool_calls.append(
                        {
                            "tool": fn_name,
                            "args": fn_args,
                            "result": tool_result,
                            "latency_ms": t_lat,
                            "status": status_str,
                        }
                    )

                    steps_trace.append(
                        AgentStepTrace(
                            iteration=iteration,
                            tool_name=fn_name,
                            tool_args=fn_args,
                            tool_result=tool_result,
                            status=status_str,
                            latency_ms=t_lat,
                            error_message=err_msg,
                        )
                    )

                    log_agent_outcome(
                        logger=engine_logger,
                        agent_name="ToolDispatcher",
                        status=status_str,
                        outcome_summary=f"Tool {fn_name} returned {status_str}",
                        latency_ms=t_lat,
                        session_id=session_id,
                        trace_id=trace_id,
                    )

                    # Build function response part
                    response_parts.append(
                        types.Part.from_function_response(
                            name=fn_name,
                            response={"result": tool_result},
                        )
                    )

                conversation_contents.append(types.Content(role="user", parts=response_parts))

        return AgentExecutionResult(
            session_id=session_id,
            status=overall_status,
            model_used=model_name,
            iterations_count=iteration,
            final_response=final_text.strip(),
            tool_calls_executed=executed_tool_calls,
            steps_trace=steps_trace,
            total_latency_ms=0.0,
        )

    @classmethod
    def _execute_mock_agent_loop(
        cls,
        prompt: str,
        context_payload: dict[str, Any],
        model_name: str,
        session_id: str,
        trace_id: str,
        steps_trace: list[AgentStepTrace],
        executed_tool_calls: list[dict[str, Any]],
    ) -> AgentExecutionResult:
        """
        Executes a deterministic multi-step tool sequence when running in mock or offline mode.
        """
        aum = float(context_payload.get("aum", 1_000_000_000.0))
        net_outflow_pct = float(context_payload.get("net_outflow_pct", 5.0))
        risk_o_meter = context_payload.get("risk_o_meter", "VERY_HIGH")
        prc_cell = context_payload.get("prc_cell", "C-III")
        initial_nav = float(context_payload.get("initial_nav", 10.0))
        redemption_amount = aum * (net_outflow_pct / 100.0)

        portfolio_exposure = context_payload.get("portfolio_exposure", {})
        liquid_ratio = portfolio_exposure.get("liquid_ratio", 0.40)
        semi_liquid_ratio = portfolio_exposure.get("semi_liquid_ratio", 0.35)
        illiquid_ratio = portfolio_exposure.get("illiquid_ratio", 0.25)

        overall_status = "COMPLETED"

        # Step 1: Query SEBI Circular
        t0 = time.perf_counter()
        circ_res = TOOL_REGISTRY["query_sebi_swing_pricing_circular"]["function"](query_topic="prc_matrix")
        t_lat = (time.perf_counter() - t0) * 1000.0
        steps_trace.append(
            AgentStepTrace(
                iteration=1,
                tool_name="query_sebi_swing_pricing_circular",
                tool_args={"query_topic": "prc_matrix"},
                tool_result=circ_res,
                status="SUCCESS",
                latency_ms=t_lat,
            )
        )
        executed_tool_calls.append(
            {
                "tool": "query_sebi_swing_pricing_circular",
                "args": {"query_topic": "prc_matrix"},
                "result": circ_res,
                "latency_ms": t_lat,
                "status": "SUCCESS",
            }
        )

        # Step 2: Execute Liquidation Step
        t0 = time.perf_counter()
        liq_res = TOOL_REGISTRY["execute_portfolio_liquidation_step"]["function"](
            aum=aum,
            liquid_ratio=liquid_ratio,
            semi_liquid_ratio=semi_liquid_ratio,
            illiquid_ratio=illiquid_ratio,
            redemption_amount=redemption_amount,
            strategy="OPTIMIZED",
            market_dislocation_active=context_payload.get("market_dislocation_active", False),
        )
        t_lat = (time.perf_counter() - t0) * 1000.0
        steps_trace.append(
            AgentStepTrace(
                iteration=2,
                tool_name="execute_portfolio_liquidation_step",
                tool_args={"strategy": "OPTIMIZED", "redemption_amount": redemption_amount},
                tool_result=liq_res,
                status="SUCCESS",
                latency_ms=t_lat,
            )
        )
        executed_tool_calls.append(
            {
                "tool": "execute_portfolio_liquidation_step",
                "args": {"strategy": "OPTIMIZED"},
                "result": liq_res,
                "latency_ms": t_lat,
                "status": "SUCCESS",
            }
        )

        # Step 3: Calculate Almgren-Chriss Impact
        t0 = time.perf_counter()
        ac_res = TOOL_REGISTRY["calculate_almgren_chriss_market_impact"]["function"](
            asset_class="illiquid",
            liquidation_amount=liq_res["liquidated_amounts"].get("illiquid", 0.0),
            market_dislocation_active=context_payload.get("market_dislocation_active", False),
        )
        t_lat = (time.perf_counter() - t0) * 1000.0
        steps_trace.append(
            AgentStepTrace(
                iteration=3,
                tool_name="calculate_almgren_chriss_market_impact",
                tool_args={"asset_class": "illiquid"},
                tool_result=ac_res,
                status="SUCCESS",
                latency_ms=t_lat,
            )
        )
        executed_tool_calls.append(
            {
                "tool": "calculate_almgren_chriss_market_impact",
                "args": {"asset_class": "illiquid"},
                "result": ac_res,
                "latency_ms": t_lat,
                "status": "SUCCESS",
            }
        )

        # Step 4: Evaluate CEL Policies
        t0 = time.perf_counter()
        swing_factor_pct, _ = calculate_swing_factor(context_payload, get_current_config().model_dump())
        cel_payload = {
            "risk_o_meter": risk_o_meter,
            "prc_cell": prc_cell,
            "net_outflow_pct": net_outflow_pct,
            "swing_pricing_active": swing_factor_pct > 0,
            "applied_swing_factor_pct": swing_factor_pct,
            "portfolio_exposure": {"illiquid_ratio": liq_res["post_liquidation_exposure"]["illiquid_ratio"]},
            "investor_aadhaar": context_payload.get("investor_aadhaar", ""),
            "investor_pan": context_payload.get("investor_pan", ""),
            "investor_name": context_payload.get("investor_name", ""),
        }
        cel_res = TOOL_REGISTRY["evaluate_cel_compliance_policy"]["function"](policy_name="all", payload=cel_payload)
        t_lat = (time.perf_counter() - t0) * 1000.0
        steps_trace.append(
            AgentStepTrace(
                iteration=4,
                tool_name="evaluate_cel_compliance_policy",
                tool_args={"policy_name": "all"},
                tool_result=cel_res,
                status="SUCCESS",
                latency_ms=t_lat,
            )
        )
        executed_tool_calls.append(
            {
                "tool": "evaluate_cel_compliance_policy",
                "args": {"policy_name": "all"},
                "result": cel_res,
                "latency_ms": t_lat,
                "status": "SUCCESS",
            }
        )

        # Step 5: HITL Evaluation (> 150 bps or > 15% outflow)
        swing_factor_bps = swing_factor_pct * 100.0
        swung_nav = initial_nav * (1.0 - swing_factor_pct / 100.0)
        post_illiquid = liq_res["post_liquidation_exposure"]["illiquid_ratio"]

        if swing_factor_bps > 150.0 or net_outflow_pct > 15.0 or post_illiquid > 0.35:
            overall_status = "HELD"
            t0 = time.perf_counter()
            reason = f"High stress trigger: Swing Factor = {swing_factor_bps:.1f} bps, Outflow = {net_outflow_pct:.1f}%, Post-Illiquid = {post_illiquid * 100:.1f}%."
            hitl_res = TOOL_REGISTRY["request_human_approval_overlimit"]["function"](
                session_id=session_id,
                reason=reason,
                swing_factor_bps=swing_factor_bps,
                redemption_pct=net_outflow_pct,
                post_illiquid_ratio=post_illiquid,
                current_nav=initial_nav,
                swung_nav=swung_nav,
            )
            t_lat = (time.perf_counter() - t0) * 1000.0
            steps_trace.append(
                AgentStepTrace(
                    iteration=5,
                    tool_name="request_human_approval_overlimit",
                    tool_args={"reason": reason},
                    tool_result=hitl_res,
                    status="HELD",
                    latency_ms=t_lat,
                )
            )
            executed_tool_calls.append(
                {
                    "tool": "request_human_approval_overlimit",
                    "args": {"reason": reason},
                    "result": hitl_res,
                    "latency_ms": t_lat,
                    "status": "HELD",
                }
            )

        final_response = (
            f"### Multi-Agent Autonomous Adjudication Summary\n\n"
            f"- **Status:** {overall_status}\n"
            f"- **Optimal Liquidation Strategy:** OPTIMIZED (Transaction Cost: INR {liq_res['transaction_costs']['total_inr']:,.2f})\n"
            f"- **Applied Swing Factor:** {swing_factor_pct:.2f}% ({swing_factor_bps:.1f} bps)\n"
            f"- **Pre-Swing NAV:** INR {initial_nav:.4f} | **Swung NAV:** INR {swung_nav:.4f}\n"
            f"- **Post-Liquidation Illiquid Exposure:** {post_illiquid * 100:.2f}%\n"
            f"- **SEBI Compliance Verdict:** {'COMPLIANT' if cel_res.get('is_compliant') else 'NON-COMPLIANT'}\n"
        )

        return AgentExecutionResult(
            session_id=session_id,
            status=overall_status,
            model_used=model_name,
            iterations_count=len(steps_trace),
            final_response=final_response,
            tool_calls_executed=executed_tool_calls,
            steps_trace=steps_trace,
            total_latency_ms=0.0,
        )
