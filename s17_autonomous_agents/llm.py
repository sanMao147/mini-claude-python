"""
============================================================================
  s11_error_recovery/llm.py — 带错误恢复的 LLM API 调用封装
============================================================================
  相比之前版本，s11 增加了：
  1. with_retry() 指数退避重试
  2. max_tokens 自动升级恢复
  3. 529 连续错误 fallback 切换
  4. 熔断器保护
============================================================================
"""

import time
from openai import OpenAI

from config import API_KEY, API_URL, MODEL, MAX_TOKENS, TEMPERATURE

_client = OpenAI(api_key=API_KEY, base_url=API_URL)

from recovery import (
    retry_delay, should_retry, is_prompt_too_long_error,
    get_upgraded_max_tokens, circuit_breaker, _state, reset_state,
)

FALLBACK_MODELS = ["deepseek-chat", "deepseek-chat"]


def call_llm(messages, tools=None, system_prompt="", max_tokens=MAX_TOKENS, allow_retry=True):
    """
    带错误恢复的 LLM 调用。

    错误处理策略：
    - 429/529：指数退避重试（最多 3 次）
    - max_tokens 截断：自动升级 token 限制
    - prompt_too_long：返回错误标记（由 main.py 调用 reactive_compact）
    """
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    model = MODEL
    if _state.fallback_model:
        model = FALLBACK_MODELS[-1]

    current_max_tokens = max_tokens
    last_error = None

    for attempt in range(3 if allow_retry else 1):
        try:
            response = _client.chat.completions.create(
                model=model,
                messages=full_messages,
                tools=tools,
                max_tokens=current_max_tokens,
                temperature=TEMPERATURE,
            )
            _state.consecutive_failures = 0
            _state.consecutive_529 = 0

            choice = response.choices[0]
            msg = choice.message
            content = msg.content if msg.content else ""
            tool_calls = [{"id": tc.id, "type": "function",
                           "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                          for tc in (msg.tool_calls or [])]
            assistant_message = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls

            return {
                "finish_reason": choice.finish_reason,
                "content": content,
                "assistant_message": assistant_message,
                "tool_calls": tool_calls,
                "error": None,
            }

        except Exception as e:
            last_error = e
            err_msg = str(e).lower()

            if is_prompt_too_long_error(e):
                return {"finish_reason": "error", "content": "",
                        "assistant_message": {"role": "assistant", "content": ""},
                        "tool_calls": [], "error": "prompt_too_long"}

            if not should_retry(e):
                break

            if circuit_breaker():
                print(f"\033[31m[熔断] 连续 {_state.consecutive_failures} 次失败，停止重试\033[0m")
                break

            if "max_tokens" in err_msg or "too many tokens" in err_msg:
                upgraded = get_upgraded_max_tokens()
                if upgraded:
                    print(f"\033[33m[恢复] max_tokens 升级: {current_max_tokens} → {upgraded}\033[0m")
                    current_max_tokens = upgraded
                    continue

            if "529" in err_msg:
                from recovery import increment_529
                if increment_529():
                    _state.fallback_model = True
                    print(f"\033[33m[恢复] 切换 fallback model: {FALLBACK_MODELS[-1]}\033[0m")

            delay = retry_delay(attempt)
            print(f"\033[33m[重试 {attempt+1}] {err_msg[:80]}... 等待 {delay:.1f}s\033[0m")
            time.sleep(delay)

    return {"finish_reason": "error", "content": f"API 调用失败: {last_error}",
            "assistant_message": {"role": "assistant", "content": f"API 调用失败: {last_error}"},
            "tool_calls": [], "error": str(last_error)}