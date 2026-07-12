"""s14 main.py — Cron 定时调度"""
import json, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
from cron import start_cron_scheduler, cron_queue, cron_lock, schedule_job, agent_lock  # s14

# 注入动态处理函数。
# tools.py 只声明工具 schema 和基础 handler；依赖运行时对象的工具在这里绑定。
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
for name in ["bash","read_file","write_file","edit_file","glob"]:
    # 子 Agent 只开放最基础的文件和命令工具，避免它直接调用主 Agent 的记忆/cron 等全局能力。
    SUB_HANDLERS[name] = TOOL_HANDLERS[name]
_orig_bash = TOOL_HANDLERS["bash"]
# 慢命令自动转后台任务，主 Agent 可以继续对话，完成结果会在后续轮次注入。
TOOL_HANDLERS["bash"] = lambda c: start_background_task(c) if should_run_background(c) else _orig_bash(c)

# 当前工具池名称列表会放入 system prompt，帮助模型知道本轮可调用哪些工具。
_all_tool_names = [t["function"]["name"] for t in TOOLS]

def agent_loop(messages: list[dict], user_query: str = ""):
    """执行一轮或多轮 Agent 推理，直到模型给出最终文本或遇到不可恢复错误。"""
    has_compacted = False  # 是否已执行过 reactive compact
    while True:
        # TodoWrite 长时间未更新时注入提醒，推动模型主动同步任务状态。
        nag = check_nag_reminder()
        if nag: print(f"\033[33m{nag}\033[0m"); messages.append({"role": "user", "content": nag})
        # 每次调用 LLM 前都跑压缩管线，优先在本地降低上下文体积。
        messages = run_compaction_pipeline(messages, call_llm)

        # s14: cron queue 消费 + background results 收集
        bg_notifications = collect_background_results()
        for bg_msg in bg_notifications:
            print(f"\033[35m[后台完成]\033[0m"); messages.append({"role": "user", "content": bg_msg})
        with cron_lock:
            # 调度线程只负责把 job 放入队列；主循环在这里把它转成用户消息交给模型处理。
            while cron_queue:
                job = cron_queue.pop(0)
                messages.append({"role": "user", "content": f"<cron_trigger>定时任务 [{job['job_id']}]: {job['prompt']}</cron_trigger>"})

        # 根据当前工具、用户输入和记忆状态动态组装 system prompt。
        context = update_context(_all_tool_names, user_query)
        if context["has_memories"] and user_query:
            # 只把最相关的记忆摘要放入 prompt，避免记忆系统本身占用过多上下文。
            rel_mems = select_relevant_memories(user_query, call_llm)
            context["memory_summaries"] = [f"{m.get('name','')}: {m.get('description','')}" for m in rel_mems[:5]]
        system_prompt = get_system_prompt(context)

        # s11: LLM 调用已内置错误恢复
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=system_prompt)

        # s11: prompt_too_long → reactive compact 后重试
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
            # 没有工具调用代表本轮要结束：先抽取长期记忆，再触发 Stop hook，最后输出文本。
            extracted = extract_memories(messages, call_llm)
            if extracted: print(f"\033[90m[记忆] {extracted}\033[0m")
            all_mems = _scan_memory_dir()
            if len(all_mems) >= 10:
                result = consolidate_memories(call_llm)
                if result: print(f"\033[90m[记忆] {result}\033[0m")
            force_continue = trigger_hooks("Stop", messages)
            if force_continue: messages.append({"role": "user", "content": str(force_continue)}); continue
            text = response["content"]
            text = response["content"]
            if text.strip(): print(f"\n{text}")
            return
        increment_todo_counter()
        for tc in response["tool_calls"]:
            # OpenAI tool_call 的 arguments 是 JSON 字符串；解析失败时按空参数处理，避免主循环崩溃。
            func = tc["function"]; tool_name = func["name"]
            try: tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError: tool_args = {}
            label = {"bash":f"$ {tool_args.get('command','')}", "read_file":f"[read] {tool_args.get('path','')}",
                     "write_file":f"[write] {tool_args.get('path','')}", "edit_file":f"[edit] {tool_args.get('path','')}",
                     "glob":f"[glob] {tool_args.get('pattern','')}", "todo_write":"[todo_write]",
                     "load_skill":f"[load_skill] {tool_args.get('name','')}", "compact":"[compact]",
                     "task":f"[task] {tool_args.get('prompt','')[:60]}"}
            print(f"\033[36m> {label.get(tool_name, tool_name)}\033[0m")
            # PreToolUse 可以拒绝或改写工具执行，PostToolUse 用于日志、摘要等旁路处理。
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
            # 工具结果必须带回对应 tool_call_id，这样下一轮 LLM 才能把结果和请求对上。
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

def main():
    """命令行入口：启动调度器，持续读取用户输入，并复用同一段 history。"""
    print("=" * 50)
    print("  s14: Cron Scheduler — 定时调度系统")
    print("  cron_matches五段匹配 + daemon轮询 + Agent空闲交付")
    print("=" * 50)
    print("输入需求后回车。q / exit 退出。\n")
    reset_recovery()
    start_cron_scheduler()  # s14: 启动 cron 调度器
    history: list[dict] = []
    while True:
        # 简化版 REPL：每次用户输入追加到同一 history，agent_loop 负责直到本轮完成。
        try: query = input("\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt): print("\n再见！"); break
        if query.lower() in ("q","exit",""): print("再见！"); break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history, query)
        print()

if __name__ == "__main__": main()
