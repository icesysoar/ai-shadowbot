"""HTTP 请求 Worker（F017）—— 封装 HTTP 请求操作。

设计要点：
  - 所有方法返回统一 dict: {success: bool, data: {status_code, headers, body, elapsed_ms}, error: "..."}
  - requests lazy import：仅在调用方法时加载
  - 支持 GET/POST/PUT/DELETE + 通用 request 方法
  - 默认超时 30 秒
  - dry_run 模式下不真发请求（由 engine 层控制）
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class HttpWorker:
    """HTTP 请求 Worker。

    封装 requests 库，提供统一的请求接口。
    """

    @staticmethod
    def _success(data: Any = None) -> dict:
        return {"success": True, "data": data, "error": None}

    @staticmethod
    def _error(msg: str, data: Any = None) -> dict:
        return {"success": False, "data": data, "error": msg}

    # ------------------------------------------------------------------
    # 通用请求
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        body: Optional[str] = None,
        timeout: int = 30,
    ) -> dict:
        """发送通用 HTTP 请求。

        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE/PATCH 等）
            url: 请求 URL
            headers: 请求头字典
            body: 请求体（字符串）
            timeout: 超时秒数

        Returns:
            {success, data: {status_code, headers: {...}, body: "...", elapsed_ms: N}, error}
        """
        try:
            import requests
        except ImportError:
            return self._error("requests 未安装，请 pip install requests")

        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                data=body,
                timeout=timeout,
            )
            elapsed_ms = int(resp.elapsed.total_seconds() * 1000)

            return self._success({
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text,
                "elapsed_ms": elapsed_ms,
            })
        except requests.exceptions.Timeout:
            return self._error(f"请求超时 ({timeout}s): {method.upper()} {url}")
        except requests.exceptions.ConnectionError as e:
            return self._error(f"连接错误: {e}")
        except Exception as e:
            return self._error(f"HTTP 请求失败: {e}")

    # ------------------------------------------------------------------
    # 快捷方法
    # ------------------------------------------------------------------

    def get(self, url: str, headers: Optional[dict] = None) -> dict:
        """发送 GET 请求。"""
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        body: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """发送 POST 请求。"""
        return self.request("POST", url, headers=headers, body=body)

    def put(
        self,
        url: str,
        body: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """发送 PUT 请求。"""
        return self.request("PUT", url, headers=headers, body=body)

    def delete(self, url: str, headers: Optional[dict] = None) -> dict:
        """发送 DELETE 请求。"""
        return self.request("DELETE", url, headers=headers)
