"""
============================================================================
  s01_agent_loop/tools.py — 工具定义与执行
============================================================================
  s01 只有 1 个工具：bash（执行 shell 命令）。

  工具定义格式：OpenAI Function Calling 格式
  - type: "function"
  - function.name: 工具名称
  - function.description: 工具描述（模型根据此描述决定何时调用）
  - function.parameters: JSON Schema 格式的参数定义

  TOOL_HANDLERS 字典：工具名 → 处理函数的映射
  当 model 返回 tool_calls 时，通过此字典找到对应处理函数并执行。
============================================================================
"""

import os
import subprocess
import shlex
from config import WORKSPACE_DIR, DANGEROUS_COMMANDS, MAX_TOOL_OUTPUT

# ============================================================================
# 工具定义 — OpenAI Function Calling 格式
# ============================================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "在终端中执行一个 shell 命令。"
                "可以用于：创建文件、运行脚本、安装依赖、查看目录内容等。"
                "命令在工作区目录下执行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    }
                },
                "required": ["command"],
            },
        },
    }
]


# ============================================================================
# 工具执行：run_bash(command) -> str
# ============================================================================

def run_bash(command: str) -> str:
    """
    执行一个 shell 命令，返回 stdout + stderr。

    安全措施：
    1. 拒绝危险命令（如 rm -rf /、fork bomb 等）
    2. 120 秒超时，防止命令卡死
    3. 输出截断至 50KB，防止撑爆上下文
    """
    # ---- 安全检查：拒绝危险命令 ----
    cmd_lower = command.lower()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return f"[已拒绝] 危险命令被阻止: {dangerous}"

    # ---- 执行命令 ----
    try:
        result = subprocess.run(
            command,
            shell=True,                   # 通过 shell 执行（支持管道、重定向等）
            cwd=WORKSPACE_DIR,            # 在工作区目录下执行
            capture_output=True,          # 捕获 stdout 和 stderr
            text=True,                    # 以文本模式返回（而非 bytes）
            timeout=120,                  # 120 秒超时
        )

        # 合并 stdout 和 stderr
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "(无输出)"

        # 截断长输出
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + f"\n\n... (输出被截断，完整 {len(result.stdout)+len(result.stderr)} 字节)"

        return output

    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时 (120 秒)"
    except FileNotFoundError as e:
        return f"错误: 命令未找到 - {e}"
    except OSError as e:
        return f"错误: 操作系统错误 - {e}"


# ============================================================================
# 工具分发映射 — 工具名 → 处理函数
# ============================================================================
# 当模型返回 tool_calls 时，循环中通过此字典查找并执行对应函数
TOOL_HANDLERS = {
    "bash": lambda command: run_bash(command),
}
