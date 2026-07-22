"""s11 main.py — 错误恢复系统"""
import json, os

from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS, WORKSPACE_DIR
from hooks import trigger_hooks
from todos import run_todo_write, check_nag_reminder, increment_todo_counter, reset_todo_counter
from subagent import spawn_subagent, SUB_HANDLERS
from skills import load_skill
from compact import run_compaction_pipeline, run_compact, reactive_compact
from memory import select_relevant_memories, extract_memories, consolidate_memories, _scan_memory_dir
from prompt import get_system_prompt, update_context
from recovery import _state, reset_state as reset_recovery

TOOL_HANDLERS["todo_write"] = lambda todos: run_todo_write(todos)
TOOL_HANDLERS["task"] = lambda prompt, cwd=None: spawn_subagent(prompt, cwd)
TOOL_HANDLERS["load_skill"] = lambda name: load_skill(name)
TOOL_HANDLERS["compact"] = lambda: run_compact(call_llm)
for name in ["bash","read_file","write_file","edit_file","glob"]:
    SUB_HANDLERS[name] = TOOL_HANDLERS[name]

_all_tool_names = [t["function"]["name"] for t in TOOLS]

def agent_loop(messages: list[dict], user_query: str = ""):
    has_compacted = False
    while True:
        nag = check_nag_reminder()
        if nag: print(f"\033[33m{nag}\033[0m"); messages.append({"role": "user", "content": nag})
        messages = run_compaction_pipeline(messages, call_llm)

        context = update_context(_all_tool_names, user_query)
        if context["has_memories"] and user_query:
            rel_mems = select_relevant_memories(user_query, call_llm)
            context["memory_summaries"] = [f"{m.get('name','')}: {m.get('description','')}" for m in rel_mems[:5]]
        system_prompt = get_system_prompt(context)

        response = call_llm(messages=messages, tools=TOOLS, system_prompt=system_prompt)

        if response.get("error") == "prompt_too_long" and not has_compacted:
            print(f"\033[33m[恢复] prompt_too_long → 执行应急压缩\033[0m")
            messages = reactive_compact(messages, call_llm)
            has_compacted = True
            continue

        if response.get("error") and not response.get("content"):
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
    print("  s11: Error Recovery — 三种错误恢复路径")
    print("  指数退避重试 + max_tokens升级 + 熔断器")
    print("=" * 50)
    print("输入需求后回车。q / exit 退出。\n")
    reset_recovery()
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