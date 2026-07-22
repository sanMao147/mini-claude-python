"""Hook 系统（与 s04 相同）"""

from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}


def register_hook(event: str, callback):
    if event in HOOKS:
        HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None:
            return result
    return None


def _check_deny_list(command: str) -> str | None:
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}'"
    return None


def _is_destructive_bash(command: str) -> bool:
    return any(kw in command.lower() for kw in ["rm ", "> /etc/", "chmod 777", "chown", "passwd"])


def _is_outside_workspace(path: str) -> bool:
    try:
        return not (Path(WORKSPACE_DIR) / path).resolve().is_relative_to(WORKSPACE_DIR)
    except Exception:
        return True


def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: {WORKSPACE_DIR}\033[0m")
    return None


def permission_hook(tool_name: str, args: dict):
    if tool_name == "bash":
        deny_reason = _check_deny_list(args.get("command", ""))
        if deny_reason:
            print(f"\n\033[31m⛔ {deny_reason}\033[0m")
            return f"权限被拒绝: {deny_reason}"
        if _is_destructive_bash(args.get("command", "")):
            print(f"\n\033[33m⚠  潜在的破坏性命令\033[0m")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝"
            print(f"\033[32m  ✓ 批准\033[0m")
    if tool_name in ("write_file", "edit_file"):
        if _is_outside_workspace(args.get("path", "")):
            print(f"\n\033[33m⚠  写入工作区外\033[0m")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝"
            print(f"\033[32m  ✓ 批准\033[0m")
    return None


def log_hook(tool_name: str, args: dict):
    first_val = str(list(args.values())[0])[:60] if args else ""
    print(f"\033[90m[HOOK] {tool_name}({first_val})\033[0m")
    return None


def large_output_hook(tool_name: str, args: dict, output: str):
    if len(output) > 100000:
        print(f"\033[33m[HOOK] ⚠ {tool_name} 输出过大: {len(output)} 字符\033[0m")
    return None


def summary_hook(messages: list[dict]):
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: {tool_count} 次工具调用\033[0m")
    return None


register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)