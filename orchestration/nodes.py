from .actions import dispatch_lead_message
from .state import CallDecisionState, SubmitLeadState

ACKNOWLEDGEMENT_MESSAGE = "Tak. Din opgave er registreret og sendt videre til den relevante modtager."
CLOSING_MESSAGE = "Tak for din besked. Din opgave er registreret og bliver sendt videre til den relevante modtager."


async def ingest_realtime_event(state: SubmitLeadState) -> SubmitLeadState:
    task_description = (state.get("task_description") or "").strip()
    return {
        "task_description": task_description,
        "lead_ready": bool(task_description),
    }


def route_lead_readiness(state: SubmitLeadState) -> str:
    if state.get("lead_ready"):
        return "dispatch_lead"
    return "request_follow_up"


async def dispatch_lead(state: SubmitLeadState) -> SubmitLeadState:
    if state.get("lead_submitted"):
        return {
            "function_call_output": "Lead was already submitted. End the call after a short acknowledgement.",
            "acknowledgement_message": ACKNOWLEDGEMENT_MESSAGE,
            "should_close": True,
            "close_reason": "lead already submitted",
            "telegram_dispatch_attempted": False,
            "telegram_dispatch_attempts": 0,
            "telegram_dispatch_succeeded": True,
            "telegram_messages_sent_delta": 0,
            "telegram_company_messages_sent_delta": 0,
            "telegram_admin_messages_sent_delta": 0,
            "telegram_dispatch_failures_delta": 0,
        }

    dispatch_result = await dispatch_lead_message(state)
    return {
        **dispatch_result,
        "lead_submitted": True,
    }


async def request_follow_up(state: SubmitLeadState) -> SubmitLeadState:
    return {
        "function_call_output": (
            "Task description was too short to route. Continue the call and ask one very short follow-up question in Danish. "
            "Do not ask for address or location details."
        ),
        "follow_up_instruction": (
            "Continue the call briefly. Ask one very short follow-up question in Danish only if needed to understand the task. "
            "Do not ask for address, location, or other extra details."
        ),
        "should_close": False,
        "close_reason": None,
    }


async def acknowledge_completion(state: SubmitLeadState) -> SubmitLeadState:
    if state.get("function_call_output"):
        return {
            "function_call_output": state["function_call_output"],
            "acknowledgement_message": state.get("acknowledgement_message", ACKNOWLEDGEMENT_MESSAGE),
        }

    if state.get("telegram_dispatch_succeeded"):
        return {
            "function_call_output": "Lead submitted successfully. End the call after a short acknowledgement.",
            "acknowledgement_message": ACKNOWLEDGEMENT_MESSAGE,
        }

    return {
        "function_call_output": "Lead captured but downstream delivery failed. End the call after a short acknowledgement.",
        "acknowledgement_message": ACKNOWLEDGEMENT_MESSAGE,
    }


async def decide_close(state: SubmitLeadState) -> SubmitLeadState:
    return {
        "should_close": True,
        "close_reason": "lead flow complete",
    }


async def evaluate_call_decision(state: CallDecisionState) -> CallDecisionState:
    if state.get("has_user_spoken") and not state.get("lead_submitted"):
        extra_instruction = (
            " The caller has already spoken for a while. Avoid any further follow-up unless it is absolutely required."
            if state.get("force_fast_close")
            else ""
        )
        return {
            "should_close": False,
            "close_reason": None,
            "follow_up_instruction": (
                "Continue the call briefly. If the task is clear enough, call submit_lead immediately. "
                "If the request is still too vague to route, ask one very short follow-up question only. "
                "Never ask for address, location, or other extra details."
                f"{extra_instruction}"
            ),
        }

    return {
        "should_close": True,
        "close_reason": "silence timeout",
        "closing_message": CLOSING_MESSAGE,
        "follow_up_instruction": f'Say exactly this in Danish and nothing else: "{CLOSING_MESSAGE}"',
    }