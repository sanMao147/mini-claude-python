"""
============================================================================
  s02_tool_use/llm.py — LLM API 调用封装
============================================================================
  与 s01 完全相同的实现。详见 s01_agent_loop/llm.py 的注释。
  封装 OpenAI 兼容接口（DeepSeek 默认），统一处理请求和响应解析。
============================================================================
"""

from openai import OpenAI
from config import API_KEY, API_URL, MODEL, MAX_TOKENS, TEMPERATURE

_client = OpenAI(api_key=API_KEY, base_url=API_URL)


def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
    system_prompt: str = "",
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """调用 LLM API，返回统一格式的响应。"""
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    response = _client.chat.completions.create(
        model=MODEL, messages=full_messages, tools=tools,
        max_tokens=max_tokens, temperature=TEMPERATURE,
    )

    choice = response.choices[0]
    msg = choice.message

    content = msg.content if msg.content else ""
    raw_tool_calls = msg.tool_calls or []
    tool_calls = []
    for tc in raw_tool_calls:
        tool_calls.append({
            "id": tc.id, "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        })

    assistant_message = {"role": "assistant", "content": content}
    if tool_calls:
        assistant_message["tool_calls"] = tool_calls

    return {
        "finish_reason": choice.finish_reason,
        "content": content,
        "assistant_message": assistant_message,
        "tool_calls": tool_calls,
    }
