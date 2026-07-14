---
name: review-and-fix-all-code-changes
overview: 审查整个项目的 105 个已修改文件，修复 bug、错误 docstring、无用代码、未使用 import，清理多余注释，同时精简冗余代码。
todos:
  - id: fix-duplicate-and-comments
    content: 修复 s20_comprehensive/main.py 重复行，清理 s01 过时注释，精简 s15-s20 main.py 中误导性的 s14/s11 步骤前缀注释和行尾冗余注释
    status: completed
  - id: fix-all-docstrings
    content: 修正 s16-s20 的 main.py 和 protocols.py 错误 docstring，以及 main() 函数中打印的步骤名称（s14 改为正确的 s16/s17/s18/s19/s20）
    status: completed
  - id: remove-dead-code
    content: 删除 config.py 中未使用的 _config_loaded 行，清理所有子模块文件（s06-s20）中因移除 sys.path.insert 而不再使用的 sys import
    status: completed
  - id: verify-all
    content: 运行 git diff --stat 验证所有修改正确，确认无遗漏
    status: completed
    dependencies:
      - fix-duplicate-and-comments
      - fix-all-docstrings
      - remove-dead-code
---

## 用户需求

审查项目中所有 105 个已修改文件的代码变更，修复发现的问题并进行代码精简。多余注释也清除，但不要影响代码阅读。

## 产品概述

纯代码审查和修复任务，不涉及新功能开发。消除 bug、错误 docstring、无用代码、未使用的 import 和多余注释。

## 核心修复项

### Bug 修复

1. s20_comprehensive/main.py 第 98-99 行：`text = response["content"]` 重复两行，删除一行

### 错误 Docstring 修复

2. s16-s20 的 main.py 文件头 docstring 都误写为 `"""s14 main.py — Cron 定时调度"""`，修正为各自步骤标识
3. s17-s20 的 protocols.py 文件头 docstring 都误写为 `"""s16 protocols.py — 团队结构化协议"""`，修正为各自步骤标识
4. s16-s20 的 main() 函数中 `print("  s14: Cron Scheduler...")` 打印文本也需同步修正

### 无用代码删除

5. config.py 第 43 行：`_config_loaded = True` 未在任何地方引用，删除
6. 所有子模块文件中未使用的 `sys` import（约 70+ 个文件）：s06-s20 目录下 subagent.py、skills.py、compact.py、memory.py、prompt.py、tasks.py、cron.py、teams.py、background.py 等

### 多余注释清除

7. s01_agent_loop/main.py:32 — `# 确保可以导入 config.py（项目根目录已在 config.py 中自动加入 sys.path）` 已过时
8. s15-s20 main.py agent_loop 中 `# s14: cron queue 消费 + background results 收集` 标注 s14 但文件在 s15+，删除错误的步骤前缀
9. s15-s20 main.py 中 `start_cron_scheduler()  # s14: 启动 cron 调度器` 行尾注释冗余

## 技术栈

- 语言：Python 3
- 操作：纯文本代码审查和修复，无框架依赖

## 实现方案

### 修复策略

分 4 步执行，每步聚焦一类问题：

1. **Bug + 注释清理**：删除 s20 重复行，清理 s01 过时注释和 s15-s20 冗余注释
2. **Docstring 修正**：修正 s16-s20 main.py/protocols.py 的错误 docstring 及 main() 中打印文本
3. **无用代码删除**：删除 config.py `_config_loaded` 行，以及所有子模块文件中的未使用 `sys` import
4. **验证**：运行 `git diff --stat` 确认所有修复正确

### 技术决策

- 保持 main.py 中 `_PROJECT_ROOT` + `sys.path.insert` 模式不变（入口脚本必要，config.py 的注入只在自身被 import 后才生效）
- 仅清理子模块中不再需要的 `sys` import，不影响功能
- 保留有助代码可读性的注释（如 `# ── 步骤 1: 调用 LLM ──`、`# 不可恢复的错误` 等），只清除过时/冗余/误导性注释

### 需修改的文件范围

- config.py（1 行删除）
- s01_agent_loop/main.py（1 行注释删除）
- s16-s20 各 main.py（docstring + 打印文本 + 注释修正）
- s17-s20 各 protocols.py（docstring 修正）
- s06-s20 各目录下约 70+ 个子模块 .py 文件（移除未使用的 sys import）