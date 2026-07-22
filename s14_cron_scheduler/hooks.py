"""s06 hooks.py — Hook 系统"""
from config import WORKSPACE_DIR

from permission import check_deny_list, is_destructive_bash, is_outside_workspace
HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}
def register_hook(event, callback):
    if event in HOOKS: HOOKS[event].append(callback)
def trigger_hooks(event, *args):
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None: return result
    return None
def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] {WORKSPACE_DIR}\033[0m"); return None
def permission_hook(tool_name: str, args: dict):
    if tool_name == "bash":
        deny_reason = check_deny_list(args.get("command", ""))
        if deny_reason: print(f"\n\033[31m⛔ {deny_reason}\033[0m"); return f"权限被拒绝: {deny_reason}"
        if is_destructive_bash(args.get("command", "")):
            print(f"\n\033[33m⚠  破坏性命令\033[0m")
            if input("   允许? [y/N] ").strip().lower() not in ("y","yes"): return "权限被拒绝"
            print(f"\033[32m  ✓\033[0m")
    if tool_name in ("write_file","edit_file") and is_outside_workspace(args.get("path","")):
        print(f"\n\033[33m⚠  写入工作区外\033[0m")
        if input("   允许? [y/N] ").strip().lower() not in ("y","yes"): return "权限被拒绝"
        print(f"\033[32m  ✓\033[0m")
    return None
def log_hook(tool_name: str, args: dict):
    first_val = str(list(args.values())[0])[:60] if args else ""; return None
def large_output_hook(tool_name, args, output):
    if len(output) > 100000: print(f"\033[33m[HOOK] ⚠ {tool_name} 输出: {len(output)} 字符\033[0m")
    return None
def summary_hook(messages):
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: {tool_count} 次工具调用\033[0m"); return None
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
