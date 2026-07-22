"""s05 TodoWrite 计划追踪。

设计思路：
  - Agent 在开始复杂任务前调用 todo_write 制定计划
  - 执行过程中更新状态（pending → in_progress → completed）
  - 如果 Agent 忘记更新，系统会主动提醒（nag，连续 3 轮）
"""

import json
import ast

# 当前会话的任务列表，每个任务为 {"content": str, "status": str}
CURRENT_TODOS: list[dict] = []

# 从上一次 todo_write 调用后经过的轮数；连续 3 轮不更新就触发 nag
rounds_since_todo = 0


def _normalize_todos(todos) -> tuple[list | None, str | None]:
    """规范化输入的 todos 数据。
    支持列表或 JSON 字符串两种格式。返回 (todos_list, error_message)。"""
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "错误: todos 必须是列表或 JSON 数组字符串"

    if not isinstance(todos, list):
        return None, "错误: todos 必须是列表"

    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"错误: todos[{i}] 必须是对象"
        if "content" not in t or "status" not in t:
            return None, f"错误: todos[{i}] 缺少 'content' 或 'status' 字段"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"错误: todos[{i}] 的 status 无效: '{t['status']}'"

    return todos, None


def run_todo_write(todos: list) -> str:
    """处理 todo_write 工具调用：更新 CURRENT_TODOS 并打印格式化列表。"""
    global CURRENT_TODOS, rounds_since_todo

    todos_data, error = _normalize_todos(todos)
    if error:
        return error

    CURRENT_TODOS = todos_data
    rounds_since_todo = 0

    lines = ["\n\033[33m## 当前任务\033[0m"]
    for t in CURRENT_TODOS:
        status = t["status"]
        icon = {
            "pending": "  ",
            "in_progress": "\033[36m▸\033[0m",   # 青色箭头
            "completed": "\033[32m✓\033[0m",     # 绿色对勾
        }[status]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))

    return f"已更新 {len(CURRENT_TODOS)} 个任务"


def check_nag_reminder() -> str | None:
    """连续 3 轮没有调用 todo_write 时返回提醒消息，否则返回 None。"""
    global rounds_since_todo
    if rounds_since_todo >= 3:
        rounds_since_todo = 0
        return (
            "<reminder>你已经连续 3 轮没有更新任务列表了。"
            "请调用 todo_write 工具更新你的任务进度。"
            "确保每个任务的 status 反映当前状态。"
            "</reminder>"
        )
    return None


def increment_todo_counter():
    global rounds_since_todo
    rounds_since_todo += 1


def reset_todo_counter():
    global rounds_since_todo
    rounds_since_todo = 0
