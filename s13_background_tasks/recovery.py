"""
============================================================================
  s11_error_recovery/recovery.py — 错误恢复系统
============================================================================
  s11 的核心新增模块。三种错误恢复路径：

  路径 1 — max_tokens 截断：
    自动升级 4K→8K→16K→64K，触发续写提示（最多 3 次）

  路径 2 — prompt_too_long：
    调用 reactive_compact() 应急压缩后重试（1 次）

  路径 3 — 429/529 限流：
    with_retry() 指数退避 + 抖动重试
    delay = min(500*2^attempt, 32000)ms + 随机0-25%
    连续 3 次 529 切换 fallback model

  RecoveryState 追踪所有恢复状态
  熔断器：连续失败 3 次停止
============================================================================
"""

import time, random

# 最大重试次数
MAX_RETRIES = 3

# 指数退避参数
BASE_DELAY = 0.5       # 基础延迟 500ms
MAX_DELAY = 32.0       # 最大延迟 32s
JITTER = 0.25          # 抖动比例 25%

# max_tokens 升级序列
TOKEN_UPGRADE_SEQUENCE = [4096, 8192, 16384, 65536]

# 529 连续次数阈值（超过后切换 fallback model）
MAX_529_COUNT = 3


class RecoveryState:
    """追踪错误恢复状态的容器。"""
    def __init__(self):
        self.total_retries = 0          # 总重试次数
        self.consecutive_failures = 0   # 连续失败次数
        self.max_tokens_level = 0       # 当前 max_tokens 升级级别
        self.consecutive_529 = 0        # 连续 529 次数
        self.has_compacted = False      # 是否已执行 reactive compact
        self.fallback_model = False     # 是否已切换到 fallback model


_state = RecoveryState()


def reset_state():
    """重置恢复状态（新会话时调用）。"""
    global _state
    _state = RecoveryState()


def retry_delay(attempt: int) -> float:
    """
    计算指数退避延迟。

    公式：min(BASE_DELAY * 2^attempt, MAX_DELAY) * (1 + random(0, JITTER))

    attempt=0 → ~0.5s
    attempt=1 → ~1.0s
    attempt=2 → ~2.0s
    attempt=3 → ~4.0s
    """
    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    delay *= (1.0 + random.random() * JITTER)  # 添加抖动
    return delay


def is_prompt_too_long_error(error: Exception) -> bool:
    """判断错误是否是上下文过长导致的。"""
    msg = str(error).lower()
    return any(kw in msg for kw in ["prompt_too_long", "context length", "maximum context", "too long"])


def is_overloaded_error(error: Exception) -> bool:
    """判断是否是服务器过载错误（429/529）。"""
    msg = str(error).lower()
    return any(str(code) in msg for code in ["429", "529"])


def should_retry(error: Exception) -> bool:
    """判断错误是否值得重试。"""
    msg = str(error).lower()
    retryable = ["rate limit", "overloaded", "timeout", "server error",
                 "internal server error", "service unavailable", "429", "529", "503"]
    return any(kw in msg for kw in retryable)


def get_upgraded_max_tokens() -> int | None:
    """
    获取升级后的 max_tokens（截断恢复用）。
    返回 None 表示已达最大级别。
    """
    if _state.max_tokens_level >= len(TOKEN_UPGRADE_SEQUENCE):
        return None
    tokens = TOKEN_UPGRADE_SEQUENCE[_state.max_tokens_level]
    _state.max_tokens_level += 1
    return tokens


def increment_529():
    """增加 529 连续计数，返回是否需要切换 fallback model。"""
    _state.consecutive_529 += 1
    return _state.consecutive_529 >= MAX_529_COUNT


def circuit_breaker() -> bool:
    """熔断器：连续失败超过阈值返回 True。"""
    if _state.consecutive_failures >= MAX_RETRIES:
        return True
    _state.consecutive_failures += 1
    _state.total_retries += 1
    return False
