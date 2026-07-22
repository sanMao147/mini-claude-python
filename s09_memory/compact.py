"""s09 四层上下文压缩管线 — 便宜先做，贵的后做

执行顺序：
  L3: tool_result_budget  — 单条 tool_result > 200KB 时落盘到文件
  L1: snip_compact        — 消息 > 50 条时保留头 3 + 尾 47
  L2: micro_compact       — 只保留最近 3 条完整 tool_result
  L4: compact_history     — 前三层不够时，调用 LLM 生成全量摘要
  应急：reactive_compact  — API 返回 prompt_too_long 时触发
  熔断：连续失败 3 次停止
"""

import os, json, hashlib, time
from pathlib import Path
from config import WORKSPACE_DIR, TASK_OUTPUT_DIR

_consecutive_failures = 0  # 连续压缩失败计数器（熔断器）
MAX_FAILURES = 3

SNIP_HEAD = 3       # snip 保留头部消息数
SNIP_TAIL = 47      # snip 保留尾部消息数
MICRO_KEEP = 3      # micro 保留最近 tool_result 数
BUDGET_LIMIT = 200 * 1024  # 200KB tool_result 总大小阈值


def reset_failures():
    global _consecutive_failures
    _consecutive_failures = 0


def _circuit_breaker() -> bool:
    """熔断器：连续失败超限返回 True。"""
    global _consecutive_failures
    _consecutive_failures += 1
    if _consecutive_failures >= MAX_FAILURES:
        print(f"\033[31m[压缩熔断] 连续 {MAX_FAILURES} 次压缩失败，停止尝试\033[0m")
        return True
    return False


# L1: Snip Compact — 消息数量截断（保留头部系统设定 + 尾部最新上下文）
def snip_compact(messages: list[dict]) -> list[dict]:
    """裁剪消息列表：保留头 SNIP_HEAD 条 + 尾 SNIP_TAIL 条，中间注入裁剪标记。"""
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


# L2: Micro Compact — 只保留最近 MICRO_KEEP 条完整 tool_result，更早的用占位符替换
def micro_compact(messages: list[dict]) -> list[dict]:
    """裁剪 tool_result 内容：只保留最近 MICRO_KEEP 条完整内容，更早的替换为占位符。"""
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


# L3: Tool Result Budget — 大输出落盘到 .task_outputs/，tool_result 替换为文件引用
def tool_result_budget(messages: list[dict]) -> list[dict]:
    """检查最近一条 user 消息大小，超过 BUDGET_LIMIT 时落盘到文件。"""
    os.makedirs(TASK_OUTPUT_DIR, exist_ok=True)

    # 从后往前找最近的一条 user 消息
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


# L4: Compact History — 前三层不够时，调用 LLM 生成对话摘要替换历史
def compact_history(messages: list[dict], call_llm_func) -> list[dict] | None:
    """调用 LLM 生成对话摘要，用摘要替换历史消息，保留最近 5 条。失败返回 None。"""
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
        # 用侧查询生成摘要
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
        abbreviated.extend(messages[-5:])  # 保留最近 5 条消息

        _consecutive_failures = 0  # 成功后重置
        print(f"\033[95m[压缩完成] 对话已浓缩为 {len(summary)} 字符摘要\033[0m")
        return abbreviated

    except Exception as e:
        print(f"\033[31m[压缩失败] {e}\033[0m")
        return None


# Reactive Compact — API 报 prompt_too_long 时触发：全部 micro + snip + LLM 摘要
def reactive_compact(messages: list[dict], call_llm_func) -> list[dict] | None:
    """应急压缩：micro + snip + LLM 摘要，LLM 失败则用激进裁剪。"""
    print(f"\033[33m[应急压缩] 检测到上下文过长，执行应急压缩...\033[0m")

    # L2 → L1
    messages = micro_compact(messages)
    messages = snip_compact(messages)

    # L4 尝试 LLM 摘要
    result = compact_history(messages, call_llm_func)
    if result:
        return result

    # LLM 摘要失败，强制 micro + snip 后返回
    print(f"\033[33m[应急压缩] LLM 摘要失败，使用激进裁剪\033[0m")
    return snip_compact(micro_compact(messages))


def run_compaction_pipeline(messages: list[dict], call_llm_func) -> list[dict]:
    """在 LLM 调用前执行完整压缩管线：L3(budget) → L1(snip) → L2(micro) → 检查 → L4(auto)。"""
    messages = tool_result_budget(messages)
    messages = snip_compact(messages)
    messages = micro_compact(messages)

    # L4 自动压缩条件：简单估算 token 数（中文约 1 字/token，英文约 0.75 字/token）
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    AUTO_COMPACT_THRESHOLD = 80 * 1024  # 约相当于 60K tokens

    if total_chars > AUTO_COMPACT_THRESHOLD:
        result = compact_history(messages, call_llm_func)
        if result:
            return result

    return messages


def run_compact(call_llm_func=None):
    """compact 工具入口：Agent 主动请求压缩，实际效果在下一轮 LLM 调用前生效。"""
    return "compact 工具已调用。上下文将在下一轮 LLM 调用前自动压缩。"
