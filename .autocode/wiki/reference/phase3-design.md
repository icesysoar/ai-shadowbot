# AI 工作流 · Phase 3 调度与生态设计

> 版本：v1.0 | 日期：2026-07-07 | 关联 F009（调度器）/ F010（日志）/ F011（模板市场）

---

## 1. 总览

在 Phase 1（工作流引擎）+ Phase 2（可视化画布）之上，补齐四个能力：

| 模块 | 核心能力 | 关联 Feature |
|------|---------|-------------|
| 定时调度器 | cron 定时执行、热键触发、手动触发 | F009 |
| 执行日志回溯 | 节点级日志、失败截图、执行历史查询 | F010 |
| 流程模板市场 | 保存为模板、从模板创建、分类浏览 | F011 |
| L5 集成 | 外部 AI 触发调度/查日志/用模板 | 扩展 F007 |

---

## 2. 定时调度器（F009）

### 2.1 架构

```
┌──────────────────────────────────────────────┐
│              Scheduler (后台线程)               │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ cron解析  │  │ 热键监听  │  │ 调度队列    │  │
│  └──────────┘  └──────────┘  └────────────┘  │
│         │            │              │          │
│         ▼            ▼              ▼          │
│  ┌──────────────────────────────────────────┐  │
│  │          WorkflowRunner (复用 Engine)    │  │
│  │  → Engine.execute() + Guardrails.check() │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### 2.2 数据模型（扩展 SQLite）

```sql
-- 已调度的工作流触发器
CREATE TABLE triggers (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    type TEXT NOT NULL CHECK(type IN ('cron', 'interval', 'manual')),
    config TEXT NOT NULL,      -- JSON: cron表达式/间隔秒数
    enabled INTEGER DEFAULT 1,  -- 0=暂停, 1=激活
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    created_at TIMESTAMP
);

-- 触发器执行历史
CREATE TABLE trigger_runs (
    id TEXT PRIMARY KEY,
    trigger_id TEXT REFERENCES triggers(id),
    workflow_id TEXT NOT NULL,
    execution_run_id TEXT REFERENCES execution_runs(id),
    triggered_at TIMESTAMP,
    status TEXT
);
```

### 2.3 调度器实现

使用 Python 标准库 `threading.Timer` + `croniter`（轻量 cron 解析），零额外依赖：

```python
class Scheduler:
    """后台调度器。"""

    def __init__(self, canvas_api: 'CanvasAPI'):
        self.canvas_api = canvas_api
        self._triggers: Dict[str, threading.Timer] = {}
        self._running = False

    def start(self):
        """启动调度线程。"""
        self._running = True
        self._load_and_schedule()

    def stop(self):
        """停止调度器。"""
        self._running = False
        for t in self._triggers.values():
            t.cancel()

    def add_trigger(self, trigger_data: dict):
        """添加一个触发器。"""
        ...

    def remove_trigger(self, trigger_id: str):
        """删除触发器。"""
        ...

    def _execute_workflow(self, workflow_id: str):
        """触发工作流执行。"""
        ...
```

### 2.4 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/scheduler/triggers` | 列出所有触发器 |
| `POST` | `/api/scheduler/triggers` | 创建触发器 |
| `PUT` | `/api/scheduler/triggers/{id}` | 更新触发器 |
| `DELETE` | `/api/scheduler/triggers/{id}` | 删除触发器 |
| `POST` | `/api/scheduler/triggers/{id}/toggle` | 启用/暂停 |
| `GET` | `/api/scheduler/status` | 调度器状态（正在运行的定时任务） |

### 2.5 前端集成

画布界面新增「调度」面板：
- 工作流详情页 → "设置定时" 按钮
- 弹出配置界面：cron 表达式 / 间隔分钟 / 热键组合
- 列表显示已设置的定时任务（下次执行时间、状态开关）

---

## 3. 执行日志回溯（F010）

### 3.1 数据模型（扩展已有 execution_runs 表）

```sql
-- 节点级执行日志（补充 execution_runs 的详情）
ALTER TABLE execution_runs ADD COLUMN summary TEXT;       -- 执行摘要 JSON
ALTER TABLE execution_runs ADD COLUMN screenshot_b64 TEXT; -- 失败时的截图(base64)

-- 节点详细日志
CREATE TABLE node_logs (
    id TEXT PRIMARY KEY,
    execution_run_id TEXT NOT NULL REFERENCES execution_runs(id),
    node_id TEXT NOT NULL,
    node_type TEXT,
    status TEXT,
    started_at REAL,
    finished_at REAL,
    error TEXT,
    output TEXT,        -- 节点输出摘要
    screenshot_b64 TEXT  -- 该节点执行时的截图
);
```

