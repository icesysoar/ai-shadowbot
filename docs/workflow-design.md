# AI 工作流引擎 Phase 1 架构细化设计

> 版本：v1.0 | 日期：2026-07-07 | 作者：云见微（Soara 七曜工程团 · 共识分析师）
> 状态：设计稿 · 待鲁千机实现审查
> 关联 F006（project-spec.json: status=planned, depends_on=[F001,F002,F004,F005]）

---

## 目录

1. [工作流 DAG 数据结构](#1-工作流-dag-数据结构)
2. [AI 工作流编译器接口](#2-ai-工作流编译器接口)
3. [执行引擎设计](#3-执行引擎设计)
4. [变量系统规则](#4-变量系统规则)
5. [错误策略处理](#5-错误策略处理)
6. [安全集成](#6-安全集成)
7. [CLI 入口设计](#7-cli-入口设计)
8. [与现有系统的集成清单](#8-与现有系统的集成清单)

---

## 1. 工作流 DAG 数据结构

### 1.1 完整 JSON Schema

```json
{
  "definitions": {
    "NodeType": {
      "type": "string",
      "enum": ["atomic", "condition", "loop", "wait", "start", "end"]
    },
    "ErrorStrategyType": {
      "type": "string",
      "enum": ["retry", "skip", "abort", "degrade"]
    },
    "TriggerType": {
      "type": "string",
      "enum": ["cron", "hotkey", "manual"]
    },
    "VariableScope": {
      "type": "string",
      "enum": ["global", "local"]
    },
    "VariableType": {
      "type": "string",
      "enum": ["str", "int", "bool", "list", "dict"]
    }
  },
  "type": "object",
  "required": ["id", "name", "nodes"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^wf_[a-z0-9]{8}$",
      "description": "工作流唯一标识，格式 wf_xxxxxxxx"
    },
    "name": {
      "type": "string",
      "maxLength": 128,
      "description": "工作流名称"
    },
    "description": {
      "type": "string",
      "maxLength": 1024,
      "description": "工作流描述（由编译器生成）"
    },
    "version": {
      "type": "string",
      "default": "1.0"
    },

    "triggers": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/Trigger"
      },
      "description": "触发器列表（Phase 1 支持 manual，cron/hotkey 为 schema 预留）"
    },

    "variables": {
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
          "$ref": "#/definitions/Variable"
        }
      },
      "description": "变量声明，键为变量名"
    },

    "nodes": {
      "type": "array",
      "minItems": 2,
      "items": {
        "$ref": "#/definitions/Node"
      },
      "description": "节点列表（有序，各节点通过 next/branches/children 构成 DAG）"
    },

    "error_strategy": {
      "$ref": "#/definitions/ErrorStrategy",
      "description": "工作级默认错误策略（节点可覆盖）"
    },

    "metadata": {
      "type": "object",
      "properties": {
        "created_at": {"type": "string", "format": "date-time"},
        "compiled_from": {"type": "string", "description": "此工作流由哪句自然语言编译而来"},
        "total_steps": {"type": "integer", "description": "预估原子动作步数"}
      }
    }
  },

  "definitions": {
    "Node": {
      "type": "object",
      "required": ["id", "type"],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^n[0-9]+$",
          "description": "节点 ID，如 n1, n2"
        },
        "type": {"$ref": "#/definitions/NodeType"},
        "params": {
          "type": "object",
          "description": "节点参数（依 type 而异，见下方各 type 的 params 定义）"
        },

        "next": {
          "type": "string",
          "pattern": "^n[0-9]+$",
          "description": "单链接后继节点 ID（atomic/wait 类型使用）"
        },

        "branches": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["condition", "next"],
            "properties": {
              "condition": {
                "type": "string",
                "description": "条件表达式（如 '{{variables.status}} == \"success\"'）"
              },
              "next": {
                "type": "string",
                "pattern": "^n[0-9]+$",
                "description": "满足条件时的分支目标"
              },
              "label": {
                "type": "string",
                "description": "分支标签（如 '新邮件时'），仅用于展示"
              }
            }
          },
          "description": "条件分支列表（condition 类型使用，至少 2 条）"
        },

        "children": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^n[0-9]+$"
          },
          "description": "循环体子节点 ID 列表（loop 类型使用）"
        },

        "continue_on": {
          "type": "string",
          "pattern": "^n[0-9]+$",
          "description": "循环结束后的后继节点（loop 类型使用）"
        },

        "vision_query": {
          "type": "string",
          "description": "可选，视觉定位目标文本（供 F005 grounding，仅 atomic 类型用）"
        },

        "error_strategy": {
          "$ref": "#/definitions/ErrorStrategy",
          "description": "节点级错误策略（覆盖工作流级默认）"
        },

        "output_variable": {
          "type": "string",
          "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$",
          "description": "本节点输出写入的变量名（自动在 variables 中声明）"
        },

        "label": {
          "type": "string",
          "maxLength": 64,
          "description": "节点标签（仅用于展示与日志）"
        }
      }
    },

    "Trigger": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {"$ref": "#/definitions/TriggerType"},
        "config": {
          "type": "object",
          "description": "触发器配置",
          "properties": {
            "cron": {
              "type": "string",
              "description": "cron 表达式（type=cron 时必填），如 '0 9 * * 1-5'"
            },
            "timezone": {
              "type": "string",
              "default": "Asia/Shanghai"
            },
            "hotkey": {
              "type": "string",
              "description": "热键组合（type=hotkey 时必填），如 'ctrl+alt+e'"
            }
          }
        }
      }
    },

    "Variable": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {"$ref": "#/definitions/VariableType"},
        "scope": {
          "$ref": "#/definitions/VariableScope",
          "default": "global"
        },
        "default": {
          "description": "默认值（须与 type 一致）"
        },
        "description": {
          "type": "string",
          "description": "变量说明"
        },
        "source": {
          "type": "string",
          "description": "来源节点 ID，如 'n3.output'，表示本变量由节点 n3 的输出填充"
        }
      }
    },

    "ErrorStrategy": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {"$ref": "#/definitions/ErrorStrategyType"},
        "max_retries": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10,
          "default": 3,
          "description": "最大重试次数（type=retry 时有效）"
        },
        "retry_interval": {
          "type": "number",
          "minimum": 0.5,
          "maximum": 300,
          "default": 2.0,
          "description": "重试间隔（秒，type=retry 时有效）"
        },
        "retry_backoff": {
          "type": "number",
          "minimum": 1.0,
          "maximum": 5.0,
          "default": 1.0,
          "description": "退避因子（默认 1.0 = 固定间隔；2.0 = 指数退避）"
        }
      }
    }
  }
}
```

### 1.2 各 Node type 的 params 定义

#### atomic
对应于 F001/F002 的 9 种原子动作类型。
```json
{
  "atomic_action": {
    "type": "string",
    "enum": ["click", "double_click", "right_click", "type_text", "key_press",
             "screenshot", "wait", "open_app", "scroll"]
  },
  "params": {
    "description": "原子动作参数，与 actions.py 的 ACTION_TYPES 定义完全一致"
  }
}
```

#### condition
```json
{
  "expression": {"type": "string", "description": "条件表达式，如 '{{variables.count}} > 5'"},
  "branches": {"type": "array", "description": "通过 Node.branches 定义"}
}
```

#### loop
```json
{
  "loop_type": {"type": "string", "enum": ["while", "for", "for_each"]},
  "condition": {"type": "string", "description": "while 循环条件"},
  "iterable": {"type": "string", "description": "for_each 的迭代变量引用，如 '{{variables.items}}'"},
  "item_var": {"type": "string", "description": "for_each 的迭代元素变量名", "default": "item"},
  "max_iterations": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100,
                     "description": "循环上限防护（Ken Thompson：必须硬限制）"}
}
```

#### wait
```json
{
  "seconds": {"type": "number", "minimum": 0.1, "maximum": 3600}
}
```

#### start / end
```json
{}
```

### 1.3 完整工作流实例

见 `docs/gap-analysis-vision-v1.md §3.3` 的「每日邮件对账」示例，与本 schema 完全对齐。

### 1.4 DAG 正确性约束（引擎在 compile/load 时校验）

| # | 约束 | 违反后果 |
|---|------|---------|
| 1 | 必须有且仅有一个 start 节点 | 校验失败，拒绝加载 |
| 2 | 必须有且仅有一个 end 节点（或所有支路最终汇到 end） | 校验失败，拒绝加载 |
| 3 | 所有节点 ID 在 nodes[] 内唯一 | 校验失败 |
| 4 | 所有 next/branches.next/branches[].next/children 引用的节点 ID 必须存在 | 校验失败 |
| 5 | 不能存在环路（除 loop 节点自身外，DAG 无环） | 校验失败 |
| 6 | condition 节点必须至少 2 条 branch | 编译时约束 |
| 7 | loop 节点必须至少 1 个 children | 编译时约束 |
| 8 | loop.max_iterations <= 1000（硬上限防止死循环） | 校验失败 |
| 9 | 变量引用 `{{variables.xxx}}` 必须在 variables 中有声明 | 校验警告（引用未声明变量标记为潜在错误） |

---

## 2. AI 工作流编译器接口

### 2.1 编译器接口定义

```python
# ——— 仅接口设计，不写业务代码 ———

@dataclass
class CompileResult:
    success: bool
    workflow: Optional[Workflow] = None  # 工作流 DAG
    reason: str = ""                      # 失败原因 / 编译说明
    raw: Optional[Dict[str, Any]] = None  # LLM 原始响应（debug）

class WorkflowCompiler:
    """自然语言 → 工作流 DAG 编译器。

    基于 planner 扩展：复用 OpenAIClient/MockLLMClient，
    注册新的 tool_choice 返回工作流 DAG 而非线性动作序列。
    """

    def __init__(self, config: Config, llm_client: Optional[Any] = None):
        ...

    def compile(self, natural_language_query: str,
                context: Optional[Dict[str, Any]] = None) -> CompileResult:
        """编译自然语言需求为 Workflow DAG。

        Args:
            natural_language_query: 用户自然语言需求，如『每天9点查邮件整理Excel』
            context: 可选上下文，如已有截图 base64、之前的工作流 id 等

        Returns:
            CompileResult: 编译结果（成功/失败 + Workflow）
        """
        ...
```

### 2.2 编译策略: 基于现有 planner 扩展

编译器**不是**从零写新 LLM 调用逻辑，而是在 `Planner` 上叠加一个编译层：

| 层次 | 职责 | 复用对象 |
|------|------|---------|
| 编译层（新） | 自然语言 → DAG 节点图 | `WorkflowCompiler.compile()` |
| 规划层（已有） | DAG 中的 atomic node → 动作序列 | `Planner.plan()` |
| 视觉层（已有） | 缺坐标 → 视觉定位补全 | `Planner.ground_to_action()` + `VisionLocator` |

#### 2.2.1 tool_choice 策略

编译器注册一个专门的 `compile_workflow` function（而非 9 个原子动作）：

```json
{
  "type": "function",
  "function": {
    "name": "compile_workflow",
    "description": "将自然语言需求编译为结构化工作流 DAG（节点图）",
    "parameters": {
      "type": "object",
      "properties": {
        "name": {"type": "string", "description": "工作流名称"},
        "description": {"type": "string", "description": "工作流简短描述"},
        "nodes": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "id": {"type": "string"},
              "type": {"$ref": "NodeType"},
              "label": {"type": "string"},
              "params": {"type": "object"},
              "next": {"type": "string"},
              "branches": {"type": "array"},
              "children": {"type": "array"},
              "vision_query": {"type": "string"},
              "output_variable": {"type": "string"},
              "error_strategy": {"type": "object"}
            },
            "required": ["id", "type", "params"]
          }
        },
        "triggers": {"type": "array"},
        "variables": {"type": "object"},
        "error_strategy": {"type": "object"}
      },
      "required": ["name", "nodes"]
    }
  }
}
```

#### 2.2.2 Mock 编译器

`MockWorkflowCompiler` 内置启发式（无需 LLM），驱动 dry_run 演示：

```python
class MockWorkflowCompiler:
    """Mock 编译器（无需真实 LLM），内置预置模式匹配返回工作流 DAG。"""
    ...
```

### 2.3 编译器输出示例

输入: "每天早上9点，打开Outlook，如果有新邮件就截图，然后整理到Excel"

编译输出（简化 JSON，实际按 §1 schema 完整序列化）：

```
nodes:
  n1 [start]
  n2 [open_app] "Outlook" → n3
  n3 [wait] 5秒 → n4
  n4 [condition] {{variables.has_new_email}}
    ├─ then → n5
    └─ else → n7
  n5 [screenshot] → n6
  n6 [type_text] 写入Excel → n7
  n7 [end]

variables:
  has_new_email (bool, default=false)

triggers:
  - cron: "0 9 * * 1-5"
```

### 2.4 安全约束（编译时）

| # | 约束 | 处理方 |
|---|------|--------|
| 1 | 每个 atomic node 的 params 在编译后过 `actions.validate_action()` | Compiler |
| 2 | 编译结果中的每个 atomic action 最终仍过 `guardrails.check()` | Executor |
| 3 | visual_query 字段过 `InjectionClassifier`（AC4 信道隔离） | Compiler |
| 4 | 禁止直接生成 `shell_command` / `file_delete` 等未注册动作类型 | Compiler |
| 5 | loop.max_iterations 超过 1000 → 编译器重试或拒绝 | Compiler |

---

## 3. 执行引擎设计

### 3.1 引擎接口

```python
@dataclass
class NodeExecResult:
    node_id: str
    node_type: str
    status: str          # PENDING|RUNNING|SUCCESS|FAILED|SKIPPED|ABORTED|DEGRADED
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    action_result: Optional[ExecResult] = None  # atomic 节点的 F002 执行结果
    variables_snapshot: Optional[Dict[str, Any]] = None  # 节点执行后的变量快照

@dataclass
class ExecutionResult:
    success: bool
    node_logs: List[NodeExecResult]
    final_state: str           # SUCCESS|FAILED|ABORTED|DEGRADED
    final_variables: Dict[str, Any]
    started_at: float
    finished_at: float
    total_duration: float

class Engine:
    """工作流执行引擎——解释执行 DAG 节点图。"""

    def __init__(self,
                 executor: Executor,         # 复用 F002 executor
                 guardrails: Guardrails,     # 复用 F003 guardrails
                 dry_run: bool = True,       # 铁律：默认 dry_run
                 emergency_stop: Optional[EmergencyStop] = None):
        ...

    def execute(self, workflow: Workflow) -> ExecutionResult:
        """执行完整工作流。

        1. 校验 DAG 正确性（§1.4 约束）
        2. 初始化变量系统
        3. 从 start 节点开始遍历 DAG
        4. 对每个节点分配状态、执行、记录日志
        5. 返回完整执行结果
        """
        ...

    def dry_run(self, workflow: Workflow) -> ExecutionResult:
        """dry_run 模式执行。

        与 execute() 走完全相同状态机逻辑，区别：
        - atomic 节点调用 Executor.execute(dry_run=True)
        - 不真实截图、不调用视觉模型、不真实点击
        """
        ...
```

### 3.2 执行状态机

```
                    ┌─────────────────┐
                    │    PENDING      │  ← 初始状态
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    RUNNING      │  ← 正在执行
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │ SUCCESS  │  │ FAILED   │  │ SKIPPED  │
       └──────────┘  └──────────┘  └──────────┘
                                       (skip 策略)
              │
              ▼
       ┌──────────┐  ┌──────────┐
       │ ABORTED  │  │ DEGRADED │
       └──────────┘  └──────────┘
       (abort 策略)   (degrade 策略)
```

- **PENDING**: 节点尚未开始执行
- **RUNNING**: 节点正在执行（atomic → executor.execute, condition → 判断, loop → 循环）
- **SUCCESS**: 节点执行成功
- **FAILED**: 节点执行失败（受 error_strategy 决定后续行为）
- **SKIPPED**: 跳过（error_strategy=skip 时失败后的状态）
- **ABORTED**: 中止（error_strategy=abort 时失败后的状态，整个工作流立即停）
- **DEGRADED**: 降级（error_strategy=degrade 时失败后的状态，继续后继节点）

### 3.3 节点类型处理逻辑

```python
def _execute_node(self, node: Node, variables: VariableScope) -> NodeExecResult:
    if node.type == "start":
        return NodeExecResult(node.id, "start", "SUCCESS")

    elif node.type == "end":
        return NodeExecResult(node.id, "end", "SUCCESS")

    elif node.type == "atomic":
        # 1. 解析变量引用（{{variables.xxx}} → 实际值）
        resolved_params = self._resolve_variables(node.params, variables)
        action = Action(type=node.params["atomic_action"], params=resolved_params)
        # 2. 过 guardrails.check() — 与手报坐标动作走完全相同安全路径
        guard_result = self.guardrails.check(action)
        if guard_result.decision == BLOCK:
            return self._handle_failure(node, guard_result.reason)
        # 3. 委托 F002 Executor 执行
        exec_result = self.executor.execute(action, dry_run=self.dry_run)
        # 4. 处理输出变量
        if node.output_variable and exec_result.performed:
            variables.set(node.output_variable, exec_result)
        # 5. 返回
        status = "SUCCESS" if exec_result.performed else "FAILED"
        return NodeExecResult(...)

    elif node.type == "wait":
        # 解析变量、time.sleep、返回
        ...

    elif node.type == "condition":
        # 解析条件表达式 → 匹配 branches → 确定后继
        ...

    elif node.type == "loop":
        # while/for/for_each 循环执行 children 节点列表
        # 每次迭代检查 max_iterations 上限
        ...
```

### 3.4 变量解析（模板替换）

```
输入: "打开 {{variables.app_name}}"
解析逻辑:
  1. 正则匹配 {{variables.xxx}}
  2. 在 current_scope 中查找 xxx
  3. 替换为实际值（str 直接替换，非 str 用 json.dumps）
  4. 未声明变量 → 标记为潜在错误（不崩溃，留日志）
```

### 3.5 DAG 遍历算法

采用**迭代式栈遍历**（非递归），避免 Python 递归深度限制：

```python
def _traverse(self, start_node_id: str, variables: VariableScope) -> List[NodeExecResult]:
    stack = [(start_node_id, 0)]  # (node_id, depth)
    visited = set()
    logs = []

    while stack:
        node_id, depth = stack.pop()
        if node_id in visited:
            continue  # 防环路（兜底）
        visited.add(node_id)

        node = self._get_node(node_id)
        if node is None:
            break

        result = self._execute_node(node, variables)
        logs.append(result)

        if result.status in ("FAILED", "ABORTED"):
            break  # 中止传播

        next_ids = self._resolve_next(node, result, variables)
        # 逆序入栈保持顺序
        for nid in reversed(next_ids):
            stack.append((nid, depth + 1))

    return logs
```

### 3.6 dry_run 铁律

- `Engine.dry_run()` 与 `Engine.execute()` **共享同一套状态机代码**，区别仅在于传入 `dry_run=True`
- dry_run 模式下，`Executor` 已在 dry_run 状态 → 不 import pyautogui、不真动鼠标
- 视觉节点（带 vision_query 的 atomic）在 dry_run 下**不走视觉模型**（VisionLocator 降级）
- 条件/循环节点走完整逻辑（判断分支、计数上限），但不真执行原子动作

> **双 QA 独立复验断言**：
> 断言 1：`Engine(executor=Executor(dry_run=True), dry_run=True).dry_run(wf)` 任何路径下不 import pyautogui。
> 核验：`grep -rn "import pyautogui" ai_shadowbot/engine.py` → 应不在顶层出现，仅在 `_dispatch_real` 内 lazy import。
>
> 断言 2：`Engine.dry_run()` 的 atomic 节点日志中 `action_result.performed == False`。
> 核验：`assert all(not log.action_result.performed for log in result.node_logs if log.node_type == "atomic")`。

---

## 4. 变量系统规则

### 4.1 VariableScope 实现

```python
class VariableScope:
    """变量作用域——工作流执行期间的数据流容器。

    设计要点：
    - global 变量在整个工作流生命周期内存在
    - 变量值 JSON 可序列化（str, int, bool, list, dict）
    - 变量名规则：^[a-zA-Z_][a-zA-Z0-9_]*$
    - 未声明变量引用 → 警告 + 默认空值（不崩溃）
    """

    def __init__(self, declarations: Dict[str, Variable]):
        # 用声明初始化默认值
        self._vars: Dict[str, Any] = {}
        for name, var_def in declarations.items():
            if "default" in var_def:
                self._vars[name] = var_def["default"]
        ...

    def get(self, name: str, default: Any = None) -> Any:
        ...

    def set(self, name: str, value: Any) -> None:
        # 类型检查：与声明类型对齐
        ...

    def snapshot(self) -> Dict[str, Any]:
        # 返回当前所有变量副本（用于日志/展示/调试）
        ...
```

### 4.2 数据流模型

```
节点 n1 执行 → 输出写入 output_variable "v1"
                    ↓
节点 n2 引用 {{variables.v1}} 解析为实际值
                    ↓
节点 n2 执行 → 输出写入 output_variable "v2"
                    ↓
           ...
```

### 4.3 变量类型与默认值

| 声明类型 | Python 映射 | JSON 序列化 | 默认值 |
|---------|------------|------------|--------|
| str | str | 字符串 | "" |
| int | int | 整数 | 0 |
| bool | bool | 布尔 | false |
| list | list | 数组 | [] |
| dict | dict | 对象 | {} |

### 4.4 特殊变量（内建）

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `workflow.id` | str | 当前工作流 ID |
| `workflow.step` | int | 当前执行到第几步 |
| `last_result` | dict | 上一个 atomic 节点的执行结果 `{success, summary}` |
| `last_screenshot` | str | 上一次 screenshot 动作的 base64（视觉 grounding 用） |

### 4.5 变量模板解析器

```python
VARIABLE_PATTERN = re.compile(r"\{\{variables\.([a-zA-Z_][a-zA-Z0-9_]*)\}\}")

def resolve_template(template: str, scope: VariableScope) -> str:
    """将模板字符串中的 {{variables.xxx}} 替换为实际值。"""
    def _replace(m: re.Match) -> str:
        name = m.group(1)
        value = scope.get(name)
        if value is None:
            return f"{{{{undefined:{name}}}}}"  # 标记未定义，不崩溃
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return json.dumps(value, ensure_ascii=False)
    return VARIABLE_PATTERN.sub(_replace, template)
```

---

## 5. 错误策略处理

### 5.1 错误处理流程

```
原子节点执行异常
    ↓
捕获异常 / 收到 FAILED 状态
    ↓
读取节点级 error_strategy（若无则用工作流级默认）
    ↓
    ├── retry  → 等待 retry_interval 秒 → 重试（count++）
    │             ├── 成功 → SUCCESS
    │             └── count > max_retries → 按节点级 fallback（默认 abort）
    │
    ├── skip   → 记录 SKIPPED → 继续下一节点
    │
    ├── abort  → 记录 FAILED → 停止工作流 → 返回 ExecutionResult(failed)
    │
    └── degrade → 记录 DEGRADED + warning → 继续下一节点
```

### 5.2 各策略行为表

| 策略 | 节点状态 | 后继行为 | 最终状态 | 适用场景 |
|------|---------|---------|---------|---------|
| retry | RUNNING→SUCCESS/FAILED | 最多重试 N 次，仍失败则 fallback | 取决于 fallback | 网络抖动、窗口延迟 |
| skip | SKIPPED | 跳过本节点，继续下一 | SUCCESS(with skip) | 可选步骤（如截图失败可跳过） |
| abort | FAILED | 终止整个工作流 | FAILED | 核心步骤（如打开应用失败） |
| degrade | DEGRADED | 继续下一节点，记录 warning | DEGRADED(partial) | 非关键路径（如额外截图失败） |

### 5.3 重试退避策略

```python
def _calculate_retry_delay(strategy: ErrorStrategy, attempt: int) -> float:
    """指数退避（含抖动）。"""
    base = strategy.retry_interval * (strategy.retry_backoff ** (attempt - 1))
    jitter = base * 0.1  # ±10% 抖动
    return base + random.uniform(-jitter, jitter)
```

### 5.4 节点级与工作流级策略覆盖

```
workflow.error_strategy → 所有节点的默认策略
    ↓（节点可覆盖）
node.error_strategy → 仅本节点有效
```

若某节点的 error_strategy 为 retry 且重试耗尽后未指定 fallback，默认走 abort（安全优先）。

---

## 6. 安全集成

### 6.1 安全集成总览

```
WorkflowCompiler.compile()
    │
    ▼
  编译结果中的每个 atomic node 的 params 过 validate_action()      ← §2.4 编译时校验
    │
    ▼
  工作流 JSON 展示给用户审查
    │
    ▼ 用户确认
    │
Engine.execute()
    │
    ▼
  对每个 atomic node：                                        ← §6.2 运行时安全
    1. guardrails.check(action)   ← deny-unconfirmed 不削弱
    2. vision_query → InjectionClassifier（AC4 信道隔离）
    3. Executor.execute() with guardrails.gate()
```

### 6.2 铁律清单

| # | 铁律 | 违背后果 | 核验方式 |
|---|------|---------|---------|
| 1 | 工作流中的每个 atomic 节点仍过 `guardrails.check()` | 恶意动作绕过护栏 | 在 Engine._execute_atomic 中 assert 调用 guardrails.check |
| 2 | deny-unconfirmed 不削弱：CONFIRM 动作仍需用户确认 | 自动执行高危操作 | confirm 策略全面生效 |
| 3 | 视觉派生节点仍过 `InjectionClassifier`（AC4 信道隔离） | OCR 文本诱导越权 | vision_query 字段走 classifier |
| 4 | dry_run 模式下不真实截图/识别/点击 | 用户预期安全演练 | lazy import 铁律 |
| 5 | Engine 必须接收 Guardrails 实例（不可为 None） | 无护栏裸执行 | 构造函数 assert guardrails is not None |
| 6 | loop.max_iterations 硬上限 1000 | 死循环耗尽资源 | DAG 校验 |

### 6.3 用户审查机制

编译器输出的工作流在 CLI 展示时，用户可逐节点审查：

```
📋 工作流「每日邮件对账」
  ⏰ 触发器: cron(0 9 * * 1-5, Asia/Shanghai)
  📊 变量:
    has_new_email (bool = false)
    email_count (int = 0)

  ┌─ n1 [start]
  ├─ n2 [open_app] Outlook
  ├─ n3 [wait] 5 秒
  ├─ n4 [condition] {{variables.has_new_email}}
  │  ├─ yes → n5
  │  └─ no  → n7
  ├─ n5 [screenshot]
  ├─ n6 [type_text] 数据已写入
  ├─ n7 [end]

  错误策略: retry(max=3, interval=2s)

确认执行？(y/n)>
```

### 6.4 状态虚高陷阱防护

> **历史经验（wiki_hook.inject("paritymind")）注入的状态虚高陷阱**：
> 设计文档不能只有「看起来对」的空壳。本设计的可核验断言基线：
>
> | # | 断言 | 核验命令 |
> |---|------|---------|
> | 1 | workflow.json 中不存在未声明的 $ref | `python -c "import json; json.load(open('workflow.json'))"` |
> | 2 | Engine.dry_run 不触达 pyautogui | `grep -c "import pyautogui" runtime/engine.py`（应=0，在 executor 中） |
> | 3 | 每个 atomic node 经 guardrails.check() | `grep -c "guardrails.check" runtime/engine.py`（应≥1） |
> | 4 | loop 上限硬限制 1000 | `grep "max_iterations" runtime/engine.py`（应含 <= 1000） |

---

## 7. CLI 入口设计

### 7.1 新增参数

在现有 `ai_shadowbot/cli.py` 中新增参数（不破坏现有接口）：

```python
parser.add_argument("--compile", type=str, metavar="QUERY",
                    help="自然语言→工作流编译: 输入需求，输出 DAG，确认后执行")
parser.add_argument("--run-workflow", type=str, metavar="PATH",
                    help="加载已有工作流 JSON 并执行")
parser.add_argument("--workflow-demo", action="store_true",
                    help="dry_run 下展示工作流完整流水线（编译→展示→执行→日志）")
```

### 7.2 三种入口模式

#### 模式 1: `--compile "自然语言需求"`

```
$ python -m ai_shadowbot.cli --compile "每天早上9点查邮件整理Excel"

📋 编译器输出:
  工作流「每日邮件对账」
  ...（节点图展示，如 §6.3）
  确认执行？(y/n)> y
  🤖 执行中...
    n1 [start]    ✅
    n2 [open_app] ✅ Outlook 已打开
    n3 [wait]     ⏳ 等待 5 秒...
    ...
  ✅ 执行完成
```

#### 模式 2: `--run-workflow wf.json`

```
$ python -m ai_shadowbot.cli --run-workflow daily_email.json

📋 加载工作流「每日邮件对账」
  触发器: cron(0 9 * * 1-5)
  节点: 7 个
  确认执行？(y/n)>
```

#### 模式 3: `--workflow-demo`

```
$ python -m ai_shadowbot.cli --workflow-demo

🔬 工作流流水线演示 (dry_run)
  [1] 编译: "打开记事本输入Hello然后截图"
  [2] 节点图:
    n1 [start] → n2 [open_app] 记事本 → n3 [wait] 2s → n4 [type_text] Hello → n5 [screenshot] → n6 [end]
  [3] 执行 (dry_run):
    n1 ✅ START
    n2 ✅ [dry_run] 将执行 [open_app] 记事本
    n3 ✅ [dry_run] 将执行 [wait] 2 秒
    n4 ✅ [dry_run] 将执行 [type_text] "Hello"
    n5 ✅ [dry_run] 将执行 [screenshot]
    n6 ✅ END
  [4] 变量最终状态: {}
  [dry_run] 未真实执行任何动作
```

### 7.3 CLI 确认流程

```
用户输入 / --compile 触发
    ↓
编译器输出 Workflow DAG（文本节点图 + JSON）
    ↓
show_workflow() 逐节点展示（含 guardrails 预检标记）
    ↓
用户审查 → 输入 y 确认 / n 取消
    ↓
Engine.execute() / Engine.dry_run()
    ↓
实时回显节点执行状态
```

### 7.4 工作流持久化

工作流可序列化为 JSON 文件：

```python
def save_workflow(workflow: Workflow, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow.to_dict(), f, ensure_ascii=False, indent=2)

def load_workflow(path: str) -> Workflow:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Workflow.from_dict(data)
```

---

## 8. 与现有系统的集成清单

### 8.1 新增文件

| 文件 | 说明 | 行数预估 |
|------|------|---------|
| `ai_shadowbot/workflow.py` | Workflow DAG 数据类（校验+序列化） | ~200 |
| `ai_shadowbot/compiler.py` | WorkflowCompiler + MockWorkflowCompiler | ~250 |
| `ai_shadowbot/engine.py` | Engine 执行引擎（状态机+节点处理） | ~400 |
| `ai_shadowbot/variables.py` | VariableScope + 模板解析 | ~150 |
| `ai_shadowbot/errors.py` | ErrorStrategy + 重试/退避逻辑 | ~120 |
| `docs/workflow-design.md` | 本文档 | ~500 |

### 8.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `ai_shadowbot/cli.py` | 新增 `--compile`, `--run-workflow`, `--workflow-demo` 参数入口 |
| `project-spec.json` | 新增 F006 feature 条目（status=planned, depends_on=F001/F002/F004/F005） |
| `ai_shadowbot/__init__.py` | 导出新模块（按需） |

**注意**：所有修改为 additive（叠加），不破坏现有 F001-F005 接口。

### 8.3 复用关系图

```
┌─────────────────────────────────────────────────────────────┐
│ 新增 F006                                                 │
│                                                             │
│  WorkflowCompiler          Engine                           │
│    ↓compile()                ↓execute()                     │
│  ┌────────────────┐    ┌────────────────────┐               │
│  │ 复用:           │    │ 复用:               │              │
│  │  Config          │    │  Executor (F002)    │             │
│  │  OpenAIClient    │    │  Guardrails (F003)  │             │
│  │  MockLLMClient   │    │  EmergencyStop     │             │
│  │  actions.validate │   │  VisionLocator(F005)│             │
│  │  guardrails      │    │                    │              │
│  └────────────────┘    └────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌──────────────────────┐
│ 现有 F001-F005       │    │ 复用的护栏/执行原语     │
│ 不动现有代码          │    │ guardrails.check()    │
│                      │    │ Executor.execute()   │
│                      │    │ VisionLocator        │
└──────────────────────┘    └──────────────────────┘
```

### 8.4 project-spec.json F006 新增条目

```json
{
  "id": "F006",
  "title": "工作流引擎 Phase 1（AI 编译 + DAG 执行）",
  "description": "工作流 DAG 数据结构 + AI 编译器（自然语言→节点图）+ 执行引擎（状态机/条件/循环/变量/错误策略）。用户说需求→AI 自动编节点图→展示审查→确认执行。对现有 F001-F005 完全 additive。",
  "status": "planned",
  "claimed_by": "",
  "depends_on": ["F001", "F002", "F004", "F005"],
  "acceptance_criteria": [
    "AC1: 给定『每天9点查邮件整理Excel』类需求，编译器输出合法 Workflow DAG JSON（含 start/end/condition/open_app 节点）",
    "AC2: 执行引擎能解释执行含条件分支的 DAG，atomic 节点委托 F002 executor，condition 节点正确评估分支",
    "AC3: 变量系统支持 global 作用域，{{variables.xxx}} 在节点参数中正确替换",
    "AC4: 错误策略 retry/skip/abort 正确生效；retry 耗尽后 fallback；loop 有上限 (≤1000) 防死循环",
    "AC5: 所有 atomic 节点原样过 guardrails.check()，deny-unconfirmed 不削弱；dry_run 不真执行",
    "AC6: CLI 入口 --compile / --run-workflow / --workflow-demo 三种模式均可工作"
  ]
}
```

---

## 附录 A：设计决策记录

| # | 决策 | 方案 | 备选 | 理由 |
|---|------|------|------|------|
| 1 | 编译器 vs planner 关系 | Compiler 复用 planner 的 LLM 客户端与 tool_choice 策略 | 独立新 LLM 调用链 | 减少重复代码、统一 LLM 配置路径 |
| 2 | DAG 遍历算法 | 迭代式栈遍历 | 递归 DFS | 防 Python 递归深度限制、防爆栈 |
| 3 | 变量替换时机 | 执行时实时替换（execution-time resolve） | 编译时预替换 | 运行时变量才确定值，预替换不可行 |
| 4 | loop 上限 | 硬限制 1000 | 可配置 | Ken Thompson：死循环是运行时灾难，硬上限安全 |
| 5 | 节点 vs 工作流 error_strategy | 节点可覆盖工作级默认 | 仅工作流级 | 不同步骤有不同容忍度（如截图失败可跳过、打开应用失败应中止） |
| 6 | dry_run 与 execute 代码共享 | 同一方法，参数控制 | 两套方法 | 减少维护成本，避免两处不一致 |

## 附录 B：可核验断言清单

> 按 paritymind v4.2 纪律，以下断言均附带核验命令。

| # | 断言 | 核验方式 |
|---|------|---------|
| 1 | Workflow JSON schema 中所有 $ref 均已 resolve | `python -c "import json; schema=json.load(open('docs/workflow-design.md')); assert 'definitions' in schema"`（实为文档中的 schema 定义，非运行时） |
| 2 | Engine.dry_run 不触达 pyautogui | `grep -c "pyautogui" ai_shadowbot/engine.py` 应返回 0（pyautogui 仅在 executor._dispatch_real 中） |
| 3 | 每个 atomic 节点执行前过 guardrails.check() | 在 `engine.py` 中搜索 `guardrails.check(` 应 ≥ 1 |
| 4 | loop.max_iterations 上限为 1000 | `grep "max_iterations" ai_shadowbot/engine.py` 应含 `<= 1000` 或 `max(..., 1000)` |
| 5 | compile_workflow tool 的 params 完整覆盖 Node schema | 目检：§2.2.1 的 JSON schema 含 `next/branches/children/vision_query/output_variable/error_strategy` |
| 6 | VariableScope.set() 做类型检查 | 搜索 `type()` 或 `isinstance()` 在 `variables.py` ≥ 1 |
| 7 | retry 退避含抖动 | 搜索 `random` 在 `errors.py` |
