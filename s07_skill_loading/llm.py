"""s07 llm.py — LLM API 调用封装"""

from openai import OpenAI

from config import API_KEY, API_URL, MODEL, MAX_TOKENS, TEMPERATURE

_client = OpenAI(api_key=API_KEY, base_url=API_URL)

def call_llm(messages, tools=None, system_prompt="", max_tokens=MAX_TOKENS):
    full_messages = []
    if system_prompt: full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)
    response = _client.chat.completions.create(
        model=MODEL, messages=full_messages, tools=tools, max_tokens=max_tokens, temperature=TEMPERATURE)
    choice = response.choices[0]; msg = choice.message
    content = msg.content if msg.content else ""
    tool_calls = [{"id": tc.id, "type": "function",
                   "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                  for tc in (msg.tool_calls or [])]
    assistant_message = {"role": "assistant", "content": content}
    if tool_calls: assistant_message["tool_calls"] = tool_calls
    return {"finish_reason": choice.finish_reason, "content": content,
            "assistant_message": assistant_message, "tool_calls": tool_calls}