# mini-claude-python

从零构建一个 Python Agent 系统 — 通过 20 个递进步骤，逐步理解 LLM Agent 的核心机制。

## 快速开始

```bash
# 1. 克隆项目
git clone git@github.com:sanMao147/mini-claude-python.git
cd mini-claude-python

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API
#    复制 .env.example 为 .env，并填入你的 DeepSeek（或其他兼容 OpenAI 接口的）API Key
#    API_KEY=sk-your-deepseek-api-key-here

# 4. 运行某个步骤（以 s01 为例）
python s01_agent_loop/main.py
```

## 更换 LLM 提供方

只需修改项目根目录 `.env` 中的三个变量：

```bash
# DeepSeek（默认）
API_KEY=sk-your-deepseek-key
API_URL=https://api.deepseek.com/v1
MODEL=deepseek-chat

# 切换到 OpenAI
# API_URL=https://api.openai.com/v1
# MODEL=gpt-4o

# 切换到通义千问
# API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# MODEL=qwen-plus
```

## 学习路线图 (s01 → s20)

### 🚀 阶段一：让 Agent 行动起来 (s01-s04)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s01** | `s01_agent_loop/` | Agent 循环 | `main.py`, `tools.py`, `llm.py` | 一个 while 循环 + 一个 bash 工具就是最小 Agent |
| **s02** | `s02_tool_use/` | 工具分发 | `main.py`, `tools.py`, `llm.py` | 5 个工具 (bash/read/write/edit/glob) + TOOL_HANDLERS 查表分发 |
| **s03** | `s03_permission/` | 权限管控 | + `permission.py` | 三道闸门：拒绝列表 → 规则匹配 → 人工审批 |
| **s04** | `s04_hooks/` | Hook 系统 | + `hooks.py` | 事件驱动的拦截机制，权限逻辑迁移到 PreToolUse hook |

### 🔧 阶段二：处理复杂工作 (s05-s08)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s05** | `s05_todo_write/` | TodoWrite 计划 | + `todos.py` | 先计划再行动，3 轮不更新自动提醒 |
| **s06** | `s06_subagent/` | 子代理 | + `subagent.py` | 大任务拆小，每个子 Agent 拥有干净的独立上下文 |
| **s07** | `s07_skill_loading/` | Skill 技能加载 | + `skills.py` | 两级知识加载：启动扫描 + 按需注入 |
| **s08** | `s08_context_compact/` | 上下文压缩 | + `compact.py` | 四层压缩管线 (budget→snip→micro→auto) 防止上下文溢出 |

### 🧠 阶段三：记忆与恢复 (s09-s11)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s09** | `s09_memory/` | Memory 记忆系统 | + `memory.py` | 持久化 Markdown 记忆 + LLM 智能选相关记忆 |
| **s10** | `s10_system_prompt/` | System Prompt | + `prompt.py` | 运行时按需组装 prompt 片段，不再硬编码 |
| **s11** | `s11_error_recovery/` | 错误恢复 | + `recovery.py` | 指数退避重试 + max_tokens 升级 + 熔断器 |

### ⏳ 阶段四：长时间运行 (s12-s14)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s12** | `s12_task_system/` | Task 任务系统 | + `tasks.py` | DAG 依赖图 + JSON 持久化任务管理 |
| **s13** | `s13_background_tasks/` | 后台任务 | + `background.py` | 慢操作放 daemon 线程，Agent 继续思考 |
| **s14** | `s14_cron_scheduler/` | Cron 调度 | + `cron.py` | 定时触发任务，空闲时递交给 Agent |

### 🤝 阶段五：多 Agent 协作 (s15-s18)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s15** | `s15_agent_teams/` | Agent 团队 | + `teams.py` | MessageBus 收件箱 + daemon 线程队友 |
| **s16** | `s16_team_protocols/` | 团队协议 | + `protocols.py` | 结构化请求-响应，shutdown 和 plan_approval 两种协议 |
| **s17** | `s17_autonomous_agents/` | 自主 Agent | 更新 `teams.py` | WORK→IDLE→SHUTDOWN 生命周期 + 自主扫描任务板 |
| **s18** | `s18_worktree_isolation/` | Worktree 隔离 | + `worktree.py` | Git worktree 为每个队友创建独立工作目录 |

### 🔌 阶段六：扩展与整合 (s19-s20)

| 步骤 | 目录 | 核心概念 | 文件 | 一句话总结 |
|------|------|---------|------|-----------|
| **s19** | `s19_mcp_plugin/` | MCP 插件 | + `mcp.py` | 通过 MCP 协议接入外部工具，动态工具池 |
| **s20** | `s20_comprehensive/` | 综合 Agent | 18 个模块 | 前 19 章全部机制整合到一个完整 Harness |

---

## 项目结构

```
mini-claude-python/
├── config.py              # 🔧 集中配置（修改此文件切换 API）
├── requirements.txt       # 📦 依赖声明
├── .gitignore
├── s01_agent_loop/        # 🚀 最小 Agent 循环
│   ├── main.py            #    入口 + agent_loop() 主循环
│   ├── tools.py           #    工具定义 + 处理函数
│   └── llm.py             #    LLM API 调用封装
├── s02_tool_use/          # 🔧 5 工具 + 查表分发
├── ...
└── s20_comprehensive/     # 🏗️ 完整 Agent 系统
    └── (18 个模块文件)
```

## 核心设计原则

1. **模块化** — 一个文件只做一件事，通过 import 关联
2. **渐进式** — 每步只新增一个机制，不重写已有代码
3. **独立运行** — 每个步骤可独立执行：`python sXX_xxx/main.py`
4. **注释驱动** — 所有代码附带详细中文注释，适合学习
5. **API 无关** — 通过 `.env` 一键切换 LLM 提供方

## 运行方式

每个步骤都是一个独立的 Agent 程序：

```bash
# 进入项目目录
cd mini-claude-python

# 运行任意步骤
python s01_agent_loop/main.py
python s05_todo_write/main.py
python s20_comprehensive/main.py
```

运行后进入交互模式，输入你的需求，Agent 将使用工具来完成任务。输入 `exit` 或 `quit` 退出。
