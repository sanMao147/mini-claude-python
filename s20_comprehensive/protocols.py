"""s20 protocols.py — 团队结构化协议"""
import json, os, time, uuid
# protocols.py 用来描述“团队协作消息”的结构化协议。
# 当前实现偏模拟：保存请求状态、根据消息 type 分发、把 response 匹配回 request。

class ProtocolState:
    """保存等待审批/响应的协议请求。"""
    def __init__(self):
        # requests 以 rid 为 key，value 保存 type、data、status 和 response。
        self.requests: dict[str, dict] = {}
    def create_request(self, rtype, data):
        """创建一条待处理请求；rtype 表示请求类型，data 保存原始消息。"""
        rid = str(uuid.uuid4())[:8]
        self.requests[rid] = {"type": rtype, "data": data, "status": "pending", "response": None}
        return rid
    def respond(self, rid, approve=True):
        """记录请求响应结果；approve=True 表示批准，False 表示拒绝。"""
        if rid in self.requests:
            self.requests[rid]["status"] = "approved" if approve else "rejected"
            self.requests[rid]["response"] = "approved" if approve else "rejected"

def dispatch_message(msg, protocol_state):
    """根据消息 type 创建对应协议请求，返回分发结果标记。"""
    mtype = msg.get("type", "")
    if mtype == "shutdown_request":
        protocol_state.create_request("shutdown", msg)
        return "shutdown_request_created"
    elif mtype == "plan_approval":
        protocol_state.create_request("plan_approval", msg)
        return "plan_approval_created"
    return "unknown_type"

def match_response(response, request):
    """判断一条 response 是否能回应指定 request，匹配时返回 approve 字段。"""
    rtype = request.get("type")
    rtype2 = response.get("type", "")
    if rtype == "shutdown" and rtype2 == "shutdown_response":
        return response.get("approve")
    if rtype == "plan_approval" and rtype2 == "plan_approval_response":
        return response.get("approve")
    return None
