import aiohttp
import base64
from app.core.config import settings
from app.core.logging import logger

TELNYX_BASE_URL = "https://api.telnyx.com/v2"

async def _send_call_action(call_control_id: str, action: str, payload: dict):
    url = f"{TELNYX_BASE_URL}/calls/{call_control_id}/actions/{action}"
    headers = {
        "Authorization": f"Bearer {settings.TELNYX_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status not in (200, 202):
                    resp_text = await response.text()
                    logger.error(f"Telnyx action '{action}' failed for {call_control_id}: {resp_text}")
                    return False
                return True
    except Exception as e:
        logger.error(f"Exception in Telnyx '{action}' for {call_control_id}: {e}")
        return False

async def answer_call(call_control_id: str, client_state: str = None):
    payload = {}
    if client_state:
        # Telnyx expects base64 encoded client_state in some endpoints, but plain string in others. Let's use plain string if it accepts string.
        payload["client_state"] = base64.b64encode(client_state.encode('utf-8')).decode('utf-8')
    return await _send_call_action(call_control_id, "answer", payload)

async def start_streaming(call_control_id: str, stream_url: str, client_state: str = None):
    payload = {
        "stream_url": stream_url,
        "stream_track": "both_tracks",
        "stream_bidirectional_mode": "rtp",
        "stream_bidirectional_codec": "PCMU"
    }
    if client_state:
        payload["client_state"] = base64.b64encode(client_state.encode('utf-8')).decode('utf-8')
    return await _send_call_action(call_control_id, "streaming_start", payload)

async def hangup_call(call_control_id: str, client_state: str = None):
    payload = {}
    if client_state:
        payload["client_state"] = base64.b64encode(client_state.encode('utf-8')).decode('utf-8')
    return await _send_call_action(call_control_id, "hangup", payload)
