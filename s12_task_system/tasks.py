"""
============================================================================
  s12_task_system/tasks.py — 持久化任务系统 + DAG 依赖图
============================================================================
  s12 的核心新增模块。

  Task dataclass + .tasks/{id}.json 持久化 + DAG 依赖图（blockedBy）

  5 个任务管理工具：
    create_task   — 创建任务（支持 blockedBy 声明依赖）
    list_tasks    — 列出所有任务（支持状态过滤）
    get_task      — 获取单个任务详情
    claim_task    — 认领任务（pending→in_progress，检查依赖）
    complete_task — 完成任务（in_progress→completed，报告解锁的下游任务）

  can_start() 检查所有 blockedBy 是否 completed
============================================================================
"""

import os, json, uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict

from config import TASKS_DIR
os.makedirs(TASKS_DIR, exist_ok=True)


@dataclass
class Task:
    id: str
    subject: str
    description: str = ""
    status: str = "pending"       # pending | in_progress | completed
    owner: str | None = None
    blocked_by: list[str] = field(default_factory=list)  # 依赖的任务 ID 列表

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


def _task_path(task_id: str) -> str:
    return os.path.join(TASKS_DIR, f"{task_id}.json")


def save_task(task: Task):
    Path(_task_path(task.id)).write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_task(task_id: str) -> Task | None:
    path = _task_path(task_id)
    if not os.path.exists(path): return None
    return Task.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_all_tasks() -> list[Task]:
    tasks = []
    if not os.path.isdir(TASKS_DIR): return tasks
    for f in sorted(os.listdir(TASKS_DIR)):
        if f.endswith(".json"):
            tid = f.replace(".json", "")
            t = load_task(tid)
            if t: tasks.append(t)
    return tasks


def can_start(task: Task) -> bool:
    """检查任务的所有依赖是否已完成。"""
    if not task.blocked_by:
        return True
    for dep_id in task.blocked_by:
        dep = load_task(dep_id)
        if not dep or dep.status != "completed":
            return False
    return True


# ── 5 个工具执行函数 ──

def create_task(subject: str, description: str = "", blocked_by: list[str] | None = None) -> str:
    task_id = str(uuid.uuid4())[:8]
    task = Task(id=task_id, subject=subject, description=description, blocked_by=blocked_by or [])
    save_task(task)
    return f"任务已创建: [{task_id}] {subject}"

def list_tasks(status: str | None = None) -> str:
    tasks = load_all_tasks()
    if status: tasks = [t for t in tasks if t.status == status]
    if not tasks: return "(无任务)"
    lines = [f"\n\033[33m## 任务列表 ({len(tasks)})\033[0m"]
    for t in tasks:
        icon = {"pending":" ","in_progress":"▶","completed":"✓"}.get(t.status,"?")
        deps = f" ← [{','.join(t.blocked_by)}]" if t.blocked_by else ""
        lines.append(f"  [{icon}] [{t.id}] {t.subject}{deps}")
    return "\n".join(lines)

def get_task(task_id: str) -> str:
    t = load_task(task_id)
    if not t: return f"错误: 任务 {task_id} 不存在"
    return json.dumps(t.to_dict(), ensure_ascii=False, indent=2)

def claim_task(task_id: str) -> str:
    t = load_task(task_id)
    if not t: return f"错误: 任务 {task_id} 不存在"
    if t.status != "pending": return f"错误: 任务 {task_id} 状态为 {t.status}，不是 pending"
    if not can_start(t):
        incomplete = [d for d in t.blocked_by if (dt := load_task(d)) and dt.status != "completed"]
        return f"错误: 任务 {task_id} 依赖未满足: {incomplete}"
    t.status = "in_progress"
    save_task(t)
    return f"已认领任务 [{task_id}] {t.subject}"

def complete_task(task_id: str) -> str:
    t = load_task(task_id)
    if not t: return f"错误: 任务 {task_id} 不存在"
    if t.status != "in_progress": return f"错误: 任务 {task_id} 状态为 {t.status}"
    t.status = "completed"
    save_task(t)
    # 检查解锁的任务
    unlocked = [ut for ut in load_all_tasks() if task_id in ut.blocked_by and can_start(ut)]
    msg = f"已完成任务 [{task_id}] {t.subject}"
    if unlocked: msg += f"\n已解锁 {len(unlocked)} 个下游任务: {[u.id for u in unlocked]}"
    return msg
