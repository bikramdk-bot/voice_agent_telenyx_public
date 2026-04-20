import asyncio
import base64
import json
from datetime import datetime, timezone

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.prompt import SYSTEM_PROMPT
from app.core.config import settings
from app.core.logging import logger
from app.core.session_manager import session_manager
from app.services.metrics_service import record_call_metrics
from app.services.telegram_service import send_telegram_message
from app.services.telnyx_service import hangup_call

router = APIRouter()

OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-1.5"
PCMU_SAMPLE_RATE = 8000
PCMU_FRAME_DURATION_MS = 20
PCMU_BYTES_PER_FRAME = int(PCMU_SAMPLE_RATE * (PCMU_FRAME_DURATION_MS / 1000))
WELCOME_MESSAGE = "Hej. Vi har travlt lige nu. Fortael kort om din opgave."
ACKNOWLEDGEMENT_MESSAGE = "Tak. Din opgave er registreret og sendt videre til den relevante modtager."
CLOSING_MESSAGE = "Tak for din besked. Din opgave er registreret og bliver sendt videre til den relevante modtager."
SILENCE_TIMEOUT_SECONDS = 6
MAX_CALL_DURATION_SECONDS = 50
LONG_SPEECH_SECONDS = 28
CLOSING_GRACE_SECONDS = 1.2


def _decode_base64_audio(payload: str) -> bytes:
    try:
        return base64.b64decode(payload)
    except Exception as exc:
        logger.warning(f"Failed to decode audio payload from OpenAI: {exc}")
        return b""


def _encode_base64_audio(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _extract_phone_number(from_payload) -> str | None:
    if isinstance(from_payload, dict):
        return from_payload.get("phone_number") or from_payload.get("number")
    if isinstance(from_payload, str):
        return from_payload
    return None


async def setup_openai_session(openai_ws):
    session_update = {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "instructions": SYSTEM_PROMPT,
            "voice": "alloy",
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 500,
                "silence_duration_ms": 600,
            },
            "tools": [
                {
                    "type": "function",
                    "name": "submit_lead",
                    "description": "Call this as soon as you have a short task description from the caller.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {"type": "string"},
                        },
                        "required": ["task_description"],
                    },
                }
            ],
            "tool_choice": "auto",
        },
    }
    await openai_ws.send(json.dumps(session_update))


