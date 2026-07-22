"""s02 工具使用 — 5 个工具 + 查表分发"""

import json

from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS, WORKSPACE_DIR

SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "你可以使用以下工具完成任务：\n"
    "  - bash: 执行 shell 命令\n"
    "  - read_file: 读取文件内容\n"
    "  - write_file: 写入文件\n"
    "  - edit_file: 精确替换文件中的文本\n"
    "  - glob: 通配符查找文件\n"
    "规则：\n"
    "  1. 先了解情况再行动（用 read_file 和 glob 了解项目结构）\n"
    "  2. 修改文件前先读取确认现有内容\n"
    "  3. 完成后简要汇报结果\n"
)


def agent_loop(messages: list[dict]):
    while True:
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=SYSTEM_PROMPT)

        messages.append(response["assistant_message"])

        if response["finish_reason"] != "tool_calls":
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]

            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            if tool_name == "bash":
                print(f"\033[33m$ {tool_args.get('command', '')}\033[0m")
            elif tool_name == "read_file":
                print(f"\033[33m[read] {tool_args.get('path', '')}\033[0m")
            elif tool_name == "write_file":
                print(f"\033[33m[write] {tool_args.get('path', '')}\033[0m")
            elif tool_name == "edit_file":
                print(f"\033[33m[edit] {tool_args.get('path', '')}\033[0m")
            elif tool_name == "glob":
                print(f"\033[33m[glob] {tool_args.get('pattern', '')}\033[0m")

            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                output = f"错误: 未知工具 '{tool_name}'"
            else:
                try:
                    output = handler(**tool_args)
                except Exception as e:
                    output = f"错误: 工具执行异常 - {e}"

            preview = output[:300]
            if len(output) > 300:
                preview += "..."
            if preview.strip():
                print(preview)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })


def main():
    print("=" * 50)
    print("  s02: Tool Use — 5 个工具 + 查表分发")
    print("  bash / read_file / write_file / edit_file / glob")
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

        history.append({"role": "user", "content": query})
        agent_loop(history)
        print()


if __name__ == "__main__":
    main()