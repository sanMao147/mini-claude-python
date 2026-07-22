"""
============================================================================
  s10_system_prompt/prompt.py — 运行时 System Prompt 组装
============================================================================
"""

import json, os

from config import WORKSPACE_DIR, MEMORY_DIR

from skills import build_skills_catalog
from memory import _scan_memory_dir

_cached_prompt = None
_cached_context_key = None


PROMPT_SECTIONS = {
    "identity": (
        "你是一个编程助手 Agent。\n"
        "你可以使用提供的工具来自主完成任务。"
    ),
    "workspace": "",
    "tools": "",
    "skills": "",
    "memory": "",
    "rules": (
        "规则：\n"
        "  1. 在开始多步骤任务前，使用 todo_write 制定计划\n"
        "  2. 对独立子任务使用 task 工具委托给子 Agent\n"
        "  3. 需要特定领域知识时使用 load_skill\n"
        "  4. 上下文过长时使用 compact 工具压缩\n"
        "  5. 完成后简要汇报，不要过度解释\n"
    ),
}


def assemble_system_prompt(context: dict) -> str:
    sections = []
    sections.append(PROMPT_SECTIONS["identity"])
    ws = context.get("workspace", WORKSPACE_DIR)
    sections.append(f"当前工作目录: {ws}")
    tools = context.get("tool_names", [])
    if tools:
        sections.append(f"可用工具: {', '.join(tools)}")
    skills = context.get("skills_catalog", "")
    if skills:
        sections.append(skills)
    if context.get("has_memories"):
        sections.append("以下是与当前任务相关的记忆（请参考但不要盲目遵循）：")
        for mem_summary in context.get("memory_summaries", [])[:5]:
            sections.append(f"  - {mem_summary}")
    sections.append(PROMPT_SECTIONS["rules"])
    return "\n\n".join(sections)


def get_system_prompt(context: dict) -> str:
    global _cached_prompt, _cached_context_key
    context_key = json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)
    if _cached_prompt is not None and context_key == _cached_context_key:
        return _cached_prompt
    _cached_prompt = assemble_system_prompt(context)
    _cached_context_key = context_key
    return _cached_prompt


def update_context(tool_names: list[str], user_query: str = "") -> dict:
    context = {
        "workspace": WORKSPACE_DIR,
        "tool_names": tool_names,
        "has_skills": False,
        "skills_catalog": "",
        "has_memories": False,
        "memory_summaries": [],
    }
    catalog = build_skills_catalog()
    if catalog:
        context["has_skills"] = True
        context["skills_catalog"] = catalog
    if os.path.isdir(MEMORY_DIR):
        mem_files = [f for f in os.listdir(MEMORY_DIR) if f.endswith('.md') and f != "MEMORY.md"]
        if mem_files:
            context["has_memories"] = True
            memories = _scan_memory_dir()
            context["memory_summaries"] = [
                f"{m.get('name', '').strip()}: {m.get('description', '').strip()}"
                for m in memories[:5]
                if m.get('name', '').strip()
            ]
    return context