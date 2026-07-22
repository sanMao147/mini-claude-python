"""s13 tasks.py — 任务DAG系统"""
import os, json, uuid
from pathlib import Path
from dataclasses import dataclass, field, asdict

from config import TASKS_DIR
os.makedirs(TASKS_DIR, exist_ok=True)

@dataclass
class Task:
    id: str; subject: str; description: str = ""; status: str = "pending"
    owner: str|None = None; blocked_by: list[str] = field(default_factory=list)
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, d): return cls(**d)

def _task_path(tid): return os.path.join(TASKS_DIR, f"{tid}.json")
def save_task(t): Path(_task_path(t.id)).write_text(json.dumps(t.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
def load_task(tid):
    p=_task_path(tid)
    if not os.path.exists(p): return None
    return Task.from_dict(json.loads(Path(p).read_text(encoding="utf-8")))
def load_all_tasks():
    ts=[]
    if os.path.isdir(TASKS_DIR):
        for f in sorted(os.listdir(TASKS_DIR)):
            if f.endswith(".json"):
                t=load_task(f.replace(".json",""))
                if t: ts.append(t)
    return ts
def can_start(t):
    if not t.blocked_by: return True
    return all((d:=load_task(dep)) and d.status=="completed" for dep in t.blocked_by)
def create_task(subject,description="",blocked_by=None):
    tid=str(uuid.uuid4())[:8];t=Task(id=tid,subject=subject,description=description,blocked_by=blocked_by or [])
    save_task(t);return f"任务已创建: [{tid}] {subject}"
def list_tasks(status=None):
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
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    return json.dumps(t.to_dict(),ensure_ascii=False,indent=2)
def claim_task(tid):
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    if t.status!="pending": return f"错误:任务状态为{t.status}"
    if not can_start(t):
        inc=[d for d in t.blocked_by if (dt:=load_task(d)) and dt.status!="completed"]
        return f"错误:依赖未满足:{inc}"
    t.status="in_progress";save_task(t);return f"已认领 [{tid}] {t.subject}"
def complete_task(tid):
    t=load_task(tid)
    if not t: return f"错误:任务{tid}不存在"
    if t.status!="in_progress": return f"错误:任务状态为{t.status}"
    t.status="completed";save_task(t)
    ul=[ut for ut in load_all_tasks() if tid in ut.blocked_by and can_start(ut)]
    msg=f"已完成 [{tid}] {t.subject}"
    if ul: msg+=f"\n已解锁{len(ul)}个下游任务:{[u.id for u in ul]}"
    return msg
