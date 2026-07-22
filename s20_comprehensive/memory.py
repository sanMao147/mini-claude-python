"""
============================================================================
  s09_memory/memory.py — 持久化记忆系统
============================================================================
  s09 的核心新增模块。

  三个子系统：
  1. 存储 — .memory/ 目录下 Markdown 文件 + YAML frontmatter
  2. 加载 — MEMORY_INDEX 常驻 System Prompt；select_relevant_memories() 用 LLM
            侧查询选相关记忆（最多 5 条），关键词降级兜底
  3. 写入 — 每轮 stop_reason != "tool_calls" 时 extract_memories() 自动提取

  整理：文件数达 10 时 consolidate_memories() 去重合并

  四种记忆类型：
    user     — 用户偏好
    feedback — 用户反馈
    project  — 项目上下文
    reference — 参考信息
============================================================================
"""

import os, json, yaml, re
from pathlib import Path
from tools import WORKSPACE_DIR, MEMORY_DIR

os.makedirs(MEMORY_DIR, exist_ok=True)

# 记忆索引文件。
# MEMORY.md 只保存目录摘要，真正内容分散在独立 Markdown 文件里。
MEMORY_INDEX_FILE = os.path.join(MEMORY_DIR, "MEMORY.md")

# 记忆列表缓存。
# 读多写少场景下避免每轮 prompt 组装都反复扫描 .memory/。
_memories_cache: list[dict] = []

# 记忆文件数阈值（超过此数触发整理）。
# 文件过多会让选择和 prompt 注入成本变高，所以达到阈值后触发合并。
CONSOLIDATE_THRESHOLD = 10


# ============================================================================
# 存储 — 写记忆文件
# ============================================================================

def write_memory_file(name: str, content: str, mem_type: str = "reference", description: str = "") -> str:
    """
    将记忆写入 .memory/ 目录的 Markdown 文件。

    格式：
      ---
      name: 记忆名称
      description: 简短描述
      type: user|feedback|project|reference
      ---
      记忆内容

    返回文件路径。
    """
    # 文件名只保留安全字符，避免记忆名称里带路径分隔符或特殊符号。
    safe_name = re.sub(r'[^\w\-]', '_', name.lower())
    filename = f"{safe_name}.md"
    filepath = os.path.join(MEMORY_DIR, filename)

    # 构建 YAML frontmatter + Markdown 内容。
    # frontmatter 用于快速扫描摘要，正文保存完整记忆。
    yaml_header = yaml.dump({
        "name": name,
        "description": description,
        "type": mem_type,
    }, allow_unicode=True, default_flow_style=False).strip()

    file_content = f"---\n{yaml_header}\n---\n\n{content}"

    Path(filepath).write_text(file_content, encoding="utf-8")

    # 更新索引文件，方便人工查看和 system prompt 构建目录。
    _update_memory_index(name, description, mem_type, filename)

    # 清除缓存，确保下一次读取能看到刚写入的新记忆。
    global _memories_cache
    _memories_cache = []

    return f"记忆已保存至 {filename}"


def _update_memory_index(name: str, description: str, mem_type: str, filename: str):
    """更新 MEMORY.md 索引文件。"""
    entry = f"- **{name}** ({mem_type}): {description} → `{filename}`"

    if os.path.exists(MEMORY_INDEX_FILE):
        existing = Path(MEMORY_INDEX_FILE).read_text(encoding="utf-8")
        lines = existing.strip().splitlines()
    else:
        lines = ["# Memory Index\n"]

    # 检查是否已有同名条目；同名记忆更新摘要，不额外追加重复索引。
    for i, line in enumerate(lines):
        if f"**{name}**" in line:
            lines[i] = entry
            break
    else:
        lines.append(entry)

    Path(MEMORY_INDEX_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ============================================================================
# 加载 — 选择相关记忆
# ============================================================================

def _scan_memory_dir() -> list[dict]:
    """扫描 .memory/ 目录，返回所有记忆列表。"""
    global _memories_cache
    if _memories_cache:
        # 缓存只在写入后清空，因此这里可以直接返回。
        return _memories_cache

    memories = []
    if not os.path.exists(MEMORY_DIR):
        return memories

    for entry in sorted(os.listdir(MEMORY_DIR)):
        if not entry.endswith('.md') or entry == "MEMORY.md":
            continue

        filepath = os.path.join(MEMORY_DIR, entry)
        try:
            text = Path(filepath).read_text(encoding="utf-8")
            meta = _parse_memory_frontmatter(text)
            # file 用于后续删除/合并，content 用于 LLM 做相关性选择或整理。
            meta["file"] = entry
            meta["content"] = text
            memories.append(meta)
        except Exception:
            continue

    _memories_cache = memories
    return memories


def _parse_memory_frontmatter(text: str) -> dict:
    """解析记忆文件的 YAML frontmatter。"""
    if not text.startswith("---"):
        # 没有 frontmatter 的旧文件按 reference 类型处理。
        return {"name": "unknown", "description": "", "type": "reference"}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"name": "unknown", "description": "", "type": "reference"}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {"name": "unknown", "description": "", "type": "reference"}


