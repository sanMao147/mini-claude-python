"""s07 main.py — 技能加载系统"""

import json

from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS, WORKSPACE_DIR
from hooks import trigger_hooks
from todos import run_todo_write, check_nag_reminder, increment_todo_counter, reset_todo_counter
from subagent import spawn_subagent, SUB_HANDLERS
from skills import build_skills_catalog, load_skill

TOOL_HANDLERS["todo_write"] = lambda todos: run_todo_write(todos)
TOOL_HANDLERS["task"] = lambda prompt, cwd=None: spawn_subagent(prompt, cwd)
TOOL_HANDLERS["load_skill"] = lambda name: load_skill(name)
for name in ["bash","read_file","write_file","edit_file","glob"]:
    SUB_HANDLERS[name] = TOOL_HANDLERS[name]

_skills_catalog = build_skills_catalog()
SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    f"可用工具: bash, read_file, write_file, edit_file, glob, todo_write, task, load_skill\n"
    f"{_skills_catalog}\n\n"
    "对于复杂任务：先计划，再分治。需要特定领域知识时使用 load_skill 加载技能。\n"
)

def agent_loop(messages: list[dict]):
    while True:
        nag = check_nag_reminder()
        if nag: print(f"\033[33m{nag}\033[0m"); messages.append({"role": "user", "content": nag})
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
        messages.append(response["assistant_message"])
        if response["finish_reason"] != "tool_calls":
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
                     "glob":f"[glob] {tool_args.get('pattern','')}", "todo_write":"[todo_write]", "load_skill":f"[load_skill] {tool_args.get('name','')}",
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
    print("  s07: Skill Loading — 两级知识加载")
    print(f"  技能目录: {_skills_catalog or '(无技能)'}")
    print("=" * 50)
    print("输入需求后回车。q / exit 退出。\n")
    history: list[dict] = []
    while True:
        try: query = input("\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt): print("\n再见！"); break
        if query.lower() in ("q","exit",""): print("再见！"); break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history)
        print()

if __name__ == "__main__": main()