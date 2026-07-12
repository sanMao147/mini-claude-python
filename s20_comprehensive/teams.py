"""s17 teams.py — 自主 Agent（WORK→IDLE→SHUTDOWN 生命周期 + 扫描任务板）"""
import threading, json, os, sys, uuid, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WORKSPACE_DIR, MAILBOXES_DIR, TASKS_DIR
from llm import call_llm
from protocols import ProtocolState
os.makedirs(MAILBOXES_DIR, exist_ok=True)
os.makedirs(TASKS_DIR, exist_ok=True)

# teams.py 演示更长期运行的“队友 Agent”。
# 它和 subagent.py 的一次性委托不同：队友线程完成任务后会进入 IDLE，继续监听邮箱和任务板。

class MessageBus:
    """基于 jsonl 文件的极简消息总线，每个 Agent 一个邮箱文件。"""
    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.path = os.path.join(MAILBOXES_DIR, f"{agent_name}.jsonl")
    def send(self, to_agent, msg):
        """向目标 Agent 邮箱追加一行 JSON 消息。"""
        tp = os.path.join(MAILBOXES_DIR, f"{to_agent}.jsonl")
        with open(tp, "a", encoding="utf-8") as f: f.write(json.dumps(msg,ensure_ascii=False)+"\n")
    def receive(self):
        """读取并清空当前 Agent 邮箱；解析失败的行会被忽略。"""
        if not os.path.exists(self.path): return []
        msgs = []
        for line in Path(self.path).read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                try: msgs.append(json.loads(line))
                except: pass
        Path(self.path).write_text("",encoding="utf-8")
        return msgs

def _scan_unclaimed_tasks():
    """扫描 .tasks/ 目录中 pending 且无 owner 且可开始的任务。"""
    # 当前只检查 pending + owner；更严格的依赖判断可以和 tasks.can_start() 合并。
    tasks = []
    if not os.path.isdir(TASKS_DIR): return tasks
    for f in os.listdir(TASKS_DIR):
        if f.endswith(".json"):
            try:
                data = json.loads(open(os.path.join(TASKS_DIR,f),encoding="utf-8").read())
                if data.get("status") == "pending" and not data.get("owner"):
                    tasks.append(data)
            except: pass
    return tasks

def _idle_poll(inbox, task_id=None):
    """IDLE 阶段：每5秒轮询收件箱和任务板。返回任务或None。"""
    for _ in range(12):  # 60秒超时
        # 先看邮箱，shutdown_request 优先级最高。
        msgs = inbox.receive()
        for m in msgs:
            if m.get("type") == "shutdown_request": return None  # shutdown
        # 没有消息时再看任务板，自动领取第一个未认领任务。
        tasks = _scan_unclaimed_tasks()
        if tasks:
            return tasks[0]["subject"]
        time.sleep(5)
    return None  # 超时退出

def spawn_teammate_thread(task, lead_bus, teammate_name, cwd=None):
    """启动一个 daemon 队友线程，返回 teammate_name 作为线程身份。"""
    def _run():
        # stage 是队友生命周期：WORK 执行任务，IDLE 等新任务，SHUTDOWN 退出。
        sub_msgs = [{"role":"user","content":task}]
        tools = [{"type":"function","function":{"name":"bash","description":"exec","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
                 {"type":"function","function":{"name":"send_message","description":"send to lead","parameters":{"type":"object","properties":{"content":{"type":"string"},"summary":{"type":"string"}},"required":["content","summary"]}}}]
        inbox = MessageBus(teammate_name)
        stage = "WORK"
        while stage != "SHUTDOWN":
            if stage == "WORK":
                # 队友使用自己的消息上下文，完成后通过 lead_bus 给 lead 发摘要。
                resp = call_llm(sub_msgs, tools, "你是子Agent队友。完成任务后发送摘要给Lead。")
                sub_msgs.append(resp["assistant_message"])
                if resp["finish_reason"] != "tool_calls":
                    lead_bus.send("lead",{"type":"message","from":teammate_name,"content":f"[队友{teammate_name}完成]\n{resp['content']}","summary":resp['content'][:100]})
                    stage = "IDLE"
                    continue
                for tc in resp["tool_calls"]:
                    # 示例里暂时把工具 handler 简化为 done，真实实现可接入 tools.py 的 handler。
                    handler = lambda **kw: "done"
                    try: args = json.loads(tc["function"]["arguments"])
                    except: args = {}
                    sub_msgs.append({"role":"tool","tool_call_id":tc["id"],"content":handler(**args)})
            elif stage == "IDLE":
                # IDLE 阶段不会持续占用 LLM，只轮询外部任务来源。
                new_task = _idle_poll(inbox)
                if new_task is None:
                    stage = "SHUTDOWN"  # shutdown received or timeout
                elif new_task:
                    sub_msgs = [{"role":"user","content":new_task}]
                    stage = "WORK"
        lead_bus.send("lead",{"type":"message","from":teammate_name,"content":f"[队友{teammate_name}] 已退出","summary":"shutdown"})
    t = threading.Thread(target=_run, daemon=True); t.start()
    return teammate_name
