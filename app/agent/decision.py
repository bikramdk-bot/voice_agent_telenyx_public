"""
Decision Engine.

This component handles mid-call decisions such as whether 
we have gathered enough data to end the call, or if we need 
to route to a special fallback. 

Since OpenAI Realtime logic inherently handles natural flow, 
this serves as a server-side hard override (e.g. max turns reached).
"""

from app.agent.state import CallState

def should_end_call(state: CallState) -> bool:
    """End call once the task is captured or the conversation runs too long."""
    if state.task_description:
        return True
    if state.turns > 2:
        return True
    return False
