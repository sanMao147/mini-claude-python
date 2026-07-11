"""
============================================================================
  s15_agent_teams/teams.py — Agent 团队 + MessageBus 收件箱
============================================================================
  核心机制：
  - MessageBus 类：基于文件的 JSONL 收件箱（.mailboxes/{agent}.jsonl），消费式读取
  - spawn_teammate_thread()：在 daemon 线程中启动队友 Agent
  - 队友简化工具集：bash/read/write/send_message，最多 10 轮
  - Lead 每轮结束后检查收件箱，注入队友消息到 history
============================================================================
"""

import threading, json, os, sys, uuid, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WORKSPACE_DIR, MAILBOXES_DIR
from llm import call_llm

os.makedirs(MAILBOXES_DIR, exist_ok=True)
active_teammates: dict[str, dict] = {}


class MessageBus:
    """基于文件的 JSONL 收件箱。每行一条 JSON 消息，读取后删除。"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.path = os.path.join(MAILBOXES_DIR, f"{agent_name}.jsonl")

    def send(self, to_agent: str, msg: dict):
        """发送消息到指定 Agent 的收件箱。"""
        target_path = os.path.join(MAILBOXES_DIR, f"{to_agent}.jsonl")
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def receive(self) -> list[dict]:
        """读取并清空收件箱。"""
        if not os.path.exists(self.path):
            return []
        messages = []
        lines = Path(self.path).read_text(encoding="utf-8").strip().splitlines()
        for line in lines:
            if line.strip():
                try: messages.append(json.loads(line))
                except json.JSONDecodeError: pass
        # 清空文件
        Path(self.path).write_text("", encoding="utf-8")
        return messages


# 队友可用工具
TEAMMATE_TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "执行shell命令",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取文件",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入文件",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "send_message", "description": "向Lead Agent发送消息",
        "parameters": {"type": "object", "properties": {"content": {"type": "string"}, "summary": {"type": "string"}}, "required": ["content", "summary"]}}},
]

TEAMMATE_SYSTEM = "你是一个子Agent队友。完成分配的任务后发送简洁英文摘要给Lead。"


def spawn_teammate_thread(task: str, lead_bus: MessageBus, teammate_name: str, cwd: str = None):
    """
    在 daemon 线程中启动队友 Agent。
    队友完成或达到 10 轮限制后，自动发送 summary 到 Lead 收件箱。
    """
    def _run():
        work_dir = cwd or WORKSPACE_DIR
        sub_messages = [{"role": "user", "content": task}]

        tool_handlers = {
            "bash": _run_bash_t, "read_file": _run_read_t,
            "write_file": _run_write_t, "send_message": lambda content, summary: f"sent: {summary}",
        }

        MAX_TURNS = 10
        for turn in range(MAX_TURNS):
            resp = call_llm(sub_messages, TEAMMATE_TOOLS, TEAMMATE_SYSTEM)
            sub_messages.append(resp["assistant_message"])
            if resp["finish_reason"] != "tool_calls":
                result = resp["content"]
                lead_bus.send("lead", {
                    "type": "message", "from": teammate_name,
                    "content": f"[队友 {teammate_name} 完成]\n{result}",
                    "summary": result[:100]
                })
                print(f"\033[35m[队友 {teammate_name}] 完成 ({turn+1}轮)\033[0m")
                return
            for tc in resp["tool_calls"]:
                func = tc["function"]
                handler = tool_handlers.get(func["name"])
                try: args = json.loads(func["arguments"])
                except: args = {}
                output = handler(**args) if handler else f"错误:未知工具"
                sub_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

        lead_bus.send("lead", {
            "type": "message", "from": teammate_name,
            "content": f"[队友 {teammate_name}] 达到{MAX_TURNS}轮限制",
            "summary": f"reached max turns ({MAX_TURNS})"
        })

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return teammate_name


# 队友工具实现
def _run_bash_t(command): return _run_basic(command, "bash")
def _run_read_t(path, limit=None): return _run_basic(path, "read_file")
def _run_write_t(path, content): return _run_basic(path, "write_file")

def _run_basic(a, tool):
    import subprocess as sp
    try:
        r = sp.run(f"echo tool:{tool} arg:{a}", shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or "(done)"
    except: return f"error"
