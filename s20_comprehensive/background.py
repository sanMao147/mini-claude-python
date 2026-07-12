"""
============================================================================
  s13_background_tasks/background.py — 后台任务执行
============================================================================
  慢操作（bash 含 install/build/test/deploy 等关键词）放到 daemon 线程执行。

  should_run_background() — 判断是否应后台执行
  start_background_task() — 启动 daemon 线程
  collect_background_results() — 收集完成的后台任务结果并格式化为通知
============================================================================
"""

import threading, time, uuid

# 活跃的后台任务注册表。
# key 是 bg_id，value 保存命令、线程对象和运行状态，方便主循环查询当前还有哪些慢任务。
background_tasks: dict[str, dict] = {}
# 已完成的后台任务结果队列。
# 后台线程只负责把结果放进这里，真正展示给 Agent 的通知由 collect_background_results() 统一生成。
background_results: list[dict] = []
# 所有后台任务共享这把锁，避免“线程正在写结果、主线程正在读取结果”时出现竞态。
background_lock = threading.Lock()

# 用关键词做轻量判断：这些命令通常耗时较长，适合交给 daemon 线程后台执行。
SLOW_KEYWORDS = ["install", "build", "test", "deploy", "compile", "download",
                 "npm run", "pip install", "apt-get", "brew install", "cargo build"]


def should_run_background(command: str) -> bool:
    """检查 bash 命令是否应后台执行。"""
    return any(kw in command.lower() for kw in SLOW_KEYWORDS)


def start_background_task(command: str) -> str:
    """启动后台 daemon 线程执行命令，返回 bg_id。"""
    import subprocess as sp
    # bg_id 只取 uuid 的前 8 位：足够区分本次进程里的后台任务，也便于终端展示。
    bg_id = f"bg_{uuid.uuid4().hex[:8]}"

    def _run():
        """线程入口：执行命令并把结果搬运到 background_results 队列。"""
        try:
            r = sp.run(command, shell=True, cwd=None, capture_output=True, text=True, timeout=300)
            output = (r.stdout + r.stderr).strip() or "(无输出)"
        except sp.TimeoutExpired:
            output = "错误: 后台任务超时"
        except Exception as e:
            output = f"错误: {e}"

        with background_lock:
            # 任务完成后从运行表移除，并把最终输出放入结果队列，等待主循环下一轮消费。
            background_tasks.pop(bg_id, None)
            background_results.append({
                "bg_id": bg_id, "command": command,
                "status": "completed", "output": output[:50000],
            })

    t = threading.Thread(target=_run, daemon=True)
    with background_lock:
        background_tasks[bg_id] = {"command": command, "thread": t, "status": "running"}
    t.start()

    print(f"\033[35m[后台] {bg_id}: {command[:60]}...\033[0m")
    return f"后台任务已启动 [{bg_id}]"


def collect_background_results() -> list[str]:
    """收集已完成的后台任务结果，返回通知消息列表。"""
    notifications = []
    with background_lock:
        # 一次性清空结果队列，避免同一个后台任务完成消息被重复注入上下文。
        while background_results:
            r = background_results.pop(0)
            msg = (
                f"<task_notification>\n"
                f"后台任务 [{r['bg_id']}] 已完成:\n"
                f"命令: {r['command'][:200]}\n"
                f"输出: {r['output'][:1000]}\n"
                f"</task_notification>"
            )
            notifications.append(msg)
    return notifications
