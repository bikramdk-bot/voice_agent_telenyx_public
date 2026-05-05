from typing import TypedDict


class SubmitLeadState(TypedDict, total=False):
    orchestration_trace_id: str
    call_control_id: str
    caller_phone_number: str | None
    receiver_phone_number: str | None
    company_name: str | None
    task_description: str
    lead_ready: bool
    lead_submitted: bool
    telegram_dispatch_attempted: bool
    telegram_dispatch_attempts: int
    telegram_dispatch_succeeded: bool
    telegram_messages_sent_delta: int
    telegram_company_messages_sent_delta: int
    telegram_admin_messages_sent_delta: int
    telegram_dispatch_failures_delta: int
    delivered_chat_ids: list[str]
    function_call_output: str
    acknowledgement_message: str
    should_close: bool
    close_reason: str | None
    follow_up_instruction: str | None


class CallDecisionState(TypedDict, total=False):
    orchestration_trace_id: str
    has_user_spoken: bool
    lead_submitted: bool
    force_fast_close: bool
    should_close: bool
    close_reason: str | None
    follow_up_instruction: str | None
    closing_message: str | None