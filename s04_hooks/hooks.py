"""s04 Hook 系统 — 事件驱动的扩展机制。

设计理念：不向循环中加入逻辑，而是把逻辑"挂在"循环的事件上，
循环体保持简洁，新功能通过注册 hook 来添加。

四个事件（参数约定）：
  UserPromptSubmit(query: str)                       — 用户输入后、LLM 调用前
  PreToolUse(tool_name: str, args: dict)             — 工具执行前（可阻止）
  PostToolUse(tool_name: str, args: dict, output)    — 工具执行后
  Stop(messages: list[dict])                         — 循环退出前（可强制续跑）

返回约定：
  - 返回 None：继续正常流程
  - 返回非 None 字符串：阻止该操作，返回值作为 tool_result
"""

from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}


def register_hook(event: str, callback):
    if event in HOOKS:
        HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None:
            return result
    return None


def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: 当前工作区 {WORKSPACE_DIR}\033[0m")
    return None


def _check_deny_list(command: str) -> str | None:
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}'"
    return None


def _is_destructive_bash(command: str) -> bool:
    destructive_keywords = ["rm ", "> /etc/", "chmod 777", "chown", "passwd"]
    return any(kw in command.lower() for kw in destructive_keywords)


def _is_outside_workspace(path: str) -> bool:
    try:
        return not (Path(WORKSPACE_DIR) / path).resolve().is_relative_to(WORKSPACE_DIR)
    except Exception:
        return True


def permission_hook(tool_name: str, args: dict):
    if tool_name == "bash":
        command = args.get("command", "")
        deny_reason = _check_deny_list(command)
        if deny_reason:
            print(f"\n\033[31m⛔ {deny_reason}\033[0m")
            return f"权限被拒绝: {deny_reason}"
        if _is_destructive_bash(command):
            print(f"\n\033[33m⚠  潜在的破坏性命令\033[0m")
            print(f"   工具: bash({command[:80]})")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝: 用户取消执行"
            print(f"\033[32m  ✓ 用户批准执行\033[0m")

    if tool_name in ("write_file", "edit_file"):
        path = args.get("path", "")
        if _is_outside_workspace(path):
            print(f"\n\033[33m⚠  写入工作区外的文件\033[0m")
            print(f"   工具: {tool_name}({path})")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝: 用户取消操作"
            print(f"\033[32m  ✓ 用户批准执行\033[0m")

    return None


def log_hook(tool_name: str, args: dict):
    first_val = list(args.values())[0] if args else ""
    preview = str(first_val)[:60]
    print(f"\033[90m[HOOK] 工具调用: {tool_name}({preview})\033[0m")
    return None


def large_output_hook(tool_name: str, args: dict, output: str):
    output_len = len(output)
    if output_len > 100000:
        print(f"\033[33m[HOOK] ⚠ {tool_name} 输出过大: {output_len} 字符\033[0m")
    return None


def summary_hook(messages: list[dict]):
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: 本次会话共执行 {tool_count} 次工具调用\033[0m")
    return None


register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)