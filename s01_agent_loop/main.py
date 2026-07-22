"""最小 Agent 循环"""

import json
import os

from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS, WORKSPACE_DIR

SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "你可以使用 bash 工具执行 shell 命令来完成任务。\n"
    "规则：\n"
    "  1. 先行动，后解释。直接执行命令，不要先长篇大论。\n"
    "  2. 命令执行后简要汇报结果。\n"
    "  3. 如果需要多步操作，逐步执行，每步一个命令。\n"
)


def agent_loop(messages: list[dict]):
    while True:
        response = call_llm(
            messages=messages,
            tools=TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )

        messages.append(response["assistant_message"])

        if response["finish_reason"] != "tool_calls":
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]
            tool_args = json.loads(func["arguments"])

            if tool_name == "bash":
                print(f"\033[33m$ {tool_args.get('command', '')}\033[0m")

            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                output = f"错误: 未知工具 '{tool_name}'"
            else:
                try:
                    output = handler(**tool_args)
                except Exception as e:
                    output = f"错误: 工具执行异常 - {e}"

            output_preview = output[:300]
            if len(output) > 300:
                output_preview += "..."
            if output_preview.strip():
                print(output_preview)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })


def main():
    print("=" * 50)
    print("  s01: Agent Loop — 最小 Agent 循环")
    print("  1 个工具 (bash) + while True 循环")
    print("=" * 50)
    print("输入你的需求，回车发送。输入 q / exit 退出。\n")

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

        history.append({"role": "user", "content": query})
        agent_loop(history)
        print()


if __name__ == "__main__":
    main()