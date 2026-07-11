"""
============================================================================
  s04_hooks/hooks.py — Hook 系统
============================================================================
  s04 的核心新增模块。Hook 是一种「挂在循环外部的事件驱动扩展机制」。

  设计理念：
    不在于循环中加入逻辑，而在于把逻辑"挂在"循环的事件上。
    这样循环体保持简洁，新功能通过注册 hook 来添加。

  四个事件：
    UserPromptSubmit — 用户输入后、LLM 调用前触发
    PreToolUse       — 工具执行前触发（可用于权限检查、日志）
    PostToolUse      — 工具执行后触发（可用于输出检查、后处理）
    Stop             — 循环即将退出时触发（可用于摘要、统计）

  注册方式：
    hooks.register_hook("PreToolUse", my_permission_check)

  触发方式：
    hooks.trigger_hooks("PreToolUse", tool_name, tool_args)

  返回约定：
    - 返回 None：继续正常流程
    - 返回非 None 的字符串：阻止该操作，返回值作为 tool_result
============================================================================
"""

from config import WORKSPACE_DIR
from permission import check_deny_list, is_destructive_bash, is_outside_workspace


# ============================================================================
# Hook 注册表 — 事件名 → 回调函数列表
# ============================================================================

HOOKS = {
    "UserPromptSubmit": [],   # 用户输入后触发
    "PreToolUse": [],         # 工具执行前触发
    "PostToolUse": [],        # 工具执行后触发
    "Stop": [],               # 循环退出前触发
}


def register_hook(event: str, callback):
    """
    注册一个 hook 回调。

    参数：
      event    — 事件名称（"UserPromptSubmit" / "PreToolUse" / "PostToolUse" / "Stop"）
      callback — 回调函数，接受不同事件的不同参数

    事件参数约定：
      UserPromptSubmit(query: str)           — 用户的输入文本
      PreToolUse(tool_name: str, args: dict) — 工具名 + 参数
      PostToolUse(tool_name: str, args: dict, output: str) — 工具名 + 参数 + 执行输出
      Stop(messages: list[dict])             — 完整的对话历史
    """
    if event in HOOKS:
        HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    """
    触发指定事件的所有已注册 hook。

    返回值：
      None  — 所有 hook 返回 None，继续正常流程
      str   — 某个 hook 返回了非 None 值（阻止操作），返回该值
    """
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None:
            # 非 None 的返回值表示「阻止」：权限拒绝、强制续跑等
            return result
    return None


# ============================================================================
# 内置 Hook 回调函数
# ============================================================================

def context_inject_hook(query: str):
    """
    UserPromptSubmit hook — 用户输入时记录上下文信息。

    每次用户输入时触发，可以在这里注入额外上下文或日志。
    返回 None 表示不阻止用户输入。
    """
    print(f"\033[90m[HOOK] UserPromptSubmit: 当前工作区 {WORKSPACE_DIR}\033[0m")
    return None


def permission_hook(tool_name: str, args: dict):
    """
    PreToolUse hook — 权限检查（将 s03 的权限逻辑迁移到 hook 中）。

    检查流程：
    1. bash 命令：先检查拒绝列表，再检查破坏性关键词
    2. write_file / edit_file：检查是否越界访问工作区外的路径
    3. 命中任何检查 → 请求用户审批 (y/N)
    """
    # ── bash 命令检查 ──
    if tool_name == "bash":
        command = args.get("command", "")
        # Gate 1: 硬拒绝列表
        deny_reason = check_deny_list(command)
        if deny_reason:
            print(f"\n\033[31m⛔ {deny_reason}\033[0m")
            return f"权限被拒绝: {deny_reason}"
        # Gate 2: 破坏性命令 → 用户审批
        if is_destructive_bash(command):
            print(f"\n\033[33m⚠  潜在的破坏性命令\033[0m")
            print(f"   工具: bash({command[:80]})")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝: 用户取消执行"
            print(f"\033[32m  ✓ 用户批准执行\033[0m")

    # ── 文件写入越界检查 ──
    if tool_name in ("write_file", "edit_file"):
        path = args.get("path", "")
        if is_outside_workspace(path):
            print(f"\n\033[33m⚠  写入工作区外的文件\033[0m")
            print(f"   工具: {tool_name}({path})")
            choice = input("   允许执行? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "权限被拒绝: 用户取消操作"
            print(f"\033[32m  ✓ 用户批准执行\033[0m")

    return None


def log_hook(tool_name: str, args: dict):
    """
    PreToolUse hook — 记录每个工具调用。

    用于调试和审计，不阻止任何操作。
    """
    # 取第一个参数值作为预览
    first_val = list(args.values())[0] if args else ""
    preview = str(first_val)[:60]
    print(f"\033[90m[HOOK] 工具调用: {tool_name}({preview})\033[0m")
    return None


def large_output_hook(tool_name: str, args: dict, output: str):
    """
    PostToolUse hook — 检查输出是否过大。

    当工具输出超过 100KB 时发出警告，但不阻止。
    """
    output_len = len(output)
    if output_len > 100000:
        print(f"\033[33m[HOOK] ⚠ {tool_name} 输出过大: {output_len} 字符\033[0m")
    return None


def summary_hook(messages: list[dict]):
    """
    Stop hook — 循环退出前打印统计摘要。

    统计本次会话的工具调用次数。
    """
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: 本次会话共执行 {tool_count} 次工具调用\033[0m")
    return None


# ============================================================================
# 注册内置 Hook
# ============================================================================
# 在模块加载时自动注册以下 hook：
#   1. 用户输入时注入上下文信息
#   2. 工具执行前进行权限检查和日志记录
#   3. 工具执行后检查输出大小
#   4. 循环退出时打印统计信息

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
