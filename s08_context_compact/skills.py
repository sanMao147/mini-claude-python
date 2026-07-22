"""s08 两级知识加载 — 目录常驻，详情按需"""

import os, yaml
from pathlib import Path

from config import WORKSPACE_DIR

SKILLS_DIR = Path(WORKSPACE_DIR) / "skills"

# 技能注册表：{name: {name, description, path, content}}，启动时由 _scan_skills() 填充
SKILL_REGISTRY: dict[str, dict] = {}


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML frontmatter，返回 (metadata, body)。

    失败时回退到简单 key:value 解析，保证健壮性。
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


def _scan_skills() -> list[dict]:
    """扫描 skills/ 目录，将技能信息注册到 SKILL_REGISTRY 并返回概要列表。"""
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

        SKILL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "path": str(manifest),
            "content": body,
        }

        catalog.append({"name": name, "description": description})

    return catalog


def load_skill(name: str) -> str:
    """通过 SKILL_REGISTRY 安全查找技能，防止路径遍历攻击（不直接读取用户路径）。"""
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        available = ", ".join(SKILL_REGISTRY.keys())
        return f"错误: 未找到技能 '{name}'。可用技能: {available}"

    return skill["content"]


def build_skills_catalog() -> str:
    """构建技能目录字符串，注入 System Prompt（Layer 1，约 100 tokens/技能）。"""
    catalog = _scan_skills()
    if not catalog:
        return ""

    lines = ["\n可用技能（使用 load_skill 工具加载详情）:"]
    for item in catalog:
        lines.append(f"  - {item['name']}: {item['description']}")

    return "\n".join(lines)
