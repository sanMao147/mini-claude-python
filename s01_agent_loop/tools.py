"""工具定义与执行"""

import subprocess
from config import WORKSPACE_DIR, MAX_TOOL_OUTPUT, DANGEROUS_COMMANDS


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
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                },
                "required": ["command"],
            },
        },
    }
]


def run_bash(command: str) -> str:
    cmd_lower = command.lower()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return f"[已拒绝] 危险命令被阻止: {dangerous}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = (result.stdout + result.stderr).strip()
        if not output:
            return "(无输出)"

        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + f"\n\n... (输出被截断，完整 {len(result.stdout)+len(result.stderr)} 字节)"

        return output

    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时 (120 秒)"
    except FileNotFoundError as e:
        return f"错误: 命令未找到 - {e}"
    except OSError as e:
        return f"错误: 操作系统错误 - {e}"


TOOL_HANDLERS = {
    "bash": lambda command: run_bash(command),
}