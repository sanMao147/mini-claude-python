"""s06 子 Agent 系统 — 大任务拆小，独立上下文"""

import json, os

from tools import WORKSPACE_DIR
from llm import call_llm
from hooks import trigger_hooks

SUB_SYSTEM_PROMPT = (
    f"你是一个编程助手子 Agent，工作目录为 {WORKSPACE_DIR}。\n"
    "完成被分配的任务后，返回简洁的英文摘要。不要进一步委派任务。\n"
    "可用工具: bash, read_file, write_file, edit_file, glob\n"
    "Act directly, summarize concisely when done."
)

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

SUB_HANDLERS = {}


def spawn_subagent(prompt: str, cwd: str | None = None) -> str:
    """创建子 Agent，在隔离上下文中执行任务并返回文本摘要。

    安全限制：最多 30 轮（防无限循环），无 task 工具（禁止递归）。
    """
    work_dir = cwd or WORKSPACE_DIR
    print(f"\033[35m[子 Agent 启动] {prompt[:80]}...\033[0m")

    sub_messages = [
        {"role": "user", "content": prompt},
    ]

    MAX_SUB_TURNS = 30

    for turn in range(MAX_SUB_TURNS):
        response = call_llm(
            messages=sub_messages,
            tools=SUB_TOOLS,
            system_prompt=SUB_SYSTEM_PROMPT,
        )
        sub_messages.append(response["assistant_message"])

        if response["finish_reason"] != "tool_calls":
            result = response["content"]
            print(f"\033[35m[子 Agent 完成] {turn+1} 轮, 输出 {len(result)} 字符\033[0m")
            return result

        for tc in response["tool_calls"]:
            func = tc["function"]
            tool_name = func["name"]

            try:
                tool_args = json.loads(func["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

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

            sub_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": output,
            })

    print(f"\033[35m[子 Agent 超时] 达到 {MAX_SUB_TURNS} 轮限制\033[0m")
    return f"子 Agent 达到最大轮数限制 ({MAX_SUB_TURNS})，未能完成任务。"