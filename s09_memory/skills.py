"""
============================================================================
  s07_skill_loading/skills.py — 两级知识加载系统
============================================================================
  s07 的核心新增模块。

  设计理念：知识"用到时才加载"，分两级控制成本。

  Layer 1（便宜，始终注入 System Prompt）：
    - 启动时扫描 skills/ 目录
    - 解析每个 SKILL.md 的 YAML frontmatter（name, description）
    - 将技能目录（约 100 tokens/技能）注入 System Prompt
    - 让模型知道有哪些能力可用

  Layer 2（按需，Agent 主动调用）：
    - Agent 调用 load_skill("技能名") 工具
    - 通过 SKILL_REGISTRY 安全查找（防路径遍历）
    - 完整 SKILL.md 内容通过 tool_result 注入对话
    - 约 2000+ tokens/技能

  skills/ 目录结构示例：
    skills/
      agent-builder/SKILL.md
      code-review/SKILL.md
============================================================================
"""

import os, yaml
from pathlib import Path

from config import WORKSPACE_DIR

# 技能文件目录
SKILLS_DIR = Path(WORKSPACE_DIR) / "skills"

# 技能注册表：{name: {name, description, path, content}}
# 启动时由 _scan_skills() 填充
SKILL_REGISTRY: dict[str, dict] = {}


# ============================================================================
# YAML Frontmatter 解析
# ============================================================================

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    解析 SKILL.md 的 YAML frontmatter。

    SKILL.md 格式示例：
      ---
      name: code-review
      description: Review code for bugs and improvements
      ---
      # Code Review Skill
      详细的使用说明...

    返回 (metadata, body)：
      metadata = {"name": "code-review", "description": "Review code..."}
      body     = "# Code Review Skill\n详细的使用说明..."
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        # YAML 解析失败，回退到简单 key:value 解析
        meta = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")

    return meta, parts[2].strip()


# ============================================================================
# 技能扫描 — Layer 1（启动时执行）
# ============================================================================

def _scan_skills() -> list[dict]:
    """
    扫描 skills/ 目录，将技能信息注入 SKILL_REGISTRY。

    返回技能概要列表，用于构建 System Prompt 中的技能目录。
    """
    if not SKILLS_DIR.exists():
        return []

    catalog = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue

        manifest = d / "SKILL.md"
        if not manifest.exists():
            continue

        raw = manifest.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(raw)

        name = meta.get("name", d.name)
        description = meta.get("description", "(无描述)")

        # 注册到技能表（用于安全查找）
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "path": str(manifest),
            "content": body,
        }

        catalog.append({"name": name, "description": description})

    return catalog


# ============================================================================
# 技能加载 — Layer 2（Agent 按需调用）
# ============================================================================

def load_skill(name: str) -> str:
    """
    加载指定技能的完整内容。

    通过 SKILL_REGISTRY 安全查找，防止路径遍历攻击。
    不会直接读取用户传入的路径。

    参数：
      name: 技能名称（如 "code-review"）

    返回：
      技能的完整 SKILL.md 内容，或错误消息
    """
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        # 尝试模糊匹配
        available = ", ".join(SKILL_REGISTRY.keys())
        return f"错误: 未找到技能 '{name}'。可用技能: {available}"

    return skill["content"]


# ============================================================================
# 构建 System Prompt 中的技能目录
# ============================================================================

def build_skills_catalog() -> str:
    """
    构建技能目录字符串，注入到 System Prompt 中。

    返回格式示例：
      可用技能:
        - agent-builder: Build custom agents
        - code-review: Review code for bugs
        - pdf: Create and edit PDFs
    """
    catalog = _scan_skills()
    if not catalog:
        return ""

    lines = ["\n可用技能（使用 load_skill 工具加载详情）:"]
    for item in catalog:
        lines.append(f"  - {item['name']}: {item['description']}")

    return "\n".join(lines)
