"""s07 permission.py — 权限检查辅助函数"""
from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS
def check_deny_list(c):  return next((f"危险命令被阻止: '{p}'" for p in DANGEROUS_COMMANDS if p.lower() in c.lower()), None)
def is_destructive_bash(c): return any(k in c.lower() for k in ["rm ","> /etc/","chmod 777","chown","passwd"])
def is_outside_workspace(p):
    try: return not (Path(WORKSPACE_DIR)/p).resolve().is_relative_to(WORKSPACE_DIR)
    except: return True
