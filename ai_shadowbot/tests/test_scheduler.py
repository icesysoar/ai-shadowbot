"""调度器测试（Phase 3 / F009）—— 调度 CRUD + 触发执行（mock Engine）。"""
from __future__ import annotations

import json
import os
import sys
import time
import tempfile
import threading
from unittest.mock import patch, MagicMock
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


@pytest.fixture
def scheduler(canvas_api):
    from ai_shadowbot.scheduler import Scheduler
    sched = Scheduler(canvas_api, check_interval=1)
    yield sched
    sched.stop()


# ---------------------------------------------------------------------------
# 调度 CRUD 测试
# ---------------------------------------------------------------------------

class TestSchedulerCRUD:
    def test_create_trigger_via_scheduler(self, scheduler, canvas_api):
        """通过调度器创建触发器。"""
        # 先创建一个工作流
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        tid = scheduler.add_trigger({
            "workflow_id": wf_id,
            "type": "cron",
            "config": {"cron": "*/5 * * * *"},
            "enabled": True,
        })
        assert tid.startswith("trg_")

        triggers = canvas_api.list_triggers(wf_id)
        assert len(triggers) == 1
        assert triggers[0]["id"] == tid
        assert triggers[0]["type"] == "cron"

    def test_remove_trigger(self, scheduler, canvas_api):
        """删除触发器。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        tid = scheduler.add_trigger({"workflow_id": wf_id, "type": "interval",
                                      "config": {"seconds": 300}})
        assert scheduler.remove_trigger(tid) is True
        triggers = canvas_api.list_triggers(wf_id)
        assert len(triggers) == 0

    def test_toggle_trigger(self, scheduler, canvas_api):
        """切换触发器启用/禁用。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        tid = scheduler.add_trigger({"workflow_id": wf_id, "type": "cron",
                                      "config": {"cron": "*/10 * * * *"}})

        # 默认启用
        triggers = canvas_api.list_triggers(wf_id)
        assert triggers[0]["enabled"] == 1

        # 切换禁用
        new_state = scheduler.toggle_trigger(tid)
        assert new_state is False
        triggers = canvas_api.list_triggers(wf_id)
        assert triggers[0]["enabled"] == 0

        # 切回启用
        new_state = scheduler.toggle_trigger(tid)
        assert new_state is True

    def test_update_trigger(self, canvas_api):
        """更新触发器配置。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        tid = canvas_api.create_trigger({"workflow_id": wf_id, "type": "cron",
                                          "config": {"cron": "*/5 * * * *"}})
        ok = canvas_api.update_trigger(tid, {"config": {"cron": "*/10 * * * *"}})
        assert ok is True

        triggers = canvas_api.list_triggers(wf_id)
        assert triggers[0]["config"]["cron"] == "*/10 * * * *"

    def test_delete_trigger_direct(self, canvas_api):
        """直接通过 canvas_api 删除触发器。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        tid = canvas_api.create_trigger({"workflow_id": wf_id, "type": "manual", "config": {}})
        ok = canvas_api.delete_trigger(tid)
        assert ok is True
        triggers = canvas_api.list_triggers(wf_id)
        assert len(triggers) == 0


# ---------------------------------------------------------------------------
# 调度器生命周期测试
# ---------------------------------------------------------------------------

class TestSchedulerLifecycle:
    def test_start_stop(self, scheduler):
        """启动/停止调度器。"""
        assert scheduler._running is False
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False

    def test_status(self, scheduler, canvas_api):
        """调度器状态查询。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        scheduler.start()
        scheduler.add_trigger({"workflow_id": wf_id, "type": "cron",
                                "config": {"cron": "*/5 * * * *"}})
        st = scheduler.status()
        assert st["running"] is True
        assert st["active_triggers"] == 1
        scheduler.stop()

    def test_multiple_triggers(self, scheduler, canvas_api):
        """多个触发器。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        scheduler.start()
        t1 = scheduler.add_trigger({"workflow_id": wf_id, "type": "cron",
                                     "config": {"cron": "*/5 * * * *"}})
        t2 = scheduler.add_trigger({"workflow_id": wf_id, "type": "interval",
                                     "config": {"seconds": 600}})
        assert t1 != t2
        st = scheduler.status()
        assert st["active_triggers"] == 2
        scheduler.stop()


