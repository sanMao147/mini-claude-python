"""s16 teams.py — Agent 团队 + 协议 + idle loop"""
import threading, json, os, uuid, time
from pathlib import Path
from tools import WORKSPACE_DIR, MAILBOXES_DIR
from llm import call_llm
from protocols import ProtocolState, dispatch_message

os.makedirs(MAILBOXES_DIR, exist_ok=True)

class MessageBus:
    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.path = os.path.join(MAILBOXES_DIR, f"{agent_name}.jsonl")
    def send(self, to_agent, msg):
        tp = os.path.join(MAILBOXES_DIR, f"{to_agent}.jsonl")
        with open(tp, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    def receive(self):
        if not os.path.exists(self.path): return []
        msgs = []
        for line in Path(self.path).read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                try: msgs.append(json.loads(line))
                except: pass
        Path(self.path).write_text("", encoding="utf-8")
        return msgs

def spawn_teammate_thread(task, lead_bus, teammate_name, cwd=None):
    def _run():
        sub_msgs = [{"role": "user", "content": task}]
        tools = [{"type":"function","function":{"name":"bash","description":"exec","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
                 {"type":"function","function":{"name":"send_message","description":"send to lead","parameters":{"type":"object","properties":{"content":{"type":"string"},"summary":{"type":"string"}},"required":["content","summary"]}}}]
        for turn in range(10):
            resp = call_llm(sub_msgs, tools, "你是子Agent队友。完成任务后发送摘要给Lead。")
            sub_msgs.append(resp["assistant_message"])
            if resp["finish_reason"] != "tool_calls":
                lead_bus.send("lead", {"type":"message","from":teammate_name,"content":f"[队友{teammate_name}完成]\n{resp['content']}","summary":resp['content'][:100]})
                return
            for tc in resp["tool_calls"]:
                handler = lambda **kw: f"done"
                try: args = json.loads(tc["function"]["arguments"])
                except: args = {}
                output = handler(**args)
                sub_msgs.append({"role":"tool","tool_call_id":tc["id"],"content":output})
        lead_bus.send("lead", {"type":"message","from":teammate_name,"content":f"[队友{teammate_name}] 达到10轮限制","summary":"max turns"})
    t = threading.Thread(target=_run, daemon=True); t.start()
    return teammate_name