### 3.2 执行日志 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/workflows/{id}/runs` | 工作流执行历史列表 |
| `GET` | `/api/execution/{run_id}` | 某次执行的完整日志（含节点详情） |
| `GET` | `/api/execution/{run_id}/nodes` | 某次执行的节点级日志 |
| `GET` | `/api/execution/{run_id}/screenshot/{node_id}` | 某节点的截图 |

### 3.3 前端集成

画布新增「日志」面板：
- 执行记录列表（时间、状态、耗时）
- 点击展开某次执行 → 节点级时间线（谁成功/谁失败/花多久）
- 失败节点自动展开错误详情 + 截图

### 3.4 截屏策略

- 仅在 `mode=real` 且节点失败时自动截屏
- 截屏经过 `Observer.mask_sensitive_regions` 脱敏（AC5）
- dry_run 不截屏

---

## 4. 流程模板市场（F011）

### 4.1 数据模型

```sql
CREATE TABLE templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT '通用',  -- 分类：办公/网页/数据/系统
    flow_json TEXT NOT NULL,      -- 完整画布数据
    tags TEXT,                    -- JSON 数组 ["邮件","Excel","日报"]
    author TEXT DEFAULT 'AI 编译',
    usage_count INTEGER DEFAULT 0,
    rating REAL DEFAULT 0.0,
    created_at TIMESTAMP
);
```

### 4.2 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/templates` | 模板列表（支持搜索/分类筛选） |
| `GET` | `/api/templates/{id}` | 模板详情 |
| `POST` | `/api/workflows/from-template/{id}` | 从模板创建工作流 |
| `POST` | `/api/workflows/{id}/save-template` | 当前工作流另存为模板 |
| `POST` | `/api/templates/{id}/usage` | 增加使用计数 |

### 4.3 前端集成

画布新增「模板」面板（左侧或顶部）：
- 浏览模板库（分类展示 + 搜索）
- 预览模板（展开看节点图）
- "使用模板" → 复制到画布 → 用户拖拽微调
- "另存为模板" → 当前画布保存为模板（可选分类/标签）

### 4.4 种子模板（预置）

| 模板名 | 节点流 | 适用场景 |
|--------|--------|---------|
| 每日邮件对账 | open_app→wait→screenshot→condition→... | 每天早上查邮件 |
| 网页截图存档 | open_app→wait→screenshot→save | 定时截图保存网页 |
| 文件整理 | open_app→click→type_text→screenshot | 批量文件操作 |
| 系统监控 | screenshot→condition→scroll | 监控系统状态 |

---

## 5. L5 集成（扩展 F007）

### 5.1 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/l5/schedule` | 外部 AI 设置定时触发 |
| `GET` | `/l5/logs/{workflow_id}` | 外部 AI 查执行日志 |
| `GET` | `/l5/templates` | 外部 AI 查模板列表 |
| `POST` | `/l5/templates/{id}/use` | 外部 AI 使用模板创建流 |

### 5.2 MCP Tools 新增

| Tool | 说明 |
|------|------|
| `schedule_workflow(workflow_id, cron_expr)` | 设置定时触发 |
| `get_execution_logs(workflow_id, limit)` | 查询执行日志 |
| `list_templates(category)` | 列出模板 |
| `use_template(template_id)` | 使用模板创建新工作流 |

---

## 6. 安全与集成

| 约束 | 说明 |
|------|------|
| 调度执行仍过 guardrails | 每个 atomic 节点执行前过 Guardrails.check() |
| 截图脱敏 | 失败截屏走 Observer.mask_sensitive_regions（AC5） |
| dry_run 不截屏 | 不持有截图对象 |
| 模板不含凭据 | 保存模板时自动剔除 params 中的密码/token 字段 |
| L5 调度受 token 保护 | 需要 Bearer Token（同 l5_gateway auth） |

---

## 7. 实现路线

### Step 1: 数据库扩展 + Scheduler 模块
- 扩展 canvas_api.py：triggers + node_logs + templates 表
- 新增 ai_shadowbot/scheduler.py：Scheduler 后台线程类
- 扩展 canvas_api.py：调度 CRUD + 日志查询 + 模板 CRUD

### Step 2: L5 网关扩展
- l5_gateway.py：新增调度/日志/模板路由
- MCP tools 新增

### Step 3: 前端扩展
- canvas.html：新增调度面板 + 日志面板 + 模板面板
