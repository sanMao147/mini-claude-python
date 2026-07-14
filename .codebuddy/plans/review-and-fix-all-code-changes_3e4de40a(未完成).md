---
name: review-and-fix-all-code-changes
overview: 审查整个项目的 105 个已修改文件，修复发现的 bug、错误的 docstring、无用代码和未使用 import，并进一步精简冗余代码。
todos:
  - id: fix-duplicate-line
    content: 修复 s20_comprehensive/main.py 第 98-99 行重复的 `text = response["content"]` 行
    status: pending
  - id: fix-main-docstrings
    content: 修复 s16-s20 的 main.py 错误 docstring（都误写为 s14），改为正确的步骤标识
    status: pending
  - id: fix-protocols-docstrings
    content: 修复 s17-s20 的 protocols.py 错误 docstring（都误写为 s16），改为正确的步骤标识
    status: pending
  - id: remove-dead-code
    content: 删除 config.py 中未使用的 `_config_loaded` 标志，并清理所有子模块文件中未使用的 `sys` import（约 70+ 文件）
    status: pending
  - id: verify
    content: 运行 git diff 确认所有修复正确，检查无遗漏问题
    status: pending
    dependencies:
      - fix-duplicate-line
      - fix-main-docstrings
      - fix-protocols-docstrings
      - remove-dead-code
---

## 用户需求

审查项目中所有 105 个已修改文件的代码变更，修复发现的问题并进行代码精简。

## 产品概述

本次操作是纯代码审查和修复任务，不涉及新功能开发。目标是确保所有代码变更的质量和一致性，消除 bug、错误文档、无用代码和未使用的 import。

## 核心修复项

### Bug 修复

1. **s20_comprehensive/main.py 第 98-99 行**：`text = response["content"]` 重复出现两次，删除一行

### 错误 Docstring 修复（复制粘贴遗留问题）

2. **s16-s20 的 main.py**：文件头部 docstring 都误写为 `"""s14 main.py — Cron 定时调度"""`，需修正为各自对应的步骤标识（s16/s17/s18/s19/s20）
3. **s17-s20 的 protocols.py**：文件头部 docstring 都误写为 `"""s16 protocols.py — 团队结构化协议"""`，需修正为各自对应的步骤标识（s17/s18/s19/s20）

### 无用代码删除

4. **config.py 第 43 行**：`_config_loaded = True` 定义了但项目中没有任何地方引用，应删除
5. **所有子模块文件中未使用的 `sys` import**（约 70+ 个文件）：这些文件原本通过 `sys.path.insert(...)` 使用 `sys`，在变更中移除了该行后 `sys` 不再被使用，但 import 语句残留，需清理。涉及文件涵盖 `s06_subagent/subagent.py` 到 `s20_comprehensive` 之间所有步骤目录下的 `subagent.py`、`skills.py`、`compact.py`、`memory.py`、`prompt.py`、`tasks.py`、`cron.py`、`teams.py`、`background.py` 等子模块

## 技术栈

- 语言：Python 3
- 操作：纯文本代码审查和修复，无框架依赖

## 实现方案

### 修复策略

按问题类型分 4 个独立步骤进行修复，每步聚焦一类问题：

1. **Bug 修复**：删除 s20_comprehensive/main.py 中的重复行
2. **Docstring 修复**：批量修正 s16-s20 的 main.py 和 s17-s20 的 protocols.py 中的错误 docstring
3. **无用代码删除**：删除 config.py 中的 `_config_loaded`，以及所有子模块文件中的未使用 `sys` import
4. **验证**：通过 git diff 检查所有修复是否正确，确保无遗漏

### 技术决策要点

- 保持 main.py 中的 `_PROJECT_ROOT` + `sys.path.insert` 模式不变（这是必要的，因为 main.py 作为入口脚本需要先将项目根目录加入 sys.path 才能 import config）
- 仅清理子模块文件中不再需要的 `sys` import，不影响功能
- docstring 修正使用精确的字符串替换，避免误改代码逻辑

### 实现注意事项

- **作用域控制**：所有修改仅涉及已变更的行，不触碰未变更代码，风险可控
- **性能影响**：无性能影响，纯代码清理
- **向后兼容**：所有修复不改变任何运行时行为