"""
============================================================================
  s02_tool_use/main.py — 工具使用（5 个工具 + 查表分发）
============================================================================
  核心改进（相比 s01）：
  1. 从 1 个工具扩展到 5 个：bash, read_file, write_file, edit_file, glob
  2. 引入 TOOL_HANDLERS 字典做查表分发（替代 s01 硬编码 run_bash 调用）
  3. 新增 safe_path() 路径安全校验

  Agent 循环结构与 s01 完全一致，变化仅在于工具执行方式更灵活。

  运行方式：
      python s02_tool_use/main.py
============================================================================
"""

import json
import os
import sys


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import WORKSPACE_DIR
from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS

# ============================================================================
# 系统提示词
# ============================================================================
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


# ============================================================================
# Agent 主循环
# ============================================================================

def agent_loop(messages: list[dict]):
    """
    Agent 主循环 — 与 s01 结构一致，唯一区别是工具分发方式：
      s01: output = run_bash(command)                    # 硬编码
      s02: output = TOOL_HANDLERS[name](**args)          # 查表分发
    """
    while True:
        # ── 调用 LLM ──
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=SYSTEM_PROMPT)

        # ── 保存 assistant 消息 ──
        messages.append(response["assistant_message"])

        # ── 判断是否结束 ──
        if response["finish_reason"] != "tool_calls":
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        # ── 执行工具调用（查表分发） ──
        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]

            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            # 打印工具调用信息
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

            # 查表分发执行
            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                output = f"错误: 未知工具 '{tool_name}'"
            else:
                try:
                    output = handler(**tool_args)
                except Exception as e:
                    output = f"错误: 工具执行异常 - {e}"

            # 打印部分输出
            preview = output[:300]
            if len(output) > 300:
                preview += "..."
            if preview.strip():
                print(preview)

            # ── 注入工具结果 ──
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })


# ============================================================================
# 入口
# ============================================================================

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
