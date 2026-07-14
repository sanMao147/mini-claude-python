"""
============================================================================
  s01_agent_loop/main.py — 最小 Agent 循环
============================================================================
  这是整个 mini-claude-python 项目的第一课，实现一个最小可用的 AI Agent。

  核心概念：Agent = LLM + 工具 + 循环
  ┌────────┐     ┌──────┐     ┌────────┐
  │  User  │ --> │  LLM │ --> │  Tool  │
  │ prompt │     │      │     │ execute│
  └────────┘     └──┬───┘     └───┬────┘
                    ^              │
                    │  tool_result │
                    └──────────────┘
                    (循环继续，直到模型停止调用工具)

  s01 只有 1 个工具：bash（执行 shell 命令）。

  运行方式：
      python s01_agent_loop/main.py

  对话中：
    - 输入你的需求，Agent 使用 bash 工具来完成任务
    - 输入 q / exit / 空行 退出
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
# 这是 Agent 的"人格"设定，告诉模型它的角色、能力和行为规范。
# 在 OpenAI 兼容接口中，system prompt 作为 role="system" 的消息传递。
SYSTEM_PROMPT = (
    f"你是一个编程助手 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "你可以使用 bash 工具执行 shell 命令来完成任务。\n"
    "规则：\n"
    "  1. 先行动，后解释。直接执行命令，不要先长篇大论。\n"
    "  2. 命令执行后简要汇报结果。\n"
    "  3. 如果需要多步操作，逐步执行，每步一个命令。\n"
)


# ============================================================================
# Agent 主循环 — 整个项目的核心模式
# ============================================================================

def agent_loop(messages: list[dict]):
    """
    Agent 主循环。

    这是整个项目最核心的模式，所有后续步骤都是在此基础上增加功能：

    1. 调用 LLM，传入对话历史和工具定义
    2. 如果模型返回 tool_calls，执行这些工具调用
    3. 将工具执行结果追加到对话历史
    4. 重复步骤 1，直到模型停止调用工具（finish_reason != "tool_calls"）
    """
    while True:
        # ── 步骤 1: 调用 LLM ──
        response = call_llm(
            messages=messages,
            tools=TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )

        # ── 步骤 2: 保存模型的回复到对话历史 ──
        messages.append(response["assistant_message"])

        # ── 步骤 3: 判断是否继续 ──
        # finish_reason == "tool_calls" → 模型想调用工具，继续循环
        # finish_reason == "stop"       → 模型认为任务完成，退出循环
        if response["finish_reason"] != "tool_calls":
            # 打印模型的最终回复
            text = response["content"]
            if text.strip():
                print(f"\n{text}")
            return

        # ── 步骤 4: 执行工具调用 ──
        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]
            tool_args = json.loads(func["arguments"])  # 参数是 JSON 字符串

            # 打印即将执行的命令（黄色，让用户看到 Agent 在做什么）
            if tool_name == "bash":
                print(f"\033[33m$ {tool_args.get('command', '')}\033[0m")

            # 从 TOOL_HANDLERS 查找执行函数
            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                output = f"错误: 未知工具 '{tool_name}'"
            else:
                try:
                    output = handler(**tool_args)
                except Exception as e:
                    output = f"错误: 工具执行异常 - {e}"

            # 打印部分输出
            output_preview = output[:300]
            if len(output) > 300:
                output_preview += "..."
            if output_preview.strip():
                print(output_preview)

            # ── 步骤 5: 将工具结果注入对话历史 ──
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })

        # 循环回到步骤 1，让模型看到工具结果后继续思考


# ============================================================================
# 入口 — 交互式对话
# ============================================================================

def main():
    """交互式对话入口。"""
    print("=" * 50)
    print("  s01: Agent Loop — 最小 Agent 循环")
    print("  1 个工具 (bash) + while True 循环")
    print("=" * 50)
    print("输入你的需求，回车发送。输入 q / exit 退出。\n")

    # 对话历史（不含 system prompt，system prompt 每次调用时传入）
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

        # 将用户输入加入对话历史
        history.append({"role": "user", "content": query})

        # 启动 Agent 循环
        agent_loop(history)

        print()  # 空行分隔不同轮对话


if __name__ == "__main__":
    main()
