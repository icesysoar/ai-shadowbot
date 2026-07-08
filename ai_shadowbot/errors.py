"""错误策略处理器（F006 §5）—— 节点执行失败后的行为决策。

设计要点（§5.1-5.4）：
  - 四种策略：retry / skip / abort / degrade
  - retry：指数退避 + 抖动（±10%），耗尽后 fallback 默认 abort
  - skip：标记 SKIPPED，继续下一节点
  - abort：标记 FAILED，终止工作流
  - degrade：标记 DEGRADED，继续下一节点
  - 节点级策略覆盖工作流级默认策略
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from ai_shadowbot.workflow import ErrorStrategy, ErrorStrategyType


class ErrorAction(str, Enum):
    """错误处理器返回的动作种类。"""
    retry = "retry"         # 重试（退避后）
    skip = "skip"           # 跳过当前节点
    abort = "abort"         # 终止整个工作流
    continue_ = "continue"  # 继续下一节点（degrade 用）


@dataclass
class HandleResult:
    """错误处理结果。"""
    action: ErrorAction
    node_status: str        # 节点最终状态：FAILED / SKIPPED / DEGRADED
    delay: float = 0.0      # 重试等待秒数
    retry_attempt: int = 0  # 当前第几次重试
    message: str = ""


def calculate_retry_delay(strategy: ErrorStrategy, attempt: int) -> float:
    """指数退避（含抖动），设计 §5.3。"""
    base = strategy.retry_interval * (strategy.retry_backoff ** (attempt - 1))
    jitter = base * 0.1  # ±10% 抖动
    return base + random.uniform(-jitter, jitter)


class ErrorHandler:
    """错误策略处理器 —— 决定失败节点的后续行为。

    用法：
        handler = ErrorHandler()
        result = handler.handle(node_error="timeout", strategy=error_strategy)
    """

    def __init__(self) -> None:
        self._retry_counts: Dict[str, int] = {}  # node_id -> retry count

    def handle(
        self,
        node_id: str,
        error: str,
        strategy: ErrorStrategy,
    ) -> HandleResult:
        """处理节点错误，返回决策动作。

        Args:
            node_id: 节点 ID
            error: 错误描述
            strategy: 错误策略

        Returns:
            HandleResult: 处理结果
        """
        if strategy.type == ErrorStrategyType.retry_type:
            return self._handle_retry(node_id, error, strategy)
        elif strategy.type == ErrorStrategyType.skip_type:
            return HandleResult(
                action=ErrorAction.skip,
                node_status="SKIPPED",
                message=f"节点 '{node_id}' 执行出错：{error}，已跳过",
            )
        elif strategy.type == ErrorStrategyType.abort_type:
            return HandleResult(
                action=ErrorAction.abort,
                node_status="FAILED",
                message=f"节点 '{node_id}' 执行出错：{error}，已终止工作流",
            )
        elif strategy.type == ErrorStrategyType.degrade_type:
            return HandleResult(
                action=ErrorAction.continue_,
                node_status="DEGRADED",
                message=f"节点 '{node_id}' 执行出错：{error}，以降级模式继续",
            )
        else:
            # 未知策略 → 安全降级为 abort
            return HandleResult(
                action=ErrorAction.abort,
                node_status="FAILED",
                message=f"节点 '{node_id}' 未知错误策略 {strategy.type}，已终止",
            )

    def _handle_retry(
        self,
        node_id: str,
        error: str,
        strategy: ErrorStrategy,
    ) -> HandleResult:
        """处理重试策略。"""
        current = self._retry_counts.get(node_id, 0)
        if current >= strategy.max_retries:
            # 重试耗尽 → fallback 默认 abort
            return HandleResult(
                action=ErrorAction.abort,
                node_status="FAILED",
                retry_attempt=current,
                message=(
                    f"节点 '{node_id}' 重试 {current} 次后仍然失败：{error}，"
                    f"已终止（fallback abort）"
                ),
            )
        # 计算退避时间（含抖动）
        delay = calculate_retry_delay(strategy, current + 1)
        self._retry_counts[node_id] = current + 1
        return HandleResult(
            action=ErrorAction.retry,
            node_status="RUNNING",
            delay=delay,
            retry_attempt=current + 1,
            message=(
                f"节点 '{node_id}' 执行出错：{error}，"
                f"第 {current + 1}/{strategy.max_retries} 次重试，等待 {delay:.1f}s"
            ),
        )

    def reset_retry(self, node_id: str) -> None:
        """重置指定节点的重试计数。"""
        self._retry_counts.pop(node_id, None)

    def reset_all(self) -> None:
        """重置所有重试计数。"""
        self._retry_counts.clear()
