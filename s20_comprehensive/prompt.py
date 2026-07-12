"""
============================================================================
  s10_system_prompt/prompt.py — 运行时 System Prompt 组装
============================================================================
  s10 的核心新增模块。将硬编码的 SYSTEM 字符串拆分为可组装的多段（section）。

  设计理念：
    - 不再使用单一硬编码的 SYSTEM 变量
    - 根据当前运行时状态（工具可用性、记忆文件存在、技能目录）按需拼接
    - 使用 json.dumps 做确定性缓存 key，避免重复拼接

  核心函数：
    assemble_system_prompt(context) — 根据上下文组装完整 prompt
    get_system_prompt(context)     — 带缓存的获取 prompt
    update_context()               — 检查文件系统，更新运行时上下文
============================================================================
"""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WORKSPACE_DIR, MEMORY_DIR
from skills import build_skills_catalog
from memory import _scan_memory_dir

# Prompt 段缓存。
# System Prompt 每轮都可能被请求，缓存可以避免同一上下文下重复拼接字符串。
_cached_prompt = None
_cached_context_key = None


# ============================================================================
# Prompt 段定义 — 按功能拆分，按需组装
# ============================================================================

PROMPT_SECTIONS = {
    # 静态段放在这里，动态段在 assemble_system_prompt() 根据 context 生成。
    "identity": (
        "你是一个编程助手 Agent。\n"
        "你可以使用提供的工具来自主完成任务。"
    ),
    "workspace": "",     # 动态生成
    "tools": "",         # 动态生成
    "skills": "",        # 动态生成
    "memory": "",        # 动态生成
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
    """
    根据运行时上下文动态组装 System Prompt。

    context 应该包含：
      - workspace: 工作目录路径
      - tool_names: 可用工具名列表
      - has_skills: 是否有技能目录
      - skills_catalog: 技能目录文本
      - has_memories: 是否有记忆文件
      - memory_summaries: 相关记忆摘要列表
    """
    # sections 按顺序拼接；越基础的身份/工作区信息越靠前，规则放在最后强化执行约束。
    sections = []

    # 身份
    sections.append(PROMPT_SECTIONS["identity"])

    # 工作目录
    ws = context.get("workspace", WORKSPACE_DIR)
    sections.append(f"当前工作目录: {ws}")

    # 工具列表
    tools = context.get("tool_names", [])
    if tools:
        sections.append(f"可用工具: {', '.join(tools)}")

    # 技能：只注入技能目录，不注入完整 SKILL.md，完整内容由 load_skill 按需加载。
    skills = context.get("skills_catalog", "")
    if skills:
        sections.append(skills)

    # 记忆：这里只放摘要，避免长期记忆把系统提示词撑得过大。
    if context.get("has_memories"):
        sections.append("以下是与当前任务相关的记忆（请参考但不要盲目遵循）：")
        for mem_summary in context.get("memory_summaries", [])[:5]:
            sections.append(f"  - {mem_summary}")

    # 规则
    sections.append(PROMPT_SECTIONS["rules"])

    return "\n\n".join(sections)


def get_system_prompt(context: dict) -> str:
    """
    带缓存的 System Prompt 获取。

    用 context 的确定性序列化（json.dumps, sort_keys=True）做缓存 key，
    相同上下文跳过重复组装。
    """
    global _cached_prompt, _cached_context_key

    # 确定性序列化做缓存 key。
    # sort_keys=True 确保同一内容的 dict 不会因为键顺序不同导致缓存失效。
    context_key = json.dumps(context, sort_keys=True, ensure_ascii=False, default=str)

    if _cached_prompt is not None and context_key == _cached_context_key:
        return _cached_prompt

    _cached_prompt = assemble_system_prompt(context)
    _cached_context_key = context_key
    return _cached_prompt


def update_context(tool_names: list[str], user_query: str = "") -> dict:
    """
    检查文件系统真实状态，构建运行时上下文。

    返回 context dict，供 assemble_system_prompt 使用。
    """
    # context 是 prompt 的唯一输入，后续想增加动态信息时优先扩展这个结构。
    context = {
        "workspace": WORKSPACE_DIR,
        "tool_names": tool_names,
        "has_skills": False,
        "skills_catalog": "",
        "has_memories": False,
        "memory_summaries": [],
    }

    # 检查技能目录。
    # build_skills_catalog() 内部会扫描 skills/，并顺便刷新技能注册表。
    catalog = build_skills_catalog()
    if catalog:
        context["has_skills"] = True
        context["skills_catalog"] = catalog

    # 检查记忆文件。
    # 这里只做轻量扫描；更精确的相关性选择由 main.py 调 select_relevant_memories() 完成。
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
