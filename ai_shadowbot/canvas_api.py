"""可视化画布后端 API（F008）—— SQLite 持久化 + Flow↔Workflow 转换 + CRUD。

依赖：
  - sqlite3（Python 标准库，零额外依赖）
  - ai_shadowbot.workflow（Workflow / Node / NodeType 等）
  - ai_shadowbot.compiler（WorkflowCompiler）
  - ai_shadowbot.engine（Engine）

设计文档：docs/canvas-design.md
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ai_shadowbot.workflow import (
    ErrorStrategy,
    ErrorStrategyType,
    Node,
    NodeType,
    Workflow,
    WorkflowSchema,
    WorkflowValidationError,
)
from ai_shadowbot.actions import ACTION_TYPES

# ---------------------------------------------------------------------------
# 默认数据库路径
# ---------------------------------------------------------------------------
_DEFAULT_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "workflow.db")


# ---------------------------------------------------------------------------
# Flow ↔ Workflow 双向转换
# ---------------------------------------------------------------------------

# 各分类的节点定义（调色板数据）
PALETTE_NODES = [
    # 鼠标
    {"category": "鼠标", "type": "click", "label": "点击", "node_type": "atomic",
     "params": {"atomic_action": "click", "x": 0, "y": 0},
     "desc": "在屏幕绝对坐标 (x,y) 左键单击"},
    {"category": "鼠标", "type": "double_click", "label": "双击", "node_type": "atomic",
     "params": {"atomic_action": "double_click", "x": 0, "y": 0},
     "desc": "在屏幕绝对坐标 (x,y) 左键双击"},
    {"category": "鼠标", "type": "right_click", "label": "右键单击", "node_type": "atomic",
     "params": {"atomic_action": "right_click", "x": 0, "y": 0},
     "desc": "在屏幕绝对坐标 (x,y) 右键单击"},
    {"category": "鼠标", "type": "scroll", "label": "滚动", "node_type": "atomic",
     "params": {"atomic_action": "scroll", "dx": 0, "dy": 0},
     "desc": "滚动鼠标滚轮"},
    # 键盘
    {"category": "键盘", "type": "type_text", "label": "输入文本", "node_type": "atomic",
     "params": {"atomic_action": "type_text", "text": ""},
     "desc": "在当前焦点处输入文本"},
    {"category": "键盘", "type": "key_press", "label": "按键", "node_type": "atomic",
     "params": {"atomic_action": "key_press", "key": "enter"},
     "desc": "按下键盘按键或组合键"},
    # 应用
    {"category": "应用", "type": "open_app", "label": "打开应用", "node_type": "atomic",
     "params": {"atomic_action": "open_app", "name": ""},
     "desc": "打开指定名称的应用程序"},
    # 系统
    {"category": "系统", "type": "screenshot", "label": "截图", "node_type": "atomic",
     "params": {"atomic_action": "screenshot"},
     "desc": "对当前屏幕截图"},
    {"category": "系统", "type": "wait", "label": "等待", "node_type": "wait",
     "params": {"seconds": 1.0},
     "desc": "等待指定秒数"},
    # 控制
    {"category": "控制", "type": "start", "label": "开始", "node_type": "start",
     "params": {},
     "desc": "流程起点"},
    {"category": "控制", "type": "end", "label": "结束", "node_type": "end",
     "params": {},
     "desc": "流程终点"},
    {"category": "控制", "type": "condition", "label": "条件判断", "node_type": "condition",
     "params": {"expression": ""},
     "desc": "条件判断分支"},
    {"category": "控制", "type": "loop", "label": "循环", "node_type": "loop",
     "params": {"loop_type": "while", "condition": "", "max_iterations": 100},
     "desc": "循环执行子节点"},
    # 浏览器（F015.3）
    {"category": "浏览器", "type": "browser_navigate", "label": "打开网页", "node_type": "atomic",
     "params": {"atomic_action": "browser_navigate", "url": "https://"},
     "desc": "在浏览器中打开指定网页"},
    {"category": "浏览器", "type": "browser_click", "label": "点击元素", "node_type": "atomic",
     "params": {"atomic_action": "browser_click", "x": 0, "y": 0},
     "desc": "在浏览器中点击指定坐标"},
    {"category": "浏览器", "type": "browser_type", "label": "输入文本", "node_type": "atomic",
     "params": {"atomic_action": "browser_type", "text": ""},
     "desc": "在浏览器当前焦点输入文本"},
    {"category": "浏览器", "type": "browser_screenshot", "label": "网页截图", "node_type": "atomic",
     "params": {"atomic_action": "browser_screenshot"},
     "desc": "截取当前浏览器页面"},
    {"category": "浏览器", "type": "browser_wait", "label": "等待", "node_type": "atomic",
     "params": {"atomic_action": "browser_wait", "seconds": 1},
     "desc": "在浏览器中等待指定秒数"},
    {"category": "浏览器", "type": "browser_scroll", "label": "滚动页面", "node_type": "atomic",
     "params": {"atomic_action": "browser_scroll", "dx": 0, "dy": 0},
     "desc": "在浏览器中滚动页面"},
    # Excel/CSV（F016）
    {"category": "Excel", "type": "excel_read", "label": "读取Excel/CSV", "node_type": "atomic",
     "params": {"atomic_action": "excel_read", "path": "", "column": "", "value": ""},
     "desc": "读取 Excel/CSV 文件内容"},
    {"category": "Excel", "type": "excel_write", "label": "写入Excel/CSV", "node_type": "atomic",
     "params": {"atomic_action": "excel_write", "path": "", "headers": [], "rows": [], "sheet": "Sheet1"},
     "desc": "写入数据到 Excel/CSV 文件"},
    # 网络（F017）
    {"category": "网络", "type": "http_request", "label": "HTTP请求", "node_type": "atomic",
     "params": {"atomic_action": "http_request", "method": "GET", "url": "", "headers": {}, "body": ""},
     "desc": "发送 HTTP 请求"},
    {"category": "网络", "type": "http_get", "label": "GET请求", "node_type": "atomic",
     "params": {"atomic_action": "http_get", "url": "", "headers": {}},
     "desc": "发送 HTTP GET 请求"},
    {"category": "网络", "type": "http_post", "label": "POST请求", "node_type": "atomic",
     "params": {"atomic_action": "http_post", "url": "", "body": "", "headers": {}},
     "desc": "发送 HTTP POST 请求"},
    {"category": "网络", "type": "http_put", "label": "PUT请求", "node_type": "atomic",
     "params": {"atomic_action": "http_put", "url": "", "body": "", "headers": {}},
     "desc": "发送 HTTP PUT 请求"},
    {"category": "网络", "type": "http_delete", "label": "DELETE请求", "node_type": "atomic",
     "params": {"atomic_action": "http_delete", "url": "", "headers": {}},
     "desc": "发送 HTTP DELETE 请求"},
    # 文件（F019）
    {"category": "文件", "type": "fs_read", "label": "读取文件", "node_type": "atomic",
     "params": {"atomic_action": "fs_read", "path": ""},
     "desc": "读取文件内容"},
    {"category": "文件", "type": "fs_write", "label": "写入文件", "node_type": "atomic",
     "params": {"atomic_action": "fs_write", "path": "", "content": ""},
     "desc": "写入内容到文件"},
    {"category": "文件", "type": "fs_delete", "label": "删除文件", "node_type": "atomic",
     "params": {"atomic_action": "fs_delete", "path": ""},
     "desc": "删除文件或目录（高危）"},
    {"category": "文件", "type": "fs_list", "label": "列出目录", "node_type": "atomic",
     "params": {"atomic_action": "fs_list", "path": ""},
     "desc": "列出目录中的文件"},
    {"category": "文件", "type": "fs_exists", "label": "检查是否存在", "node_type": "atomic",
     "params": {"atomic_action": "fs_exists", "path": ""},
     "desc": "检查文件/目录是否存在"},
]


def _generate_node_id(existing_ids: set) -> str:
    """生成唯一节点 ID（格式 n1, n2, ...）。"""
    i = 1
    while f"n{i}" in existing_ids:
        i += 1
    nid = f"n{i}"
    existing_ids.add(nid)
    return nid


def flow_to_workflow(
    flow_nodes: List[Dict[str, Any]],
    flow_edges: List[Dict[str, Any]],
) -> Workflow:
    """前端 React Flow 格式 → 后端 Workflow DAG。

    Args:
        flow_nodes: React Flow nodes[{id, type, position, data}]
        flow_edges: React Flow edges[{id, source, target, label}]

    Returns:
        Workflow 实例
    """
    # 构建 source→target 映射
    edge_map: Dict[str, List[Tuple[str, str]]] = {}  # source -> [(target, label)]
    for edge in flow_edges:
        src = edge["source"]
        tgt = edge["target"]
        label = edge.get("label", "")
        edge_map.setdefault(src, []).append((tgt, label))

    nodes_list: List[Node] = []
    for fn in flow_nodes:
        fid = fn["id"]
        data = fn.get("data", {})
        node_type_str = data.get("node_type", data.get("type", "atomic"))
        params = dict(data.get("params", {}))
        label = data.get("label", "")

        # 解析 node_type
        try:
            node_type = NodeType(node_type_str)
        except ValueError:
            node_type = NodeType.atomic

        # 构建 next / branches 从边
        outgoing = edge_map.get(fid, [])

        if node_type == NodeType.condition:
            # condition 节点：branch 从边取
            branches: List[Dict[str, Any]] = []
            for tgt, lbl in outgoing:
                branch: Dict[str, Any] = {"next": tgt}
                if lbl:
                    branch["label"] = lbl
                    if lbl.lower() in ("true", "yes", "是"):
                        branch["condition"] = "true"
                    elif lbl.lower() in ("false", "no", "否"):
                        branch["condition"] = "false"
                    else:
                        branch["condition"] = ""
                else:
                    branch["condition"] = ""
                branches.append(branch)
            node = Node(
                id=fid,
                type=node_type,
                params=params,
                label=label,
                branches=branches,
            )
        elif node_type == NodeType.loop:
            # loop 节点：children 从子边取，continue_on 从第一个非 children 边取
            children: List[str] = [tgt for tgt, _ in outgoing]
            node = Node(
                id=fid,
                type=node_type,
                params=params,
                label=label,
                children=children,
                continue_on=data.get("continue_on"),
            )
        else:
            # start / end / atomic / wait：取第一个出边作为 next
            nxt = outgoing[0][0] if outgoing else None
            node = Node(
                id=fid,
                type=node_type,
                params=params,
                label=label,
                next=nxt,
            )
        nodes_list.append(node)

    return Workflow(
        id=f"wf_{uuid.uuid4().hex[:8]}",
        name="未命名工作流",
        nodes=nodes_list,
    )


# 画布布局常量
_START_Y = 50
_LAYER_HEIGHT = 120
_START_X = 100
_CONDITION_BRANCH_X_OFFSET = 200


def _auto_layout(wf: Workflow) -> Tuple[List[Dict], List[Dict]]:
    """自动布局：按拓扑顺序排列节点。"""
    # 按 next/branches 关系布局
    node_order: List[str] = []
    visited: set = set()

    def _walk(nid: str):
        if nid in visited:
            return
        visited.add(nid)
        node_order.append(nid)
        node = _node_map.get(nid)
        if node is None:
            return
        if node.next:
            _walk(node.next)
        if node.branches:
            for b in node.branches:
                nid_b = b.get("next", "")
                if nid_b:
                    _walk(nid_b)

    _node_map = {n.id: n for n in wf.nodes}
    start_nodes = [n for n in wf.nodes if n.type == NodeType.start]
    if start_nodes:
        _walk(start_nodes[0].id)

    # 剩余未访问节点
    for n in wf.nodes:
        if n.id not in visited:
            node_order.append(n.id)

    # 生成画布节点
    rf_nodes: List[Dict] = []
    rf_edges: List[Dict] = []

    # condition 分支计数
    condition_branch_count: Dict[str, int] = {}

    for i, nid in enumerate(node_order):
        node = _node_map.get(nid)
        if node is None:
            continue

        label = node.label or node.type.value
        rf_node = {
            "id": node.id,
            "type": node.type.value,
            "position": {"x": _START_X, "y": _START_Y + i * _LAYER_HEIGHT},
            "data": {
                "label": label,
                "node_type": node.type.value,
                "params": dict(node.params),
            },
        }
        rf_nodes.append(rf_node)

        # 边
        if node.next:
            rf_edges.append({
                "id": f"e-{node.id}-{node.next}",
                "source": node.id,
                "target": node.next,
                "label": "",
            })

        if node.branches:
            count = 0
            for b in node.branches:
                nid_b = b.get("next", "")
                if nid_b:
                    bl = b.get("label", "")
                    rf_edges.append({
                        "id": f"e-{node.id}-{nid_b}-{count}",
                        "source": node.id,
                        "target": nid_b,
                        "label": bl or b.get("condition", ""),
                    })
                    count += 1
                    # 分支节点横移
                    _offset_x_node(_node_map, nid_b, count * _CONDITION_BRANCH_X_OFFSET)

        if node.children:
            for j, cid in enumerate(node.children):
                rf_edges.append({
                    "id": f"e-{node.id}-{cid}-child-{j}",
                    "source": node.id,
                    "target": cid,
                    "label": "child",
                })

        if node.continue_on:
            rf_edges.append({
                "id": f"e-{node.id}-{node.continue_on}-cont",
                "source": node.id,
                "target": node.continue_on,
                "label": "continue",
            })

    return rf_nodes, rf_edges


def _offset_x_node(node_map: Dict[str, Node], nid: str, offset: int):
    """位置偏移标记（画布更新时用 — 这里仅作示例不做实际偏移）。"""
    pass


def workflow_to_flow(workflow: Workflow) -> Dict[str, List]:
    """后端 Workflow DAG → 前端 React Flow 格式 {nodes, edges}。

    Args:
        workflow: Workflow 实例

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    rf_nodes, rf_edges = _auto_layout(workflow)
    return {"nodes": rf_nodes, "edges": rf_edges}


