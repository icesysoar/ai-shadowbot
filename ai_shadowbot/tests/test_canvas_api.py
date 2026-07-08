"""Canvas API 测试（F008）—— SQLite 持久化 + Flow↔Workflow 转换 + 调色板。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import pytest

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)


# ---------------------------------------------------------------------------
# 辅助：样本数据
# ---------------------------------------------------------------------------

SAMPLE_FLOW_NODES = [
    {"id": "n1", "type": "start", "position": {"x": 100, "y": 50},
     "data": {"label": "开始", "node_type": "start", "params": {}}},
    {"id": "n2", "type": "atomic", "position": {"x": 100, "y": 150},
     "data": {"label": "打开记事本", "node_type": "atomic",
              "params": {"atomic_action": "open_app", "name": "记事本"}}},
    {"id": "n3", "type": "atomic", "position": {"x": 100, "y": 250},
     "data": {"label": "输入文本", "node_type": "atomic",
              "params": {"atomic_action": "type_text", "text": "Hello"}}},
    {"id": "n4", "type": "end", "position": {"x": 100, "y": 350},
     "data": {"label": "结束", "node_type": "end", "params": {}}},
]

SAMPLE_FLOW_EDGES = [
    {"id": "e1-2", "source": "n1", "target": "n2", "label": ""},
    {"id": "e2-3", "source": "n2", "target": "n3", "label": ""},
    {"id": "e3-4", "source": "n3", "target": "n4", "label": ""},
]

SAMPLE_FLOW = {"nodes": SAMPLE_FLOW_NODES, "edges": SAMPLE_FLOW_EDGES}


@pytest.fixture
def canvas_api():
    from ai_shadowbot.canvas_api import CanvasAPI
    # 使用临时数据库文件
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    api = CanvasAPI(db_path=db_path)
    yield api
    # 清理
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ===================================================================
# Flow↔Workflow 转换测试
# ===================================================================

class TestFlowWorkflowConversion:
    """测试前后端数据格式双向转换。"""

    def test_flow_to_workflow_basic(self):
        """基本线性流程转换：4 节点线性 DAG → Workflow。"""
        from ai_shadowbot.canvas_api import flow_to_workflow
        wf = flow_to_workflow(SAMPLE_FLOW_NODES, SAMPLE_FLOW_EDGES)
        assert wf is not None
        assert wf.name == "未命名工作流"
        assert len(wf.nodes) == 4
        # 检查节点链接
        n1 = wf.nodes[0]
        assert n1.type.value == "start"
        assert n1.next == "n2"
        n2 = wf.nodes[1]
        assert n2.type.value == "atomic"
        assert n2.params.get("atomic_action") == "open_app"
        assert n2.next == "n3"

    def test_flow_to_workflow_condition_branches(self):
        """含条件分支的 Flow → Workflow。"""
        from ai_shadowbot.canvas_api import flow_to_workflow
        nodes = [
            {"id": "n1", "type": "start", "position": {"x": 0, "y": 0},
             "data": {"label": "开始", "node_type": "start", "params": {}}},
            {"id": "n2", "type": "condition", "position": {"x": 0, "y": 100},
             "data": {"label": "判断", "node_type": "condition",
                      "params": {"expression": "count > 5"}}},
            {"id": "n3", "type": "end", "position": {"x": 0, "y": 200},
             "data": {"label": "结束", "node_type": "end", "params": {}}},
            {"id": "n4", "type": "end", "position": {"x": 200, "y": 200},
             "data": {"label": "其他结束", "node_type": "end", "params": {}}},
        ]
        edges = [
            {"id": "e1-2", "source": "n1", "target": "n2"},
            {"id": "e2-3", "source": "n2", "target": "n3", "label": "yes"},
            {"id": "e2-4", "source": "n2", "target": "n4", "label": "no"},
        ]
        wf = flow_to_workflow(nodes, edges)
        assert len(wf.nodes) == 4
        cond_node = [n for n in wf.nodes if n.type.value == "condition"][0]
        assert len(cond_node.branches) == 2
        branch_labels = {b.get("label", "") for b in cond_node.branches}
        assert "yes" in branch_labels or "true" in branch_labels
        assert "no" in branch_labels or "false" in branch_labels

    def test_workflow_to_flow_basic(self):
        """Workflow → Flow 基本转换。"""
        from ai_shadowbot.workflow import Workflow, Node, NodeType
        from ai_shadowbot.canvas_api import workflow_to_flow
        wf = Workflow(
            id="wf_test",
            name="测试工作流",
            nodes=[
                Node(id="n1", type=NodeType.start, label="开始", next="n2"),
                Node(id="n2", type=NodeType.atomic, label="打开",
                     params={"atomic_action": "open_app", "name": "记事本"}, next="n3"),
                Node(id="n3", type=NodeType.end, label="结束"),
            ],
        )
        result = workflow_to_flow(wf)
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2  # n1→n2, n2→n3
        # 检查画布坐标存在
        for node in result["nodes"]:
            assert "position" in node
            assert "data" in node

    def test_workflow_to_flow_with_branches(self):
        """含条件分支的 Workflow → Flow。"""
        from ai_shadowbot.workflow import Workflow, Node, NodeType
        from ai_shadowbot.canvas_api import workflow_to_flow
        wf = Workflow(
            id="wf_test",
            name="分支工作流",
            nodes=[
                Node(id="n1", type=NodeType.start, label="开始", next="n2"),
                Node(id="n2", type=NodeType.condition, label="判断",
                     params={"expression": "x > 5"},
                     branches=[
                         {"condition": "true", "next": "n3", "label": "yes"},
                         {"condition": "false", "next": "n4", "label": "no"},
                     ]),
                Node(id="n3", type=NodeType.atomic, label="成功",
                     params={"atomic_action": "screenshot"}, next="n4"),
                Node(id="n4", type=NodeType.end, label="结束"),
            ],
        )
        result = workflow_to_flow(wf)
        assert len(result["edges"]) == 4  # n1→n2, n2→n3, n2→n4, n3→n4
        condition_edges = [e for e in result["edges"] if e["source"] == "n2"]
        assert len(condition_edges) == 2
        # 分支边应有 label
        assert any(e.get("label") for e in condition_edges)

    def test_flow_roundtrip(self):
        """Flow → Workflow → Flow 往返转换不丢数据。"""
        from ai_shadowbot.canvas_api import flow_to_workflow, workflow_to_flow
        wf = flow_to_workflow(SAMPLE_FLOW_NODES, SAMPLE_FLOW_EDGES)
        result = workflow_to_flow(wf)
        # 节点数一致
        assert len(result["nodes"]) == len(SAMPLE_FLOW_NODES)
        # 边数一致（或更多——因为可能加了位置边）
        assert len(result["edges"]) >= len(SAMPLE_FLOW_EDGES)


# ===================================================================
# CanvasAPI CRUD 测试
# ===================================================================

class TestCanvasAPICRUD:
    """SQLite 持久化 CRUD 操作测试。"""

    def test_create_list_workflow(self, canvas_api):
        """创建并列出工作流。"""
        wf_id = canvas_api.create_workflow({
            "name": "测试工作流",
            "flow": SAMPLE_FLOW,
        })
        assert wf_id is not None
        assert len(wf_id) > 0

        workflows = canvas_api.list_workflows()
        assert len(workflows) >= 1
        names = [w["name"] for w in workflows]
        assert "测试工作流" in names

    def test_get_workflow(self, canvas_api):
        """按 ID 获取工作流详情。"""
        wf_id = canvas_api.create_workflow({
            "name": "获取测试",
            "flow": SAMPLE_FLOW,
        })
        wf = canvas_api.get_workflow(wf_id)
        assert wf is not None
        assert wf["name"] == "获取测试"
        assert "flow_json" in wf
        flow = json.loads(wf["flow_json"])
        assert len(flow["nodes"]) == 4

    def test_get_workflow_not_found(self, canvas_api):
        """获取不存在的工作流返回 None。"""
        wf = canvas_api.get_workflow("nonexistent")
        assert wf is None

    def test_update_workflow(self, canvas_api):
        """更新工作流。"""
        wf_id = canvas_api.create_workflow({
            "name": "原名称",
            "flow": SAMPLE_FLOW,
        })
        updated = canvas_api.update_workflow(wf_id, {
            "name": "新名称",
        })
        assert updated is True
        wf = canvas_api.get_workflow(wf_id)
        assert wf["name"] == "新名称"

    def test_update_workflow_not_found(self, canvas_api):
        """更新不存在的工作流返回 False。"""
        result = canvas_api.update_workflow("nonexistent", {"name": "新名称"})
        assert result is False

    def test_delete_workflow(self, canvas_api):
        """删除工作流。"""
        wf_id = canvas_api.create_workflow({
            "name": "待删除",
            "flow": SAMPLE_FLOW,
        })
        deleted = canvas_api.delete_workflow(wf_id)
        assert deleted is True
        wf = canvas_api.get_workflow(wf_id)
        assert wf is None

    def test_delete_workflow_not_found(self, canvas_api):
        """删除不存在的工作流返回 False。"""
        result = canvas_api.delete_workflow("nonexistent")
        assert result is False

    def test_create_workflow_with_description(self, canvas_api):
        """创建时带描述和来源。"""
        wf_id = canvas_api.create_workflow({
            "name": "AI 生成",
            "description": "由 AI 编译",
            "compiled_from": "帮我打开记事本",
            "flow": SAMPLE_FLOW,
        })
        assert wf_id is not None
        wf = canvas_api.get_workflow(wf_id)
        assert wf.get("description", "") == "由 AI 编译"


# ===================================================================
# 执行记录测试
# ===================================================================

class TestExecutionRuns:
    """执行记录 CRUD 测试。"""

    def test_save_execution_run(self, canvas_api):
        """保存执行记录。"""
        wf_id = canvas_api.create_workflow({
            "name": "执行测试",
            "flow": SAMPLE_FLOW,
        })
        run_id = canvas_api.save_execution_run(wf_id, "dry_run", {
            "success": True,
            "final_state": "SUCCESS",
            "node_logs": [],
        })
        assert run_id is not None

        runs = canvas_api.get_execution_runs(wf_id)
        assert len(runs) >= 1
        assert runs[0]["mode"] == "dry_run"

    def test_get_execution_runs_empty(self, canvas_api):
        """无执行记录时返回空列表。"""
        runs = canvas_api.get_execution_runs("nonexistent")
        assert isinstance(runs, list)
        assert len(runs) == 0


# ===================================================================
# 调色板端点测试
# ===================================================================

class TestPalette:
    """节点调色板端点测试。"""

    def test_get_palette_returns_categories(self, canvas_api):
        """调色板返回分类节点列表。"""
        palette = canvas_api.get_palette()
        assert isinstance(palette, list)
        assert len(palette) > 0
        categories = {p["category"] for p in palette}
        # 应包含主要分类
        assert "鼠标" in categories or "Mouse" in categories


# ===================================================================
# 编译→Flow 测试
# ===================================================================

class TestCompileToFlow:
    """AI 编译到 Flow 的适配测试。"""

    def test_compile_to_flow(self, canvas_api):
        """自然语言编译 → Flow 格式。"""
        result = canvas_api.compile_to_flow("打开记事本并输入Hello")
        assert result is not None
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) >= 3  # start + action + end

    def test_compile_to_flow_empty_query(self, canvas_api):
        """空查询编译返回空 flow。"""
        result = canvas_api.compile_to_flow("")
        assert result is not None
        assert "nodes" in result
        assert "edges" in result


# ===================================================================
# Flow 校验测试
# ===================================================================

class TestFlowValidation:
    """Flow 校验测试。"""

    def test_validate_valid_flow(self, canvas_api):
        """合法 Flow 校验通过。"""
        result = canvas_api.validate_flow(SAMPLE_FLOW)
        assert result.get("valid") is True
        assert "errors" not in result or len(result.get("errors", [])) == 0

    def test_validate_flow_missing_start(self, canvas_api):
        """缺少 start 节点的 Flow 校验失败。"""
        bad_flow = {
            "nodes": [
                {"id": "n1", "type": "atomic", "position": {"x": 0, "y": 0},
                 "data": {"node_type": "atomic", "params": {}}},
            ],
            "edges": [],
        }
        result = canvas_api.validate_flow(bad_flow)
        assert result.get("valid") is False


# ===================================================================
# 执行进度测试（stub 模式）
# ===================================================================

class TestExecutionProgress:
    """执行进度查询测试。"""

    def test_get_execution_progress_not_found(self, canvas_api):
        """不存在的 run_id 返回 None。"""
        progress = canvas_api.get_execution_progress("nonexistent_run")
        assert progress is None

    def test_get_execution_progress(self, canvas_api):
        """保存后查询执行进度。"""
        wf_id = canvas_api.create_workflow({
            "name": "进度测试",
            "flow": SAMPLE_FLOW,
        })
        run_id = canvas_api.save_execution_run(wf_id, "dry_run", {
            "success": True,
            "final_state": "SUCCESS",
        })
        progress = canvas_api.get_execution_progress(run_id)
        assert progress is not None
        assert progress["mode"] == "dry_run"
        assert progress["workflow_id"] == wf_id


# ===================================================================
# 执行工作流测试（集成 Engine）
# ===================================================================

class TestExecuteWorkflow:
    """执行工作流集成测试。"""

    def test_execute_workflow_dry_run(self, canvas_api):
        """dry_run 模式执行工作流。"""
        wf_id = canvas_api.create_workflow({
            "name": "执行测试",
            "flow": SAMPLE_FLOW,
        })
        result = canvas_api.execute_workflow(wf_id, mode="dry_run")
        assert result is not None
        assert "run_id" in result
        assert "execution" in result or "result" in result or "status" in result

    def test_execute_workflow_not_found(self, canvas_api):
        """执行不存在的工作流返回错误。"""
        result = canvas_api.execute_workflow("nonexistent", mode="dry_run")
        assert result is None or result.get("error") is not None
