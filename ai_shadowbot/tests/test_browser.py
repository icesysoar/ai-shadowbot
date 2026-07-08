"""F015.4 浏览器 Worker 测试 —— Mock requests 避免依赖真实 bridge。

覆盖：
  - BrowserWorker 构造（auto_start=False，不连 bridge）
  - URL 校验 / navigate
  - click 坐标范围
  - screenshot mock
  - wait mock
  - navigate URL 规范化
  - extract_text mock
  - 全部 dry_run 模式，不依赖真实浏览器
  - Engine._execute_browser_action 集成（dry_run 返回描述性结果）
"""
from __future__ import annotations

import sys
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 测试 BrowserWorker（mock requests）
# ---------------------------------------------------------------------------

class TestBrowserWorker:
    """BrowserWorker 单元测试 —— 所有 HTTP 调用均 mock。"""

    @pytest.fixture
    def mock_requests(self):
        """Mock requests 模块，模拟 bridge HTTP API。"""
        with mock.patch.dict(sys.modules, {"requests": mock.MagicMock()}):
            import requests as mock_req
            # 默认返回成功的 /status
            mock_req.get.return_value.json.return_value = {
                "connected": True,
                "extInfo": {"version": "1.0"},
            }
            mock_req.post.return_value.json.return_value = {
                "success": True,
                "result": {},
            }
            yield mock_req

    def test_construct_no_auto_start(self):
        """auto_start=False 时不连接 bridge。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        assert bw._auto_start is False
        assert bw._ready is False

    def test_construct_default_bridge_url(self):
        """默认 bridge_url 为 127.0.0.1:16789。"""
        from ai_shadowbot.browser_worker import BrowserWorker, DEFAULT_BRIDGE_URL
        bw = BrowserWorker(auto_start=False)
        assert bw._bridge_url == DEFAULT_BRIDGE_URL.rstrip("/")

    def test_is_ready_connected(self, mock_requests):
        """bridge 返回 connected=True 时 is_ready 返回 True。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        assert bw.is_ready() is True

    def test_is_ready_not_connected(self, mock_requests):
        """bridge 返回 connected=False 时 is_ready 返回 False。"""
        mock_requests.get.return_value.json.return_value = {
            "connected": False,
        }
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        assert bw.is_ready() is False

    def test_is_ready_connection_error(self, mock_requests):
        """bridge 不可达时 is_ready 返回 False（不抛异常）。"""
        mock_requests.get.side_effect = ConnectionError("refused")
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        assert bw.is_ready() is False

    def test_navigate_success(self, mock_requests):
        """navigate 调用 /invoke 成功。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.navigate("https://example.com")
        assert result["success"] is True
        mock_requests.post.assert_called_with(
            "http://127.0.0.1:16789/invoke",
            json={"tool": "navigate", "arguments": {"url": "https://example.com"}},
            timeout=60,
        )

    def test_navigate_error(self, mock_requests):
        """navigate 调用失败时返回 success=False。"""
        mock_requests.post.side_effect = ConnectionError("refused")
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.navigate("https://example.com")
        assert result["success"] is False
        assert result["error"] is not None

    def test_click_default_coords(self, mock_requests):
        """click 默认坐标 (0,0)。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.click()
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["tool"] == "computer"
        assert json_data["arguments"]["action"] == "left_click"

    def test_click_custom_coords(self, mock_requests):
        """click 自定义坐标 (100, 200)。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.click(x=100, y=200)
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["coordinate"] == [100, 200]

    def test_click_negative_coords(self, mock_requests):
        """click 负数坐标（边界情况）。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.click(x=-10, y=-50)
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["coordinate"] == [-10, -50]

    def test_type_text(self, mock_requests):
        """type_text 发送文本到 bridge。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.type_text("hello world")
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["tool"] == "computer"
        assert json_data["arguments"]["action"] == "type"
        assert json_data["arguments"]["text"] == "hello world"

    def test_type_text_empty(self, mock_requests):
        """type_text 空字符串。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.type_text("")
        assert result["success"] is True

    def test_screenshot_success(self, mock_requests):
        """screenshot 返回 base64 数据。"""
        mock_requests.get.return_value.json.return_value = {
            "screenshot_b64": "iVBORw0KGgo=",
        }
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.screenshot()
        assert result["success"] is True
        assert result["data"]["screenshot_b64"] == "iVBORw0KGgo="

    def test_screenshot_error(self, mock_requests):
        """screenshot 失败时返回 error。"""
        mock_requests.get.side_effect = ConnectionError("refused")
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.screenshot()
        assert result["success"] is False
        assert result["error"] is not None

    def test_wait_default_seconds(self, mock_requests):
        """wait 默认 1 秒。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.wait()
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["action"] == "wait"
        assert json_data["arguments"]["text"] == "1.0"

    def test_wait_custom_seconds(self, mock_requests):
        """wait 自定义秒数。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.wait(seconds=3.5)
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["text"] == "3.5"

    def test_scroll(self, mock_requests):
        """scroll 发送滚动参数。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.scroll(dx=0, dy=-500)
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["action"] == "scroll"
        assert json_data["arguments"]["coordinate"] == [0, -500]

    def test_extract_text_no_selector(self, mock_requests):
        """extract_text 无 selector 返回 body.innerText。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.extract_text()
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["tool"] == "javascript_tool"
        assert "body.innerText" in json_data["arguments"]["code"]

    def test_extract_text_with_selector(self, mock_requests):
        """extract_text 带 selector 使用 querySelector。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.extract_text("#content")
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert 'querySelector' in json_data["arguments"]["code"]
        assert '#content' in json_data["arguments"]["code"]

    def test_exec_js(self, mock_requests):
        """exec_js 执行任意 JS。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.exec_js("return document.title")
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["tool"] == "javascript_tool"
        assert json_data["arguments"]["code"] == "return document.title"

    def test_read_page(self, mock_requests):
        """read_page 调用 /read_page API。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.read_page(depth="auto")
        assert result["success"] is True
        mock_requests.post.assert_called_with(
            "http://127.0.0.1:16789/read_page",
            json={"depth": "auto"},
            timeout=30,
        )

    def test_navigate_https_url(self, mock_requests):
        """navigate 支持 HTTPS URL。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.navigate("https://github.com")
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["url"] == "https://github.com"

    def test_navigate_http_url(self, mock_requests):
        """navigate 支持 HTTP URL。"""
        from ai_shadowbot.browser_worker import BrowserWorker
        bw = BrowserWorker(auto_start=False)
        result = bw.navigate("http://localhost:3000")
        assert result["success"] is True
        call_args = mock_requests.post.call_args
        json_data = call_args[1]["json"]
        assert json_data["arguments"]["url"] == "http://localhost:3000"


