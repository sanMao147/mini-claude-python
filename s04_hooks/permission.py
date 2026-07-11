"""
============================================================================
  s04_hooks/permission.py — 权限检查逻辑（与 s03 类似，但通过 hooks 触发）
============================================================================
  s04 中，权限检查不再在循环体中硬编码调用，而是注册为 PreToolUse hook。
  本文件保留权限判断的核心逻辑，供 hooks.py 中的 permission_hook 调用。
============================================================================
"""

from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


def check_deny_list(command: str) -> str | None:
    """检查命令是否在硬拒绝列表中。"""
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}'"
    return None


def is_destructive_bash(command: str) -> bool:
    """判断 bash 命令是否具有破坏性。"""
    destructive_keywords = ["rm ", "> /etc/", "chmod 777", "chown", "passwd"]
    return any(kw in command.lower() for kw in destructive_keywords)


def is_outside_workspace(path: str) -> bool:
    """判断路径是否在工作区之外。"""
    try:
        return not (Path(WORKSPACE_DIR) / path).resolve().is_relative_to(WORKSPACE_DIR)
    except Exception:
        return True
