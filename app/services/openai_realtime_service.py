"""
This is an abstraction layer for OpenAI Realtime API.
At the moment, bidirectional streaming is handled natively 
in `app/ws/telnyx_stream.py`.

Configurations specific to the OpenAI realtime connection 
are kept here if needed.
"""

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-1.5"

def build_session_update_event(instructions: str) -> dict:
    return {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "instructions": instructions,
            "voice": "alloy",
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 600
            },
            "tools": [
                {
                    "type": "function",
                    "name": "submit_lead",
                    "description": "Call this as soon as you have a short task description from the caller.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {"type": "string"}
                        },
                        "required": ["task_description"]
                    }
                }
            ],
            "tool_choice": "auto"
        }
    }
