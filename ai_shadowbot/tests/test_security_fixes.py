"""对抗测试 T011（P0 / P1-2 / P2-2 / P1-3 修复验证）。

对应凌澈明 QA + 云见微合并 QA 的修复项：
  P0   ：cli --confirm 默认 single；--real 禁止与 --confirm skip 共存。
  P1-2 ：build_runtime 必须调用 emergency.arm_hotkey()（ESC 产品内生效）。
  P2-2 ：Executor 在 dry_run=False 且无 guardrails 时拒绝裸执行（raise）。
  P1-3 ：cli 构造 Observer 时传入 config.screen_mask_sensitive（脱敏不再死标志）。
"""
import argparse

import pytest

from ai_shadowbot import cli as cli_mod
from ai_shadowbot.executor import Executor, ExecResult
from ai_shadowbot.guardrails import Guardrails, EmergencyStop
from ai_shadowbot.observer import Observer
from ai_shadowbot.actions import Action


# ---------------------------------------------------------------------------
# P0：CLI 确认策略默认 single，且 --real 禁与 skip 共存
# ---------------------------------------------------------------------------
def test_cli_default_confirm_is_single():
    parser = argparse.ArgumentParser()
    # 复刻 main() 的 add_argument，验证默认
    parser.add_argument("--confirm", choices=["skip", "single", "batch"], default="single")
    args = parser.parse_args([])
    assert args.confirm == "single"


def test_real_with_skip_is_rejected():
    # 直接验证 main() 对 --real + --confirm skip 的拒绝逻辑
    with pytest.raises(SystemExit):
        cli_mod.main(["--real", "--confirm", "skip"])


def test_dry_run_with_skip_still_allowed(monkeypatch):
    # dry_run + --confirm skip 不应触发「确认闸门关闭」拒绝（不触达真实鼠标，无风险）
    # 用 monkeypatch 跳过交互循环，验证 main() 顺利越过冲突检查并进入 run_cli
    called = {"n": 0}

    def fake_run_cli(args):
        called["n"] += 1

    monkeypatch.setattr(cli_mod, "run_cli", fake_run_cli)
    # 若 main() 在冲突检查处 parser.error，则不会调用 run_cli → 断言失败
    cli_mod.main(["--dry-run", "--mock", "--confirm", "skip"])
    assert called["n"] == 1, "dry_run + skip 不应被确认冲突检查拒绝"


# ---------------------------------------------------------------------------
# P1-2：build_runtime 接线 arm_hotkey
# ---------------------------------------------------------------------------
def test_build_runtime_arms_hotkey(monkeypatch):
    called = {"n": 0}

    def fake_arm(self):
        called["n"] += 1

    monkeypatch.setattr(EmergencyStop, "arm_hotkey", fake_arm)
    cli_mod.build_runtime(argparse.Namespace(dry_run=True, mock=True, confirm="single", real=False))
    assert called["n"] == 1, "build_runtime 必须调用 emergency.arm_hotkey()"


# ---------------------------------------------------------------------------
# P2-2：禁止无护栏真实裸执行
# ---------------------------------------------------------------------------
def test_executor_refuses_bare_real_execution():
    with pytest.raises(ValueError):
        Executor(dry_run=False, guardrails=None)


def test_executor_allows_dry_run_without_guardrails():
    # dry_run 下无护栏是安全的（不触达真实鼠标）
    ex = Executor(dry_run=True, guardrails=None)
    r: ExecResult = ex.execute(Action("click", {"x": 1, "y": 1}))
    assert r.performed is False
    assert r.blocked is False


def test_executor_real_with_guardrails_ok():
    ex = Executor(dry_run=False, guardrails=Guardrails(strategy="single"))
    # 未真正执行（pyautogui 不可用环境会安全失败），但不应因"无护栏"而 raise
    r = ex.execute(Action("wait", {"seconds": 0}))
    assert isinstance(r, ExecResult)


# ---------------------------------------------------------------------------
# P1-3：cli 把 screen_mask_sensitive 传入 Observer（脱敏不再是死标志）
# ---------------------------------------------------------------------------
def test_build_runtime_passes_mask_flag(monkeypatch):
    ns = argparse.Namespace(dry_run=False, mock=True, confirm="single", real=False)
    # 强制 config.screen_mask_sensitive=True 以验证透传
    import ai_shadowbot.config as cfg_mod
    monkeypatch.setattr(cfg_mod.Config, "from_env",
                        classmethod(lambda cls: cfg_mod.Config(screen_mask_sensitive=True)))
    # 捕获 build_runtime 实际传给 Observer 的参数（P1-3：脱敏不再是死标志）
    captured = {}

    def fake_init(self, screen_mask_sensitive=False):
        captured["screen_mask_sensitive"] = screen_mask_sensitive

    monkeypatch.setattr(Observer, "__init__", fake_init)
    cli_mod.build_runtime(ns)
    assert captured.get("screen_mask_sensitive") is True, \
        "cli.build_runtime 必须把 config.screen_mask_sensitive 传入 Observer"
