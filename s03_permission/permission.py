"""
============================================================================
  s03_permission/permission.py — 权限三道闸门管线
============================================================================
  s03 的核心新增模块。在工具执行前插入三道安全闸门：

    Gate 1: 硬拒绝列表 (DENY_LIST)
        → 永远禁止的命令（如 rm -rf /），直接拒绝，不给任何机会

    Gate 2: 规则匹配 (PERMISSION_RULES)
        → 根据上下文判断是否需要审批（如写工作区外的文件、危险命令）

    Gate 3: 用户审批 (ask_user)
        → 当 Gate 2 命中时，暂停并等待用户确认 (y/N)

  核心函数：check_permission(tool_name, tool_args) -> bool
    返回 True 表示允许执行，False 表示拒绝执行。
============================================================================
"""

import json
from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS


# ============================================================================
# Gate 1: 硬拒绝列表 — 永远禁止的命令
# ============================================================================
# 这些命令无论什么情况都不会执行。
# DANGEROUS_COMMANDS 从 config.py 导入，包含：
#   rm -rf /, sudo, shutdown, reboot, mkfs, dd if=, fork bomb 等

def check_deny_list(command: str) -> str | None:
    """
    检查命令是否命中硬拒绝列表。
    返回 None 表示安全，返回字符串表示被拒绝的原因。
    """
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMANDS:
        if pattern.lower() in cmd_lower:
            return f"危险命令被阻止: '{pattern}' 在黑名单中"
    return None


# ============================================================================
# Gate 2: 规则匹配 — 上下文敏感的风险检测
# ============================================================================
# 每条规则包含：
#   - tools: 适用的工具列表
#   - check: 判断函数，接收工具参数 dict，返回 True 表示需要审批
#   - message: 命中时显示的提示消息

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
    """
    遍历所有权限规则，检查当前工具调用是否命中。
    返回第一条命中的规则消息，或 None 表示安全。
    """
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


# ============================================================================
# Gate 3: 用户审批 — 暂停等待用户确认
# ============================================================================

def ask_user(tool_name: str, args: dict, reason: str) -> str:
    """
    向用户展示即将执行的操作，请求批准。

    返回:
      "allow" — 用户同意执行
      "deny"  — 用户拒绝执行
    """
    print(f"\n\033[33m⚠  需要审批: {reason}\033[0m")
    print(f"   工具: {tool_name}")

    # 格式化显示参数（JSON 序列化不可序列化的值）
    try:
        args_str = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(args)
    if len(args_str) > 200:
        args_str = args_str[:200] + "..."
    print(f"   参数: {args_str}")

    choice = input("   允许执行? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# ============================================================================
# 权限检查管线 — 串联三道闸门
# ============================================================================

def check_permission(tool_name: str, tool_args: dict) -> bool:
    """
    完整的权限检查管线，串联三道闸门。

    参数：
      tool_name: 工具名称（如 "bash", "write_file" 等）
      tool_args: 工具参数字典

    返回：
      True  — 允许执行
      False — 拒绝执行（已打印拒绝原因）
    """
    # ── Gate 1: 硬拒绝列表 ──
    # 仅对 bash 命令检查（其他工具在 tools.py 的 safe_path() 中已有保护）
    if tool_name == "bash":
        reason = check_deny_list(tool_args.get("command", ""))
        if reason:
            print(f"\n\033[31m⛔ {reason}\033[0m")
            return False

    # ── Gate 2 + Gate 3: 规则匹配 → 用户审批 ──
    reason = check_rules(tool_name, tool_args)
    if reason:
        decision = ask_user(tool_name, tool_args, reason)
        if decision == "deny":
            print(f"\033[31m  ✗ 用户拒绝执行\033[0m")
            return False
        print(f"\033[32m  ✓ 用户批准执行\033[0m")

    # ── 通过所有检查 ──
    return True
