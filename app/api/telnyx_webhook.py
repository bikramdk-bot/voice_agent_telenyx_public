from fastapi import APIRouter, Request, BackgroundTasks
from app.core.config import settings
from app.core.logging import logger
from app.core.session_manager import session_manager
from app.services.telnyx_service import answer_call, start_streaming

router = APIRouter()


def _extract_phone_number(from_payload):
    if isinstance(from_payload, dict):
        return from_payload.get("phone_number") or from_payload.get("number")
    if isinstance(from_payload, str):
        return from_payload
    return None

@router.post("/webhook/telnyx")
async def telnyx_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        event_type = data.get("data", {}).get("event_type")
        payload = data.get("data", {}).get("payload", {})
        call_control_id = payload.get("call_control_id")
        caller_phone_number = _extract_phone_number(payload.get("from"))
        receiver_phone_number = _extract_phone_number(payload.get("to"))

        if call_control_id:
            session = session_manager.get_or_create(call_control_id)
            if caller_phone_number:
                session.caller_phone_number = caller_phone_number
            if receiver_phone_number:
                session.receiver_phone_number = receiver_phone_number
                session.company_name = settings.get_company_name_by_receiver_phone_number(receiver_phone_number)

        logger.info(f"Received Telnyx webhook: {event_type} for call {call_control_id}")

        if event_type == "call.initiated":
            # Answer the call
            background_tasks.add_task(answer_call, call_control_id)
            
        elif event_type == "call.answered":
            # Determine standard base url to construct websocket domain
            ws_url = settings.BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
            stream_url = f"{ws_url}/ws/media?call_id={call_control_id}"
            logger.info(f"Starting to stream audio to {stream_url}")
            background_tasks.add_task(start_streaming, call_control_id, stream_url)
            
        elif event_type == "call.hangup":
            logger.info(f"Call {call_control_id} hung up.")
            
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error handling Telnyx webhook: {e}")
        return {"status": "error"}
