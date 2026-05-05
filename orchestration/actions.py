from app.core.config import settings
from app.core.logging import logger
from app.services.telegram_service import send_telegram_message
from .state import SubmitLeadState


MAX_TELEGRAM_DISPATCH_ATTEMPTS = 2


def build_lead_message(state: SubmitLeadState) -> str:
    return (
        "🚨 New Voice Lead\n\n"
        f"Company: {state.get('company_name') or 'Unknown'}\n"
        f"Receiver: {state.get('receiver_phone_number') or 'Unknown'}\n"
        f"Caller: {state.get('caller_phone_number') or 'Unknown'}\n"
        f"Task: {state.get('task_description') or 'Unknown'}"
    )


async def dispatch_lead_message(state: SubmitLeadState) -> SubmitLeadState:
    delivered_chat_ids: list[str] = []
    attempts = 0
    while attempts < MAX_TELEGRAM_DISPATCH_ATTEMPTS and not delivered_chat_ids:
        attempts += 1
        logger.info(
            "Dispatching Telegram lead for call %s (attempt %s/%s)",
            state.get("call_control_id"),
            attempts,
            MAX_TELEGRAM_DISPATCH_ATTEMPTS,
        )
        delivered_chat_ids = await send_telegram_message(
            build_lead_message(state),
            company_name=state.get("company_name"),
        )
        if delivered_chat_ids:
            break
        if attempts < MAX_TELEGRAM_DISPATCH_ATTEMPTS:
            logger.warning(
                "Telegram lead dispatch returned no recipients for call %s; retrying.",
                state.get("call_control_id"),
            )

    company_chat_id = settings.get_company_chat_id(state.get("company_name"))
    admin_chat_id = settings.get_admin_chat_id()
    dispatch_failures = 0 if delivered_chat_ids else 1
    if dispatch_failures:
        logger.error(
            "Telegram lead dispatch failed after %s attempt(s) for call %s.",
            attempts,
            state.get("call_control_id"),
        )

    return {
        "telegram_dispatch_attempted": True,
        "telegram_dispatch_attempts": attempts,
        "telegram_dispatch_succeeded": bool(delivered_chat_ids),
        "delivered_chat_ids": delivered_chat_ids,
        "telegram_messages_sent_delta": len(delivered_chat_ids),
        "telegram_company_messages_sent_delta": delivered_chat_ids.count(company_chat_id) if company_chat_id else 0,
        "telegram_admin_messages_sent_delta": delivered_chat_ids.count(admin_chat_id) if admin_chat_id else 0,
        "telegram_dispatch_failures_delta": dispatch_failures,
    }