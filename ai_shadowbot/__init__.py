"""AI 版影刀（ai-shadowbot） —— 自然语言驱动电脑操作的 Python 工具。

模块：
  actions    原子动作词汇表 + schema 强校验（F001/F002/F003 共享事实来源）
  planner    规划层：LLM function calling，自然语言 → 动作序列（F001）
  executor   执行引擎：PyAutoGUI 执行 + dry_run 安全演练（F002）
  observer   观测层：屏幕截图 → base64（F002）
  guardrails 护栏层：白名单 + 黑名单 + 危险动作二次确认（F003）
  cli        CLI 聊天入口（F004）
"""
from __future__ import annotations

from ai_shadowbot.actions import Action, validate_action, build_tool_schema, ALLOWED_ACTION_TYPES
from ai_shadowbot.config import Config
from ai_shadowbot.planner import Planner, PlanResult, MockLLMClient, OpenAIClient
from ai_shadowbot.executor import Executor, ExecResult
from ai_shadowbot.guardrails import Guardrails, GuardResult, EmergencyStop, ALLOW, BLOCK, CONFIRM
from ai_shadowbot.observer import Observer
from ai_shadowbot.injection_classifier import InjectionClassifier, ClassifyResult

__version__ = "0.1.0"

__all__ = [
    "Action", "validate_action", "build_tool_schema", "ALLOWED_ACTION_TYPES",
    "Config", "Planner", "PlanResult", "MockLLMClient", "OpenAIClient",
    "Executor", "ExecResult", "Guardrails", "GuardResult", "EmergencyStop",
    "ALLOW", "BLOCK", "CONFIRM", "Observer",
    "InjectionClassifier", "ClassifyResult",
]
