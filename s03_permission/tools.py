"""工具定义与执行（5 个工具，与 s02 相同）"""

import subprocess
import glob as glob_module
from pathlib import Path
from config import WORKSPACE_DIR, MAX_TOOL_OUTPUT, MAX_FILE_SIZE


def safe_path(relative_path: str) -> Path:
    absolute = (Path(WORKSPACE_DIR) / relative_path).resolve()
    if not absolute.is_relative_to(WORKSPACE_DIR):
        raise ValueError(f"路径越界！拒绝访问工作区外的路径: {relative_path}")
    return absolute


def run_bash(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, cwd=WORKSPACE_DIR,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120)
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "(无输出)"
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n\n... (输出被截断)"
        return output
    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时 (120 秒)"
    except Exception as e:
        return f"错误: {e}"


def run_read_file(path: str, limit: int | None = None) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_SIZE:
            text = text[:MAX_FILE_SIZE] + f"\n\n... (文件被截断，完整大小 {file_path.stat().st_size} 字节)"
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... (剩余 {len(lines) - limit} 行)"]
        return "\n".join(lines)
    except ValueError as e:
        return f"错误: 路径校验失败 - {e}"
    except FileNotFoundError:
        return f"错误: 文件不存在 - {path}"
    except Exception as e:
        return f"错误: {e}"


def run_write_file(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"已写入 {len(content)} 字节到 {path}"
    except ValueError as e:
        return f"错误: 路径校验失败 - {e}"
    except Exception as e:
        return f"错误: {e}"


def run_edit_file(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误: 在 {path} 中未找到指定文本"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"已编辑 {path}（替换了 1 处）"
    except ValueError as e:
        return f"错误: 路径校验失败 - {e}"
    except FileNotFoundError:
        return f"错误: 文件不存在 - {path}"
    except Exception as e:
        return f"错误: {e}"


def run_glob(pattern: str) -> str:
    try:
        matches = []
        for match in glob_module.glob(pattern, root_dir=WORKSPACE_DIR, recursive=True):
            if (Path(WORKSPACE_DIR) / match).resolve().is_relative_to(WORKSPACE_DIR):
                matches.append(match)
        return "\n".join(matches) if matches else "(无匹配)"
    except Exception as e:
        return f"错误: {e}"


TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "在终端中执行一个 shell 命令。",
        "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "要执行的 shell 命令"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取工作区中文件的内容。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}, "limit": {"type": "integer", "description": "最多行数"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "将内容写入文件。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}, "content": {"type": "string", "description": "文件内容"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "在文件中精确替换文本。",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "glob", "description": "通配符查找文件。",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "通配符模式"}}, "required": ["pattern"]}}},
]

TOOL_HANDLERS = {
    "bash": lambda command: run_bash(command),
    "read_file": lambda path, limit=None: run_read_file(path, limit),
    "write_file": lambda path, content: run_write_file(path, content),
    "edit_file": lambda path, old_text, new_text: run_edit_file(path, old_text, new_text),
    "glob": lambda pattern: run_glob(pattern),
}