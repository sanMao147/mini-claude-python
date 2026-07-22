"""s10 持久化记忆系统 — 存储/加载/写入/整理四子系统"""

import os, json, yaml, re
from pathlib import Path

from config import MEMORY_DIR

os.makedirs(MEMORY_DIR, exist_ok=True)

MEMORY_INDEX_FILE = os.path.join(MEMORY_DIR, "MEMORY.md")
_memories_cache: list[dict] = []
CONSOLIDATE_THRESHOLD = 10


def write_memory_file(name: str, content: str, mem_type: str = "reference", description: str = "") -> str:
    safe_name = re.sub(r'[^\w\-]', '_', name.lower())
    filename = f"{safe_name}.md"
    filepath = os.path.join(MEMORY_DIR, filename)

    yaml_header = yaml.dump({
        "name": name,
        "description": description,
        "type": mem_type,
    }, allow_unicode=True, default_flow_style=False).strip()

    file_content = f"---\n{yaml_header}\n---\n\n{content}"
    Path(filepath).write_text(file_content, encoding="utf-8")

    _update_memory_index(name, description, mem_type, filename)

    global _memories_cache
    _memories_cache = []

    return f"记忆已保存至 {filename}"


def _update_memory_index(name: str, description: str, mem_type: str, filename: str):
    entry = f"- **{name}** ({mem_type}): {description} → `{filename}`"

    if os.path.exists(MEMORY_INDEX_FILE):
        existing = Path(MEMORY_INDEX_FILE).read_text(encoding="utf-8")
        lines = existing.strip().splitlines()
    else:
        lines = ["# Memory Index\n"]

    for i, line in enumerate(lines):
        if f"**{name}**" in line:
            lines[i] = entry
            break
    else:
        lines.append(entry)

    Path(MEMORY_INDEX_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scan_memory_dir() -> list[dict]:
    global _memories_cache
    if _memories_cache:
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
            meta["file"] = entry
            meta["content"] = text
            memories.append(meta)
        except Exception:
            continue

    _memories_cache = memories
    return memories


def _parse_memory_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {"name": "unknown", "description": "", "type": "reference"}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"name": "unknown", "description": "", "type": "reference"}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {"name": "unknown", "description": "", "type": "reference"}


def select_relevant_memories(query: str, call_llm_func) -> list[dict]:
    all_memories = _scan_memory_dir()
    if not all_memories:
        return []

    if len(all_memories) <= 5:
        return all_memories

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
        keywords = query.lower().split()
        scored = []
        for m in all_memories:
            score = sum(1 for kw in keywords if kw in str(m).lower())
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        selected_names = [m["name"] for _, m in scored[:5]]

    result = []
    for name in selected_names:
        for m in all_memories:
            if m.get("name", "").strip() == name:
                result.append(m)
                break

    return result[:5]


def extract_memories(messages: list[dict], call_llm_func) -> str | None:
    if len(messages) < 3:
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

    summary_messages = [{"role": "system", "content": extract_prompt}]
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


def consolidate_memories(call_llm_func) -> str | None:
    all_memories = _scan_memory_dir()
    if len(all_memories) < CONSOLIDATE_THRESHOLD:
        return None

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

        for m in all_memories:
            filepath = os.path.join(MEMORY_DIR, m.get("file", ""))
            if os.path.exists(filepath) and m.get("file", "") != "MEMORY.md":
                os.remove(filepath)

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