@router.websocket("/ws/media")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    call_control_id = websocket.query_params.get("call_id")
    session = session_manager.get_or_create(call_control_id) if call_control_id else None
    logger.info(f"WebSocket connected for call {call_control_id}")
    stream_id = None
    greeting_sent = False
    assistant_speaking = False
    caller_speaking = False
    current_response_has_audio = False
    current_response_mark_sent = False
    pending_mark_names = set()
    outbound_audio_buffer = bytearray()
    telnyx_send_lock = asyncio.Lock()
    openai_send_lock = asyncio.Lock()
    last_activity_at = datetime.now(timezone.utc)
    caller_speech_started_at = None
    hangup_requested = False
    closing_started = False
    closing_started_at = None
    has_user_spoken = False

    def mark_activity() -> None:
        nonlocal last_activity_at
        last_activity_at = datetime.now(timezone.utc)

    async def send_to_telnyx(message: dict):
        async with telnyx_send_lock:
            await websocket.send_text(json.dumps(message))

    async def send_to_openai(message: dict):
        async with openai_send_lock:
            await openai_ws.send(json.dumps(message))

    async def request_hangup(reason: str) -> None:
        nonlocal hangup_requested
        if hangup_requested or not call_control_id:
            return
        hangup_requested = True
        if session:
            session.ended = True
        logger.info(f"Ending call {call_control_id}: {reason}")
        asyncio.create_task(hangup_call(call_control_id))

    async def send_scripted_response(text: str) -> None:
        await send_to_openai(
            {
                "type": "response.create",
                "response": {
                    "instructions": f'Say exactly this in Danish and nothing else: "{text}"',
                    "modalities": ["audio", "text"],
                },
            }
        )

    async def prompt_model_to_finish(force_fast_close: bool = False) -> None:
        extra_instruction = (
            "The caller has already spoken for a while. Avoid any further follow-up unless it is absolutely required."
            if force_fast_close
            else ""
        )
        await send_to_openai(
            {
                "type": "response.create",
                "response": {
                    "instructions": (
                        "Continue the call briefly. If the task is clear enough, call submit_lead immediately. "
                        "If the request is still too vague to route, ask one very short follow-up question only. "
                        "Never ask for address, location, or other extra details. "
                        f"{extra_instruction}"
                    ).strip(),
                    "modalities": ["audio", "text"],
                },
            }
        )

    async def start_closing(text: str) -> None:
        nonlocal closing_started, closing_started_at
        if closing_started:
            return
        closing_started = True
        closing_started_at = datetime.now(timezone.utc)
        mark_activity()
        await send_scripted_response(text)

    async def flush_outbound_audio(send_mark: bool = False):
        nonlocal assistant_speaking

        if not outbound_audio_buffer:
            if send_mark:
                mark_name = f"response-{len(pending_mark_names) + 1}"
                pending_mark_names.add(mark_name)
                await send_to_telnyx({"event": "mark", "mark": {"name": mark_name}})
            return

        while len(outbound_audio_buffer) >= PCMU_BYTES_PER_FRAME:
            chunk = bytes(outbound_audio_buffer[:PCMU_BYTES_PER_FRAME])
            del outbound_audio_buffer[:PCMU_BYTES_PER_FRAME]
            await send_to_telnyx({
                "event": "media",
                "media": {"payload": _encode_base64_audio(chunk)},
            })

        if outbound_audio_buffer:
            padded_chunk = bytes(outbound_audio_buffer) + (b"\xff" * (PCMU_BYTES_PER_FRAME - len(outbound_audio_buffer)))
            outbound_audio_buffer.clear()
            await send_to_telnyx({
                "event": "media",
                "media": {"payload": _encode_base64_audio(padded_chunk)},
            })

        if send_mark:
            mark_name = f"response-{len(pending_mark_names) + 1}"
            pending_mark_names.add(mark_name)
            await send_to_telnyx({"event": "mark", "mark": {"name": mark_name}})
        else:
            assistant_speaking = True

    async def enforce_call_limits() -> None:
        while not hangup_requested:
            await asyncio.sleep(0.5)
            if not session:
                continue

            elapsed_seconds = (datetime.now(timezone.utc) - session.call_started_at).total_seconds()
            if elapsed_seconds >= MAX_CALL_DURATION_SECONDS:
                await request_hangup("hard cutoff reached")
                return

            idle_seconds = (datetime.now(timezone.utc) - last_activity_at).total_seconds()
            if closing_started:
                closing_elapsed_seconds = (
                    (datetime.now(timezone.utc) - closing_started_at).total_seconds()
                    if closing_started_at
                    else 0.0
                )
                if (
                    not assistant_speaking
                    and not caller_speaking
                    and not pending_mark_names
                    and closing_elapsed_seconds >= CLOSING_GRACE_SECONDS
                ):
                    await request_hangup("closing finished")
                    return
                continue

            if idle_seconds < SILENCE_TIMEOUT_SECONDS or assistant_speaking or caller_speaking:
                continue

            if has_user_spoken and not session.lead_submitted:
                await prompt_model_to_finish(force_fast_close=True)
                mark_activity()
                continue

            await start_closing(CLOSING_MESSAGE)

    try:
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }
        async with websockets.connect(OPENAI_WS_URL, additional_headers=headers) as openai_ws:
            await setup_openai_session(openai_ws)
            monitor_task = asyncio.create_task(enforce_call_limits())

            async def receive_from_telnyx():
                nonlocal assistant_speaking, greeting_sent, stream_id
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)

                        if data.get("event") != "media":
                            logger.info(f"Telnyx event: {data.get('event')} - {data}")

                        if data.get("event") == "start":
                            stream_id = data.get("stream_id")
                            start_data = data.get("start", {})
                            media_format = start_data.get("media_format", {})
                            caller_phone_number = _extract_phone_number(start_data.get("from"))
                            receiver_phone_number = _extract_phone_number(start_data.get("to"))
                            if session and caller_phone_number and not session.caller_phone_number:
                                session.caller_phone_number = caller_phone_number
                            if session and receiver_phone_number:
                                session.receiver_phone_number = receiver_phone_number
                                session.company_name = settings.get_company_name_by_receiver_phone_number(receiver_phone_number)
                            logger.info(f"Captured Telnyx stream_id {stream_id} with media format {media_format}")
                            if not greeting_sent:
                                greeting_sent = True
                                mark_activity()
                                await send_scripted_response(WELCOME_MESSAGE)

                        elif data.get("event") == "media":
                            media_data = data.get("media", {})
                            track = media_data.get("track")
                            payload = media_data.get("payload")

                            if track and track != "inbound":
                                continue

                            if payload:
                                mark_activity()
                                await send_to_openai({"type": "input_audio_buffer.append", "audio": payload})

                        elif data.get("event") == "mark":
                            mark_name = data.get("mark", {}).get("name")
                            if mark_name in pending_mark_names:
                                pending_mark_names.remove(mark_name)
                            if not pending_mark_names:
                                assistant_speaking = False
                                mark_activity()

                        elif data.get("event") == "error":
                            logger.error(f"Telnyx stream error for {call_control_id}: {data}")
                except WebSocketDisconnect:
                    logger.info("Telnyx disconnected.")
                except Exception as exc:
                    logger.error(f"Error receiving from Telnyx: {exc}")

            async def receive_from_openai():
                nonlocal assistant_speaking, caller_speaking, caller_speech_started_at
                nonlocal current_response_has_audio, current_response_mark_sent, has_user_spoken
                try:
                    while True:
                        message = await openai_ws.recv()
                        data = json.loads(message)

                        if data.get("type") != "response.audio.delta":
                            logger.info(f"OpenAI event: {data.get('type')} - {data}")

                        if data.get("type") == "response.audio.delta":
                            base64_audio = data.get("delta")
                            if base64_audio and stream_id:
                                audio_chunk = _decode_base64_audio(base64_audio)
                                if audio_chunk:
                                    mark_activity()
                                    assistant_speaking = True
                                    current_response_has_audio = True
                                    current_response_mark_sent = False
                                    outbound_audio_buffer.extend(audio_chunk)

                                    while len(outbound_audio_buffer) >= PCMU_BYTES_PER_FRAME:
                                        chunk = bytes(outbound_audio_buffer[:PCMU_BYTES_PER_FRAME])
                                        del outbound_audio_buffer[:PCMU_BYTES_PER_FRAME]
                                        await send_to_telnyx({
                                            "event": "media",
                                            "media": {"payload": _encode_base64_audio(chunk)},
                                        })

                        elif data.get("type") == "response.audio.done":
                            if current_response_has_audio and not current_response_mark_sent:
                                await flush_outbound_audio(send_mark=True)
                                current_response_mark_sent = True

                        elif data.get("type") == "response.done":
                            mark_activity()
                            response_payload = data.get("response", {})
                            usage = response_payload.get("usage") or {}
                            if session and usage:
                                input_token_details = usage.get("input_token_details", {})
                                output_token_details = usage.get("output_token_details", {})
                                session.openai_total_tokens += int(usage.get("total_tokens") or 0)
                                session.openai_input_tokens += int(usage.get("input_tokens") or 0)
                                session.openai_output_tokens += int(usage.get("output_tokens") or 0)
                                session.openai_text_input_tokens += int(input_token_details.get("text_tokens") or 0)
                                session.openai_audio_input_tokens += int(input_token_details.get("audio_tokens") or 0)
                                session.openai_text_output_tokens += int(output_token_details.get("text_tokens") or 0)
                                session.openai_audio_output_tokens += int(output_token_details.get("audio_tokens") or 0)

                            if current_response_has_audio and not current_response_mark_sent:
                                await flush_outbound_audio(send_mark=True)
                            current_response_has_audio = False
                            current_response_mark_sent = False

                        elif data.get("type") == "input_audio_buffer.speech_started":
                            mark_activity()
                            caller_speaking = True
                            has_user_spoken = True
                            caller_speech_started_at = datetime.now(timezone.utc)
                            if session:
                                session.turns += 1
                            if assistant_speaking:
                                logger.info("Caller speech detected while assistant audio was active. Clearing queued Telnyx audio.")
                                outbound_audio_buffer.clear()
                                pending_mark_names.clear()
                                assistant_speaking = False
                                current_response_has_audio = False
                                current_response_mark_sent = False
                                await send_to_telnyx({"event": "clear"})
                                await send_to_openai({"type": "response.cancel"})

                        elif data.get("type") == "input_audio_buffer.speech_stopped":
                            mark_activity()
                            caller_speaking = False
                            if caller_speech_started_at and not closing_started and session and not session.lead_submitted:
                                speech_seconds = (datetime.now(timezone.utc) - caller_speech_started_at).total_seconds()
                                if speech_seconds >= LONG_SPEECH_SECONDS:
                                    await prompt_model_to_finish(force_fast_close=True)
                            caller_speech_started_at = None

                        elif data.get("type") == "response.function_call_arguments.done" and data.get("name") == "submit_lead":
                            args = json.loads(data.get("arguments", "{}"))
                            task = (args.get("task_description") or "").strip()
                            caller_phone_number = session.caller_phone_number if session else None
                            receiver_phone_number = session.receiver_phone_number if session else None
                            company_name = session.company_name if session else None
                            if session:
                                session.task_description = task
                                session.lead_submitted = True
                            logger.info(f"Lead extracted - Task: {task}")
                            call_id = data.get("call_id")

                            msg = (
                                "🚨 New Voice Lead\n\n"
                                f"Company: {company_name or 'Unknown'}\n"
                                f"Receiver: {receiver_phone_number or 'Unknown'}\n"
                                f"Caller: {caller_phone_number or 'Unknown'}\n"
                                f"Task: {task}"
                            )
                            delivered_chat_ids = await send_telegram_message(msg, company_name=company_name)
                            if session:
                                session.telegram_messages_sent += len(delivered_chat_ids)
                                company_chat_id = settings.get_company_chat_id(company_name)
                                admin_chat_id = settings.get_admin_chat_id()
                                session.telegram_company_messages_sent += delivered_chat_ids.count(company_chat_id) if company_chat_id else 0
                                session.telegram_admin_messages_sent += delivered_chat_ids.count(admin_chat_id) if admin_chat_id else 0

                            if call_id:
                                await send_to_openai(
                                    {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "function_call_output",
                                            "call_id": call_id,
                                            "output": "Lead submitted successfully. End the call after a short acknowledgement.",
                                        },
                                    }
                                )
                            await start_closing(ACKNOWLEDGEMENT_MESSAGE)

                except websockets.exceptions.ConnectionClosed:
                    logger.info("OpenAI WS closed")
                except Exception as exc:
                    logger.error(f"Error receiving from OpenAI: {exc}")

            try:
                await asyncio.gather(receive_from_telnyx(), receive_from_openai())
            finally:
                monitor_task.cancel()

    except Exception as exc:
        logger.error(f"Failed to connect to OpenAI Realtime: {exc}")
    finally:
        if session:
            session.call_finished_at = datetime.now(timezone.utc)
            record_call_metrics(session)
        session_manager.delete(call_control_id)
        logger.info(f"Session cleaned up for {call_control_id}")
