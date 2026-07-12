"""s19 mcp.py — MCP 插件协议（模拟实现）"""
import json, re

# 这是一个“模拟 MCP”实现，用来演示如何把外部工具服务器接入 Agent 工具池。
# 真正的 MCP 传输层没有在这里实现；本文件只负责名称规范化、mock client 和工具 schema 拼装。

def normalize_mcp_name(name: str) -> str:
    """规范化 MCP 工具名：非 [a-zA-Z0-9_-] 替换为 _。"""
    # LLM function name 只能使用安全字符；server/tool 名里出现的其它符号统一替换。
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

class MCPClient:
    """模拟 MCP 客户端。"""
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.tools: list[dict] = []
    def list_tools(self) -> list[dict]:
        """返回当前 mock server 暴露的工具 schema 列表。"""
        return self.tools
    def call_tool(self, name: str, args: dict) -> str:
        """模拟工具调用结果；真实实现中这里会通过 MCP 协议请求外部 server。"""
        return f"[MCP {self.server_name}/{name}] 模拟执行: {json.dumps(args,ensure_ascii=False)}"

# Mock MCP Server 注册表。
# 每个 server 下的 tools 字段格式尽量贴近 OpenAI function schema，方便 assemble_tool_pool 复用。
MOCK_SERVERS = {
    "filesystem": {
        "tools": [
            {"name":"list_directory","description":"(readOnly) List files in a directory","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
            {"name":"search_files","description":"(readOnly) Search files by pattern","parameters":{"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]}},
        ]
    },
    "web_search": {
        "tools": [
            {"name":"web_search","description":"(readOnly) Search the web","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}},
        ]
    }
}

def connect_mcp(name: str) -> MCPClient | None:
    """连接 MCP Mock Server。返回 MCPClient 或 None。"""
    # 未注册 server 返回 None，调用方可以据此决定是否向用户报错。
    if name not in MOCK_SERVERS: return None
    client = MCPClient(name)
    for tool in MOCK_SERVERS[name]["tools"]:
        client.tools.append(tool)
    return client

def assemble_tool_pool(builtin_tools, mcp_clients: dict[str, MCPClient]) -> list[dict]:
    """每轮动态组装工具池：内置工具 + MCP 工具。MCP 工具命名为 mcp__{server}__{tool}。"""
    # 复制内置工具，避免把 MCP 工具追加回原始 builtin_tools 造成重复污染。
    pool = list(builtin_tools)
    for srv_name, client in mcp_clients.items():
        for tool in client.list_tools():
            safe_name = normalize_mcp_name(f"mcp__{srv_name}__{tool['name']}")
            # 给 MCP 工具名前缀，既能避免和内置工具重名，也便于调用时反查 server。
            pool.append({
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": f"[MCP:{srv_name}] {tool.get('description','')}",
                    "parameters": tool.get("parameters", {"type":"object","properties":{}})
                }
            })
    return pool
