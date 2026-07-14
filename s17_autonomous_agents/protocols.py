"""s17 protocols.py — 团队结构化协议"""
import json, os, time, uuid
class ProtocolState:
    def __init__(self):
        self.requests: dict[str, dict] = {}
    def create_request(self, rtype, data):
        rid = str(uuid.uuid4())[:8]
        self.requests[rid] = {"type": rtype, "data": data, "status": "pending", "response": None}
        return rid
    def respond(self, rid, approve=True):
        if rid in self.requests:
            self.requests[rid]["status"] = "approved" if approve else "rejected"
            self.requests[rid]["response"] = "approved" if approve else "rejected"

def dispatch_message(msg, protocol_state):
    mtype = msg.get("type", "")
    if mtype == "shutdown_request":
        protocol_state.create_request("shutdown", msg)
        return "shutdown_request_created"
    elif mtype == "plan_approval":
        protocol_state.create_request("plan_approval", msg)
        return "plan_approval_created"
    return "unknown_type"

def match_response(response, request):
    rtype = request.get("type")
    rtype2 = response.get("type", "")
    if rtype == "shutdown" and rtype2 == "shutdown_response":
        return response.get("approve")
    if rtype == "plan_approval" and rtype2 == "plan_approval_response":
        return response.get("approve")
    return None