def select_relevant_memories(query: str, call_llm_func) -> list[dict]:
    """
    根据用户查询选择最相关的记忆（最多 5 条）。

    策略：
    1. 如果记忆数 <= 5，全部返回
    2. 用 LLM 侧查询选择相关记忆
    3. LLM 调用失败时，用关键词匹配降级
    """
    all_memories = _scan_memory_dir()
    if not all_memories:
        return []

    if len(all_memories) <= 5:
        return all_memories

    # 用 LLM 选择相关记忆。
    # 这里给 LLM 的只是 name/description 列表，不直接塞入完整记忆内容，控制选择成本。
    memory_list = "\n".join(
        f"- {m.get('name','unknown')}: {m.get('description','')}"
        for m in all_memories
    )

    select_prompt = (
        f"用户查询: {query}\n\n"
        f"可用记忆:\n{memory_list}\n\n"
        "从以上记忆中选择与用户查询最相关的最多 5 条。"
        "只返回记忆名称列表（逗号分隔），如: name1, name2, name3"
    )

    try:
        response = call_llm_func(
            messages=[{"role": "user", "content": select_prompt}],
            system_prompt="你是一个记忆选择助手。只返回相关的记忆名称。",
            max_tokens=200,
        )
        selected_names = [n.strip() for n in response.get("content", "").split(",")]
    except Exception:
        selected_names = []

    if not selected_names:
        # 降级：关键词匹配。
        # LLM 选择失败时仍尽量给出相关记忆，而不是完全丢弃记忆能力。
        keywords = query.lower().split()
        scored = []
        for m in all_memories:
            score = sum(1 for kw in keywords if kw in str(m).lower())
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        selected_names = [m["name"] for _, m in scored[:5]]

    # 按名查找。
    # 只返回真正命中的条目，避免 LLM 输出不存在名称时污染结果。
    result = []
    for name in selected_names:
        for m in all_memories:
            if m.get("name", "").strip() == name:
                result.append(m)
                break

    return result[:5]


# ============================================================================
# 写入 — 自动提取记忆
# ============================================================================

def extract_memories(messages: list[dict], call_llm_func) -> str | None:
    """
    从对话历史中提取值得保存的记忆。

    在每轮 stop_reason != "tool_calls" 时调用。
    返回新创建的记忆数量字符串，如未提取则返回 None。
    """
    if len(messages) < 3:
        # 对话太短时通常没有稳定偏好或项目结论，跳过可减少误提取。
        return None

    extract_prompt = (
        "从以下对话中提取值得持久化保存的信息。只提取以下类型：\n"
        "1. 用户的偏好和习惯 (user)\n"
        "2. 用户的明确反馈 (feedback)\n"
        "3. 重要的项目上下文 (project)\n"
        "4. 有用的参考信息 (reference)\n\n"
        "如果没有值得保存的信息，回复 'NONE'。\n"
        "如果有，用 JSON 数组格式回复：[{\"name\":\"...\", \"description\":\"...\", \"type\":\"...\", \"content\":\"...\"}]"
    )

    summary_messages = [
        {"role": "system", "content": extract_prompt},
    ]

    # 取最近的对话轮次（最后 8 条消息）。
    # 只抽取最近内容，避免每轮都重新总结很久以前的历史。
    recent = messages[-8:] if len(messages) > 8 else messages
    summary_messages.extend(recent)

    try:
        response = call_llm_func(
            messages=summary_messages,
            max_tokens=1000,
        )
        result_text = response.get("content", "").strip()
        if result_text.upper() == "NONE" or not result_text:
            return None

        # 尝试解析 JSON；模型输出不合规时直接忽略，避免写入脏记忆。
        memories = json.loads(result_text)
        for mem in memories:
            write_memory_file(
                name=mem.get("name", "unnamed"),
                content=mem.get("content", ""),
                mem_type=mem.get("type", "reference"),
                description=mem.get("description", ""),
            )

        return f"已提取 {len(memories)} 条新记忆"
    except (json.JSONDecodeError, Exception):
        return None


# ============================================================================
# 整理 — 合并重复记忆
# ============================================================================

def consolidate_memories(call_llm_func) -> str | None:
    """
    当记忆文件数超过阈值时，调用 LLM 做去重合并。

    返回整理结果描述。
    """
    all_memories = _scan_memory_dir()
    if len(all_memories) < CONSOLIDATE_THRESHOLD:
        return None

    # 将现有记忆内容合并。
    # 用分隔线保留每条记忆边界，帮助整理模型识别重复和冲突。
    combined = "\n\n---\n\n".join(
        f"【{m.get('name','unknown')}】({m.get('type','reference')}):\n{m.get('content','')}"
        for m in all_memories
    )

    consolidate_prompt = (
        "以下是多条记忆记录，请整理去重合并，保留唯一和重要的信息。\n"
        "用 JSON 数组格式输出：[{\"name\":\"...\", \"description\":\"...\", \"type\":\"...\", \"content\":\"...\"}]\n\n"
        f"{combined}"
    )

    try:
        response = call_llm_func(
            messages=[{"role": "user", "content": consolidate_prompt}],
            system_prompt="你是一个记忆整理助手。",
            max_tokens=2000,
        )
        result_text = response.get("content", "").strip()

        # 清除旧记忆文件。
        # MEMORY.md 是索引文件，不作为独立记忆删除。
        for m in all_memories:
            filepath = os.path.join(MEMORY_DIR, m.get("file", ""))
            if os.path.exists(filepath) and m.get("file", "") != "MEMORY.md":
                os.remove(filepath)

        # 写入整理后的记忆；write_memory_file 会顺便重建索引和清缓存。
        consolidated = json.loads(result_text)
        for mem in consolidated:
            write_memory_file(
                name=mem.get("name", "unnamed"),
                content=mem.get("content", ""),
                mem_type=mem.get("type", "reference"),
                description=mem.get("description", ""),
            )

        return f"记忆整理完成：{len(all_memories)} → {len(consolidated)} 条"
    except Exception:
        return None
