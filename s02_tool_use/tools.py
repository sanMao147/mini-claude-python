"""
============================================================================
  s02_tool_use/tools.py — 工具定义与执行（5 个工具）
============================================================================
  相比 s01，s02 新增了 4 个文件操作工具：
    - read_file  : 读取文件内容
    - write_file : 写入文件内容
    - edit_file  : 替换文件中的精确文本
    - glob       : 通配符查找文件

  新增 safe_path() 路径安全校验：
    - 确保所有文件操作都在 WORKSPACE_DIR 内进行
    - 防止路径遍历攻击（如 ../../etc/passwd）

  TOOL_HANDLERS 字典取代了 s01 中硬编码的工具调用方式，
  实现「工具名 → 处理函数」的查表分发。
============================================================================
"""

import os
import subprocess
import glob as glob_module
from pathlib import Path
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS, MAX_TOOL_OUTPUT, MAX_FILE_SIZE

# ============================================================================
# 路径安全校验 — s02 新增
# ============================================================================

def safe_path(relative_path: str) -> Path:
    """
    将相对路径解析为绝对路径，并确保路径在 WORKSPACE_DIR 之内。

    为什么需要这个？
      - 防止 Agent 读取/写入工作区外的文件（如 ~/.ssh/id_rsa）
      - 防止..路径遍历攻击（如 ../../../etc/passwd）
      - 所有文件操作都必须经过此函数校验
    """
    # resolve() 会解析 .. 和符号链接，得到真正的绝对路径
    absolute = (Path(WORKSPACE_DIR) / relative_path).resolve()
    # is_relative_to() 确保路径是工作区的子目录或文件
    if not absolute.is_relative_to(WORKSPACE_DIR):
        raise ValueError(f"路径越界！拒绝访问工作区外的路径: {relative_path}")
    return absolute


# ============================================================================
# 工具执行函数
# ============================================================================

def run_bash(command: str) -> str:
    """
    执行 shell 命令（与 s01 相同）。
    危险命令会被拒绝，命令超时 120 秒。
    """
    cmd_lower = command.lower()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return f"[已拒绝] 危险命令被阻止: {dangerous}"

    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKSPACE_DIR,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "(无输出)"
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + f"\n\n... (输出被截断)"
        return output
    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时 (120 秒)"
    except Exception as e:
        return f"错误: {e}"


# ── s02 新增的工具 ──────────────────────────────────────

def run_read_file(path: str, limit: int | None = None) -> str:
    """
    读取文件内容。
    - path: 文件路径（相对于工作区）
    - limit: 最大行数（可选，用于大文件预览）
    输出截断至 MAX_FILE_SIZE (50KB)。
    """
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
    """
    写入（或覆盖）文件。
    - path: 文件路径（相对于工作区）
    - content: 要写入的内容
    会自动创建父目录。
    """
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
    """
    在文件中精确替换一段文本（仅替换第一次出现）。
    - path: 文件路径
    - old_text: 要替换的原文本（必须精确匹配）
    - new_text: 替换后的新文本
    """
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"错误: 在 {path} 中未找到指定文本。请确认 old_text 与原文件完全一致。"
        new_content = text.replace(old_text, new_text, 1)
        file_path.write_text(new_content, encoding="utf-8")
        return f"已编辑 {path}（替换了 1 处）"
    except ValueError as e:
        return f"错误: 路径校验失败 - {e}"
    except FileNotFoundError:
        return f"错误: 文件不存在 - {path}"
    except Exception as e:
        return f"错误: {e}"


def run_glob(pattern: str) -> str:
    """
    使用通配符查找工作区中的文件。
    - pattern: glob 模式，如 "*.py"、"**/*.md"、"s01*/**"
    """
    try:
        matches = []
        for match in glob_module.glob(pattern, root_dir=WORKSPACE_DIR, recursive=True):
            # 双重校验：确保匹配结果也在工作区内
            if (Path(WORKSPACE_DIR) / match).resolve().is_relative_to(WORKSPACE_DIR):
                matches.append(match)
        return "\n".join(matches) if matches else "(无匹配)"
    except Exception as e:
        return f"错误: {e}"


# ============================================================================
# 工具定义 — OpenAI Function Calling 格式（5 个工具）
# ============================================================================

TOOLS = [
    # ── bash: 执行 shell 命令 ──
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "在终端中执行一个 shell 命令。可用于创建文件、运行脚本、安装依赖等。",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "要执行的 shell 命令"}},
                "required": ["command"],
            },
        },
    },
    # ── read_file: 读取文件 ──
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作区中文件的内容。使用 limit 参数可以只阅读前 N 行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作区）"},
                    "limit": {"type": "integer", "description": "最多读取的行数（可选）"},
                },
                "required": ["path"],
            },
        },
    },
    # ── write_file: 写入文件 ──
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入文件。如果文件已存在则覆盖，父目录不存在则自动创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作区）"},
                    "content": {"type": "string", "description": "要写入的文件内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    # ── edit_file: 编辑文件 ──
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "在文件中进行精确的文本替换（仅替换第一处匹配）。old_text 必须与原文件内容完全一致。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作区）"},
                    "old_text": {"type": "string", "description": "要被替换的原始文本（必须精确匹配）"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    # ── glob: 查找文件 ──
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "使用通配符模式查找工作区中的文件。例如 '*.py' 查找所有 Python 文件，'**/*.md' 递归查找所有 Markdown 文件。",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string", "description": "通配符模式，如 '*.py' 或 '**/*.md'"}},
                "required": ["pattern"],
            },
        },
    },
]

# ============================================================================
# 工具分发映射 — 工具名 → 处理函数
# ============================================================================
# s02 的核心改进：从 s01 的「硬编码 run_bash」变为「查表分发」
# 以后新增工具只需：1) 定义 TOOLS 条目 2) 在 TOOL_HANDLERS 中注册
TOOL_HANDLERS = {
    "bash": lambda command: run_bash(command),
    "read_file": lambda path, limit=None: run_read_file(path, limit),
    "write_file": lambda path, content: run_write_file(path, content),
    "edit_file": lambda path, old_text, new_text: run_edit_file(path, old_text, new_text),
    "glob": lambda pattern: run_glob(pattern),
}