# ---------------------------------------------------------------------------
# SQLite 持久化
# ---------------------------------------------------------------------------

def _get_db_path(db_path: Optional[str] = None) -> str:
    """确定数据库路径。"""
    if db_path:
        return db_path
    # 确保 data 目录存在
    os.makedirs(_DEFAULT_DB_DIR, exist_ok=True)
    return _DEFAULT_DB_PATH


def _init_db(conn: sqlite3.Connection):
    """初始化数据库表结构（含 Phase 3 扩展表）。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            flow_json TEXT NOT NULL DEFAULT '{"nodes":[],"edges":[]}',
            compiled_from TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS execution_runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT REFERENCES workflows(id),
            mode TEXT NOT NULL DEFAULT 'dry_run',
            result_json TEXT NOT NULL DEFAULT '{}',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            summary TEXT DEFAULT NULL,
            screenshot_b64 TEXT DEFAULT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_exec_runs_wf
            ON execution_runs(workflow_id);

        -- Phase 3: 触发器表
        CREATE TABLE IF NOT EXISTS triggers (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL REFERENCES workflows(id),
            type TEXT NOT NULL CHECK(type IN ('cron', 'interval', 'manual')),
            config TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_triggers_wf
            ON triggers(workflow_id);

        -- Phase 3: 触发器执行历史
        CREATE TABLE IF NOT EXISTS trigger_runs (
            id TEXT PRIMARY KEY,
            trigger_id TEXT REFERENCES triggers(id),
            workflow_id TEXT NOT NULL,
            execution_run_id TEXT REFERENCES execution_runs(id),
            triggered_at TIMESTAMP,
            status TEXT
        );

        -- Phase 3: 节点级日志表
        CREATE TABLE IF NOT EXISTS node_logs (
            id TEXT PRIMARY KEY,
            execution_run_id TEXT NOT NULL REFERENCES execution_runs(id),
            node_id TEXT NOT NULL,
            node_type TEXT,
            status TEXT,
            started_at REAL,
            finished_at REAL,
            error TEXT,
            output TEXT,
            screenshot_b64 TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_node_logs_run
            ON node_logs(execution_run_id);

        -- Phase 3: 模板表
        CREATE TABLE IF NOT EXISTS templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT '通用',
            flow_json TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            author TEXT DEFAULT 'AI 编译',
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_templates_category
            ON templates(category);
    """)
    conn.commit()

    # 兼容旧表：确保 execution_runs 有 summary 和 screenshot_b64 列
    _ensure_column(conn, "execution_runs", "summary", "TEXT DEFAULT NULL")
    _ensure_column(conn, "execution_runs", "screenshot_b64", "TEXT DEFAULT NULL")


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, col_type: str):
    """安全地添加列（如果不存在）。"""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在


