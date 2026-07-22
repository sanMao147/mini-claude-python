"""
============================================================================
  s08_context_compact/compact.py — 四层上下文压缩管线
============================================================================
"""

import os, json, hashlib, time
from pathlib import Path

from config import WORKSPACE_DIR, TASK_OUTPUT_DIR

_consecutive_failures = 0
MAX_FAILURES = 3
SNIP_HEAD = 3
SNIP_TAIL = 47
MICRO_KEEP = 3
BUDGET_LIMIT = 200 * 1024


def reset_failures():
    global _consecutive_failures
    _consecutive_failures = 0


def _circuit_breaker() -> bool:
    global _consecutive_failures
    _consecutive_failures += 1
    if _consecutive_failures >= MAX_FAILURES:
        print(f"\033[31m[压缩熔断] 连续 {MAX_FAILURES} 次压缩失败，停止尝试\033[0m")
        return True
    return False


def snip_compact(messages: list[dict]) -> list[dict]:
    if len(messages) <= SNIP_HEAD + SNIP_TAIL:
        return messages

    head = messages[:SNIP_HEAD]
    tail = messages[-SNIP_TAIL:]
    removed = len(messages) - SNIP_HEAD - SNIP_TAIL

    marker = {
        "role": "user",
        "content": f"[上下文裁剪] 已移除中间 {removed} 条消息以节省上下文空间。保留开头 {SNIP_HEAD} 条和结尾 {SNIP_TAIL} 条。",
    }
    return head + [marker] + tail


def micro_compact(messages: list[dict]) -> list[dict]:
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    keep_count = 0
    indices_to_truncate = []

    for idx in reversed(tool_indices):
        if keep_count < MICRO_KEEP:
            keep_count += 1
        else:
            indices_to_truncate.append(idx)

    if not indices_to_truncate:
        return messages

    for idx in indices_to_truncate:
        old_content = messages[idx].get("content", "")
        messages[idx]["content"] = f"[输出已压缩] ({len(old_content)} 字符的旧工具输出被替换为占位符)"

    return messages


def tool_result_budget(messages: list[dict]) -> list[dict]:
    os.makedirs(TASK_OUTPUT_DIR, exist_ok=True)

    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > BUDGET_LIMIT:
            filename = f"tool_result_{int(time.time())}_{hashlib.md5(content[:100].encode()).hexdigest()[:8]}.txt"
            filepath = os.path.join(TASK_OUTPUT_DIR, filename)
            Path(filepath).write_text(content, encoding="utf-8", errors="replace")
            m["content"] = f"[大输出已落盘] 完整内容 ({len(content)} 字节) 保存在 {filepath}"
        break

    return messages


def compact_history(messages: list[dict], call_llm_func) -> list[dict] | None:
    global _consecutive_failures

    if _circuit_breaker():
        return None

    compact_prompt = (
        "请总结以下对话历史的关键信息。保留：\n"
        "1. 用户的需求和约束条件\n"
        "2. 已完成的操作及其结果\n"
        "3. 当前任务进度和待完成事项\n"
        "4. 重要的文件修改记录\n\n"
        "用简洁的要点形式输出摘要。"
    )

    try:
        summary_messages = messages + [{"role": "user", "content": compact_prompt}]
        response = call_llm_func(
            messages=summary_messages,
            system_prompt="你是一个对话摘要助手。用简洁的要点总结对话。",
            max_tokens=2000,
        )

        summary = response["content"]
        if not summary:
            return None

        abbreviated = [
            {"role": "user", "content": f"[对话摘要]\n{summary}\n\n（以下为最近对话）"},
        ]
        abbreviated.extend(messages[-5:])

        _consecutive_failures = 0
        print(f"\033[95m[压缩完成] 对话已浓缩为 {len(summary)} 字符摘要\033[0m")
        return abbreviated

    except Exception as e:
        print(f"\033[31m[压缩失败] {e}\033[0m")
        return None


def reactive_compact(messages: list[dict], call_llm_func) -> list[dict] | None:
    print(f"\033[33m[应急压缩] 检测到上下文过长，执行应急压缩...\033[0m")

    messages = micro_compact(messages)
    messages = snip_compact(messages)

    result = compact_history(messages, call_llm_func)
    if result:
        return result

    print(f"\033[33m[应急压缩] LLM 摘要失败，使用激进裁剪\033[0m")
    return snip_compact(micro_compact(messages))


def run_compaction_pipeline(messages: list[dict], call_llm_func) -> list[dict]:
    messages = tool_result_budget(messages)
    messages = snip_compact(messages)
    messages = micro_compact(messages)

    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    AUTO_COMPACT_THRESHOLD = 80 * 1024

    if total_chars > AUTO_COMPACT_THRESHOLD:
        result = compact_history(messages, call_llm_func)
        if result:
            return result

    return messages


def run_compact(call_llm_func=None):
    return "compact 工具已调用。上下文将在下一轮 LLM 调用前自动压缩。"