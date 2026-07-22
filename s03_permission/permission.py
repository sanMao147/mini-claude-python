"""s03 权限三道闸门管线：拒绝列表 → 规则匹配 → 用户审批。"""

import json
from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


def check_deny_list(command: str) -> str | None:
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}' 在黑名单中"
    return None


PERMISSION_RULES = [
    {
        "tools": ["write_file", "edit_file"],
        "check": lambda args: not (Path(WORKSPACE_DIR) / args.get("path", "")).resolve().is_relative_to(WORKSPACE_DIR),
        "message": "写入工作区外的文件",
    },
    {
        "tools": ["bash"],
        "check": lambda args: any(
            kw in args.get("command", "").lower()
            for kw in ["rm ", "> /etc/", "chmod 777", "chown", "passwd"]
        ),
        "message": "潜在的破坏性命令",
    },
    {
        "tools": ["write_file", "edit_file"],
        "check": lambda args: args.get("path", "").startswith("..") or "/.." in args.get("path", ""),
        "message": "路径包含 .. 可能存在越界风险",
    },
]


def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m⚠  需要审批: {reason}\033[0m")
    print(f"   工具: {tool_name}")

    try:
        args_str = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(args)
    if len(args_str) > 200:
        args_str = args_str[:200] + "..."
    print(f"   参数: {args_str}")

    choice = input("   允许执行? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


def check_permission(tool_name: str, tool_args: dict) -> bool:
    if tool_name == "bash":
        reason = check_deny_list(tool_args.get("command", ""))
        if reason:
            print(f"\n\033[31m⛔ {reason}\033[0m")
            return False

    reason = check_rules(tool_name, tool_args)
    if reason:
        decision = ask_user(tool_name, tool_args, reason)
        if decision == "deny":
            print(f"\033[31m  ✗ 用户拒绝执行\033[0m")
            return False
        print(f"\033[32m  ✓ 用户批准执行\033[0m")

    return True