"""s10 两级知识加载 — 目录常驻，详情按需"""

import yaml
from pathlib import Path

from config import WORKSPACE_DIR

SKILLS_DIR = Path(WORKSPACE_DIR) / "skills"

SKILL_REGISTRY: dict[str, dict] = {}


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")

    return meta, parts[2].strip()


def _scan_skills() -> list[dict]:
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
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        available = ", ".join(SKILL_REGISTRY.keys())
        return f"错误: 未找到技能 '{name}'。可用技能: {available}"
    return skill["content"]


def build_skills_catalog() -> str:
    catalog = _scan_skills()
    if not catalog:
        return ""

    lines = ["\n可用技能（使用 load_skill 工具加载详情）:"]
    for item in catalog:
        lines.append(f"  - {item['name']}: {item['description']}")

    return "\n".join(lines)