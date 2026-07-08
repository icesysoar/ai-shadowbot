"""浏览器自动化 Worker（F015.1）—— 封装 Soara_browser bridge HTTP API。

设计要点：
  - 所有方法返回统一 dict: {success: bool, data: ..., error: "..."}
  - bridge 离线时自动 _spawn_bridge()
  - BRIDGE_DIR 指向 E:\\WorkBuddy\\AIproject-team\\scripts\\Soara_browser
  - 依赖仅 requests（已在 requirements.txt 中，openai 自带）
  - lazy import：仅在 engine._execute_atomic 中以 browser_ 开头时加载
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BRIDGE_DIR = Path("E:/WorkBuddy/AIproject-team/scripts/Soara_browser")
BRIDGE_SCRIPT = "bridge-server.js"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:16789"
_BRIDGE_STARTUP_TIMEOUT = 15.0  # 最多等 15 秒
_BRIDGE_POLL_INTERVAL = 0.5  # 每 0.5 秒检查一次


# ---------------------------------------------------------------------------
# BrowserWorker
# ---------------------------------------------------------------------------

class BrowserWorker:
    """浏览器自动化 Worker —— 封装 Soara_browser bridge HTTP API。

    Usage::

        worker = BrowserWorker(auto_start=True)
        if worker.is_ready():
            worker.navigate("https://example.com")
            worker.screenshot()
    """

    def __init__(
        self,
        bridge_url: str = DEFAULT_BRIDGE_URL,
        auto_start: bool = True,
    ):
        """初始化 BrowserWorker。

        Args:
            bridge_url: Bridge HTTP 服务地址
            auto_start: True 时自动检测 bridge 是否运行，未运行则 node bridge-server.js
        """
        self._bridge_url = bridge_url.rstrip("/")
        self._auto_start = auto_start
        self._ready = False

        if auto_start:
            self._ensure_bridge()

    # ------------------------------------------------------------------
    # 就绪检测
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        """检查 bridge 是否就绪（GET /status → connected==True）。"""
        try:
            import requests
            resp = requests.get(
                f"{self._bridge_url}/status",
                timeout=5,
            )
            data = resp.json()
            self._ready = data.get("connected", False)
            return self._ready
        except Exception:
            self._ready = False
            return False

    # ------------------------------------------------------------------
    # 核心动作 API
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> dict:
        """导航到指定 URL。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("navigate", {"url": url})

    def click(self, x: int = 0, y: int = 0) -> dict:
        """在浏览器中点击指定坐标。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("computer", {
            "action": "left_click",
            "coordinate": [x, y],
        })

    def type_text(self, text: str = "") -> dict:
        """在浏览器当前焦点输入文本。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("computer", {
            "action": "type",
            "text": text,
        })

    def screenshot(self) -> dict:
        """截取当前浏览器页面的截图（PNG base64）。

        Returns:
            {success: bool, data: {screenshot_b64: "..."}, error: "..."}
        """
        try:
            import requests
            resp = requests.get(
                f"{self._bridge_url}/screenshot",
                timeout=30,
            )
            data = resp.json()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def read_page(self, depth: str = "auto") -> dict:
        """读取页面可访问性树。

        Args:
            depth: "auto" | "full" | "minimal"

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        try:
            import requests
            resp = requests.post(
                f"{self._bridge_url}/read_page",
                json={"depth": depth},
                timeout=30,
            )
            data = resp.json()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def wait(self, seconds: float = 1.0) -> dict:
        """在浏览器中等待指定秒数。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("computer", {
            "action": "wait",
            "text": str(seconds),
        })

    def scroll(self, dx: int = 0, dy: int = 0) -> dict:
        """在浏览器中滚动页面。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("computer", {
            "action": "scroll",
            "coordinate": [dx, dy],
        })

    def extract_text(self, selector: str = "") -> dict:
        """提取页面文本。

        Args:
            selector: CSS 选择器，为空则返回 body.innerText

        Returns:
            {success: bool, data: {text: "..."}, error: "..."}
        """
        if selector:
            code = (
                f"(() => {{ "
                f"const el = document.querySelector({json.dumps(selector)}); "
                f"return el ? el.innerText : ''; "
                f"}})()"
            )
        else:
            code = "document.body ? document.body.innerText : ''"
        return self.exec_js(code)

    def exec_js(self, code: str) -> dict:
        """在浏览器中执行 JavaScript 代码。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        return self._invoke("javascript_tool", {"code": code})

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _invoke(self, tool: str, arguments: dict) -> dict:
        """通用 /invoke 调用。

        Returns:
            {success: bool, data: {...}, error: "..."}
        """
        try:
            import requests
            resp = requests.post(
                f"{self._bridge_url}/invoke",
                json={"tool": tool, "arguments": arguments},
                timeout=60,
            )
            data = resp.json()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def _ensure_bridge(self) -> None:
        """确保 bridge 已运行，未运行则自动启动。"""
        if self.is_ready():
            return
        self._spawn_bridge()

    def _spawn_bridge(self) -> None:
        """启动 bridge-server.js 并等待就绪。"""
        bridge_js = BRIDGE_DIR / BRIDGE_SCRIPT
        if not bridge_js.exists():
            # 不报错，仅标记不可用
            self._ready = False
            return

        try:
            subprocess.Popen(
                ["node", str(bridge_js)],
                cwd=str(BRIDGE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if sys.platform.startswith("win")
                    else 0
                ),
            )
        except Exception:
            self._ready = False
            return

        # 等待 bridge 启动
        deadline = time.time() + _BRIDGE_STARTUP_TIMEOUT
        while time.time() < deadline:
            if self.is_ready():
                return
            time.sleep(_BRIDGE_POLL_INTERVAL)

        self._ready = False
