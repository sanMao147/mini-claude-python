"""
============================================================================
  集中配置文件 — mini-claude-python（唯一入口）
============================================================================
  本模块是整个项目的唯一配置加载入口，在被首次 import 时自动完成：

    1. 计算项目根目录 WORKSPACE_DIR
    2. 加载项目根目录 .env 文件（通过 python-dotenv）
    3. 将项目根目录注入 sys.path（使所有步骤可 from config import）

  所有其他模块无需再手动操作 sys.path 或调用 load_dotenv，
  只需 import config 即可保证 .env 已可靠加载且路径已就绪。

  更换 LLM 提供方只需修改项目根目录 .env 中的 API_KEY / API_URL / MODEL。

  支持的提供方示例：
    - DeepSeek (默认):  API_URL = "https://api.deepseek.com/v1"
    - OpenAI:           API_URL = "https://api.openai.com/v1"
    - 通义千问:         API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    - 智谱 GLM:         API_URL = "https://open.bigmodel.cn/api/paas/v4"
    - 本地 Ollama:      API_URL = "http://localhost:11434/v1"
============================================================================
"""

import os
import sys

from dotenv import load_dotenv

# ── 唯一入口：项目根目录计算 + .env 加载 + sys.path 注入（幂等） ──

# 自动检测项目根目录（即本文件所在目录）
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

# 确保项目根目录在 sys.path 中，使 from config import 在任何模块都可用
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

# 加载 .env 文件（override=False 表示不覆盖已有的系统环境变量）
load_dotenv(os.path.join(WORKSPACE_DIR, ".env"), override=False)

# ============================================================================
#  LLM API 配置
# ============================================================================

# DeepSeek API Key（在项目根目录 .env 中配置）
API_KEY = os.getenv("API_KEY", "")

# API 端点地址（OpenAI 兼容接口）
API_URL = os.getenv("API_URL", "https://api.deepseek.com/v1")

# 模型名称
MODEL = os.getenv("MODEL", "deepseek-chat")

# ============================================================================
#  调用参数
# ============================================================================

# 每次 LLM 调用的最大输出 token 数
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

# 采样温度，0.0 表示确定性输出（推荐用于工具调用场景）
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))

# ============================================================================
#  安全配置
# ============================================================================

# 危险命令黑名单 — 这些命令永远不被执行
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf .",
    "mkfs.",
    "dd if=",
    ":(){ :|:& };:",       # fork bomb
    "chmod -R 777 /",
    "> /dev/sda",
    "shutdown",
    "reboot",
]

# 文件读取最大字节数（防止大文件撑爆上下文）
MAX_FILE_SIZE = 50 * 1024  # 50 KB

# 工具输出截断最大字节数
MAX_TOOL_OUTPUT = 50 * 1024  # 50 KB

# ============================================================================
#  运行时路径（自动创建）
# ============================================================================

# 任务输出缓存目录
TASK_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, ".task_outputs")

# 记忆文件目录
MEMORY_DIR = os.path.join(WORKSPACE_DIR, ".memory")

# 任务持久化目录
TASKS_DIR = os.path.join(WORKSPACE_DIR, ".tasks")

# 定时任务持久化文件
SCHEDULED_TASKS_FILE = os.path.join(WORKSPACE_DIR, ".scheduled_tasks.json")

# 团队收件箱目录
MAILBOXES_DIR = os.path.join(WORKSPACE_DIR, ".mailboxes")
