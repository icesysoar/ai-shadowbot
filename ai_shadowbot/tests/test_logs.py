"""执行日志测试（Phase 3 / F010）—— 节点日志 CRUD + 截图存储。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import pytest

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)


@pytest.fixture
def canvas_api():
    from ai_shadowbot.canvas_api import CanvasAPI
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    api = CanvasAPI(db_path=db_path)
    yield api
    if os.path.exists(db_path):
        os.unlink(db_path)


SAMPLE_FLOW = {
    "nodes": [
        {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
         "data": {"label": "开始", "node_type": "start", "params": {}}},
        {"id": "n2", "type": "default", "position": {"x": 100, "y": 150},
         "data": {"label": "截图", "node_type": "atomic",
                  "params": {"atomic_action": "screenshot"}}},
        {"id": "n3", "type": "default", "position": {"x": 100, "y": 250},
         "data": {"label": "结束", "node_type": "end", "params": {}}},
    ],
    "edges": [
        {"id": "e-n1-n2", "source": "n1", "target": "n2"},
        {"id": "e-n2-n3", "source": "n2", "target": "n3"},
    ],
}


# ---------------------------------------------------------------------------
# 节点日志 CRUD 测试
# ---------------------------------------------------------------------------

class TestNodeLogs:
    def test_save_and_get_node_logs(self, canvas_api):
        """保存并获取节点级日志。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": SAMPLE_FLOW})

        # 先执行获得 run_id
        result = canvas_api.execute_workflow(wf_id, mode="dry_run")
        assert result is not None
        run_id = result["run_id"]

        # 获取节点日志
        node_logs = canvas_api.get_node_logs(run_id)
        assert len(node_logs) > 0

        # 检查节点日志结构
        log = node_logs[0]
        assert "node_id" in log
        assert "status" in log

    def test_get_execution_detail(self, canvas_api):
        """获取执行详情（含节点日志）。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": SAMPLE_FLOW})
        result = canvas_api.execute_workflow(wf_id, mode="dry_run")
        run_id = result["run_id"]

        detail = canvas_api.get_execution_detail(run_id)
        assert detail is not None
        assert detail["id"] == run_id
        assert "node_logs" in detail
        assert len(detail["node_logs"]) > 0

    def test_execution_detail_not_found(self, canvas_api):
        """不存在的执行详情返回 None。"""
        detail = canvas_api.get_execution_detail("nonexistent")
        assert detail is None

    def test_node_logs_empty(self, canvas_api):
        """没有节点日志时返回空列表。"""
        logs = canvas_api.get_node_logs("nonexistent_run")
        assert logs == []

    def test_save_node_logs_directly(self, canvas_api):
        """直接保存节点日志。"""
        # 先创建一个 execution run
        run_id = canvas_api.save_execution_run("wf_test", "dry_run", {"success": True})
        logs = [
            {"node_id": "n1", "node_type": "start", "status": "SUCCESS",
             "started_at": 100.0, "finished_at": 101.0, "error": None, "output": ""},
            {"node_id": "n2", "node_type": "atomic", "status": "SUCCESS",
             "started_at": 101.0, "finished_at": 102.0, "error": None,
             "output": "screenshot taken", "screenshot_b64": None},
        ]
        canvas_api.save_node_logs(run_id, logs)

        retrieved = canvas_api.get_node_logs(run_id)
        assert len(retrieved) == 2
        # 按 started_at 排序
        assert retrieved[0]["node_id"] == "n1"


# ---------------------------------------------------------------------------
# 截图存储测试
# ---------------------------------------------------------------------------

class TestScreenshotStorage:
    def test_get_node_screenshot_none(self, canvas_api):
        """没有截图时返回 None。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": SAMPLE_FLOW})
        result = canvas_api.execute_workflow(wf_id, mode="dry_run")
        run_id = result["run_id"]

        ss = canvas_api.get_node_screenshot(run_id, "n1")
        assert ss is None

    def test_save_and_get_screenshot(self, canvas_api):
        """保存并获取截图（base64）。"""
        run_id = canvas_api.save_execution_run("wf_test", "dry_run", {"success": True})
        test_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAElFTkSuQmCC"

        # 保存带截图的节点日志
        canvas_api.save_node_logs(run_id, [
            {"node_id": "n1", "node_type": "atomic", "status": "SUCCESS",
             "started_at": 100.0, "finished_at": 101.0, "error": None,
             "output": "", "screenshot_b64": test_b64},
        ])

        ss = canvas_api.get_node_screenshot(run_id, "n1")
        assert ss == test_b64

    def test_get_execution_runs_extended(self, canvas_api):
        """扩展执行历史含 summary。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": SAMPLE_FLOW})
        summary = {"success": True, "node_count": 3, "total_duration": 1.5}
        result = canvas_api.execute_workflow(wf_id, mode="dry_run")
        run_id = result["run_id"]

        runs = canvas_api.get_execution_runs_extended(wf_id)
        assert len(runs) >= 1
        # 检查字段
        assert "started_at" in runs[0]
        assert "mode" in runs[0]

    def test_execution_runs_with_summary(self, canvas_api):
        """用 summary 参数保存执行记录。"""
        summary = {"success": True, "node_count": 2, "total_duration": 0.5}
        run_id = canvas_api.save_execution_run(
            "wf_test", "dry_run", {"success": True}, summary=summary,
        )
        detail = canvas_api.get_execution_detail(run_id)
        assert detail is not None
        assert detail["summary"]["success"] is True
        assert detail["summary"]["node_count"] == 2
