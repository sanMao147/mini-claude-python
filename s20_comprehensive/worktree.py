"""s18 worktree.py — Git Worktree 目录隔离"""
import os, subprocess, re
from pathlib import Path

# worktree.py 用于给子任务创建隔离工作目录。
# 这样可以让实验性修改和主工作区分开，review 后再决定是否合并。

def validate_worktree_name(name: str) -> bool:
    """只允许字母、数字、下划线和短横线，避免把路径片段注入 worktree 名称。"""
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', name))

def _run_git(args, cwd=None):
    """执行 git 子命令，返回 stdout/stderr 字符串，异常时转换为错误文本。"""
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, timeout=30, cwd=cwd)
        return r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return "", str(e)

def create_worktree(name: str, base_cwd: str) -> str:
    """创建 Git worktree + 分支 wt/{name}。返回 worktree 路径。"""
    if not validate_worktree_name(name): return f"错误: 无效名称 '{name}'"
    # worktree 放在 base_cwd 的兄弟目录，命名为 wt-{name}，便于人工识别。
    wt_path = os.path.join(os.path.dirname(base_cwd), f"wt-{name}")
    branch = f"wt/{name}"
    # 优先创建新分支；如果分支已存在等情况失败，再尝试直接添加 worktree。
    out, err = _run_git(["worktree", "add", "-b", branch, wt_path], cwd=base_cwd)
    if err and "already" not in err.lower():
        out2, _ = _run_git(["worktree", "add", wt_path], cwd=base_cwd)
        if out2: out = out2
    return wt_path if os.path.isdir(wt_path) else f"错误: {err}"

def remove_worktree(wt_path: str, discard_changes: bool = False) -> str:
    """移除 worktree。有未提交改动时默认拒绝。"""
    if not discard_changes:
        # 默认保护未提交改动；只有调用方明确 discard_changes=True 才强制删除。
        out, _ = _run_git(["status", "--porcelain"], cwd=wt_path)
        if out.strip():
            return "错误: worktree 有未提交改动，使用 discard_changes=true 强制移除"
    out, err = _run_git(["worktree", "remove", "--force", wt_path])
    return out or err or f"已移除 worktree: {wt_path}"

def keep_worktree(wt_path: str) -> str:
    """保留 worktree（不删除，等待 review）。"""
    # 这个函数只是显式表达“保留给人工 review”的决策，不执行 git 操作。
    return f"Worktree 已保留: {wt_path}"
