"""
This file is reserved for defining specific Pydantic schemas
used to extract the lead task from the user.

Currently, extraction is directly configured via OpenAI
function parameter schema in the websocket stream setup.
"""

from pydantic import BaseModel, Field

class LeadExtraction(BaseModel):
    task_description: str = Field(..., description="The main task the caller wants done.")
