"""F017 测试 HttpWorker —— 全部 mock 模式 dry_run。

覆盖：
  - HttpWorker.request（mock requests）
  - HttpWorker.get / post / put / delete
  - 超时处理
  - 连接错误处理
  - Engine._execute_http_action 集成（dry_run 返回描述性结果）
  - guardrails.check() 通过（不拦截 http_*）
"""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from ai_shadowbot.actions import Action
from ai_shadowbot.guardrails import ALLOW, BLOCK, CONFIRM, Guardrails


# ── HttpWorker 单元测试 ────────────────────────────────────────────


class TestHttpWorker:
    """HttpWorker 单元测试 —— 所有 HTTP 调用均 mock。"""

    @pytest.fixture
    def mock_requests(self):
        """Mock requests 模块。"""
        with mock.patch.dict(sys.modules, {"requests": mock.MagicMock()}):
            import requests as mock_req

            # 默认返回成功
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{"ok": true}'
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.elapsed.total_seconds.return_value = 0.15

            mock_req.request.return_value = mock_resp
            mock_req.exceptions.Timeout = type("Timeout", (Exception,), {})
            mock_req.exceptions.ConnectionError = type("ConnectionError", (Exception,), {})
            yield mock_req

    def test_get_success(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.get("https://example.com/api")
        assert result["success"] is True
        assert result["data"]["status_code"] == 200
        assert result["data"]["body"] == '{"ok": true}'

    def test_post_success(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.post("https://example.com/api", body='{"x": 1}')
        assert result["success"] is True
        assert result["data"]["status_code"] == 200

    def test_put_success(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.put("https://example.com/api/1", body='{"x": 2}')
        assert result["success"] is True

    def test_delete_success(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.delete("https://example.com/api/1")
        assert result["success"] is True

    def test_request_custom_method(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.request("PATCH", "https://example.com/api", body="data")
        assert result["success"] is True

    def test_request_timeout_error(self):
        """超时返回错误。"""
        import requests as real_requests

        from ai_shadowbot.http_worker import HttpWorker

        with mock.patch.dict(sys.modules, {"requests": mock.MagicMock()}):
            import requests as mock_req
            mock_req.request.side_effect = real_requests.exceptions.Timeout("timeout")
            mock_req.exceptions.Timeout = real_requests.exceptions.Timeout
            mock_req.exceptions.ConnectionError = real_requests.exceptions.ConnectionError

            worker = HttpWorker()
            result = worker.get("https://slow.example.com")
            assert result["success"] is False
            assert "超时" in result["error"]

    def test_request_connection_error(self):
        """连接错误返回错误。"""
        import requests as real_requests

        from ai_shadowbot.http_worker import HttpWorker

        with mock.patch.dict(sys.modules, {"requests": mock.MagicMock()}):
            import requests as mock_req
            mock_req.request.side_effect = real_requests.exceptions.ConnectionError("refused")
            mock_req.exceptions.Timeout = real_requests.exceptions.Timeout
            mock_req.exceptions.ConnectionError = real_requests.exceptions.ConnectionError

            worker = HttpWorker()
            result = worker.get("https://down.example.com")
            assert result["success"] is False
            assert "连接错误" in result["error"]

    def test_elapsed_ms(self, mock_requests):
        from ai_shadowbot.http_worker import HttpWorker
        worker = HttpWorker()
        result = worker.get("https://example.com")
        assert result["data"]["elapsed_ms"] == 150  # 0.15s → 150ms


# ── Engine 集成测试（dry_run） ─────────────────────────────────────


class TestEngineHttpIntegration:
    """测试 Engine._execute_http_action —— dry_run 模式。"""

    @pytest.fixture
    def engine(self):
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        guardrails = Guardrails()
        executor = Executor(guardrails=guardrails, dry_run=True)
        return Engine(
            executor=executor,
            guardrails=guardrails,
            dry_run=True,
        )

    def test_http_get_dry_run(self, engine):
        """dry_run 模式不真发请求。"""
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={
                "atomic_action": "http_get",
                "url": "https://example.com/api",
            },
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()

    def test_http_post_dry_run(self, engine):
        """dry_run 模式 POST 不真发请求。"""
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={
                "atomic_action": "http_post",
                "url": "https://example.com/api",
                "body": '{"key": "value"}',
            },
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()

    def test_http_request_with_method_dry_run(self, engine):
        """dry_run 模式 http_request 不真发请求。"""
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={
                "atomic_action": "http_request",
                "method": "DELETE",
                "url": "https://example.com/api/1",
            },
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()


# ── Guardrails 集成测试 ────────────────────────────────────────────


class TestHttpGuardrails:
    """测试 guardrails 对 http_* 的检查。"""

    def test_http_get_allowed(self):
        guardrails = Guardrails()
        action = Action(type="http_get", params={"url": "https://example.com"})
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_http_post_allowed(self):
        guardrails = Guardrails()
        action = Action(
            type="http_post",
            params={"url": "https://example.com", "body": "data"},
        )
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_http_delete_allowed(self):
        guardrails = Guardrails()
        action = Action(type="http_delete", params={"url": "https://example.com/1"})
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_http_request_with_rm_in_url_blocked(self):
        """URL 中含 'rm' 不会触发 BLOCK（它是 URL 的一部分，不是命令动词）。"""
        guardrails = Guardrails()
        action = Action(
            type="http_get",
            params={"url": "https://example.com/rm/user/1"},
        )
        result = guardrails.check(action)
        # URL 中的 'rm' 作为路径的一部分，不会被误判为 shell 命令
        # 因为 _normalize_tokens 按空白分词，URL 中的 '/' 分隔的 'rm' 不会被归一化
        # 为独立命令动词
        assert result.decision == ALLOW
