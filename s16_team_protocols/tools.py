"""s12 tools.py — 14 个工具（新增 5 个任务管理工具）"""
import subprocess, glob as g_mod
from pathlib import Path

from config import WORKSPACE_DIR, MAX_TOOL_OUTPUT, MAX_FILE_SIZE, DANGEROUS_COMMANDS, TASK_OUTPUT_DIR, TASKS_DIR, MEMORY_DIR, SCHEDULED_TASKS_FILE, MAILBOXES_DIR

def safe_path(p):
    a=(Path(WORKSPACE_DIR)/p).resolve()
    if not a.is_relative_to(WORKSPACE_DIR): raise ValueError(f"路径越界！{p}")
    return a
def run_bash(c):
    try:
        r=subprocess.run(c,shell=True,cwd=WORKSPACE_DIR,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120)
        o=(r.stdout+r.stderr).strip()
        if not o: return "(无输出)"
        if len(o)>MAX_TOOL_OUTPUT: o=o[:MAX_TOOL_OUTPUT]+"\n...(截断)"
        return o
    except subprocess.TimeoutExpired: return "错误:超时(120s)"
    except Exception as e: return f"错误:{e}"
def run_read(p,l=None):
    try:
        fp=safe_path(p);t=fp.read_text(encoding="utf-8",errors="replace")
        if len(t)>MAX_FILE_SIZE: t=t[:MAX_FILE_SIZE]+"\n...(截断)"
        ls=t.splitlines()
        if l and l<len(ls): ls=ls[:l]+[f"...(剩余{len(ls)-l}行)"]
        return "\n".join(ls)
    except ValueError as e: return f"错误:路径校验失败-{e}"
    except FileNotFoundError: return f"错误:文件不存在-{p}"
    except Exception as e: return f"错误:{e}"
def run_write(p,c):
    try: fp=safe_path(p);fp.parent.mkdir(parents=True,exist_ok=True);fp.write_text(c,encoding="utf-8");return f"已写入{len(c)}字节到{p}"
    except ValueError as e: return f"错误:路径校验失败-{e}"
    except Exception as e: return f"错误:{e}"
def run_edit(p,ot,nt):
    try:
        fp=safe_path(p);t=fp.read_text(encoding="utf-8")
        if ot not in t: return f"错误:未找到指定文本"
        fp.write_text(t.replace(ot,nt,1),encoding="utf-8");return f"已编辑{p}"
    except ValueError as e: return f"错误:路径校验失败-{e}"
    except FileNotFoundError: return f"错误:文件不存在-{p}"
    except Exception as e: return f"错误:{e}"
def run_glob(pt):
    try:
        ms=[]
        for m in g_mod.glob(pt,root_dir=WORKSPACE_DIR,recursive=True):
            if (Path(WORKSPACE_DIR)/m).resolve().is_relative_to(WORKSPACE_DIR): ms.append(m)
        return "\n".join(ms) if ms else "(无匹配)"
    except Exception as e: return f"错误:{e}"

TOOLS = [
    {"type":"function","function":{"name":"bash","description":"执行shell命令","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"read_file","description":"读取文件","parameters":{"type":"object","properties":{"path":{"type":"string"},"limit":{"type":"integer"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write_file","description":"写入文件","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"edit_file","description":"精确替换文本","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_text":{"type":"string"},"new_text":{"type":"string"}},"required":["path","old_text","new_text"]}}},
    {"type":"function","function":{"name":"glob","description":"通配符查找文件","parameters":{"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"todo_write","description":"管理任务列表","parameters":{"type":"object","properties":{"todos":{"type":"array","items":{"type":"object","properties":{"content":{"type":"string"},"status":{"type":"string","enum":["pending","in_progress","completed"]}},"required":["content","status"]}}},"required":["todos"]}}},
    {"type":"function","function":{"name":"task","description":"委托给子Agent","parameters":{"type":"object","properties":{"prompt":{"type":"string"},"cwd":{"type":"string"}},"required":["prompt"]}}},
    {"type":"function","function":{"name":"load_skill","description":"加载技能","parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}},
    {"type":"function","function":{"name":"compact","description":"压缩上下文","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"create_task","description":"创建新任务，可声明blockedBy依赖",
        "parameters":{"type":"object","properties":{"subject":{"type":"string"},"description":{"type":"string"},"blocked_by":{"type":"array","items":{"type":"string"}}},"required":["subject"]}}},
    {"type":"function","function":{"name":"list_tasks","description":"列出所有任务，可按状态过滤",
        "parameters":{"type":"object","properties":{"status":{"type":"string","enum":["pending","in_progress","completed"]}},"required":[]}}},
    {"type":"function","function":{"name":"get_task","description":"获取任务详情",
        "parameters":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}}},
    {"type":"function","function":{"name":"claim_task","description":"认领任务(pending→in_progress，检查依赖)",
        "parameters":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}}},
    {"type":"function","function":{"name":"complete_task","description":"完成任务(in_progress→completed)",
        "parameters":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}}},
    {"type":"function","function":{"name":"schedule_job","description":"注册定时任务(cron表达式)。格式: 分 时 日 月 星期。例: */5 * * * * 每5分钟",
        "parameters":{"type":"object","properties":{"cron":{"type":"string"},"prompt":{"type":"string"},"durable":{"type":"boolean"}},"required":["cron","prompt"]}}},
]

TOOL_HANDLERS = {
    "bash":lambda c:run_bash(c),"read_file":lambda p,l=None:run_read(p,l),"write_file":lambda p,c:run_write(p,c),
    "edit_file":lambda p,o,n:run_edit(p,o,n),"glob":lambda p:run_glob(p),
    "todo_write":None,"task":None,"load_skill":None,"compact":None,
    "create_task":None,"list_tasks":None,"get_task":None,"claim_task":None,"complete_task":None,
    "schedule_job":None,
}