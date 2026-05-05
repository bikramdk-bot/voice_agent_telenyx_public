from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.logging import logger
from .nodes import (
    acknowledge_completion,
    decide_close,
    dispatch_lead,
    evaluate_call_decision,
    ingest_realtime_event,
    request_follow_up,
    route_lead_readiness,
)
from .state import CallDecisionState, SubmitLeadState
from app.services.dashboard_service import record_orchestration_event


TRACE_KEYS = {
    "call_control_id",
    "lead_ready",
    "lead_submitted",
    "telegram_dispatch_attempted",
    "telegram_dispatch_attempts",
    "telegram_dispatch_succeeded",
    "telegram_dispatch_failures_delta",
    "telegram_messages_sent_delta",
    "should_close",
    "close_reason",
    "has_user_spoken",
    "force_fast_close",
}


def _trace_enabled() -> bool:
    return settings.ORCHESTRATION_TRACE_ENABLED


def _snapshot_state(state: dict) -> dict:
    if settings.ORCHESTRATION_TRACE_INCLUDE_STATE:
        return dict(state)
    return {key: state[key] for key in TRACE_KEYS if key in state}


def _trace(graph_name: str, event: str, trace_id: str, payload: dict) -> None:
    if not _trace_enabled():
        return
    record_orchestration_event(graph_name, event, trace_id, payload)
    logger.info(
        "orchestration_trace graph=%s event=%s trace_id=%s payload=%s",
        graph_name,
        event,
        trace_id,
        payload,
    )


def _instrument_node(graph_name: str, node_name: str, node_fn):
    async def wrapped(state):
        trace_id = state.get("orchestration_trace_id", "unknown")
        _trace(graph_name, f"node_start:{node_name}", trace_id, _snapshot_state(state))
        result = await node_fn(state)
        _trace(graph_name, f"node_end:{node_name}", trace_id, _snapshot_state(result))
        return result

    return wrapped


def _instrument_router(graph_name: str, router_name: str, router_fn):
    def wrapped(state):
        trace_id = state.get("orchestration_trace_id", "unknown")
        decision = router_fn(state)
        _trace(
            graph_name,
            f"route:{router_name}",
            trace_id,
            {
                **_snapshot_state(state),
                "decision": decision,
            },
        )
        return decision

    return wrapped


def _build_submit_lead_graph():
    graph = StateGraph(SubmitLeadState)
    graph.add_node("ingest_realtime_event", _instrument_node("submit_lead", "ingest_realtime_event", ingest_realtime_event))
    graph.add_node("dispatch_lead", _instrument_node("submit_lead", "dispatch_lead", dispatch_lead))
    graph.add_node("request_follow_up", _instrument_node("submit_lead", "request_follow_up", request_follow_up))
    graph.add_node("acknowledge_completion", _instrument_node("submit_lead", "acknowledge_completion", acknowledge_completion))
    graph.add_node("decide_close", _instrument_node("submit_lead", "decide_close", decide_close))

    graph.add_edge(START, "ingest_realtime_event")
    graph.add_conditional_edges(
        "ingest_realtime_event",
        _instrument_router("submit_lead", "lead_readiness", route_lead_readiness),
        {
            "dispatch_lead": "dispatch_lead",
            "request_follow_up": "request_follow_up",
        },
    )
    graph.add_edge("dispatch_lead", "acknowledge_completion")
    graph.add_edge("acknowledge_completion", "decide_close")
    graph.add_edge("request_follow_up", END)
    graph.add_edge("decide_close", END)
    return graph.compile()


submit_lead_graph = _build_submit_lead_graph()


def _build_call_decision_graph():
    graph = StateGraph(CallDecisionState)
    graph.add_node("evaluate_call_decision", _instrument_node("call_decision", "evaluate_call_decision", evaluate_call_decision))
    graph.add_edge(START, "evaluate_call_decision")
    graph.add_edge("evaluate_call_decision", END)
    return graph.compile()


call_decision_graph = _build_call_decision_graph()


async def run_submit_lead_orchestration(state: SubmitLeadState) -> SubmitLeadState:
    trace_id = uuid4().hex[:12]
    traced_state = {
        **state,
        "orchestration_trace_id": trace_id,
    }
    _trace("submit_lead", "graph_start", trace_id, _snapshot_state(traced_state))
    result = await submit_lead_graph.ainvoke(traced_state)
    _trace("submit_lead", "graph_end", trace_id, _snapshot_state(result))
    return result


async def run_call_decision_orchestration(state: CallDecisionState) -> CallDecisionState:
    trace_id = uuid4().hex[:12]
    traced_state = {
        **state,
        "orchestration_trace_id": trace_id,
    }
    _trace("call_decision", "graph_start", trace_id, _snapshot_state(traced_state))
    result = await call_decision_graph.ainvoke(traced_state)
    _trace("call_decision", "graph_end", trace_id, _snapshot_state(result))
    return result