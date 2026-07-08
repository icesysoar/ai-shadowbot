"""模型配置（F001 依赖）。

从环境变量读取 LLM 配置；提供 mock 开关，便于无 API key 的测试与 dry_run 演示。
所有读取带默认值，缺失 API key 时自动回退 mock 模式（绝不因缺 key 崩溃）。

环境变量：
  LLM_API_KEY   必填（真实模式）；缺失则强制 mock
  LLM_BASE_URL  可选，自定义/私有化网关
  LLM_MODEL     可选，模型名
  LLM_MOCK      可选，设为 1/true 强制 mock 模式
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4o"
    mock: bool = False
    # 隐私脱敏（T003.6 / AC5 / P1-3）：截图外发前对敏感区打码。
    # 隐私优先：默认开启（True），避免敏感截图外发；显式设 SCREEN_MASK_SENSITIVE=0/false 才关。
    screen_mask_sensitive: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.environ.get("LLM_API_KEY") or None
        base_url = os.environ.get("LLM_BASE_URL") or None
        model = os.environ.get("LLM_MODEL") or "gpt-4o"
        mock_flag = os.environ.get("LLM_MOCK", "").lower() in ("1", "true", "yes", "on")
        mask_env = os.environ.get("SCREEN_MASK_SENSITIVE")
        # 隐私优先：未显式设置时默认开启脱敏（AC5 / P1-3），避免敏感截图外发
        mask = True if mask_env is None else mask_env.lower() in ("1", "true", "yes", "on")
        # 缺 api_key 时强制 mock —— 本地模型默认，避免截图外发（隐私）
        mock = mock_flag or (api_key is None)
        return cls(api_key=api_key, base_url=base_url, model=model,
                   mock=mock, screen_mask_sensitive=mask)

    def make_llm_client(self):
        """根据配置返回 LLM 客户端：mock 或 OpenAI 兼容客户端。"""
        # 延迟 import，避免测试/无网络环境下 import 失败
        if self.mock or not self.api_key:
            from ai_shadowbot.planner import MockLLMClient
            return MockLLMClient()
        from ai_shadowbot.planner import OpenAIClient
        return OpenAIClient(self)
