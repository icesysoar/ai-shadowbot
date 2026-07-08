# AI 版影刀 · ai-shadowbot

> 自然语言驱动电脑操作的 RPA / Computer-Use 平台。v0.1.1

用户用聊天说"要做什么"，AI 编译为结构化工作流并自动执行。
架构自下而上五层：**观测层 → 执行引擎 → 规划层 → 护栏层 → 交互层**。

## 功能矩阵 (F001-F014)

| ID | 功能 | 状态 |
|----|------|------|
| F001 | 自然语言解析与动作规划 (LLM function calling) | ✅ |
| F002 | 桌面动作执行引擎 (鼠标/键盘/截图) | ✅ |
| F003 | 安全护栏与人工确认机制 | ✅ |
| F004 | CLI / 聊天交互入口 | ✅ |
| F005 | 视觉坐标系统 (多模态 LLM 定位) | ✅ |
| F006 | 工作流引擎 (DAG 编译 + 执行) | ✅ |
| F007 | L5 跨 AI 触发网关 (HTTP+MCP) | ✅ |
| F008 | 可视化画布 (Vue3 + LiteGraph.js) | ✅ |
| F009 | 定时调度器 (cron/interval) | ✅ |
| F010 | 执行日志回溯 (节点级日志+截图) | ✅ |
| F011 | 流程模板市场 (4 种子模板) | ✅ |
| F012 | 画布增强 (拖拽放置/面板/DPR) | ⬜ 计划中 |
| F013 | 工程卫生与治理 | ✅ 已就绪 |
| F014 | 端口统一 + --mode both 修复 | ✅ 已就绪 |

## 安装

```bash
pip install -r requirements.txt
```

`pyautogui` / `Pillow` 仅真实执行模式需要；**dry_run 演示与 pytest 测试无需安装**。

## 配置（环境变量）

|变量|说明|默认|
|-|-|-|
|`LLM\_API\_KEY`|LLM provider key（OpenAI 兼容）|缺失则强制 mock|
|`LLM\_BASE\_URL`|自定义/私有化网关地址|无|
|`LLM\_MODEL`|模型名|`gpt-4o`|
|`LLM\_MOCK`|设为 `1` 强制 mock 规划|无|

> 缺 `LLM\_API\_KEY` 时自动进入 \*\*mock 模式\*\*（内置启发式规划器），
> 可直接跑通演示，无需任何 API key。

## 快速开始（安全演练）

```bash
# 默认 dry\_run：只生成并展示动作序列，绝不真动鼠标
python -m ai\_shadowbot.cli

# 或显式指定
python -m ai\_shadowbot.cli --dry-run --mock --confirm skip
```

聊天示例：

```
👤 你> 打开记事本并输入 hello

📋 计划（2 步）：
  1. ✅ \[open\_app] 打开应用：记事本
  2. ✅ \[type\_text] 输入文本：'hello'

🤖 执行结果：
  \[dry\_run] 将执行 \[open\_app] 打开应用：记事本
  \[dry\_run] 将执行 \[type\_text] 输入文本：'hello'
```

## 真实执行（⚠️ 会真动鼠标）

```bash
python -m ai\_shadowbot.cli --real --confirm single
```

## 启动 Web 画布（推荐）

```bash
# 方式一：一键启动（自动清理端口 + 打开浏览器）
python -m ai_shadowbot.run_server

# 方式二：双击 launcher_gui.py（图形启动器）

# 方式三：命令行
python -m ai_shadowbot.l5_gateway --mode http --port 8792
# 浏览器访问 http://localhost:8792/
```

## 测试

```bash
pytest            # 370+ passed，17 测试文件，覆盖全部核心模块
```

独立安全验证：
```bash
python verify_security_fixes.py   # 34 PASS（注入防护/黑名单/脱敏/急停）
```

## 动作 Schema（原子动作词汇表）

规划层输出的 JSON 动作，护栏层全部覆盖：

|动作|参数|说明|
|-|-|-|
|`click`|`x,y`|左键单击|
|`double\_click`|`x,y`|左键双击|
|`right\_click`|`x,y`|右键单击|
|`type\_text`|`text`|输入文本|
|`key\_press`|`key`|按键/组合键，如 `enter`、`ctrl+c`|
|`screenshot`|—|截图（base64 供 LLM 看）|
|`wait`|`seconds`|等待|
|`open\_app`|`name`|打开应用|
|`scroll`|`dx,dy`|滚动|

## 安全设计（护栏层 F003）

* **白名单**：动作类型只能是原子动作，未授权类型直接拦截。
* **语义化黑名单**：`rm -rf` / `format` / `shutdown` / `dd` / `powershell -e` / `curl|sh` / `reg delete` 等硬拦截，命令归一化+动词集合抗绕过。
* **LLM 语义注入分类器**：提示注入（"忽略指令…"）→ CONFIRM 不自动放行，信道隔离保数据不混指令。
* **三档确认策略**：`skip`（跳过）/ `single`（单步，默认）/ `batch`（批量确认一次）。
* **不可逆动作强提示**：删除/发送/支付等含后果+回滚点。
* **隐私脱敏**：截图外发前敏感区打码（SCREEN_MASK_SENSITIVE 默认开）。
* **全局紧急停止**：ESC / Ctrl+C 触发后队列立即中止。
* **dry_run 铁律**：演练模式绝不 import pyautogui、绝不真实移动鼠标。

## 模块结构

```
ai_shadowbot/
├── __init__.py
├── actions.py              # 原子动作词汇表 + schema 强校验
├── config.py               # 模型配置（环境变量 + mock 开关）
├── planner.py              # 规划层：LLM function calling（F001）
├── executor.py             # 执行引擎：PyAutoGUI + dry_run（F002）
├── observer.py             # 观测层：截图脱敏 + base64（F002）
├── guardrails.py           # 护栏层：白/黑名单 + 语义gate（F003）
├── injection_classifier.py # 提示注入 LLM 语义分类器（R1/M4）
├── cli.py                  # CLI 聊天入口（F004）
├── vision.py               # 视觉坐标系统（F005）
├── workflow.py             # 工作流 DAG 数据结构（F006）
├── compiler.py             # AI 编译器：自然语言→DAG（F006）
├── engine.py               # DAG 执行引擎（F006）
├── variables.py            # 变量系统：{{variables.xxx}} 模板
├── errors.py               # 错误策略处理器
├── l5_gateway.py           # L5 网关：FastAPI + FastMCP（F007）
├── run_server.py            # 启动助手（F007）
├── canvas_api.py           # 画布后端：SQLite CRUD（F008）
├── scheduler.py            # 定时调度器（F009）
├── frontend/               # Vue3 + LiteGraph.js 画布前端（F008）
│   ├── src/
│   │   ├── App.vue         # 主布局
│   │   ├── components/GraphCanvas.vue  # 画布封装
│   │   ├── nodes/specs.ts  # 14 节点规格定义
│   │   └── ...
│   └── dist/               # 构建产物
└── tests/                  # 17 测试文件，370+用例
```

## 画布节点清单（14 种）

| 分类 | 节点 | 类型 |
|------|------|------|
| 控制 | 开始、结束、条件判断、循环 | start/end/condition/loop |
| 系统 | 等待、截图 | wait/atomic |
| 鼠标 | 点击、双击、右键单击、滚动 | atomic |
| 键盘 | 输入文本、按键 | atomic |
| 应用 | 打开应用 | atomic |

