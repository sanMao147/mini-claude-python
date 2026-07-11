"""
============================================================================
  s04_hooks/main.py — Hook 系统（事件驱动的扩展机制）
============================================================================
  核心改进（相比 s03）：
  1. s03 的 check_permission() 从循环体中移除
  2. 权限逻辑迁移到 PreToolUse hook（permission_hook）
  3. 新增 4 个事件 + 5 个内置 hook 回调
  4. 循环体更简洁：只调用 trigger_hooks()，不关心具体 hook 逻辑

  事件流：
    UserPromptSubmit → LLM调用 → PreToolUse → 工具执行 → PostToolUse → Stop

  运行方式：
      python s04_hooks/main.py
============================================================================
"""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import WORKSPACE_DIR
from llm import call_llm
from tools import TOOLS, TOOL_HANDLERS
from hooks import trigger_hooks  # <-- s04 核心：用 hook 替代硬编码权限检查

SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "可用工具: bash, read_file, write_file, edit_file, glob\n"
    "先了解再行动。破坏性操作需要用户审批。\n"
)


def agent_loop(messages: list[dict]):
    """Agent 主循环 — 通过 trigger_hooks() 挂载扩展逻辑，循环体保持简洁。"""
    while True:
        # ── 调用 LLM ──
        response = call_llm(messages=messages, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
        messages.append(response["assistant_message"])

        # ── 模型没有请求工具调用 → 触发 Stop hook 并退出 ──
        if response["finish_reason"] != "tool_calls":
            # Stop hook: 退出前做统计/摘要
            # 如果 hook 返回非 None，说明要求继续（强制续跑）
            force_continue = trigger_hooks("Stop", messages)
            if force_continue:
                messages.append({"role": "user", "content": str(force_continue)})
                continue
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        # ── 执行工具调用 ──
        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]

            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            # 打印工具名（简化显示）
            label = {"bash": f"$ {tool_args.get('command','')}",
                     "read_file": f"[read] {tool_args.get('path','')}",
                     "write_file": f"[write] {tool_args.get('path','')}",
                     "edit_file": f"[edit] {tool_args.get('path','')}",
                     "glob": f"[glob] {tool_args.get('pattern','')}"}
            print(f"\033[36m> {label.get(tool_name, tool_name)}\033[0m")

            # ── s04 核心改进：PreToolUse hook 替代硬编码权限检查 ──
            # trigger_hooks 调用所有已注册的 PreToolUse hook（如 permission_hook, log_hook）
            # 如果某个 hook 返回非 None → 表示阻止执行
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

                # ── PostToolUse hook: 工具执行后处理 ──
                # 可用于检查输出大小、后处理等
                trigger_hooks("PostToolUse", tool_name, tool_args, output)

            preview = output[:300]
            if len(output) > 300:
                preview += "..."
            if preview.strip():
                print(preview)

            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})


def main():
    print("=" * 50)
    print("  s04: Hooks — 事件驱动的扩展机制")
    print("  4 事件: UserPromptSubmit / PreToolUse / PostToolUse / Stop")
    print("  5 Hook: context_inject / permission / log / large_output / summary")
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

        # UserPromptSubmit hook: 用户输入后、LLM 调用前触发
        trigger_hooks("UserPromptSubmit", query)

        history.append({"role": "user", "content": query})
        agent_loop(history)
        print()


if __name__ == "__main__":
    main()
