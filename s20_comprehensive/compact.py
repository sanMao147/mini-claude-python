"""
============================================================================
  s08_context_compact/compact.py — 四层上下文压缩管线
============================================================================
  s08 的核心新增模块。当对话历史太长时，通过四层压缩避免上下文溢出。

  执行顺序（沿用 Claude Code 的策略：便宜先做，贵的后做）：

    L3: tool_result_budget  — 单条消息 tool_result 总和 > 200KB 时落盘到文件
    L1: snip_compact        — 消息 > 50 条时保留头 3 + 尾 47
    L2: micro_compact       — 只保留最近 3 条完整 tool_result
    L4: compact_history     — 前三层不够时，调用 LLM 生成全量摘要

  应急：reactive_compact    — API 返回 prompt_too_long 时触发
  熔断：连续失败 3 次停止

  已新增 compact 工具，允许 Agent 主动触发压缩。
============================================================================
"""

import os, sys, json, hashlib, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WORKSPACE_DIR, TASK_OUTPUT_DIR

# 连续压缩失败计数器（熔断器）。
# 只有 LLM 摘要类压缩可能失败；普通裁剪是本地确定性操作，不需要计入失败。
_consecutive_failures = 0
MAX_FAILURES = 3

# 压缩参数。
# 这里的数值偏保守：优先保留最新上下文，避免 Agent 丢掉正在执行的任务状态。
SNIP_HEAD = 3       # snip 保留头部消息数
SNIP_TAIL = 47      # snip 保留尾部消息数
MICRO_KEEP = 3      # micro 保留最近 tool_result 数
BUDGET_LIMIT = 200 * 1024  # 200KB tool_result 总大小阈值


def reset_failures():
    """重置熔断器计数器。"""
    global _consecutive_failures
    # 摘要成功或外部明确恢复后调用，允许后续再次尝试 LLM 压缩。
    _consecutive_failures = 0


def _circuit_breaker() -> bool:
    """熔断器：连续失败超限返回 True。"""
    global _consecutive_failures
    # 每次进入 LLM 摘要前先记一次失败风险；真正成功时 compact_history 会清零。
    _consecutive_failures += 1
    if _consecutive_failures >= MAX_FAILURES:
        print(f"\033[31m[压缩熔断] 连续 {MAX_FAILURES} 次压缩失败，停止尝试\033[0m")
        return True
    return False


# ============================================================================
# L1: Snip Compact — 消息数量截断
# ============================================================================
# 当消息数超过 SNIP_HEAD + SNIP_TAIL 时，删除中间的消息。
# 保留头部（系统设定、早期对话）和尾部（最新上下文）。

def snip_compact(messages: list[dict]) -> list[dict]:
    """
    裁剪消息列表：保留头 SNIP_HEAD 条 + 尾 SNIP_TAIL 条。
    如果消息数不超标则原样返回。
    """
    if len(messages) <= SNIP_HEAD + SNIP_TAIL:
        return messages

    # head 通常包含系统设定和最早的任务背景；tail 包含最近操作和工具结果。
    head = messages[:SNIP_HEAD]
    tail = messages[-SNIP_TAIL:]
    removed = len(messages) - SNIP_HEAD - SNIP_TAIL

    # 注入裁剪标记，让模型知道中间历史不是“自然消失”，而是被主动压缩。
    marker = {
        "role": "user",
        "content": f"[上下文裁剪] 已移除中间 {removed} 条消息以节省上下文空间。保留开头 {SNIP_HEAD} 条和结尾 {SNIP_TAIL} 条。",
    }
    return head + [marker] + tail


# ============================================================================
# L2: Micro Compact — 保留最近几条完整输出
# ============================================================================
# 对于 tool 角色消息（role: "tool"），只保留最近 MICRO_KEEP 条的完整 content。
# 更早的 tool 消息用占位符替换 content。

def micro_compact(messages: list[dict]) -> list[dict]:
    """
    裁剪 tool_result 内容：只保留最近 MICRO_KEEP 条完整内容。
    更早的 tool 消息替换为占位符。
    """
    # 从后往前找 tool 消息：越靠后的工具结果越新，通常越可能影响当前下一步。
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
        # 只替换 content，不删除整条 tool 消息，避免破坏 tool_call_id 等对话结构。
        messages[idx]["content"] = f"[输出已压缩] ({len(old_content)} 字符的旧工具输出被替换为占位符)"

    return messages


# ============================================================================
# L3: Tool Result Budget — 大输出落盘
# ============================================================================
# 单条 user 消息中所有 tool_result 的总大小超过 BUDGET_LIMIT (200KB) 时，
# 将大的结果写入 .task_outputs/ 目录文件，tool_result 中替换为文件引用。

def tool_result_budget(messages: list[dict]) -> list[dict]:
    """
    检查最后一条 user 消息中的 tool_result 大小。
    对于超过预算的结果，将其落盘到文件中。
    """
    os.makedirs(TASK_OUTPUT_DIR, exist_ok=True)

    # 从后往前找最近的一条 user 消息。
    # 当前实现只处理最近消息，避免扫描整段历史时反复改写旧上下文。
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > BUDGET_LIMIT:
            # 落盘到文件：上下文里只保留引用，完整内容留在工作区供工具按需读取。
            filename = f"tool_result_{int(time.time())}_{hashlib.md5(content[:100].encode()).hexdigest()[:8]}.txt"
            filepath = os.path.join(TASK_OUTPUT_DIR, filename)
            Path(filepath).write_text(content, encoding="utf-8", errors="replace")
            m["content"] = f"[大输出已落盘] 完整内容 ({len(content)} 字节) 保存在 {filepath}"
        break

    return messages


