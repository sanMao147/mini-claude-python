"""
============================================================================
  s03_permission/main.py — 权限管控（三道闸门管线）
============================================================================
  核心改进（相比 s02）：
  s03 在工具执行前插入三道安全闸门：

    工具调用 → Gate1(拒绝列表) → Gate2(规则匹配) → Gate3(用户审批) → 执行

  循环中只加了一行：
      if not check_permission(tool_name, tool_args):
          ...  # 拒绝，跳过执行

  运行方式：
      python s03_permission/main.py
============================================================================
"""

import json, os, sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import WORKSPACE_DIR
from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS
from permission import check_permission  # <-- s03 新增

SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "可用工具: bash, read_file, write_file, edit_file, glob\n"
    "规则：破坏性操作需要用户审批。先了解再行动。\n"
)


def agent_loop(messages: list[dict]):
    """Agent 主循环 — 在工具执行前插入权限检查。"""
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

            # 打印工具调用信息
            label = {"bash": f"$ {tool_args.get('command','')}",
                     "read_file": f"[read] {tool_args.get('path','')}",
                     "write_file": f"[write] {tool_args.get('path','')}",
                     "edit_file": f"[edit] {tool_args.get('path','')}",
                     "glob": f"[glob] {tool_args.get('pattern','')}"}
            print(f"\033[36m> {label.get(tool_name, tool_name)}\033[0m")

            # ── s03 核心：权限检查 ──
            # 在工具执行前运行三道闸门管线，拒绝则跳过执行
            if not check_permission(tool_name, tool_args):
                output = "权限被拒绝。"
            else:
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

            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})


def main():
    print("=" * 50)
    print("  s03: Permission — 三道闸门权限管控")
    print("  Gate1(拒绝列表) → Gate2(规则匹配) → Gate3(用户审批)")
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
