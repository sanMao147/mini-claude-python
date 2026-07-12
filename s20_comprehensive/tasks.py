"""s13 tasks.py — 任务DAG系统（从s12复制）"""
import os, json, uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict
from config import TASKS_DIR
os.makedirs(TASKS_DIR, exist_ok=True)

# tasks.py 管理“持久任务 DAG”。
# 每个任务保存为 TASKS_DIR 下的 JSON 文件，blocked_by 表示前置任务依赖。
# 这和 todos.py 的临时 TodoWrite 不同：这里的任务可以跨轮次、跨 Agent 继续使用。

@dataclass
class Task:
    """单个任务节点：status 表示生命周期，blocked_by 表示必须先完成的上游任务。"""
    id: str; subject: str; description: str = ""; status: str = "pending"
    owner: str|None = None; blocked_by: list[str] = field(default_factory=list)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, d): return cls(**d)

def _task_path(tid): return os.path.join(TASKS_DIR, f"{tid}.json")

def save_task(t): Path(_task_path(t.id)).write_text(json.dumps(t.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")

def load_task(tid):
    """从磁盘读取单个任务；不存在时返回 None，方便调用方生成错误提示。"""
    p=_task_path(tid)
    if not os.path.exists(p): return None
    return Task.from_dict(json.loads(Path(p).read_text(encoding="utf-8")))

def load_all_tasks():
    """扫描任务目录，按文件名排序后加载所有 JSON 任务。"""
    ts=[]
    if os.path.isdir(TASKS_DIR):
        for f in sorted(os.listdir(TASKS_DIR)):
            if f.endswith(".json"):
                t=load_task(f.replace(".json",""))
                if t: ts.append(t)
    return ts

def can_start(t):
    """只有所有 blocked_by 任务都 completed 时，当前任务才允许被认领。"""
    if not t.blocked_by: return True
    return all((d:=load_task(dep)) and d.status=="completed" for dep in t.blocked_by)

def create_task(subject,description="",blocked_by=None):
    """创建 pending 任务；blocked_by 默认为空列表，表示可立即认领。"""
    tid=str(uuid.uuid4())[:8];t=Task(id=tid,subject=subject,description=description,blocked_by=blocked_by or [])
    save_task(t);return f"任务已创建: [{tid}] {subject}"

def list_tasks(status=None):
    """列出任务摘要；传入 status 时只显示该状态的任务。"""
    ts=load_all_tasks()
    if status: ts=[t for t in ts if t.status==status]
    if not ts: return "(无任务)"
    lines=[f"\n\033[33m## 任务列表 ({len(ts)})\033[0m"]
    for t in ts:
        icon={"pending":" ","in_progress":"▶","completed":"✓"}.get(t.status,"?")
        deps=f" ← [{','.join(t.blocked_by)}]" if t.blocked_by else ""
        lines.append(f"  [{icon}] [{t.id}] {t.subject}{deps}")
    return "\n".join(lines)

def get_task(tid):
    """返回完整任务 JSON，便于模型查看 description、owner 和依赖信息。"""
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    return json.dumps(t.to_dict(),ensure_ascii=False,indent=2)

def claim_task(tid):
    """把 pending 任务推进到 in_progress；依赖不满足时拒绝认领。"""
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    if t.status!="pending": return f"错误:任务状态为{t.status}"
    if not can_start(t):
        inc=[d for d in t.blocked_by if (dt:=load_task(d)) and dt.status!="completed"]
        return f"错误:依赖未满足:{inc}"
    t.status="in_progress";save_task(t);return f"已认领 [{tid}] {t.subject}"

def complete_task(tid):
    """完成 in_progress 任务，并提示因此被解锁的下游任务。"""
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    if t.status!="in_progress": return f"错误:任务状态为{t.status}"
    t.status="completed";save_task(t)
    # 找出所有依赖当前任务、且现在已经满足全部依赖的任务，给 Agent 一个下一步提示。
    ul=[ut for ut in load_all_tasks() if tid in ut.blocked_by and can_start(ut)]
    msg=f"已完成 [{tid}] {t.subject}"
    if ul: msg+=f"\n已解锁{len(ul)}个下游任务:{[u.id for u in ul]}"
    return msg
