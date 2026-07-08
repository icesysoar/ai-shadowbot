"""Phase 3 API 集成测试 —— 所有新增 API 端点。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)


# ---------------------------------------------------------------------------
# 创建测试用的 FastAPI app
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_scheduler_start():
    """禁用调度器自动启动（测试用）。"""
    with patch('ai_shadowbot.l5_gateway._scheduler.start'):
        yield


@pytest.fixture
def client(patch_scheduler_start):
    """创建测试客户端（使用临时数据库）。"""
    from ai_shadowbot.canvas_api import CanvasAPI
    from ai_shadowbot.l5_gateway import build_app, _canvas_api, _scheduler

    # 替换为临时数据库
    orig_db_path = _canvas_api._db_path
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    _canvas_api._db_path = test_db
    # 重新初始化（创建新表+种子）
    _canvas_api._init_db()
    _canvas_api._seed_templates()

    app = build_app()
    with TestClient(app) as c:
        yield c

    # 清理
    _canvas_api._db_path = orig_db_path
    _canvas_api._init_db()
    if os.path.exists(test_db):
        os.unlink(test_db)


def _create_test_workflow(client) -> str:
    """创建测试工作流，返回 ID。"""
    resp = client.post("/api/workflows", json={
        "name": "集成测试",
        "flow": {
            "nodes": [
                {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                 "data": {"label": "开始", "node_type": "start", "params": {}}},
                {"id": "n2", "type": "default", "position": {"x": 100, "y": 150},
                 "data": {"label": "结束", "node_type": "end", "params": {}}},
            ],
            "edges": [{"id": "e-n1-n2", "source": "n1", "target": "n2"}],
        },
    })
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 调度器 API 测试
# ---------------------------------------------------------------------------

class TestSchedulerAPI:
    def test_list_triggers_empty(self, client):
        """列出触发器（空）。"""
        resp = client.get("/api/scheduler/triggers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_trigger(self, client):
        """创建触发器。"""
        wf_id = _create_test_workflow(client)
        resp = client.post("/api/scheduler/triggers", json={
            "workflow_id": wf_id,
            "type": "cron",
            "config": {"cron": "*/5 * * * *"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "id" in data

    def test_list_triggers_with_workflow(self, client):
        """按工作流列出触发器。"""
        wf_id = _create_test_workflow(client)
        client.post("/api/scheduler/triggers", json={
            "workflow_id": wf_id, "type": "cron", "config": {"cron": "0 * * * *"},
        })
        resp = client.get(f"/api/scheduler/triggers?workflow_id={wf_id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_delete_trigger(self, client):
        """删除触发器。"""
        wf_id = _create_test_workflow(client)
        create_resp = client.post("/api/scheduler/triggers", json={
            "workflow_id": wf_id, "type": "manual", "config": {},
        })
        tid = create_resp.json()["id"]
        resp = client.delete(f"/api/scheduler/triggers/{tid}")
        assert resp.status_code == 200

        # 验证已删除
        list_resp = client.get(f"/api/scheduler/triggers?workflow_id={wf_id}")
        assert len(list_resp.json()) == 0

    def test_toggle_trigger(self, client):
        """切换触发器。"""
        wf_id = _create_test_workflow(client)
        create_resp = client.post("/api/scheduler/triggers", json={
            "workflow_id": wf_id, "type": "interval", "config": {"seconds": 300},
        })
        tid = create_resp.json()["id"]
        resp = client.post(f"/api/scheduler/triggers/{tid}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # 再切回来
        resp = client.post(f"/api/scheduler/triggers/{tid}/toggle")
        assert resp.json()["enabled"] is True

    def test_scheduler_status(self, client):
        """调度器状态。"""
        resp = client.get("/api/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "active_triggers" in data

    def test_update_trigger(self, client):
        """更新触发器。"""
        wf_id = _create_test_workflow(client)
        create_resp = client.post("/api/scheduler/triggers", json={
            "workflow_id": wf_id, "type": "cron", "config": {"cron": "0 * * * *"},
        })
        tid = create_resp.json()["id"]
        resp = client.put(f"/api/scheduler/triggers/{tid}", json={
            "config": {"cron": "*/10 * * * *"},
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 执行日志 API 测试
# ---------------------------------------------------------------------------

class TestLogAPI:
    def test_execution_detail(self, client):
        """执行详情。"""
        wf_id = _create_test_workflow(client)
        # 先执行
        exec_resp = client.post(f"/api/workflows/{wf_id}/execute?mode=dry_run")
        assert exec_resp.status_code == 200
        run_id = exec_resp.json()["run_id"]

        resp = client.get(f"/api/execution/{run_id}/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert "node_logs" in data

    def test_execution_nodes(self, client):
        """节点日志。"""
        wf_id = _create_test_workflow(client)
        exec_resp = client.post(f"/api/workflows/{wf_id}/execute?mode=dry_run")
        run_id = exec_resp.json()["run_id"]

        resp = client.get(f"/api/execution/{run_id}/nodes")
        assert resp.status_code == 200
        nodes = resp.json()
        assert isinstance(nodes, list)
        if nodes:
            assert "node_id" in nodes[0]

    def test_execution_screenshot_not_found(self, client):
        """节点截图不存在。"""
        wf_id = _create_test_workflow(client)
        exec_resp = client.post(f"/api/workflows/{wf_id}/execute?mode=dry_run")
        run_id = exec_resp.json()["run_id"]

        resp = client.get(f"/api/execution/{run_id}/screenshot/n1")
        assert resp.status_code == 404

    def test_runs_extended(self, client):
        """扩展执行历史。"""
        wf_id = _create_test_workflow(client)
        client.post(f"/api/workflows/{wf_id}/execute?mode=dry_run")

        resp = client.get(f"/api/workflows/{wf_id}/runs-extended")
        assert resp.status_code == 200
        runs = resp.json()
        assert isinstance(runs, list)
        if runs:
            assert "mode" in runs[0]

    def test_execution_detail_not_found(self, client):
        """不存在的执行详情返回 404。"""
        resp = client.get("/api/execution/nonexistent/detail")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 模板 API 测试
# ---------------------------------------------------------------------------

class TestTemplateAPI:
    def test_list_templates(self, client):
        """列出模板（含种子）。"""
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) >= 4

    def test_list_templates_with_category(self, client):
        """按分类筛选模板。"""
        resp = client.get("/api/templates?category=办公")
        assert resp.status_code == 200
        for t in resp.json():
            assert t["category"] == "办公"

    def test_list_templates_with_search(self, client):
        """搜索模板。"""
        resp = client.get("/api/templates?search=邮件")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_template(self, client):
        """获取模板详情。"""
        resp = client.get("/api/templates")
        templates = resp.json()
        if templates:
            tid = templates[0]["id"]
            resp = client.get(f"/api/templates/{tid}")
            assert resp.status_code == 200
            assert "name" in resp.json()

    def test_get_template_not_found(self, client):
        """不存在的模板返回 404。"""
        resp = client.get("/api/templates/nonexistent")
        assert resp.status_code == 404

    def test_create_from_template(self, client):
        """从模板创建工作流。"""
        resp = client.get("/api/templates")
        templates = resp.json()
        if templates:
            tid = templates[0]["id"]
            resp = client.post(f"/api/workflows/from-template/{tid}", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["id"].startswith("wf_")

    def test_create_from_template_not_found(self, client):
        """不存在模板返回 404。"""
        resp = client.post("/api/workflows/from-template/nonexistent", json={})
        assert resp.status_code == 404

    def test_save_as_template(self, client):
        """另存为模板。"""
        wf_id = _create_test_workflow(client)
        resp = client.post(f"/api/workflows/{wf_id}/save-template", json={
            "name": "API 测试模板",
            "description": "通过 API 测试创建",
            "category": "通用",
            "tags": ["API", "测试"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["id"].startswith("tpl_")

    def test_save_as_template_not_found(self, client):
        """不存在工作流返回 404。"""
        resp = client.post("/api/workflows/nonexistent/save-template", json={"name": "test"})
        assert resp.status_code == 404

    def test_increment_usage(self, client):
        """增加使用计数。"""
        resp = client.get("/api/templates")
        templates = resp.json()
        if templates:
            tid = templates[0]["id"]
            resp = client.post(f"/api/templates/{tid}/usage")
            assert resp.status_code == 200

    def test_increment_usage_not_found(self, client):
        """不存在的模板返回 404。"""
        resp = client.post("/api/templates/nonexistent/usage")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# L5 扩展 API 测试
# ---------------------------------------------------------------------------

class TestL5ExtAPI:
    def test_l5_schedule(self, client):
        """L5 设置定时触发。"""
        wf_id = _create_test_workflow(client)
        # 不加 token（TOKEN 为空）
        resp = client.post("/l5/schedule", json={
            "workflow_id": wf_id,
            "type": "cron",
            "config": {"cron": "*/5 * * * *"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_l5_logs(self, client):
        """L5 查询执行日志。"""
        wf_id = _create_test_workflow(client)
        client.post(f"/api/workflows/{wf_id}/execute?mode=dry_run")
        resp = client.get(f"/l5/logs/{wf_id}?limit=5")
        assert resp.status_code == 200
        logs = resp.json()
        assert isinstance(logs, list)

    def test_l5_templates(self, client):
        """L5 查询模板列表。"""
        resp = client.get("/l5/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) >= 4

    def test_l5_use_template(self, client):
        """L5 使用模板创建流。"""
        resp = client.get("/api/templates")
        templates = resp.json()
        if templates:
            tid = templates[0]["id"]
            resp = client.post(f"/l5/templates/{tid}/use", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_l5_use_template_not_found(self, client):
        """L5 使用不存在的模板返回 404。"""
        resp = client.post("/l5/templates/nonexistent/use", json={})
        assert resp.status_code == 404
