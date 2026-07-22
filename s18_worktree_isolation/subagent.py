"""
============================================================================
  s06_subagent/subagent.py — 子 Agent 系统
============================================================================
  s06 的核心新增模块。

  设计理念：大任务拆成小任务，每个子 Agent 拥有全新的 messages[]，
  中间过程全部丢弃，只回传最终文本摘要。

  子 Agent 的限制：
    - 无 task 工具（禁止递归创建子子 Agent）
    - 最多 30 轮安全限制
    - 工具调用也走 PreToolUse hook（权限不跳过）

  核心函数：spawn_subagent(prompt, cwd=None) -> str
============================================================================
"""

import json, os

from tools import WORKSPACE_DIR
from llm import call_llm
from hooks import trigger_hooks


# ============================================================================
# 子 Agent 专用工具集（无 task 工具，禁止递归）
# ============================================================================

# 子 Agent 的系统提示词 — 强调"完成即返回摘要，不要委派"
SUB_SYSTEM_PROMPT = (
    f"你是一个编程助手子 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "完成被分配的任务后，返回简洁的英文摘要。不要进一步委派任务。\n"
    "可用工具: bash, read_file, write_file, edit_file, glob\n"
    "Act directly, summarize concisely when done."
)

# 子 Agent 可用的工具 — 不含 task 工具（防止递归创建子 Agent）
SUB_TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "执行 shell 命令。",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取文件。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入文件。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "精确替换文本。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "glob", "description": "通配符查找文件。",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
]

# 子 Agent 工具处理函数（从 tools 模块导入）
SUB_HANDLERS = {}  # 将在 main.py 中从 tools.TOOL_HANDLERS 复制基础 5 个工具


# ============================================================================
# 子 Agent 执行函数
# ============================================================================

def spawn_subagent(prompt: str, cwd: str | None = None) -> str:
    """
    创建一个子 Agent，在全新上下文中执行指定任务。

    参数：
      prompt: 给子 Agent 的任务描述
      cwd:    子 Agent 的工作目录（None 表示使用默认工作区）

    返回：
      子 Agent 的最终文本摘要
      （所有中间工具调用和内部对话都被丢弃，不污染主 Agent 上下文）

    安全限制：
      - 最多 30 轮对话（防止无限循环）
      - 无 task 工具（无法再创建子 Agent）
    """
    work_dir = cwd or WORKSPACE_DIR
    print(f"\033[35m[子 Agent 启动] {prompt[:80]}...\033[0m")

    # ── 子 Agent 拥有全新的 messages 列表（上下文隔离） ──
    sub_messages = [
        {"role": "user", "content": prompt},
    ]

    MAX_SUB_TURNS = 30  # 安全限制：最多 30 轮

    for turn in range(MAX_SUB_TURNS):
        # 调用 LLM
        response = call_llm(
            messages=sub_messages,
            tools=SUB_TOOLS,
            system_prompt=SUB_SYSTEM_PROMPT,
        )
        sub_messages.append(response["assistant_message"])

        # ── 模型完成（不再调用工具）→ 返回最终文本 ──
        if response["finish_reason"] != "tool_calls":
            result = response["content"]
            print(f"\033[35m[子 Agent 完成] {turn+1} 轮, 输出 {len(result)} 字符\033[0m")
            return result

        # ── 执行工具调用 ──
        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]

            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            # 子 Agent 的工具调用也走 PreToolUse hook（权限不跳过）
            blocked = trigger_hooks("PreToolUse", tool_name, tool_args)
            if blocked:
                output = str(blocked)
            else:
                handler = SUB_HANDLERS.get(tool_name)
                if handler:
                    try:
                        output = handler(**tool_args)
                    except Exception as e:
                        output = f"错误: {e}"
                else:
                    output = f"错误: 子 Agent 不支持工具 '{tool_name}'"

            # 注入工具结果
            sub_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })

    # 达到最大轮数限制
    print(f"\033[35m[子 Agent 超时] 达到 {MAX_SUB_TURNS} 轮限制\033[0m")
    return f"子 Agent 达到最大轮数限制 ({MAX_SUB_TURNS})，未能完成任务。"
