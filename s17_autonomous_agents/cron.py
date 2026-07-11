"""
============================================================================
  s14_cron_scheduler/cron.py — Cron 定时调度系统
============================================================================
  四层模型：
  1. Scheduler — daemon 线程每秒轮询，cron_matches() 做五段式匹配
  2. Queue — cron_queue，调度线程写入
  3. Queue Processor — queue_processor_loop() 在 Agent 空闲时交付
  4. Consumer — agent_loop 从队列消费并注入

  Cron 支持: 分钟 小时 日 月 星期 (* 匹配全部)
  Durable job 持久化到 .scheduled_tasks.json
============================================================================
"""

import threading, time, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SCHEDULED_TASKS_FILE

# 调度队列
cron_queue: list[dict] = []
cron_lock = threading.Lock()
agent_lock = threading.Lock()  # 判断 Agent 是否空闲

# 日期感知标记（防止同一分钟重复触发）
_last_marker = ""


class CronJob:
    def __init__(self, job_id: str, cron: str, prompt: str, durable: bool = False):
        self.job_id = job_id
        self.cron = cron    # "*/5 * * * *" 格式
        self.prompt = prompt
        self.durable = durable
        self.last_run: str | None = None

    def to_dict(self): return {"job_id": self.job_id, "cron": self.cron, "prompt": self.prompt, "durable": self.durable, "last_run": self.last_run}
    @classmethod
    def from_dict(cls, d):
        j = cls(d["job_id"], d["cron"], d["prompt"], d.get("durable", False))
        j.last_run = d.get("last_run")
        return j


# 注册的定时任务
_cron_jobs: dict[str, CronJob] = {}


def cron_matches(cron_expr: str, dt=None) -> bool:
    """五段式 cron 匹配（分钟/小时/日/月/星期）。DOM和DOW同时约束时OR语义。"""
    if dt is None:
        dt = time.localtime()
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    fields = [
        (dt.tm_min, 0, 59),      # 分钟
        (dt.tm_hour, 0, 23),     # 小时
        (dt.tm_mday, 1, 31),     # 日
        (dt.tm_mon, 1, 12),      # 月
        ((dt.tm_wday + 1) % 7, 0, 6),  # 星期 (0=周日)
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
    """注册一个定时任务。返回 job_id。"""
    import uuid
    job_id = f"cron_{uuid.uuid4().hex[:8]}"
    job = CronJob(job_id, cron, prompt, durable)
    _cron_jobs[job_id] = job
    _save_durable_jobs()
    return f"定时任务已注册 [{job_id}] {cron}"


def _load_durable_jobs():
    """从持久化文件加载定时任务。"""
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
    """持久化 durable 类型的定时任务。"""
    durable = [j.to_dict() for j in _cron_jobs.values() if j.durable]
    with open(SCHEDULED_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(durable, f, ensure_ascii=False, indent=2)


def cron_scheduler_loop():
    """Daemon 线程：每秒轮询，匹配的 cron 任务写入队列。"""
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
    """在 Agent 空闲时从队列交付出任务。"""
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


# 启动 cron scheduler（在 main.py 中调用）
_cron_thread_started = False


def start_cron_scheduler():
    global _cron_thread_started
    if _cron_thread_started: return
    t = threading.Thread(target=cron_scheduler_loop, daemon=True)
    t.start()
    _cron_thread_started = True
