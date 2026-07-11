"""s19 mcp.py — MCP 插件协议（模拟实现）"""
import json, re

def normalize_mcp_name(name: str) -> str:
    """规范化 MCP 工具名：非 [a-zA-Z0-9_-] 替换为 _。"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

class MCPClient:
    """模拟 MCP 客户端。"""
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.tools: list[dict] = []
    def list_tools(self) -> list[dict]:
        return self.tools
    def call_tool(self, name: str, args: dict) -> str:
        return f"[MCP {self.server_name}/{name}] 模拟执行: {json.dumps(args,ensure_ascii=False)}"

# Mock MCP Server 注册表
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
    if name not in MOCK_SERVERS: return None
    client = MCPClient(name)
    for tool in MOCK_SERVERS[name]["tools"]:
        client.tools.append(tool)
    return client

def assemble_tool_pool(builtin_tools, mcp_clients: dict[str, MCPClient]) -> list[dict]:
    """每轮动态组装工具池：内置工具 + MCP 工具。MCP 工具命名为 mcp__{server}__{tool}。"""
    pool = list(builtin_tools)
    for srv_name, client in mcp_clients.items():
        for tool in client.list_tools():
            safe_name = normalize_mcp_name(f"mcp__{srv_name}__{tool['name']}")
            pool.append({
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": f"[MCP:{srv_name}] {tool.get('description','')}",
                    "parameters": tool.get("parameters", {"type":"object","properties":{}})
                }
            })
    return pool
