# AI 版影刀 · ai-shadowbot

自然语言驱动电脑操作的 Python 工具（MVP）。

用户用聊天说"要做什么"，AI 把指令编译为鼠标/键盘/截图/应用动作并自动执行。
架构自下而上五层：**观测层 → 执行引擎 → 规划层 → 护栏层 → 交互层**。

## 安装

```bash
pip install -r requirements.txt
```

`pyautogui` / `Pillow` 仅真实执行模式需要；**dry\_run 演示与 pytest 测试无需安装**。

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

## 测试

```bash
pytest            # 40 个用例，覆盖 planner/guardrails/executor(dry\_run)
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

* **白名单**：动作类型只能是上述原子动作，未授权类型直接拦截。
* **破坏性黑名单**：`rm -rf` / `format` / `shutdown` / `sudo` / `dd` 等硬拦截，永不放行。
* **危险动作二次确认**：终端/系统设置类（`cmd`/`powershell`/`注册表`…）需人工确认。
* **三档确认策略**：`skip`（跳过）/ `single`（单步）/ `batch`（批量确认一次）。
* **全局紧急停止**：ESC / Ctrl+C 触发后队列立即中止。
* **dry\_run 铁律**：演练模式绝不 import pyautogui、绝不真实移动鼠标。

## 模块结构

```
ai\_shadowbot/
├── \_\_init\_\_.py
├── actions.py      # 原子动作词汇表 + schema 强校验（共享事实来源）
├── config.py       # 模型配置（环境变量 + mock 开关）
├── planner.py      # 规划层：LLM function calling（F001）
├── executor.py     # 执行引擎：PyAutoGUI + dry\_run（F002）
├── observer.py     # 观测层：截图 → base64（F002）
├── guardrails.py   # 护栏层：白/黑名单 + 二次确认（F003）
├── cli.py          # CLI 聊天入口（F004）
└── tests/          # test\_planner / test\_guardrails / test\_executor\_dryrun
```

