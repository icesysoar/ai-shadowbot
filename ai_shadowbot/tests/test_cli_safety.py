"""TDD 红阶段：CLI 安全接线（P0 / P1-2）对抗测试。

覆盖：
  - P0：build_runtime 的 auto_confirm 恒为 False（删除 skip 整体放行短路，
        deny-unconfirmed 落实；危险动作不再零确认执行）。
  - P1-2：emergency.arm_hotkey() 在无 keyboard 库/无权限时静默（不抛异常）。
  - P0 验证：--real 模式下『打开 cmd』等危险动作不再零确认执行；破坏性命令被硬拦。
"""
import argparse

import pytest

from ai_shadowbot.actions import Action
from ai_shadowbot.cli import build_runtime
from ai_shadowbot.executor import Executor
from ai_shadowbot.guardrails import Guardrails, BLOCK


def _args(confirm="single", dry_run=True, real=False, mock=False):
    return argparse.Namespace(dry_run=dry_run, real=real, mock=mock, confirm=confirm)


def test_build_runtime_auto_confirm_false_even_when_skip():
    # P0：即便显式传 --confirm skip，auto_confirm 也必须是 False（危险动作不整体放行）
    _, _, executor, _, _ = build_runtime(_args(confirm="skip"))
    assert executor.auto_confirm is False


def test_emergency_arm_hotkey_is_safe_noop_without_keyboard():
    # P1-2：arm_hotkey 在缺少 keyboard 库/权限时应静默，不抛异常
    _, _, _, _, emergency = build_runtime(_args())
    emergency.arm_hotkey()  # 不应抛异常


def test_real_mode_dangerous_app_not_zero_confirmed():
    # cli --real 输入『打开 cmd』不再零确认执行（deny-unconfirmed）
    ex = Executor(dry_run=False, guardrails=Guardrails(strategy="single"), auto_confirm=False)
    r = ex.execute(Action("open_app", {"name": "cmd"}))
    assert r.blocked is True and r.performed is False


def test_real_mode_destructive_blocked():
    ex = Executor(dry_run=False, guardrails=Guardrails(strategy="single"), auto_confirm=False)
    r = ex.execute(Action("type_text", {"text": "del /f /q C:\\temp"}))
    assert r.blocked is True and r.performed is False
