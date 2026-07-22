"""s07 permission.py — 权限检查辅助函数"""
from pathlib import Path
from tools import WORKSPACE_DIR, DANGEROUS_COMMANDS

# permission.py 只做“判断”，不负责和用户交互。
# 交互确认逻辑放在 hooks.py，这样底层判断函数可以被其他模块复用。

def check_deny_list(c):  return next((f"危险命令被阻止: '{p}'" for p in DANGEROUS_COMMANDS if p.lower() in c.lower()), None)

# 破坏性命令启发式：命中时不一定绝对禁止，但需要 hooks.py 进行人工确认。
def is_destructive_bash(c): return any(k in c.lower() for k in ["rm ","> /etc/","chmod 777","chown","passwd"])

def is_outside_workspace(p):
    """解析路径后判断是否越过 WORKSPACE_DIR；异常时按不安全处理。"""
    try: return not (Path(WORKSPACE_DIR)/p).resolve().is_relative_to(WORKSPACE_DIR)
    except: return True
