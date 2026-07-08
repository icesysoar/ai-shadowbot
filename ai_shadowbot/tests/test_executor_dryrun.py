"""TDD 红阶段：执行引擎（F002）+ dry_run 安全演练测试。

核心铁律：dry_run 模式下**绝不** import pyautogui、**绝不**真实移动鼠标/键盘。

覆盖：
  - dry_run 不 import pyautogui（F002 + 铁律）
  - dry_run 返回 performed=False、含 dry_run 摘要
  - 护栏在 executor 内拦截破坏性动作（即便 dry_run=False 也不执行）
  - pre/post action 钩子被调用（F002 AC3 接 F003）
  - 紧急停止中断 run_plan 队列（F003 AC3）
  - run_plan 批量 dry_run 全部不真实执行
  - screenshot 动作 dry_run 返回占位摘要

迁移知识：
  - 「动作生成 ≠ 动作执行」：dry_run 是"生成≠执行"的工程化保证。
  - 「Windows Python GBK 编码崩溃」：真实执行的回显用 utf-8 安全字符串。
"""
import sys

import pytest

from ai_shadowbot.actions import Action
from ai_shadowbot.guardrails import Guardrails, EmergencyStop, ALLOW, BLOCK
from ai_shadowbot.executor import Executor, ExecResult


def _skip_guard():
    return Guardrails(strategy="skip")


def test_dry_run_never_imports_pyautogui():
    before = "pyautogui" in sys.modules
    ex = Executor(dry_run=True, guardrails=_skip_guard())
    ex.execute(Action("click", {"x": 1, "y": 1}))
    after = "pyautogui" in sys.modules
    assert before is False
    assert after is False  # 全程未触碰 pyautogui —— 绝不真动鼠标


def test_dry_run_marked_not_performed():
    ex = Executor(dry_run=True, guardrails=_skip_guard())
    r: ExecResult = ex.execute(Action("click", {"x": 5, "y": 5}))
    assert r.performed is False
    assert r.blocked is False
    assert "dry_run" in r.summary


def test_destructive_blocked_even_in_real_mode():
    # 即便 dry_run=False，护栏拦截后也不执行、也不 import pyautogui
    ex = Executor(dry_run=False, guardrails=_skip_guard())
    r = ex.execute(Action("type_text", {"text": "rm -rf /"}))
    assert r.blocked is True
    assert "pyautogui" not in sys.modules
    assert r.performed is False


def test_pre_and_post_hooks_called():
    calls = []
    ex = Executor(dry_run=True, guardrails=_skip_guard())
    ex.pre_hooks.append(lambda a: calls.append(("pre", a.type)))
    ex.post_hooks.append(lambda a, res: calls.append(("post", a.type)))
    ex.execute(Action("wait", {"seconds": 1}))
    assert ("pre", "wait") in calls
    assert ("post", "wait") in calls


def test_emergency_stop_halts_queue():
    es = EmergencyStop()
    ex = Executor(dry_run=True, guardrails=_skip_guard(), emergency_stop=es)
    actions = [Action("click", {"x": 1, "y": 1}), Action("click", {"x": 2, "y": 2})]
    es.trigger()
    results = ex.run_plan(actions)
    assert len(results) == 1  # 首动作即被紧急停止，队列中止
    assert results[0].blocked is True
    assert "紧急停止" in results[0].reason


def test_run_plan_all_dry_run():
    ex = Executor(dry_run=True, guardrails=_skip_guard())
    actions = [
        Action("open_app", {"name": "notepad"}),
        Action("type_text", {"text": "hello"}),
        Action("wait", {"seconds": 1}),
    ]
    results = ex.run_plan(actions)
    assert len(results) == 3
    assert all(not r.performed for r in results)
    assert all(not r.blocked for r in results)


def test_screenshot_dry_run_placeholder():
    ex = Executor(dry_run=True, guardrails=_skip_guard())
    r = ex.execute(Action("screenshot", {}))
    assert r.performed is False
    assert ("截图" in r.summary) or ("screenshot" in r.summary.lower())


def test_risky_app_pends_confirm_in_single_mode():
    # 单步策略下未确认 → 不执行
    ex = Executor(dry_run=True, guardrails=Guardrails(strategy="single"))
    r = ex.execute(Action("open_app", {"name": "cmd"}))
    assert r.blocked is True
    assert r.performed is False
