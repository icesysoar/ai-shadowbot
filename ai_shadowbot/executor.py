"""执行引擎（F002） —— 把原子动作落到真实系统。

铁律：dry_run=True 时**绝不** import pyautogui、**绝不**真实移动鼠标/键盘。
真实执行仅在 dry_run=False 时 lazy import pyautogui 并 dispatch。

- 每个动作执行前经 guardrails.gate() 闸门（接 F003）；被拦截则不执行并记录原因。
- pre/post action 钩子（F002 AC3）用于回显、截图、日志等。
- 支持全局紧急停止（emergutor.emergency_stop），队列中实时检查。

迁移知识：
  - 「动作生成 ≠ 动作执行」：dry_run 是"生成≠执行"的工程化保证。
  - 「跨平台编码/DPI」：真实执行回显一律走 utf-8 安全字符串（见 _describe）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from ai_shadowbot.actions import Action
from ai_shadowbot.guardrails import ALLOW, BLOCK, Guardrails, EmergencyStop

# 钩子签名：pre(action) / post(action, result)
PreHook = Callable[[Action], None]
PostHook = Callable[[Action, "ExecResult"], None]


@dataclass
class ExecResult:
    action: Action
    performed: bool = False       # 是否真实执行
    blocked: bool = False          # 是否被护栏/紧急停止拦截
    reason: str = ""
    error: Optional[str] = None
    summary: str = ""


class Executor:
    def __init__(
        self,
        guardrails: Optional[Guardrails] = None,
        dry_run: bool = True,
        observer: Optional[Any] = None,
        emergency_stop: Optional[EmergencyStop] = None,
        auto_confirm: bool = False,
    ):
        self.guardrails = guardrails
        self.dry_run = dry_run
        self.observer = observer
        self.emergency_stop = emergency_stop
        self.auto_confirm = auto_confirm
        self.pre_hooks: List[PreHook] = []
        self.post_hooks: List[PostHook] = []
        # P2-2：真实模式（dry_run=False）禁止无护栏裸执行，杜绝安全校验真空
        if not self.dry_run and self.guardrails is None:
            raise ValueError(
                "真实执行模式（dry_run=False）必须提供 guardrails，"
                "禁止无护栏裸执行任意动作。"
            )

    # -- 单个动作执行 ------------------------------------------------------
    def execute(self, action: Action, dry_run: Optional[bool] = None) -> ExecResult:
        dr = self.dry_run if dry_run is None else dry_run

        # 前置钩子（pre）
        for h in self.pre_hooks:
            h(action)

        # 护栏闸门（pre）
        if self.guardrails is not None:
            res = self.guardrails.gate(action, user_confirmed=self.auto_confirm)
            if res.decision == BLOCK:
                result = ExecResult(
                    action, performed=False, blocked=True, reason=res.reason,
                    summary=f"[拦截] {self._describe(action)} —— {res.reason}",
                )
                self._run_post(result)
                return result
            if res.decision == "confirm" and not self.auto_confirm:
                result = ExecResult(
                    action, performed=False, blocked=True, reason="等待人工确认",
                    summary=f"[待确认] {self._describe(action)}",
                )
                self._run_post(result)
                return result

        if dr:
            # dry_run：只描述，不执行
            summary = f"[dry_run] 将执行 {self._describe(action)}"
            result = ExecResult(
                action, performed=False, blocked=False,
                reason="dry_run 模式未真实执行", summary=summary,
            )
        else:
            result = self._dispatch_real(action)

        self._run_post(result)
        return result

    # -- 批量执行（带紧急停止） -------------------------------------------
    def run_plan(self, actions: List[Action]) -> List[ExecResult]:
        results: List[ExecResult] = []
        for action in actions:
            if self.emergency_stop is not None and self.emergency_stop.is_stopped():
                results.append(ExecResult(
                    action, performed=False, blocked=True, reason="紧急停止",
                    summary="[紧急停止] 队列已中止",
                ))
                break
            results.append(self.execute(action))
        return results

    # -- 真实执行（仅 dry_run=False 调用，lazy import pyautogui） ----------
    def _dispatch_real(self, action: Action) -> ExecResult:
        try:
            import pyautogui  # 真正需要时才 import
        except Exception as e:
            return ExecResult(
                action, performed=False, blocked=True,
                reason=f"pyautogui 不可用：{e}", error=str(e),
                summary=f"[错误] {self._describe(action)} —— pyautogui 不可用",
            )
        try:
            if action.type == "click":
                pyautogui.click(action.params["x"], action.params["y"])
            elif action.type == "double_click":
                pyautogui.doubleClick(action.params["x"], action.params["y"])
            elif action.type == "right_click":
                pyautogui.rightClick(action.params["x"], action.params["y"])
            elif action.type == "type_text":
                pyautogui.write(action.params["text"], interval=0.02)
            elif action.type == "key_press":
                self._press_keys(pyautogui, action.params["key"])
            elif action.type == "wait":
                import time
                time.sleep(float(action.params["seconds"]))
            elif action.type == "open_app":
                self._open_app(action.params["name"])
            elif action.type == "scroll":
                pyautogui.scroll(action.params["dy"], action.params["dx"])
            elif action.type == "screenshot":
                self._capture_and_store()
            return ExecResult(
                action, performed=True, blocked=False,
                summary=f"[执行] {self._describe(action)}",
            )
        except Exception as e:
            return ExecResult(
                action, performed=False, blocked=False,
                reason=f"执行出错：{e}", error=str(e),
                summary=f"[错误] {self._describe(action)} —— {e}",
            )

    # -- 真实执行的辅助 ---------------------------------------------------
    @staticmethod
    def _press_keys(pyautogui, key: str) -> None:
        # 支持 'ctrl+c' / 'enter' 等组合键
        parts = [k.strip() for k in key.lower().split("+")]
        if len(parts) > 1:
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(parts[0])

    def _open_app(self, name: str) -> None:
        # Windows 用 start；其余平台用 open/xdg-open。仅在真实模式走 shell。
        import subprocess, sys
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", name])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen(["xdg-open", name])

    def _capture_and_store(self) -> None:
        if self.observer is not None:
            self.observer.screenshot()

    # -- 钩子与描述 -------------------------------------------------------
    def _run_post(self, result: ExecResult) -> None:
        for h in self.post_hooks:
            h(result.action, result)

    @staticmethod
    def _describe(action: Action) -> str:
        # utf-8 安全描述，杜绝 GBK 崩溃（见知识库「Windows Python GBK 编码崩溃」）
        from ai_shadowbot.guardrails import Guardrails as _G
        return _G.summarize(action)
