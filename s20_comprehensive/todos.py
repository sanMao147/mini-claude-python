"""s06 todos.py — TodoWrite 计划追踪"""
import json, ast

# CURRENT_TODOS 是轻量的内存态任务列表，只在当前进程内有效。
# 更持久的任务管理在 tasks.py；这里主要服务 TodoWrite 的“当前步骤展示”。
CURRENT_TODOS: list[dict] = []
# 统计距离上次 TodoWrite 更新过去了多少轮工具调用，用于触发温和提醒。
rounds_since_todo = 0

def _normalize_todos(todos):
    """兼容 JSON 字符串、Python 字面量字符串和 list，并校验 TodoWrite 必要字段。"""
    if isinstance(todos, str):
        try: todos = json.loads(todos)
        except json.JSONDecodeError:
            try: todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError): return None, "错误: todos 必须是列表"
    if not isinstance(todos, list): return None, "错误: todos 必须是列表"
    for i, t in enumerate(todos):
        if not isinstance(t, dict): return None, f"错误: todos[{i}] 必须是对象"
        if "content" not in t or "status" not in t: return None, f"todos[{i}] 缺少字段"
        if t["status"] not in ("pending","in_progress","completed"): return None, f"todos[{i}] status 无效"
    return todos, None

def run_todo_write(todos: list) -> str:
    """更新当前任务列表，并在终端用颜色展示 pending / in_progress / completed。"""
    global CURRENT_TODOS, rounds_since_todo
    todos_data, error = _normalize_todos(todos)
    if error: return error
    CURRENT_TODOS = todos_data; rounds_since_todo = 0
    lines = ["\n\033[33m## 当前任务\033[0m"]
    for t in CURRENT_TODOS:
        icon = {"pending":"  ","in_progress":"\033[36m▸\033[0m","completed":"\033[32m✓\033[0m"}[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))
    return f"已更新 {len(CURRENT_TODOS)} 个任务"

def check_nag_reminder() -> str | None:
    """连续多轮没有更新 TodoWrite 时返回提醒文本；调用方会把它注入对话。"""
    global rounds_since_todo
    if rounds_since_todo >= 3: rounds_since_todo = 0; return "<reminder>请更新你的任务进度。</reminder>"
    return None

def increment_todo_counter():
    """工具调用后递增计数，表示 Agent 又推进了一步但还没同步 TodoWrite。"""
    global rounds_since_todo; rounds_since_todo += 1

def reset_todo_counter():
    """TodoWrite 成功执行后清零计数，避免刚更新完就继续提醒。"""
    global rounds_since_todo; rounds_since_todo = 0