# ---------------------------------------------------------------------------
# CanvasAPI 类
# ---------------------------------------------------------------------------

class CanvasAPI:
    """画布后端 API 类（供 FastAPI 路由调用）。"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = _get_db_path(db_path)
        self._init_db()
        self._seed_templates()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            _init_db(conn)

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------

    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有工作流（不含 flow_json 全文，减少传输）。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, description, compiled_from, created_at, updated_at "
                "FROM workflows ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_workflow(self, wf_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流详情（含完整 flow_json）。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE id = ?", (wf_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_workflow(self, data: Dict[str, Any]) -> str:
        """创建工作流，返回新 ID。"""
        wf_id = f"wf_{uuid.uuid4().hex[:8]}"
        name = data.get("name", "未命名工作流")
        description = data.get("description", "")
        compiled_from = data.get("compiled_from", "")
        flow = data.get("flow", {"nodes": [], "edges": []})
        flow_json = json.dumps(flow, ensure_ascii=False)
        now = datetime.utcnow().isoformat(timespec="seconds")

        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO workflows (id, name, description, flow_json, "
                "compiled_from, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (wf_id, name, description, flow_json, compiled_from, now, now),
            )
            conn.commit()
        return wf_id

    def update_workflow(self, wf_id: str, data: Dict[str, Any]) -> bool:
        """更新工作流，返回是否更新成功。"""
        fields = []
        params = []
        for key in ("name", "description", "compiled_from"):
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])
        if "flow" in data:
            fields.append("flow_json = ?")
            params.append(json.dumps(data["flow"], ensure_ascii=False))
        if not fields:
            return False
        fields.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat(timespec="seconds"))
        params.append(wf_id)

        with self._get_conn() as conn:
            cursor = conn.execute(
                f"UPDATE workflows SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_workflow(self, wf_id: str) -> bool:
        """删除工作流，返回是否删除成功。"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM workflows WHERE id = ?", (wf_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 执行记录
    # ------------------------------------------------------------------

    def save_execution_run(
        self,
        workflow_id: str,
        mode: str,
        result: Dict[str, Any],
        summary: Optional[Dict[str, Any]] = None,
        screenshot_b64: Optional[str] = None,
    ) -> str:
        """保存执行记录，返回 run_id。"""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        result_json = json.dumps(result, ensure_ascii=False)
        now = datetime.utcnow().isoformat(timespec="seconds")
        summary_json = json.dumps(summary, ensure_ascii=False) if summary else None

        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO execution_runs (id, workflow_id, mode, result_json, "
                "started_at, finished_at, summary, screenshot_b64) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, workflow_id, mode, result_json, now, now, summary_json, screenshot_b64),
            )
            conn.commit()
        return run_id

    def save_node_logs(self, run_id: str, node_logs: List[Dict[str, Any]]):
        """批量保存节点级执行日志。"""
        with self._get_conn() as conn:
            for log in node_logs:
                nid = f"nl_{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO node_logs (id, execution_run_id, node_id, node_type, "
                    "status, started_at, finished_at, error, output, screenshot_b64) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        nid,
                        run_id,
                        log.get("node_id", ""),
                        log.get("node_type", ""),
                        log.get("status", ""),
                        log.get("started_at"),
                        log.get("finished_at"),
                        log.get("error"),
                        log.get("output"),
                        log.get("screenshot_b64"),
                    ),
                )
            conn.commit()

    def get_execution_runs(self, wf_id: str) -> List[Dict[str, Any]]:
        """获取工作流的历史执行记录。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, workflow_id, mode, result_json, started_at, finished_at "
                "FROM execution_runs WHERE workflow_id = ? "
                "ORDER BY started_at DESC LIMIT 50",
                (wf_id,),
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["result"] = json.loads(d.get("result_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["result"] = {}
            d.pop("result_json", None)
            results.append(d)
        return results

    def get_execution_progress(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取执行进度。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM execution_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            result = json.loads(d.get("result_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            result = {}
        d["result"] = result
        # 从 result 中提取 node_logs 作为进度信息
        d["node_logs"] = result.get("node_logs", [])
        d.pop("result_json", None)
        return d

    # ------------------------------------------------------------------
    # 调色板
    # ------------------------------------------------------------------

    def get_palette(self) -> List[Dict[str, Any]]:
        """获取节点调色板（节点类型列表）。"""
        return PALETTE_NODES

    # ------------------------------------------------------------------
    # AI 编译 → Flow
    # ------------------------------------------------------------------

    def compile_to_flow(self, query: str) -> Dict[str, List]:
        """自然语言 → Flow 格式（AI 编译 + 转画布格式）。

        Args:
            query: 自然语言描述

        Returns:
            {"nodes": [...], "edges": [...]}
        """
        from ai_shadowbot.config import Config
        from ai_shadowbot.compiler import WorkflowCompiler

        config = Config()
        compiler = WorkflowCompiler(config)
        result = compiler.compile(query)

        if not result.success or result.workflow is None:
            return {"nodes": [], "edges": []}

        return workflow_to_flow(result.workflow)

    # ------------------------------------------------------------------
    # Flow 校验
    # ------------------------------------------------------------------

    def validate_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """校验画布提交的 Flow（转 Workflow 后过 WorkflowSchema）。

        Args:
            flow: {"nodes": [...], "edges": [...]}

        Returns:
            {"valid": bool, "errors": [str, ...]}
        """
        try:
            flow_nodes = flow.get("nodes", [])
            flow_edges = flow.get("edges", [])
            wf = flow_to_workflow(flow_nodes, flow_edges)
            WorkflowSchema.validate(wf)
            return {"valid": True, "errors": []}
        except WorkflowValidationError as e:
            return {"valid": False, "errors": [str(e)]}
        except Exception as e:
            return {"valid": False, "errors": [f"校验异常: {e}"]}

    # ------------------------------------------------------------------
    # 触发器 CRUD（Phase 3 / F009）
    # ------------------------------------------------------------------

    def list_triggers(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有触发器，可选按工作流筛选。"""
        with self._get_conn() as conn:
            if workflow_id:
                rows = conn.execute(
                    "SELECT * FROM triggers WHERE workflow_id = ? ORDER BY created_at DESC",
                    (workflow_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM triggers ORDER BY created_at DESC"
                ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["config"] = json.loads(d.get("config", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["config"] = {}
            results.append(d)
        return results

    def create_trigger(self, data: Dict[str, Any]) -> str:
        """创建触发器，返回新 ID。"""
        tid = f"trg_{uuid.uuid4().hex[:8]}"
        workflow_id = data.get("workflow_id", "")
        if not workflow_id:
            raise ValueError("workflow_id 不能为空")
        typ = data.get("type", "manual")
        config = json.dumps(data.get("config", {}), ensure_ascii=False)
        enabled = 1 if data.get("enabled", True) else 0
        next_run = data.get("next_run")
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO triggers (id, workflow_id, type, config, enabled, next_run, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tid, workflow_id, typ, config, enabled, next_run, now),
            )
            conn.commit()
        return tid

    def update_trigger(self, tid: str, data: Dict[str, Any]) -> bool:
        """更新触发器。"""
        fields = []
        params = []
        for key in ("workflow_id", "type", "enabled", "last_run", "next_run"):
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])
        if "config" in data:
            fields.append("config = ?")
            params.append(json.dumps(data["config"], ensure_ascii=False))
        if not fields:
            return False
        params.append(tid)
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"UPDATE triggers SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_trigger(self, tid: str) -> bool:
        """删除触发器。"""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM triggers WHERE id = ?", (tid,))
            conn.commit()
            return cursor.rowcount > 0

    def toggle_trigger(self, tid: str) -> Optional[bool]:
        """切换触发器启用/禁用状态，返回新的 enabled 值。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT enabled FROM triggers WHERE id = ?", (tid,)
            ).fetchone()
            if row is None:
                return None
            new_enabled = 0 if row["enabled"] else 1
            conn.execute(
                "UPDATE triggers SET enabled = ? WHERE id = ?",
                (new_enabled, tid),
            )
            conn.commit()
            return bool(new_enabled)

    # ------------------------------------------------------------------
    # 执行日志查询（Phase 3 / F010）
    # ------------------------------------------------------------------

    def get_execution_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取某次执行的完整详情（含节点日志）。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM execution_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["result"] = json.loads(d.get("result_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["result"] = {}
        try:
            d["summary"] = json.loads(d.get("summary", "null"))
        except (json.JSONDecodeError, TypeError):
            d["summary"] = None
        d.pop("result_json", None)
        # 附加节点日志
        d["node_logs"] = self.get_node_logs(run_id)
        return d

    def get_node_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """获取某次执行的节点级日志。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM node_logs WHERE execution_run_id = ? ORDER BY started_at ASC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_node_screenshot(self, run_id: str, node_id: str) -> Optional[str]:
        """获取某节点的执行截图（base64）。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT screenshot_b64 FROM node_logs "
                "WHERE execution_run_id = ? AND node_id = ? AND screenshot_b64 IS NOT NULL "
                "LIMIT 1",
                (run_id, node_id),
            ).fetchone()
        return row["screenshot_b64"] if row else None

    def get_execution_runs_extended(self, wf_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取工作流的历史执行记录（含 summary）。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, workflow_id, mode, result_json, started_at, finished_at, summary "
                "FROM execution_runs WHERE workflow_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (wf_id, limit),
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["result"] = json.loads(d.get("result_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["result"] = {}
            try:
                d["summary"] = json.loads(d.get("summary", "null"))
            except (json.JSONDecodeError, TypeError):
                d["summary"] = None
            d.pop("result_json", None)
            results.append(d)
        return results

    # ------------------------------------------------------------------
    # 模板 CRUD（Phase 3 / F011）
    # ------------------------------------------------------------------

    def list_templates(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出模板，可按分类筛选和搜索。"""
        with self._get_conn() as conn:
            query = "SELECT * FROM templates WHERE 1=1"
            params = []
            if category:
                query += " AND category = ?"
                params.append(category)
            if search:
                query += " AND (name LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            query += " ORDER BY usage_count DESC, created_at DESC"
            rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            try:
                d["flow_json"] = json.loads(d.get("flow_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["flow_json"] = {}
            results.append(d)
        return results

    def get_template(self, tid: str) -> Optional[Dict[str, Any]]:
        """获取模板详情。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE id = ?", (tid,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        try:
            d["flow_json"] = json.loads(d.get("flow_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["flow_json"] = {}
        return d

    def create_from_template(self, template_id: str, name: Optional[str] = None) -> Optional[str]:
        """从模板创建工作流，返回新工作流 ID。"""
        tmpl = self.get_template(template_id)
        if tmpl is None:
            return None
        flow = tmpl.get("flow_json", {})
        if isinstance(flow, str):
            try:
                flow = json.loads(flow)
            except (json.JSONDecodeError, TypeError):
                flow = {"nodes": [], "edges": []}
        wf_name = name or f"来自模板: {tmpl.get('name', '未命名')}"
        wf_id = self.create_workflow({
            "name": wf_name,
            "description": tmpl.get("description", ""),
            "flow": flow,
        })
        # 增加使用计数
        self.increment_template_usage(template_id)
        return wf_id

    def save_as_template(self, workflow_id: str, data: Dict[str, Any]) -> Optional[str]:
        """将工作流另存为模板，返回模板 ID。"""
        wf = self.get_workflow(workflow_id)
        if wf is None:
            return None
        # 从 flow_json 中剔除敏感字段
        try:
            flow = json.loads(wf.get("flow_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            flow = {"nodes": [], "edges": []}
        # 剔除 params 中的敏感字段
        _sensitive_keys = {"password", "token", "api_key", "secret", "credential", "auth"}
        for node in flow.get("nodes", []):
            params = node.get("data", {}).get("params", {})
            for skey in list(params.keys()):
                if any(s in skey.lower() for s in _sensitive_keys):
                    params[skey] = "***"

        tid = f"tpl_{uuid.uuid4().hex[:8]}"
        name = data.get("name", wf.get("name", "未命名"))
        description = data.get("description", "")
        category = data.get("category", "通用")
        tags = json.dumps(data.get("tags", []), ensure_ascii=False)
        author = data.get("author", "AI 编译")
        flow_json = json.dumps(flow, ensure_ascii=False)
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO templates (id, name, description, category, flow_json, "
                "tags, author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tid, name, description, category, flow_json, tags, author, now),
            )
            conn.commit()
        return tid

    def increment_template_usage(self, tid: str) -> bool:
        """增加模板使用计数。"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE templates SET usage_count = usage_count + 1 WHERE id = ?",
                (tid,),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 种子模板（Phase 3 / F011）
    # ------------------------------------------------------------------

    def _seed_templates(self):
        """预置种子模板（模板表为空时插入）。"""
        with self._get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) as cnt FROM templates").fetchone()["cnt"]
            if count > 0:
                return

        seeds = [
            {
                "name": "每日邮件对账",
                "description": "每天早上自动打开邮箱，查收邮件并截图记录，根据条件判断是否执行后续操作",
                "category": "办公",
                "tags": ["邮件", "Excel", "日报"],
                "flow_json": json.dumps({
                    "nodes": [
                        {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                         "data": {"label": "开始", "node_type": "start", "params": {}}},
                        {"id": "n2", "type": "default", "position": {"x": 100, "y": 170},
                         "data": {"label": "打开邮箱", "node_type": "atomic",
                                  "params": {"atomic_action": "open_app", "name": "mail"}}},
                        {"id": "n3", "type": "default", "position": {"x": 100, "y": 290},
                         "data": {"label": "等待加载", "node_type": "wait",
                                  "params": {"seconds": 3}}},
                        {"id": "n4", "type": "default", "position": {"x": 100, "y": 410},
                         "data": {"label": "截图", "node_type": "atomic",
                                  "params": {"atomic_action": "screenshot"}}},
                        {"id": "n5", "type": "default", "position": {"x": 100, "y": 530},
                         "data": {"label": "条件判断", "node_type": "condition",
                                  "params": {"expression": "true"}}},
                        {"id": "n6", "type": "default", "position": {"x": 100, "y": 650},
                         "data": {"label": "结束", "node_type": "end", "params": {}}},
                    ],
                    "edges": [
                        {"id": "e-n1-n2", "source": "n1", "target": "n2"},
                        {"id": "e-n2-n3", "source": "n2", "target": "n3"},
                        {"id": "e-n3-n4", "source": "n3", "target": "n4"},
                        {"id": "e-n4-n5", "source": "n4", "target": "n5"},
                        {"id": "e-n5-n6", "source": "n5", "target": "n6", "label": "true"},
                    ],
                }, ensure_ascii=False),
                "author": "AI 编译",
            },
            {
                "name": "网页截图存档",
                "description": "打开目标网页，等待加载完成后截图保存",
                "category": "网页",
                "tags": ["网页", "截图", "存档"],
                "flow_json": json.dumps({
                    "nodes": [
                        {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                         "data": {"label": "开始", "node_type": "start", "params": {}}},
                        {"id": "n2", "type": "default", "position": {"x": 100, "y": 170},
                         "data": {"label": "打开浏览器", "node_type": "atomic",
                                  "params": {"atomic_action": "open_app", "name": "chrome"}}},
                        {"id": "n3", "type": "default", "position": {"x": 100, "y": 290},
                         "data": {"label": "等待加载", "node_type": "wait",
                                  "params": {"seconds": 5}}},
                        {"id": "n4", "type": "default", "position": {"x": 100, "y": 410},
                         "data": {"label": "截图", "node_type": "atomic",
                                  "params": {"atomic_action": "screenshot"}}},
                        {"id": "n5", "type": "default", "position": {"x": 100, "y": 530},
                         "data": {"label": "保存", "node_type": "atomic",
                                  "params": {"atomic_action": "screenshot"}}},
                        {"id": "n6", "type": "default", "position": {"x": 100, "y": 650},
                         "data": {"label": "结束", "node_type": "end", "params": {}}},
                    ],
                    "edges": [
                        {"id": "e-n1-n2", "source": "n1", "target": "n2"},
                        {"id": "e-n2-n3", "source": "n2", "target": "n3"},
                        {"id": "e-n3-n4", "source": "n3", "target": "n4"},
                        {"id": "e-n4-n5", "source": "n4", "target": "n5"},
                        {"id": "e-n5-n6", "source": "n5", "target": "n6"},
                    ],
                }, ensure_ascii=False),
                "author": "AI 编译",
            },
            {
                "name": "文件整理",
                "description": "打开文件管理器，执行点击操作选中文件，输入关键词筛选，最后截图确认",
                "category": "办公",
                "tags": ["文件", "整理", "批量"],
                "flow_json": json.dumps({
                    "nodes": [
                        {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                         "data": {"label": "开始", "node_type": "start", "params": {}}},
                        {"id": "n2", "type": "default", "position": {"x": 100, "y": 170},
                         "data": {"label": "打开资源管理器", "node_type": "atomic",
                                  "params": {"atomic_action": "open_app", "name": "explorer"}}},
                        {"id": "n3", "type": "default", "position": {"x": 100, "y": 290},
                         "data": {"label": "点击文件夹", "node_type": "atomic",
                                  "params": {"atomic_action": "click", "x": 200, "y": 300}}},
                        {"id": "n4", "type": "default", "position": {"x": 100, "y": 410},
                         "data": {"label": "输入筛选", "node_type": "atomic",
                                  "params": {"atomic_action": "type_text", "text": "report"}}},
                        {"id": "n5", "type": "default", "position": {"x": 100, "y": 530},
                         "data": {"label": "截图确认", "node_type": "atomic",
                                  "params": {"atomic_action": "screenshot"}}},
                        {"id": "n6", "type": "default", "position": {"x": 100, "y": 650},
                         "data": {"label": "结束", "node_type": "end", "params": {}}},
                    ],
                    "edges": [
                        {"id": "e-n1-n2", "source": "n1", "target": "n2"},
                        {"id": "e-n2-n3", "source": "n2", "target": "n3"},
                        {"id": "e-n3-n4", "source": "n3", "target": "n4"},
                        {"id": "e-n4-n5", "source": "n4", "target": "n5"},
                        {"id": "e-n5-n6", "source": "n5", "target": "n6"},
                    ],
                }, ensure_ascii=False),
                "author": "AI 编译",
            },
            {
                "name": "系统监控",
                "description": "定时截图监控系统状态，通过条件判断异常并滚动查看详情",
                "category": "系统",
                "tags": ["监控", "系统", "运维"],
                "flow_json": json.dumps({
                    "nodes": [
                        {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                         "data": {"label": "开始", "node_type": "start", "params": {}}},
                        {"id": "n2", "type": "default", "position": {"x": 100, "y": 170},
                         "data": {"label": "截图", "node_type": "atomic",
                                  "params": {"atomic_action": "screenshot"}}},
                        {"id": "n3", "type": "default", "position": {"x": 100, "y": 290},
                         "data": {"label": "检查状态", "node_type": "condition",
                                  "params": {"expression": "true"}}},
                        {"id": "n4", "type": "default", "position": {"x": 100, "y": 410},
                         "data": {"label": "滚动查看", "node_type": "atomic",
                                  "params": {"atomic_action": "scroll", "dy": -500}}},
                        {"id": "n5", "type": "default", "position": {"x": 300, "y": 410},
                         "data": {"label": "结束", "node_type": "end", "params": {}}},
                    ],
                    "edges": [
                        {"id": "e-n1-n2", "source": "n1", "target": "n2"},
                        {"id": "e-n2-n3", "source": "n2", "target": "n3"},
                        {"id": "e-n3-n4", "source": "n3", "target": "n4", "label": "true"},
                        {"id": "e-n3-n5", "source": "n3", "target": "n5", "label": "false"},
                    ],
                }, ensure_ascii=False),
                "author": "AI 编译",
            },
        ]

        with self._get_conn() as conn:
            for seed in seeds:
                conn.execute(
                    "INSERT INTO templates (id, name, description, category, flow_json, "
                    "tags, author, usage_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (
                        f"tpl_{uuid.uuid4().hex[:8]}",
                        seed["name"],
                        seed["description"],
                        seed["category"],
                        seed["flow_json"],
                        json.dumps(seed["tags"], ensure_ascii=False),
                        seed["author"],
                        datetime.utcnow().isoformat(timespec="seconds"),
                    ),
                )
            conn.commit()

    # ------------------------------------------------------------------
    # 执行工作流
    # ------------------------------------------------------------------

    def execute_workflow(
        self,
        wf_id: str,
        mode: str = "dry_run",
    ) -> Optional[Dict[str, Any]]:
        """执行工作流（通过 Engine）。

        Args:
            wf_id: 工作流 ID
            mode: "dry_run" 或 "real"

        Returns:
            包含 run_id 和 execution 结果的 dict，失败返回 None
        """
        wf_data = self.get_workflow(wf_id)
        if wf_data is None:
            return None

        try:
            flow = json.loads(wf_data.get("flow_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            return {"error": "flow_json 解析失败"}

        flow_nodes = flow.get("nodes", [])
        flow_edges = flow.get("edges", [])
        workflow = flow_to_workflow(flow_nodes, flow_edges)

        from ai_shadowbot.config import Config
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails, EmergencyStop
        from ai_shadowbot.observer import Observer

        config = Config()
        guardrails = Guardrails(config=config, strategy="single")
        emergency = EmergencyStop()
        observer = Observer(screen_mask_sensitive=config.screen_mask_sensitive)
        executor = Executor(
            dry_run=(mode != "real"),
            guardrails=guardrails,
            emergency_stop=emergency,
            observer=observer,
        )
        engine = Engine(
            executor=executor,
            guardrails=guardrails,
            emergency_stop=emergency,
        )

        is_dry = mode == "dry_run"
        if is_dry:
            exec_result = engine.dry_run(workflow)
        else:
            exec_result = engine.execute(workflow)

        # 保存执行记录
        execution_data = {
            "success": exec_result.success,
            "final_state": exec_result.final_state,
            "total_duration": exec_result.total_duration,
            "node_count": len(exec_result.node_logs),
            "final_variables": exec_result.final_variables,
            "node_logs": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "status": n.status,
                    "error": n.error,
                    "duration": round(
                        (n.finished_at or 0) - (n.started_at or 0), 2
                    ),
                }
                for n in exec_result.node_logs
            ],
        }

        run_id = self.save_execution_run(wf_id, mode, execution_data)

        # 持久化节点级日志
        node_log_records = []
        for n in exec_result.node_logs:
            node_log_records.append({
                "node_id": n.node_id,
                "node_type": n.node_type,
                "status": n.status,
                "started_at": n.started_at,
                "finished_at": n.finished_at,
                "error": n.error,
                "output": str(n.action_result.summary if n.action_result else ""),
                "screenshot_b64": None,
            })
        self.save_node_logs(run_id, node_log_records)

        return {
            "run_id": run_id,
            "mode": mode,
            "execution": execution_data,
        }
