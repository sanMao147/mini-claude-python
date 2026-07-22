"""
============================================================================
  s14_cron_scheduler/cron.py — Cron 定时调度系统
============================================================================
"""

import threading, time, json, os

from config import SCHEDULED_TASKS_FILE

cron_queue: list[dict] = []
cron_lock = threading.Lock()
agent_lock = threading.Lock()

_last_marker = ""


class CronJob:
    def __init__(self, job_id: str, cron: str, prompt: str, durable: bool = False):
        self.job_id = job_id
        self.cron = cron
        self.prompt = prompt
        self.durable = durable
        self.last_run: str | None = None

    def to_dict(self): return {"job_id": self.job_id, "cron": self.cron, "prompt": self.prompt, "durable": self.durable, "last_run": self.last_run}
    @classmethod
    def from_dict(cls, d):
        j = cls(d["job_id"], d["cron"], d["prompt"], d.get("durable", False))
        j.last_run = d.get("last_run")
        return j


_cron_jobs: dict[str, CronJob] = {}


def cron_matches(cron_expr: str, dt=None) -> bool:
    if dt is None:
        dt = time.localtime()
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    fields = [
        (dt.tm_min, 0, 59),
        (dt.tm_hour, 0, 23),
        (dt.tm_mday, 1, 31),
        (dt.tm_mon, 1, 12),
        ((dt.tm_wday + 1) % 7, 0, 6),
    ]

    for i, (val, lo, hi) in enumerate(fields):
        spec = parts[i]
        if spec == "*":
            continue
        match = False
        for item in spec.split(","):
            if "/" in item:
                base, step = item.split("/", 1)
                base = 0 if base == "*" else int(base)
                step = int(step)
                if val >= base and (val - base) % step == 0:
                    match = True; break
            elif "-" in item:
                s, e = item.split("-", 1)
                if int(s) <= val <= int(e):
                    match = True; break
            elif int(item) == val:
                match = True; break
        if not match:
            return False
    return True


def schedule_job(cron: str, prompt: str, durable: bool = False) -> str:
    import uuid
    job_id = f"cron_{uuid.uuid4().hex[:8]}"
    job = CronJob(job_id, cron, prompt, durable)
    _cron_jobs[job_id] = job
    _save_durable_jobs()
    return f"定时任务已注册 [{job_id}] {cron}"


def _load_durable_jobs():
    if not os.path.exists(SCHEDULED_TASKS_FILE):
        return
    try:
        data = json.loads(open(SCHEDULED_TASKS_FILE, "r", encoding="utf-8").read())
        for item in data:
            job = CronJob.from_dict(item)
            _cron_jobs[job.job_id] = job
    except Exception:
        pass


def _save_durable_jobs():
    durable = [j.to_dict() for j in _cron_jobs.values() if j.durable]
    with open(SCHEDULED_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(durable, f, ensure_ascii=False, indent=2)


def cron_scheduler_loop():
    global _last_marker
    _load_durable_jobs()

    while True:
        now = time.localtime()
        minute_marker = f"{now.tm_year}{now.tm_mon}{now.tm_mday}{now.tm_hour}{now.tm_min}"

        if minute_marker != _last_marker:
            _last_marker = minute_marker
            for job in list(_cron_jobs.values()):
                if cron_matches(job.cron, now):
                    with cron_lock:
                        cron_queue.append({"job_id": job.job_id, "prompt": job.prompt, "cron": job.cron})
                        print(f"\033[35m[Cron] 触发: [{job.job_id}] {job.prompt[:60]}\033[0m")

        time.sleep(1)


def queue_processor_loop():
    while True:
        if cron_queue and agent_lock.acquire(blocking=False):
            try:
                with cron_lock:
                    if cron_queue:
                        job = cron_queue.pop(0)
                        return job
            finally:
                agent_lock.release()
        time.sleep(0.5)


_cron_thread_started = False


def start_cron_scheduler():
    global _cron_thread_started
    if _cron_thread_started: return
    t = threading.Thread(target=cron_scheduler_loop, daemon=True)
    t.start()
    _cron_thread_started = True
