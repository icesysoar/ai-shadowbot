"""定时调度器（Phase 3 / F009）—— 后台线程驱动，支持 cron/interval 触发。

架构：
  Scheduler 后台线程定时检查数据库中的触发器记录，到期时调用
  CanvasAPI.execute_workflow() 执行关联工作流（仍过 guardrails.check()）。

设计文档：docs/phase3-design.md §2
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 简化 cron 解析器（零外部依赖）
# ---------------------------------------------------------------------------

def _parse_cron_minute(expr: str) -> List[int]:
    """解析 cron 表达式的前 5 位（仅分钟级，格式 */5 * * * * 或 * 或 N,M 或 N-M）。

    Args:
        expr: 标准 cron 表达式 "分 时 日 月 周"

    Returns:
        匹配的分钟列表 [0, 5, 10, ...]
    """
    parts = expr.strip().split()
    minute_part = parts[0] if parts else "*"

    if minute_part == "*":
        return list(range(60))

    # */N
    if minute_part.startswith("*/"):
        try:
            step = int(minute_part[2:])
            return list(range(0, 60, step))
        except ValueError:
            return list(range(60))

    # N-M
    if "-" in minute_part:
        try:
            parts_range = minute_part.split("-")
            start = int(parts_range[0])
            end = int(parts_range[1])
            return list(range(start, min(end + 1, 60)))
        except ValueError:
            return list(range(60))

    # N,M,...
    if "," in minute_part:
        try:
            return [int(x) for x in minute_part.split(",") if 0 <= int(x) < 60]
        except ValueError:
            return list(range(60))

    # 单个数字
    try:
        val = int(minute_part)
        return [val] if 0 <= val < 60 else list(range(60))
    except ValueError:
        return list(range(60))


def _should_run_at(cron_expr: str, now: datetime) -> bool:
    """检查当前分钟是否匹配 cron 表达式。

    Args:
        cron_expr: cron 表达式 "分 时 日 月 周"
        now: 当前时间

    Returns:
        是否应该执行
    """
    minutes = _parse_cron_minute(cron_expr)
    return now.minute in minutes


def _compute_next_run(cron_expr: str, from_time: Optional[datetime] = None) -> Optional[str]:
    """计算下一次执行时间。

    Args:
        cron_expr: cron 表达式
        from_time: 起始时间（默认当前时间）

    Returns:
        ISO 格式时间字符串，或 None（无法计算）
    """
    now = from_time or datetime.now()
    for offset in range(60):
        check_time = now + timedelta(minutes=offset)
        if _should_run_at(cron_expr, check_time):
            return check_time.isoformat(timespec="seconds")
    return None


# ---------------------------------------------------------------------------
# Scheduler 类
# ---------------------------------------------------------------------------

class Scheduler:
    """后台调度器 —— 从数据库加载触发器，按 cron/interval 定时执行工作流。

    用法:
        scheduler = Scheduler(canvas_api)
        scheduler.start()
        # ... 运行中 ...
        scheduler.stop()
    """

    def __init__(self, canvas_api: "CanvasAPI", check_interval: int = 30):
        self.canvas_api = canvas_api
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._active_triggers: Dict[str, Dict[str, Any]] = {}
        self._check_interval = check_interval  # 检查间隔（秒）

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动调度器后台线程。"""
        if self._running:
            logger.warning("[scheduler] 调度器已在运行")
            return
        self._running = True
        self._load_active_triggers()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="scheduler")
        self._thread.start()
        logger.info(f"[scheduler] 调度器已启动 | 活动触发器: {len(self._active_triggers)}")

    def stop(self):
        """停止调度器。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("[scheduler] 调度器已停止")

    def status(self) -> Dict[str, Any]:
        """获取调度器状态。"""
        with self._lock:
            return {
                "running": self._running,
                "active_triggers": len(self._active_triggers),
                "triggers": [
                    {
                        "id": tid,
                        "workflow_id": t.get("workflow_id", ""),
                        "type": t.get("type", ""),
                        "enabled": t.get("enabled", False),
                        "next_run": t.get("next_run"),
                    }
                    for tid, t in self._active_triggers.items()
                ],
            }

    # ------------------------------------------------------------------
    # 触发器管理
    # ------------------------------------------------------------------

    def add_trigger(self, trigger_data: Dict[str, Any]) -> str:
        """添加一个触发器（写入 DB 并激活）。"""
        tid = self.canvas_api.create_trigger(trigger_data)
        # 计算下次执行时间
        self._update_next_run(tid)
        # 重新加载活动触发器
        self._load_active_triggers()
        return tid

    def remove_trigger(self, trigger_id: str) -> bool:
        """删除触发器。"""
        ok = self.canvas_api.delete_trigger(trigger_id)
        if ok:
            with self._lock:
                self._active_triggers.pop(trigger_id, None)
        return ok

    def toggle_trigger(self, trigger_id: str) -> Optional[bool]:
        """切换触发器启用/禁用状态。"""
        new_state = self.canvas_api.toggle_trigger(trigger_id)
        if new_state is not None:
            self._load_active_triggers()
        return new_state

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load_active_triggers(self):
        """从数据库加载已启用的触发器。"""
        with self._lock:
            triggers = self.canvas_api.list_triggers()
            self._active_triggers = {}
            for t in triggers:
                if t.get("enabled"):
                    tid = t["id"]
                    self._active_triggers[tid] = dict(t)
                    # 确保 next_run 存在
                    if not t.get("next_run"):
                        self._update_next_run(tid)

    def _update_next_run(self, trigger_id: str):
        """计算并更新触发器的下次执行时间（仅当当前无 next_run 时）。"""
        with self._lock:
            t = self._active_triggers.get(trigger_id)
            if t is None:
                return
            # 如果已有 next_run 且不为空，保留
            if t.get("next_run"):
                return
            typ = t.get("type", "")
            config = t.get("config", {})
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except (json.JSONDecodeError, TypeError):
                    config = {}
            next_run = None
            if typ == "cron":
                cron_expr = config.get("cron", "")
                if cron_expr:
                    next_run = _compute_next_run(cron_expr)
            elif typ == "interval":
                seconds = int(config.get("seconds", 300))
                next_run = (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds")
            if next_run:
                t["next_run"] = next_run
                self.canvas_api.update_trigger(trigger_id, {"next_run": next_run})

    def _run_loop(self):
        """调度器主循环——每 30 秒检查一次。"""
        while self._running:
            try:
                self._check_triggers()
            except Exception as e:
                logger.error(f"[scheduler] 检查异常: {e}")
            time.sleep(self._check_interval)

    def _check_triggers(self):
        """检查并触发到期的定时任务。"""
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")

        with self._lock:
            triggered_ids = []
            for tid, t in list(self._active_triggers.items()):
                next_run = t.get("next_run")
                if next_run and next_run <= now_iso:
                    triggered_ids.append(tid)

        for tid in triggered_ids:
            with self._lock:
                t = self._active_triggers.get(tid)
                if t is None:
                    continue
                workflow_id = t.get("workflow_id", "")
                typ = t.get("type", "")
                config = t.get("config", {})
                if isinstance(config, str):
                    try:
                        config = json.loads(config)
                    except (json.JSONDecodeError, TypeError):
                        config = {}
            if not workflow_id:
                continue

            logger.info(f"[scheduler] 触发工作流 {workflow_id} (触发器 {tid})")
            try:
                self._execute_workflow(workflow_id)
                # 更新 last_run
                self.canvas_api.update_trigger(tid, {
                    "last_run": now_iso,
                })
                # 清除 next_run 以便重新计算下次执行时间
                with self._lock:
                    if tid in self._active_triggers:
                        del self._active_triggers[tid]["next_run"]
                self._update_next_run(tid)
            except Exception as e:
                logger.error(f"[scheduler] 执行失败: {e}")

    def _execute_workflow(self, workflow_id: str):
        """触发工作流执行（通过 Engine，仍过 guardrails.check()）。

        Args:
            workflow_id: 工作流 ID
        """
        # 复用 canvas_api 的 execute_workflow 方法（已集成 guardrails）
        result = self.canvas_api.execute_workflow(workflow_id, mode="real")
        if result is None:
            logger.warning(f"[scheduler] 工作流 {workflow_id} 不存在")
        elif "error" in result:
            logger.error(f"[scheduler] 工作流 {workflow_id} 执行错误: {result['error']}")
        else:
            logger.info(f"[scheduler] 工作流 {workflow_id} 执行完成: run_id={result.get('run_id')}")
