from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

class CallState(BaseModel):
    call_control_id: str
    call_started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    call_finished_at: Optional[datetime] = None
    caller_phone_number: Optional[str] = None
    receiver_phone_number: Optional[str] = None
    company_name: Optional[str] = None
    task_description: Optional[str] = None
    lead_submitted: bool = False
    openai_total_tokens: int = 0
    openai_input_tokens: int = 0
    openai_output_tokens: int = 0
    openai_text_input_tokens: int = 0
    openai_audio_input_tokens: int = 0
    openai_text_output_tokens: int = 0
    openai_audio_output_tokens: int = 0
    telegram_messages_sent: int = 0
    telegram_company_messages_sent: int = 0
    telegram_admin_messages_sent: int = 0
    urgency: Optional[str] = None
    trade_category: Optional[str] = None
    confidence: float = 0.0
    turns: int = 0
    ended: bool = False
