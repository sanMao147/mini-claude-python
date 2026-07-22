"""权限检查辅助函数（供 hooks.py 中的 permission_hook 调用）"""

from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


def check_deny_list(command: str) -> str | None:
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}'"
    return None


def is_destructive_bash(command: str) -> bool:
    destructive_keywords = ["rm ", "> /etc/", "chmod 777", "chown", "passwd"]
    return any(kw in command.lower() for kw in destructive_keywords)


def is_outside_workspace(path: str) -> bool:
    try:
        return not (Path(WORKSPACE_DIR) / path).resolve().is_relative_to(WORKSPACE_DIR)
    except Exception:
        return True