# ---------------------------------------------------------------------------
# 测试 Engine._execute_browser_action（dry_run 集成）
# ---------------------------------------------------------------------------

class TestEngineBrowserIntegration:
    """Engine 浏览器动作集成测试 —— 全部 dry_run 模式。"""

    def test_browser_navigate_dry_run(self):
        """dry_run 模式下 browser_navigate 返回描述性结果。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )
        # 构建一个假 Node 和 action params
        from ai_shadowbot.actions import Action

        result = engine._execute_browser_action(
            "browser_navigate",
            {"url": "https://example.com"},
            dry_run=True,
        )
        assert result.performed is False
        assert "dry_run" in result.summary
        assert "browser_navigate" in result.summary

    def test_browser_click_dry_run(self):
        """dry_run 模式下 browser_click 不连 bridge。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_click",
            {"x": 100, "y": 200},
            dry_run=True,
        )
        assert result.performed is False
        assert "dry_run" in result.summary

    def test_browser_type_dry_run(self):
        """dry_run 模式下 browser_type 不真输入。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_type",
            {"text": "test input"},
            dry_run=True,
        )
        assert result.performed is False

    def test_browser_screenshot_dry_run(self):
        """dry_run 模式下 browser_screenshot 不截图。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_screenshot",
            {},
            dry_run=True,
        )
        assert result.performed is False

    def test_browser_wait_dry_run(self):
        """dry_run 模式下 browser_wait 不真实等待。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_wait",
            {"seconds": 5},
            dry_run=True,
        )
        assert result.performed is False

    def test_browser_scroll_dry_run(self):
        """dry_run 模式下 browser_scroll 不真滚动。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_scroll",
            {"dx": 0, "dy": -300},
            dry_run=True,
        )
        assert result.performed is False

    def test_browser_extract_text_dry_run(self):
        """dry_run 模式下 browser_extract_text 不真提取。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_extract_text",
            {"selector": "#main"},
            dry_run=True,
        )
        assert result.performed is False

    def test_unknown_browser_action_returns_error(self):
        """未知 browser_ 动作返回错误结果。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            dry_run=True,
        )

        result = engine._execute_browser_action(
            "browser_unknown_action",
            {},
            dry_run=False,  # 非 dry_run 但动作仍未知
        )
        assert result.performed is False
        assert "未知浏览器动作" in result.summary or "未知浏览器动作" in str(result.reason)

    def test_engine_accepts_browser_worker_param(self):
        """Engine.__init__ 接受 browser_worker 参数。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails

        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            browser_worker=None,
        )
        assert engine._browser_worker is None

    def test_engine_with_browser_worker_instance(self):
        """Engine 接受 BrowserWorker 实例。"""
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        from ai_shadowbot.guardrails import Guardrails
        from ai_shadowbot.browser_worker import BrowserWorker

        bw = BrowserWorker(auto_start=False)
        engine = Engine(
            executor=Executor(dry_run=True, guardrails=Guardrails(strategy="skip")),
            guardrails=Guardrails(strategy="skip"),
            browser_worker=bw,
        )
        assert engine._browser_worker is bw
        assert engine._browser_worker._auto_start is False


# ---------------------------------------------------------------------------
# 测试 compiler 浏览器关键词检测（F015.3）
# ---------------------------------------------------------------------------

class TestCompilerBrowserKeywords:
    """compiler._detect_actions_from_query 浏览器关键词检测。"""

    def test_detect_navigate_keyword(self):
        """"打开网页" → browser_navigate。"""
        from ai_shadowbot.compiler import _detect_actions_from_query

        actions = _detect_actions_from_query("打开网页 https://example.com")
        assert len(actions) >= 1
        assert actions[0]["params"]["atomic_action"] == "browser_navigate"

    def test_detect_click_button_keyword(self):
        """"点击按钮" → browser_click。"""
        from ai_shadowbot.compiler import _detect_actions_from_query

        actions = _detect_actions_from_query("点击按钮")
        assert any(
            a["params"].get("atomic_action") == "browser_click"
            for a in actions
        )

    def test_detect_input_search_keyword(self):
        """"输入搜索" → browser_type。"""
        from ai_shadowbot.compiler import _detect_actions_from_query

        actions = _detect_actions_from_query("输入搜索关键词")
        assert any(
            a["params"].get("atomic_action") == "browser_type"
            for a in actions
        )

    def test_detect_screenshot_keyword(self):
        """"网页截图" → browser_screenshot。"""
        from ai_shadowbot.compiler import _detect_actions_from_query

        actions = _detect_actions_from_query("对网页截图")
        assert any(
            a["params"].get("atomic_action") == "browser_screenshot"
            for a in actions
        )

    def test_non_browser_query_returns_original(self):
        """非浏览器关键词保持原有行为。"""
        from ai_shadowbot.compiler import _detect_actions_from_query

        actions = _detect_actions_from_query("打开记事本输入hello")
        # 应该走原有的 open_app + type_text
        assert any(
            a["params"].get("atomic_action") in ("open_app", "type_text")
            for a in actions
        )
        # 不应有 browser_ 前缀
        assert not any(
            str(a["params"].get("atomic_action", "")).startswith("browser_")
            for a in actions
        )


# ---------------------------------------------------------------------------
# 测试 canvas_api 调色板（F015.3）
# ---------------------------------------------------------------------------

class TestCanvasPaletteBrowser:
    """canvas_api.PALETTE_NODES 包含浏览器分类。"""

    def test_palette_has_browser_category(self):
        """PALETTE_NODES 包含 "浏览器" 分类。"""
        from ai_shadowbot.canvas_api import PALETTE_NODES

        categories = {n.get("category") for n in PALETTE_NODES}
        assert "浏览器" in categories, f"调色板缺少 '浏览器' 分类，现有: {categories}"

    def test_palette_browser_nodes_count(self):
        """浏览器分类至少有 6 个节点。"""
        from ai_shadowbot.canvas_api import PALETTE_NODES

        browser_nodes = [
            n for n in PALETTE_NODES if n.get("category") == "浏览器"
        ]
        assert len(browser_nodes) >= 6, f"浏览器节点不足: {len(browser_nodes)}"

    def test_palette_browser_navigate(self):
        """browser_navigate 节点存在且参数正确。"""
        from ai_shadowbot.canvas_api import PALETTE_NODES

        node = next(
            (n for n in PALETTE_NODES if n["type"] == "browser_navigate"),
            None,
        )
        assert node is not None, "browser_navigate 节点缺失"
        assert node["params"]["atomic_action"] == "browser_navigate"
        assert "url" in node["params"]

    def test_palette_browser_screenshot(self):
        """browser_screenshot 节点存在。"""
        from ai_shadowbot.canvas_api import PALETTE_NODES

        node = next(
            (n for n in PALETTE_NODES if n["type"] == "browser_screenshot"),
            None,
        )
        assert node is not None, "browser_screenshot 节点缺失"
        assert node["params"]["atomic_action"] == "browser_screenshot"
