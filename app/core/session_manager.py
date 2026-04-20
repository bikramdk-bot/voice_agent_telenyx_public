from typing import Dict
from app.agent.state import CallState

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, CallState] = {}
        
    def get_or_create(self, call_control_id: str) -> CallState:
        if call_control_id not in self.sessions:
            self.sessions[call_control_id] = CallState(call_control_id=call_control_id)
        return self.sessions[call_control_id]
        
    def get(self, call_control_id: str) -> CallState:
        return self.sessions.get(call_control_id)
        
    def delete(self, call_control_id: str):
        if call_control_id in self.sessions:
            del self.sessions[call_control_id]

session_manager = SessionManager()
