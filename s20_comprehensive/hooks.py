"""s06 hooks.py — Hook 系统"""
from tools import WORKSPACE_DIR
from permission import check_deny_list, is_destructive_bash, is_outside_workspace

# 事件名到回调列表的映射。
# main.py 在用户提交、工具执行前后、最终停止前触发对应事件。
HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event, callback):
    """注册 hook；未知事件会被忽略，避免拼错事件名导致运行时报错。"""
    if event in HOOKS: HOOKS[event].append(callback)

def trigger_hooks(event, *args):
    """按注册顺序执行 hook；回调返回非 None 时短路，把结果交回调用方处理。"""
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        # PreToolUse 返回字符串通常代表拦截原因；Stop 返回字符串可用于强制继续对话。
        if result is not None: return result
    return None

def context_inject_hook(query: str):
    """用户输入提交时触发；当前只打印工作区，用作可观察性示例。"""
    print(f"\033[90m[HOOK] {WORKSPACE_DIR}\033[0m"); return None

def permission_hook(tool_name: str, args: dict):
    """工具执行前的权限检查：危险命令直接阻止，破坏性操作要求人工确认。"""
    if tool_name == "bash":
        deny_reason = check_deny_list(args.get("command", ""))
        if deny_reason: print(f"\n\033[31m⛔ {deny_reason}\033[0m"); return f"权限被拒绝: {deny_reason}"
        if is_destructive_bash(args.get("command", "")):
            # rm/chmod/chown 等命令可能造成不可恢复影响，所以走人工确认。
            print(f"\n\033[33m⚠  破坏性命令\033[0m")
            if input("   允许? [y/N] ").strip().lower() not in ("y","yes"): return "权限被拒绝"
            print(f"\033[32m  ✓\033[0m")
    if tool_name in ("write_file","edit_file") and is_outside_workspace(args.get("path","")):
        # 写入工作区外风险更高，默认也需要人工确认。
        print(f"\n\033[33m⚠  写入工作区外\033[0m")
        if input("   允许? [y/N] ").strip().lower() not in ("y","yes"): return "权限被拒绝"
        print(f"\033[32m  ✓\033[0m")
    return None

def log_hook(tool_name: str, args: dict):
    """工具执行前的日志 hook 示例；first_val 预留给后续调试输出。"""
    first_val = str(list(args.values())[0])[:60] if args else ""; return None

def large_output_hook(tool_name, args, output):
    """工具执行后检查输出体积；真正截断仍由 tools.py 负责。"""
    if len(output) > 100000: print(f"\033[33m[HOOK] ⚠ {tool_name} 输出: {len(output)} 字符\033[0m")
    return None

def summary_hook(messages):
    """本轮 Agent 停止前输出工具调用次数，帮助观察模型是否过度调用工具。"""
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: {tool_count} 次工具调用\033[0m"); return None

# 默认 hook 链：上下文可见性、权限检查、轻量日志、大输出提醒、停止前摘要。
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
