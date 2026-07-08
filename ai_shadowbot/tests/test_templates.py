"""模板测试（Phase 3 / F011）—— 模板 CRUD + 从模板创建 + 另存为模板。"""
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
# 种子模板测试
# ---------------------------------------------------------------------------

class TestSeedTemplates:
    def test_seed_templates_exist(self, canvas_api):
        """种子模板自动插入。"""
        templates = canvas_api.list_templates()
        assert len(templates) >= 4

    def test_seed_template_content(self, canvas_api):
        """验证种子模板内容。"""
        templates = canvas_api.list_templates()
        names = [t["name"] for t in templates]
        assert "每日邮件对账" in names
        assert "网页截图存档" in names
        assert "文件整理" in names
        assert "系统监控" in names

    def test_seed_templates_have_flow(self, canvas_api):
        """种子模板包含有效 flow_json。"""
        templates = canvas_api.list_templates()
        for t in templates:
            flow = t.get("flow_json", {})
            if isinstance(flow, dict):
                assert "nodes" in flow

    def test_seed_templates_have_category(self, canvas_api):
        """种子模板有分类。"""
        templates = canvas_api.list_templates()
        categories = {t["category"] for t in templates}
        assert "办公" in categories
        assert "网页" in categories
        assert "系统" in categories


# ---------------------------------------------------------------------------
# 模板 CRUD 测试
# ---------------------------------------------------------------------------

class TestTemplateCRUD:
    def test_list_templates_by_category(self, canvas_api):
        """按分类筛选模板。"""
        office = canvas_api.list_templates(category="办公")
        assert len(office) >= 1
        for t in office:
            assert t["category"] == "办公"

    def test_search_templates(self, canvas_api):
        """搜索模板。"""
        results = canvas_api.list_templates(search="邮件")
        assert len(results) >= 1
        assert "邮件" in results[0]["name"] or "邮件" in results[0].get("description", "")

    def test_get_template_detail(self, canvas_api):
        """获取模板详情。"""
        templates = canvas_api.list_templates()
        if templates:
            t = canvas_api.get_template(templates[0]["id"])
            assert t is not None
            assert "name" in t
            assert "description" in t
            assert "flow_json" in t

    def test_get_template_not_found(self, canvas_api):
        """不存在的模板返回 None。"""
        t = canvas_api.get_template("nonexistent")
        assert t is None

    def test_increment_usage(self, canvas_api):
        """增加使用计数。"""
        templates = canvas_api.list_templates()
        if templates:
            tid = templates[0]["id"]
            old_count = templates[0]["usage_count"]
            ok = canvas_api.increment_template_usage(tid)
            assert ok is True
            t = canvas_api.get_template(tid)
            assert t["usage_count"] == old_count + 1

    def test_increment_usage_not_found(self, canvas_api):
        """不存在的模板增加计数返回 False。"""
        ok = canvas_api.increment_template_usage("nonexistent")
        assert ok is False


# ---------------------------------------------------------------------------
# 从模板创建 + 另存为模板 测试
# ---------------------------------------------------------------------------

class TestTemplateOperations:
    def test_create_from_template(self, canvas_api):
        """从模板创建工作流。"""
        templates = canvas_api.list_templates()
        if templates:
            tid = templates[0]["id"]
            wf_id = canvas_api.create_from_template(tid, "我的测试工作流")
            assert wf_id is not None
            assert wf_id.startswith("wf_")

            # 验证工作流已创建
            wf = canvas_api.get_workflow(wf_id)
            assert wf is not None
            assert "测试" in wf["name"]

    def test_create_from_template_not_found(self, canvas_api):
        """不存在的模板创建返回 None。"""
        wf_id = canvas_api.create_from_template("nonexistent")
        assert wf_id is None

    def test_save_as_template(self, canvas_api):
        """将工作流另存为模板。"""
        wf_id = canvas_api.create_workflow({"name": "测试工作流", "flow": SAMPLE_FLOW})
        tid = canvas_api.save_as_template(wf_id, {
            "name": "测试模板",
            "description": "由测试创建",
            "category": "通用",
            "tags": ["测试", "样例"],
        })
        assert tid is not None
        assert tid.startswith("tpl_")

        # 验证模板
        t = canvas_api.get_template(tid)
        assert t["name"] == "测试模板"
        assert t["category"] == "通用"

    def test_save_as_template_not_found(self, canvas_api):
        """不存在的工作流返回 None。"""
        tid = canvas_api.save_as_template("nonexistent", {"name": "test"})
        assert tid is None

    def test_save_template_sanitizes_sensitive_params(self, canvas_api):
        """保存模板时剔除敏感参数。"""
        sensitive_flow = {
            "nodes": [
                {"id": "n1", "type": "default", "position": {"x": 100, "y": 50},
                 "data": {"label": "测试", "node_type": "atomic",
                          "params": {"atomic_action": "type_text", "text": "hello",
                                     "password": "secret123", "token": "abc123"}}},
            ],
            "edges": [],
        }
        wf_id = canvas_api.create_workflow({"name": "敏感测试", "flow": sensitive_flow})
        tid = canvas_api.save_as_template(wf_id, {"name": "安全模板"})
        t = canvas_api.get_template(tid)
        flow = t["flow_json"]
        if isinstance(flow, str):
            flow = json.loads(flow)
        params = flow["nodes"][0]["data"]["params"]
        assert params["password"] == "***"
        assert params["token"] == "***"
        assert params["text"] == "hello"  # 不敏感字段保持

    def test_create_from_template_increments_usage(self, canvas_api):
        """从模板创建自动增加使用计数。"""
        templates = canvas_api.list_templates()
        if templates:
            tid = templates[0]["id"]
            old_count = canvas_api.get_template(tid)["usage_count"]
            canvas_api.create_from_template(tid)
            new_count = canvas_api.get_template(tid)["usage_count"]
            assert new_count == old_count + 1
