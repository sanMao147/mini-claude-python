"""s05 TodoWrite — 先计划再执行 + Nag 提醒（连续 3 轮不更新则注入提醒）"""

import json

from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS, WORKSPACE_DIR
from hooks import trigger_hooks
from todos import (
    run_todo_write, check_nag_reminder,
    increment_todo_counter, reset_todo_counter,
)

TOOL_HANDLERS["todo_write"] = lambda todos: run_todo_write(todos)

SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "可用工具: bash, read_file, write_file, edit_file, glob, todo_write\n\n"
    "重要: 在开始任何多步骤任务之前，必须先调用 todo_write 制定计划。\n"
    "执行过程中及时更新各任务的状态（pending → in_progress → completed）。\n"
    "先计划再行动，逐个完成任务。\n"
)


def agent_loop(messages: list[dict]):
    while True:
        nag = check_nag_reminder()
        if nag:
            print(f"\033[33m{nag}\033[0m")
            messages.append({"role": "user", "content": nag})

        response = call_llm(messages=messages, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
        messages.append(response["assistant_message"])

        if response["finish_reason"] != "tool_calls":
            force_continue = trigger_hooks("Stop", messages)
            if force_continue:
                messages.append({"role": "user", "content": str(force_continue)})
                continue
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        increment_todo_counter()

        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]
            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            label = {"bash": f"$ {tool_args.get('command','')}",
                     "read_file": f"[read] {tool_args.get('path','')}",
                     "write_file": f"[write] {tool_args.get('path','')}",
                     "edit_file": f"[edit] {tool_args.get('path','')}",
                     "glob": f"[glob] {tool_args.get('pattern','')}",
                     "todo_write": "[todo_write] 更新任务列表"}
            print(f"\033[36m> {label.get(tool_name, tool_name)}\033[0m")

            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked:
                output = str(blocked)
            else:
                handler = TOOL_HANDLERS.get(tool_name)
                if handler is None:
                    output = f"错误: 未知工具 '{tool_name}'"
                else:
                    try:
                        output = handler(**tool_args)
                    except Exception as e:
                        output = f"错误: 工具执行异常 - {e}"

                trigger_hooks("PostToolUse", tool_name, tool_args, output)

                if tool_name == "todo_write":
                    reset_todo_counter()

            preview = output[:300]
            if len(output) > 300:
                preview += "..."
            if preview.strip():
                print(preview)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})


def main():
    print("=" * 50)
    print("  s05: TodoWrite — 先计划再执行 + Nag 提醒")
    print("  6 个工具: bash/read/write/edit/glob/todo_write")
    print("=" * 50)
    print("输入需求后回车。q / exit 退出。\n")

    history: list[dict] = []
    while True:
        try:
            query = input("\033[36m>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if query.lower() in ("q", "exit", ""):
            print("再见！")
            break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history)
        print()


if __name__ == "__main__":
    main()