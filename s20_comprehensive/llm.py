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
from recovery import (
    retry_delay, should_retry, is_prompt_too_long_error,
    get_upgraded_max_tokens, circuit_breaker, _state, reset_state,
)

_client = OpenAI(api_key=API_KEY, base_url=API_URL)

# Fallback model 列表（当前 529 过多时切换）。
# 这里保留为列表，方便后续扩展多个备用模型；当前示例里两个值相同。
FALLBACK_MODELS = ["deepseek-chat", "deepseek-chat"]


def call_llm(messages, tools=None, system_prompt="", max_tokens=MAX_TOKENS, allow_retry=True):
    """
    带错误恢复的 LLM 调用。

    错误处理策略：
    - 429/529：指数退避重试（最多 3 次）
    - max_tokens 截断：自动升级 token 限制
    - prompt_too_long：返回错误标记（由 main.py 调用 reactive_compact）
    """
    # OpenAI 兼容接口要求 system prompt 也放在 messages 列表里。
    # 调用方只传业务 messages，这里统一拼接，避免每个调用点重复处理。
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    # 默认使用配置里的主模型；如果恢复模块记录了 fallback 状态，就切到备用模型。
    model = MODEL
    if _state.fallback_model:
        model = FALLBACK_MODELS[-1]

    # current_max_tokens 会在 max_tokens 类错误时动态升级，不直接修改全局配置。
    current_max_tokens = max_tokens
    last_error = None

    for attempt in range(3 if allow_retry else 1):
        try:
            # 所有 LLM 请求都从这里出去，便于统一处理 tools、温度、token 限制和错误恢复。
            response = _client.chat.completions.create(
                model=model,
                messages=full_messages,
                tools=tools,
                max_tokens=current_max_tokens,
                temperature=TEMPERATURE,
            )
            # 成功 → 重置状态，避免一次短暂故障影响后续正常请求。
            _state.consecutive_failures = 0
            _state.consecutive_529 = 0

            choice = response.choices[0]
            msg = choice.message
            content = msg.content if msg.content else ""
            # 将 SDK 对象转换成普通 dict，后续 main.py 可以直接 json.loads(arguments)。
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

            # prompt_too_long → 返回错误标记，由 main.py 处理。
            # 这里不直接压缩，是为了让主循环保留对 messages 的统一控制权。
            if is_prompt_too_long_error(e):
                return {"finish_reason": "error", "content": "",
                        "assistant_message": {"role": "assistant", "content": ""},
                        "tool_calls": [], "error": "prompt_too_long"}

            # 不可重试的错误直接跳出；继续重试只会增加延迟和 API 成本。
            if not should_retry(e):
                break

            # 检查熔断器：连续失败过多时停止本轮重试，避免卡住交互。
            if circuit_breaker():
                print(f"\033[31m[熔断] 连续 {_state.consecutive_failures} 次失败，停止重试\033[0m")
                break

            # 检查是否需要升级 max_tokens
            if "max_tokens" in err_msg or "too many tokens" in err_msg:
                upgraded = get_upgraded_max_tokens()
                if upgraded:
                    print(f"\033[33m[恢复] max_tokens 升级: {current_max_tokens} → {upgraded}\033[0m")
                    current_max_tokens = upgraded
                    continue

            # 529 过载处理：服务过载通常是临时现象，先重试；连续出现再启用 fallback。
            if "529" in err_msg:
                from recovery import increment_529
                if increment_529():
                    _state.fallback_model = True
                    print(f"\033[33m[恢复] 切换 fallback model: {FALLBACK_MODELS[-1]}\033[0m")

            # 指数退避等待：让服务端有恢复时间，也避免高频重试放大拥塞。
            delay = retry_delay(attempt)
            print(f"\033[33m[重试 {attempt+1}] {err_msg[:80]}... 等待 {delay:.1f}s\033[0m")
            time.sleep(delay)

    # 所有重试失败后仍返回统一结构，调用方不需要再为异常分支单独适配。
    return {"finish_reason": "error", "content": f"API 调用失败: {last_error}",
            "assistant_message": {"role": "assistant", "content": f"API 调用失败: {last_error}"},
            "tool_calls": [], "error": str(last_error)}
