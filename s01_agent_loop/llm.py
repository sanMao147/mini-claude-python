"""
============================================================================
  s01_agent_loop/llm.py — LLM API 调用封装
============================================================================
  封装 OpenAI 兼容接口（DeepSeek 默认），统一处理请求和响应解析。

  核心函数：call_llm(messages, tools, system_prompt) -> dict

  返回格式：
  {
      "finish_reason": "stop" | "tool_calls" | "length",
      "content": "模型文本回复",
      "assistant_message": {完整的 assistant 消息 dict},
      "tool_calls": [{...}]  # 工具调用列表
  }

  更换 LLM 提供方：只需修改 config.py 中的 API_KEY/API_URL/MODEL
============================================================================
"""

import os
from openai import OpenAI

# 从顶级 config.py 导入集中配置
# 注意：s01 目录运行时，sys.path 已包含项目根目录（由 config.py 自动设置）
from config import API_KEY, API_URL, MODEL, MAX_TOKENS, TEMPERATURE

# ---------------------------------------------------------------------------
# 创建 OpenAI 兼容客户端
# base_url 指向 DeepSeek（或其他兼容接口），api_key 传入你的 key
# ---------------------------------------------------------------------------
_client = OpenAI(
    api_key=API_KEY,
    base_url=API_URL,
)


def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
    system_prompt: str = "",
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """
    调用 LLM API，返回统一格式的响应。

    参数：
        messages  : 对话历史 [{"role": "user"/"assistant"/"tool", "content": ...}, ...]
        tools     : 工具定义列表（OpenAI function 格式），None 表示不传工具
        system_prompt : 系统提示词
        max_tokens    : 最大输出 token 数

    返回：
        {
            "finish_reason": str,      # "stop" / "tool_calls" / "length"
            "content": str,            # 模型文本回复内容
            "assistant_message": dict, # 完整 assistant 消息（含 tool_calls）
            "tool_calls": list[dict],  # 工具调用列表 [{"id":..., "function":{...}}]
        }
    """
    # 构建完整消息列表：system 消息放在最前面
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    # 调用 API
    response = _client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        tools=tools,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
    )

    # 解析响应
    choice = response.choices[0]
    msg = choice.message

    # 提取文本内容
    content = msg.content if msg.content else ""

    # 提取工具调用（转换为 dict 格式，方便后续处理）
    raw_tool_calls = msg.tool_calls or []
    tool_calls = []
    for tc in raw_tool_calls:
        tool_calls.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,  # JSON 字符串
            },
        })

    # 构建 assistant 消息（存入对话历史）
    assistant_message = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls:
        assistant_message["tool_calls"] = tool_calls

    return {
        "finish_reason": choice.finish_reason,  # "stop" / "tool_calls" / "length"
        "content": content,
        "assistant_message": assistant_message,
        "tool_calls": tool_calls,
    }
