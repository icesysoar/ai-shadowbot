# AI 工作流画布 · Phase 2 架构设计

> 版本：v1.0 | 日期：2026-07-07 | 关联 F008

---

## 1. 核心目标

在 Phase 1（CLI 工作流引擎）之上，提供 **可视化 Web 画布**，让用户能：
1. **拖拽编辑**：像影刀一样拖拽节点搭流程
2. **AI 辅助搭建**：自然语言→AI 自动生成节点图→用户拖拽微调
3. **一键执行**：在画布上点击运行，实时看节点状态

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────┐
│               用户浏览器 (React Flow)             │
│  节点调色板 │ 拖拽画布 │ 属性面板 │ 执行监控       │
└──────────────────┬──────────────────────────────┘
                   │ HTTP REST API (JSON)
                   ▼
┌─────────────────────────────────────────────────┐
│          FastAPI 后端（扩展 l5_gateway）          │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐   │
│  │ Workflow │ │ 画布 CRUD │ │ L5 外部触发     │   │
│  │ Compiler │ │ /api/wf/  │ │ (已有 F007)     │   │
│  └──────────┘ └──────────┘ └────────────────┘   │
│  ┌──────────────────────────────────────────┐    │
│  │ Engine (F006) + Guardrails (F003) + Vision│   │
│  └──────────────────────────────────────────┘    │
└──────────────────┬──────────────────────────────┘
                   │ SQLite / JSON
                   ▼
           ┌──────────────┐
           │ workflow.db   │
           │ (持久化存储)   │
           └──────────────┘
```

---

## 3. 前端方案选型

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **React Flow** | 专注 DAG/流程图，轻量 50KB，React 生态，拖拽/缩放/节点自定义开箱即用 | 需 React 基础 | ✅ **推荐** |
| LiteGraph.js | 节点编辑器老牌，零框架依赖 | 文档差，UI 过时，维护不活跃 | ❌ |
| Vue Flow | Vue 版 React Flow | 生态较小 | ❌ |

**选 React Flow + CDN 引入**（不搞 webpack 构建，减少依赖成本）

---

## 4. 后端 API 设计

### 4.1 工作流 CRUD（新增，扩展 FastAPI）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/workflows` | 列出所有保存的工作流 |
| `POST` | `/api/workflows` | 创建新工作流（或保存 AI 编译结果） |
| `GET` | `/api/workflows/{id}` | 获取工作流详情（含完整 DAG） |
| `PUT` | `/api/workflows/{id}` | 更新工作流（拖拽修改后保存） |
| `DELETE` | `/api/workflows/{id}` | 删除工作流 |
| `POST` | `/api/workflows/{id}/execute` | 执行工作流（dry_run/real） |
| `GET` | `/api/workflows/{id}/runs` | 查看历史执行记录 |

### 4.2 画布专用端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/compile-to-flow` | 自然语言→可编辑的 Flow JSON（前端画布可加载） |
| `GET` | `/api/palette` | 获取节点调色板（可用动作列表） |
| `POST` | `/api/flow/validate` | 校验画布提交的 Flow 是否合法 |
| `GET` | `/api/execution/{run_id}` | 轮询执行进度（节点级状态更新） |

### 4.3 Flow ↔ Workflow 数据映射

前端 React Flow 用 `{nodes[], edges[]}` 格式，后端 Workflow 用 `{nodes[], triggers[]}` DAG 格式。

**转换规则**（内置适配器）：

```python
def flow_to_workflow(flow_nodes, flow_edges) -> Workflow:
    """前端 Flow JSON → 后端 Workflow DAG"""
    # 每个 Flow node → Workflow Node（带 param 面板数据）
    # Flow edges → Workflow Node.next/branches
    ...

def workflow_to_flow(workflow) -> dict:
    """后端 Workflow DAG → 前端 Flow JSON (nodes + edges)"""
    ...
```

---

## 5. 持久化方案

使用 SQLite（轻量，零配置）：

```sql
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    flow_json TEXT NOT NULL,    -- 前端画布格式的完整 JSON
    compiled_from TEXT,         -- AI 编译来源（自然语言原文）
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE execution_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id),
    mode TEXT,           -- dry_run / real
    result_json TEXT,    -- ExecutionResult JSON
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
```

---

## 6. 前端 UI 布局

```
┌─────────────────────────────────────────────────┐
│  Header: Logo | 保存/另存 | 执行(dry_run/real)  │
├──────────┬──────────────────────┬───────────────┤
│ 调色板   │     画布区域         │  属性面板      │
│ Palette  │   (React Flow)      │  Properties   │
│          │                     │               │
│ ▶ 鼠标   │  [start] → [screenshot]             │
│ ▶ 键盘   │              ↓      │  节点类型:     │
│ ▶ 应用   │          [type_text] │  atomic       │
│ ▶ 系统   │              ↓      │  动作: screenshot│
│ ▶ 控制   │            [end]    │               │
│ ▶ 视觉   │                     │               │
├──────────┴──────────────────────┴───────────────┤
│  状态栏: 运行状态 / 节点日志 / 错误信息           │
└─────────────────────────────────────────────────┘
```

---

## 7. 节点调色板（初始）

基于现有 9 个原子动作 + 4 个控制节点：

| 分类 | 节点 | 说明 |
|------|------|------|
| **鼠标** | click / double_click / right_click / scroll | 4 种点击操作 |
| **键盘** | type_text / key_press | 输入文本和按键 |
| **应用** | open_app | 打开程序 |
| **系统** | wait / screenshot | 等待和截图 |
| **控制** | condition / loop / start / end | 流程控制 |

每个节点配有：
- 名称 + 图标 + 简述
- 参数面板（自动生成自 actions.py 的 schema）
- 安全标记（危险动作自动标注）

---

## 8. 实现路线

### Step 1: 后端扩展（api/workflow_canvas.py）
- 工作流 CRUD 端点（SQLite 持久化）
- Flow ↔ Workflow 转换适配器
- 画布校验 + 执行端点

### Step 2: 前端（static/canvas.html + JS）
- 单页 HTML（React + React Flow CDN 引入，零构建）
- 拖拽画布 + 节点调色板 + 属性面板
- 保存/加载/执行操作

### Step 3: 集成与测试
- 与现有 l5_gateway 合并路由
- L5 bridge MCP 工具同步暴露画布 API
- 安全集成（画布上每个节点仍过 guardrails）

---

## 9. 与现有系统集成

| 现有模块 | 集成方式 | 改动量 |
|---------|---------|--------|
| F006 workflow.py | 复用 DAG 数据结构 | ✅ 零改动 |
| F006 compiler.py | 复用编译器（画布调"AI 生成"按钮） | ✅ 零改动 |
| F006 engine.py | 复执行引擎（画布点击执行） | ✅ 零改动 |
| F007 l5_gateway.py | 扩展路由（画布 API 挂载到同一 FastAPI） | ⚡ 加法 |
| F003 guardrails.py | 画布执行仍过 guardrails.check() | ✅ 零改动 |
| F005 vision.py | 视觉节点可拖拽到画布 | ✅ 零改动 |

---

## 10. 安全红线（不可协商）

- 画布上的每个 atomic 节点执行前仍过 `guardrails.check()`
- AI 编译的工作流展示在画布上时，危险节点自动标红提示
- 用户拖拽修改后保存的流程，执行时仍过完整安全链路
- 画布 API 仅监听 127.0.0.1（与 l5_gateway 一致）