# ---------------------------------------------------------------------------
# 调度执行测试（mock Engine）
# ---------------------------------------------------------------------------

class TestSchedulerExecution:
    def test_execute_on_trigger(self, scheduler, canvas_api):
        """触发器到期时执行工作流（mock execute_workflow）。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})

        with patch.object(canvas_api, 'execute_workflow', return_value={"run_id": "mock_run", "execution": {"success": True}}) as mock_exec:
            scheduler.start()
            # 创建间隔触发器，设置 next_run 为过去时间以立即触发
            tid = scheduler.add_trigger({
                "workflow_id": wf_id,
                "type": "interval",
                "config": {"seconds": 60},
                "next_run": "2020-01-01T00:00:00",
            })
            # 等待调度循环检查（_check_interval=1）
            time.sleep(2)
            scheduler.stop()
            # execute_workflow 应该被调用
            assert mock_exec.called

    def test_interval_trigger_executes(self, scheduler, canvas_api):
        """interval 类型触发器到期执行。"""
        wf_id = canvas_api.create_workflow({"name": "test", "flow": {"nodes": [], "edges": []}})
        # 设置过去的时间作为 next_run 以立即触发
        canvas_api.create_trigger({
            "workflow_id": wf_id,
            "type": "interval",
            "config": {"seconds": 60},
            "enabled": True,
            "next_run": "2020-01-01T00:00:00",
        })
        with patch.object(canvas_api, 'execute_workflow', return_value={"run_id": "mock"}) as mock_exec:
            scheduler.start()
            time.sleep(2)
            scheduler.stop()
            assert mock_exec.called


# ---------------------------------------------------------------------------
# cron 解析器测试
# ---------------------------------------------------------------------------

class TestCronParser:
    def test_every_minute(self):
        from ai_shadowbot.scheduler import _parse_cron_minute, _should_run_at
        minutes = _parse_cron_minute("* * * * *")
        assert len(minutes) == 60
        assert 0 in minutes
        assert 59 in minutes

    def test_every_5_minutes(self):
        from ai_shadowbot.scheduler import _parse_cron_minute
        minutes = _parse_cron_minute("*/5 * * * *")
        assert minutes == [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

    def test_specific_minute(self):
        from ai_shadowbot.scheduler import _parse_cron_minute
        minutes = _parse_cron_minute("30 * * * *")
        assert minutes == [30]

    def test_multiple_minutes(self):
        from ai_shadowbot.scheduler import _parse_cron_minute
        minutes = _parse_cron_minute("15,30,45 * * * *")
        assert minutes == [15, 30, 45]

    def test_range_minutes(self):
        from ai_shadowbot.scheduler import _parse_cron_minute
        minutes = _parse_cron_minute("10-15 * * * *")
        assert minutes == [10, 11, 12, 13, 14, 15]

    def test_should_run_at(self):
        from ai_shadowbot.scheduler import _should_run_at
        from datetime import datetime

        dt = datetime(2026, 7, 7, 10, 30, 0)
        assert _should_run_at("*/5 * * * *", dt) is True  # 30 在 */5 中
        assert _should_run_at("0 * * * *", dt) is False   # 30 ≠ 0
        assert _should_run_at("* * * * *", dt) is True     # 每分钟

    def test_compute_next_run(self):
        from ai_shadowbot.scheduler import _compute_next_run
        from datetime import datetime

        dt = datetime(2026, 7, 7, 10, 0, 0)
        nr = _compute_next_run("5 * * * *", dt)
        assert nr is not None
        # 下次应为 10:05
        assert "10:05" in nr
