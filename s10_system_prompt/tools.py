"""s10 tools.py — 9 个工具（含 compact）"""

import subprocess, glob as glob_module
from pathlib import Path

from config import WORKSPACE_DIR, MAX_TOOL_OUTPUT, MAX_FILE_SIZE

def safe_path(p):
    absolute = (Path(WORKSPACE_DIR) / p).resolve()
    if not absolute.is_relative_to(WORKSPACE_DIR): raise ValueError(f"路径越界！{p}")
    return absolute

def run_bash(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, cwd=WORKSPACE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        output = (result.stdout + result.stderr).strip()
        if not output: return "(无输出)"
        if len(output) > MAX_TOOL_OUTPUT: output = output[:MAX_TOOL_OUTPUT] + "\n... (截断)"
        return output
    except subprocess.TimeoutExpired: return "错误: 超时 (120s)"
    except Exception as e: return f"错误: {e}"

def run_read_file(path: str, limit=None):
    try:
        file_path = safe_path(path); text = file_path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_SIZE: text = text[:MAX_FILE_SIZE] + "\n... (截断)"
        lines = text.splitlines()
        if limit and limit < len(lines): lines = lines[:limit] + [f"... (剩余 {len(lines)-limit} 行)"]
        return "\n".join(lines)
    except ValueError as e: return f"错误: 路径校验失败 - {e}"
    except FileNotFoundError: return f"错误: 文件不存在 - {path}"
    except Exception as e: return f"错误: {e}"

def run_write_file(path: str, content: str) -> str:
    try: file_path = safe_path(path); file_path.parent.mkdir(parents=True, exist_ok=True); file_path.write_text(content, encoding="utf-8"); return f"已写入 {len(content)} 字节到 {path}"
    except ValueError as e: return f"错误: 路径校验失败 - {e}"
    except Exception as e: return f"错误: {e}"

def run_edit_file(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path); text = file_path.read_text(encoding="utf-8")
        if old_text not in text: return f"错误: 未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8"); return f"已编辑 {path}"
    except ValueError as e: return f"错误: 路径校验失败 - {e}"
    except FileNotFoundError: return f"错误: 文件不存在 - {path}"
    except Exception as e: return f"错误: {e}"

def run_glob(pattern: str) -> str:
    try:
        matches = []
        for match in glob_module.glob(pattern, root_dir=WORKSPACE_DIR, recursive=True):
            if (Path(WORKSPACE_DIR) / match).resolve().is_relative_to(WORKSPACE_DIR): matches.append(match)
        return "\n".join(matches) if matches else "(无匹配)"
    except Exception as e: return f"错误: {e}"

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "执行 shell 命令。",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取文件。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入文件。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "精确替换文本。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "glob", "description": "通配符查找文件。",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "todo_write", "description": "管理任务列表。",
        "parameters": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object",
            "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending","in_progress","completed"]}},
            "required": ["content","status"]}}}, "required": ["todos"]}}},
    {"type": "function", "function": {"name": "task", "description": "将子任务委托给子 Agent。",
        "parameters": {"type": "object", "properties": {"prompt": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["prompt"]}}},
    {"type": "function", "function": {"name": "load_skill", "description": "加载技能完整说明。",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "compact", "description": "压缩对话上下文，释放上下文空间。当对话历史过长导致问题时可调用此工具。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

TOOL_HANDLERS = {
    "bash": lambda command: run_bash(command),
    "read_file": lambda path, limit=None: run_read_file(path, limit),
    "write_file": lambda path, content: run_write_file(path, content),
    "edit_file": lambda path, old_text, new_text: run_edit_file(path, old_text, new_text),
    "glob": lambda pattern: run_glob(pattern),
    "todo_write": None, "task": None, "load_skill": None, "compact": None,
}