# ============================================================================
# L4: Compact History — LLM 全量摘要
# ============================================================================
# 前三层压缩后仍不够时，调用 LLM 生成对话摘要。
# 用一个侧查询（side query）让 LLM 总结历史，用摘要替换历史消息。

def compact_history(messages: list[dict], call_llm_func) -> list[dict] | None:
    """
    调用 LLM 生成对话摘要，用摘要替换历史消息。

    参数：
      messages:     完整对话历史
      call_llm_func: LLM 调用函数（来自 llm.py）

    返回压缩后的消息列表，失败返回 None。
    """
    global _consecutive_failures

    if _circuit_breaker():
        return None

    # 构建压缩提示词。
    # 摘要必须保留“约束、已做动作、当前进度、文件修改”，否则压缩后容易跑偏。
    compact_prompt = (
        "请总结以下对话历史的关键信息。保留：\n"
        "1. 用户的需求和约束条件\n"
        "2. 已完成的操作及其结果\n"
        "3. 当前任务进度和待完成事项\n"
        "4. 重要的文件修改记录\n\n"
        "用简洁的要点形式输出摘要。"
    )

    try:
        # 用侧查询生成摘要：不直接改原 messages，只有拿到有效 summary 后才替换历史。
        summary_messages = messages + [{"role": "user", "content": compact_prompt}]
        response = call_llm_func(
            messages=summary_messages,
            system_prompt="你是一个对话摘要助手。用简洁的要点总结对话。",
            max_tokens=2000,
        )

        summary = response["content"]
        if not summary:
            return None

        # 用摘要替换历史。
        # 摘要作为 user 消息注入，后面再拼最近 5 条，兼顾长期背景和短期上下文。
        abbreviated = [
            {"role": "user", "content": f"[对话摘要]\n{summary}\n\n（以下为最近对话）"},
        ]
        # 保留最近 5 条消息
        abbreviated.extend(messages[-5:])

        _consecutive_failures = 0  # 成功后重置
        print(f"\033[95m[压缩完成] 对话已浓缩为 {len(summary)} 字符摘要\033[0m")
        return abbreviated

    except Exception as e:
        print(f"\033[31m[压缩失败] {e}\033[0m")
        return None


# ============================================================================
# Reactive Compact — 应急压缩
# ============================================================================
# 当 API 仍返回 prompt_too_long 错误时触发。
# 执行最激进的压缩策略：全部 micro + snip + LLM 摘要。

def reactive_compact(messages: list[dict], call_llm_func) -> list[dict] | None:
    """
    应急压缩：API 报告上下文过长时触发。

    策略：
    1. 执行 micro compact（只保留最近 3 条完整输出）
    2. 执行 snip compact（消息数限制）
    3. 尝试 LLM 全量摘要
    """
    print(f"\033[33m[应急压缩] 检测到上下文过长，执行应急压缩...\033[0m")

    # L2 → L1：先压缩工具大输出，再裁剪消息数量，尽量保留近期对话结构。
    messages = micro_compact(messages)
    messages = snip_compact(messages)

    # L4 尝试 LLM 摘要；如果此时 API 仍然接受请求，摘要质量通常最好。
    result = compact_history(messages, call_llm_func)
    if result:
        return result

    # 如果 LLM 摘要也失败了，强制 micro + snip 后返回
    print(f"\033[33m[应急压缩] LLM 摘要失败，使用激进裁剪\033[0m")
    return snip_compact(micro_compact(messages))


# ============================================================================
# 压缩检查入口 — 在 LLM 调用前执行
# ============================================================================

def run_compaction_pipeline(messages: list[dict], call_llm_func) -> list[dict]:
    """
    在 LLM 调用前执行完整的压缩管线。

    顺序：L3(budget) → L1(snip) → L2(micro) → 检查 → L4(auto)

    返回压缩后的消息列表。
    """
    # L3: tool_result 大小预算检查。
    # 先处理大块输出，可以用最小代价快速降低上下文体积。
    messages = tool_result_budget(messages)

    # L1: 消息数量截断
    messages = snip_compact(messages)

    # L2: 微压缩
    messages = micro_compact(messages)

    # L4 自动压缩的条件判断：
    # 简单估算 token 数（中文约 1 字/token，英文约 0.75 字/token）
    # 如果总字符数超过阈值，触发 LLM 摘要
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    AUTO_COMPACT_THRESHOLD = 80 * 1024  # 约相当于 60K tokens

    if total_chars > AUTO_COMPACT_THRESHOLD:
        result = compact_history(messages, call_llm_func)
        if result:
            return result

    return messages


# ============================================================================
# Compact 工具 — 允许 Agent 主动触发压缩
# ============================================================================

def run_compact(call_llm_func=None):
    """
    compact 工具：Agent 主动请求压缩上下文。

    这是一个简化版，实际效果取决于调用时的 messages 状态。
    参数 call_llm_func 由 main.py 在运行时注入。
    """
    return "compact 工具已调用。上下文将在下一轮 LLM 调用前自动压缩。"
