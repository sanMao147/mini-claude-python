"""s15 main.py — Agent 团队 + MessageBus"""
import json, os, sys, threading, uuid
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import WORKSPACE_DIR
from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS
from hooks import trigger_hooks
from todos import run_todo_write, check_nag_reminder, increment_todo_counter, reset_todo_counter
from subagent import spawn_subagent, SUB_HANDLERS
from skills import load_skill
from compact import run_compaction_pipeline, run_compact, reactive_compact
from memory import select_relevant_memories, extract_memories, consolidate_memories, _scan_memory_dir
from prompt import get_system_prompt, update_context
from recovery import _state, reset_state as reset_recovery
from tasks import create_task, list_tasks, get_task, claim_task, complete_task
from background import should_run_background, start_background_task, collect_background_results
from cron import start_cron_scheduler, cron_queue, cron_lock, schedule_job, agent_lock
from teams import MessageBus, spawn_teammate_thread

# 注入动态处理函数
TOOL_HANDLERS["todo_write"] = lambda todos: run_todo_write(todos)
TOOL_HANDLERS["task"] = lambda prompt, cwd=None: spawn_subagent(prompt, cwd)
TOOL_HANDLERS["load_skill"] = lambda name: load_skill(name)
TOOL_HANDLERS["compact"] = lambda: run_compact(call_llm)
TOOL_HANDLERS["create_task"] = lambda s, d="", b=None: create_task(s,d,b)
TOOL_HANDLERS["list_tasks"] = lambda status=None: list_tasks(status)
TOOL_HANDLERS["get_task"] = lambda tid: get_task(tid)
TOOL_HANDLERS["claim_task"] = lambda tid: claim_task(tid)
TOOL_HANDLERS["complete_task"] = lambda tid: complete_task(tid)
TOOL_HANDLERS["schedule_job"] = lambda cron, prompt, durable=False: schedule_job(cron, prompt, durable)
_lead_bus = MessageBus("lead")
TOOL_HANDLERS["spawn_teammate"] = lambda task: f"队友已启动: {spawn_teammate_thread(task, _lead_bus, f'tm_{uuid.uuid4().hex[:6]}')}"
TOOL_HANDLERS["send_message"] = lambda content, summary: f"已发送"
TOOL_HANDLERS["check_inbox"] = lambda: _check_inbox_impl()
for name in ["bash","read_file","write_file","edit_file","glob"]:
    SUB_HANDLERS[name] = TOOL_HANDLERS[name]
_orig_bash = TOOL_HANDLERS["bash"]
TOOL_HANDLERS["bash"] = lambda c: start_background_task(c) if should_run_background(c) else _orig_bash(c)

_all_tool_names = [t["function"]["name"] for t in TOOLS]

def _check_inbox_impl():
    msgs = _lead_bus.receive()
    if not msgs: return "(收件箱为空)"
    return "\n".join(f"来自 {m.get('from','?')}: {m.get('summary','')}" for m in msgs)

def agent_loop(messages: list[dict], user_query: str = ""):
    has_compacted = False  # 是否已执行过 reactive compact
    while True:
        nag = check_nag_reminder()
        if nag: print(f"\033[33m{nag}\033[0m"); messages.append({"role": "user", "content": nag})
        messages = run_compaction_pipeline(messages, call_llm)

        # cron queue 消费 + background results 收集
        bg_notifications = collect_background_results()
        for bg_msg in bg_notifications:
            print(f"\033[35m[后台完成]\033[0m"); messages.append({"role": "user", "content": bg_msg})
        with cron_lock:
            while cron_queue:
                job = cron_queue.pop(0)
                messages.append({"role": "user", "content": f"<cron_trigger>定时任务 [{job['job_id']}]: {job['prompt']}</cron_trigger>"})
        # 检查队友收件箱
        msgs = _lead_bus.receive()
        for m in msgs:
            print(f"\033[35m[收件] 来自 {m.get('from','?')}: {m.get('summary','')[:80]}\033[0m")
            messages.append({"role": "user", "content": m.get("content", "")})

        context = update_context(_all_tool_names, user_query)
        if context["has_memories"] and user_query:
            rel_mems = select_relevant_memories(user_query, call_llm)
            context["memory_summaries"] = [f"{m.get('name','')}: {m.get('description','')}" for m in rel_mems[:5]]
        system_prompt = get_system_prompt(context)

        # LLM 调用已内置错误恢复
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=system_prompt)

        # prompt_too_long → reactive compact 后重试
        if response.get("error") == "prompt_too_long" and not has_compacted:
            print(f"\033[33m[恢复] prompt_too_long → 执行应急压缩\033[0m")
            messages = reactive_compact(messages, call_llm)
            has_compacted = True
            continue

        if response.get("error") and not response.get("content"):
            # 不可恢复的错误
            print(f"\n\033[31m[错误] 不可恢复: {response.get('error')}\033[0m")
            return

        messages.append(response["assistant_message"])
        if response["finish_reason"] != "tool_calls":
            extracted = extract_memories(messages, call_llm)
            if extracted: print(f"\033[90m[记忆] {extracted}\033[0m")
            all_mems = _scan_memory_dir()
            if len(all_mems) >= 10:
                result = consolidate_memories(call_llm)
                if result: print(f"\033[90m[记忆] {result}\033[0m")
            force_continue = trigger_hooks("Stop", messages)
            if force_continue: messages.append({"role": "user", "content": str(force_continue)}); continue
            text = response["content"]
            if text.strip(): print(f"\n{text}")
            return
        increment_todo_counter()
        for tc in response["tool_calls"]:
            func = tc["function"]; tool_name = func["name"]
            try: tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError: tool_args = {}
            label = {"bash":f"$ {tool_args.get('command','')}", "read_file":f"[read] {tool_args.get('path','')}",
                     "write_file":f"[write] {tool_args.get('path','')}", "edit_file":f"[edit] {tool_args.get('path','')}",
                     "glob":f"[glob] {tool_args.get('pattern','')}", "todo_write":"[todo_write]",
                     "load_skill":f"[load_skill] {tool_args.get('name','')}", "compact":"[compact]",
                     "task":f"[task] {tool_args.get('prompt','')[:60]}"}
            print(f"\033[36m> {label.get(tool_name, tool_name)}\033[0m")
            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked: output = str(blocked)
            else:
                handler = TOOL_HANDLERS.get(tool_name)
                output = handler(**tool_args) if handler else f"错误: 未知工具 '{tool_name}'"
                trigger_hooks("PostToolUse", tool_name, tool_args, output)
                if tool_name == "todo_write": reset_todo_counter()
            preview = output[:300]
            if len(output) > 300: preview += "..."
            if preview.strip(): print(preview)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

def main():
    print("=" * 50)
    print("  s15: Agent Teams — 团队协作")
    print("  MessageBus + spawn_teammate + 收件箱轮询")
    print("=" * 50)
    print("输入需求后回车。q / exit 退出。\n")
    reset_recovery()
    start_cron_scheduler()
    history: list[dict] = []
    while True:
        try: query = input("\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt): print("\n再见！"); break
        if query.lower() in ("q","exit",""): print("再见！"); break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history, query)
        print()

if __name__ == "__main__": main()
