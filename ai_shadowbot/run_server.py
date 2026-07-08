#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 影刀 · 网关启动助手

职责（全部用 Python 实现，避开 cmd 批处理的编码/语法陷阱）：
  1. 清理已被占用的端口（避免 10048 冲突）
  2. 用 `cmd /k` 起 L5 网关到独立控制台窗口（出错也保持窗口便于排查）
  3. 轮询 /health 直到就绪
  4. 自动打开浏览器画布
  5. 本进程随后退出，网关在独立窗口继续运行
"""
import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # .../ai_shadowbot
PROJECT_ROOT = ROOT.parent                       # .../自动系统
PORT = 8792
PY = r"C:\Users\Soara\.workbuddy\binaries\python\envs\l5bridge\Scripts\python.exe"
URL = f"http://localhost:{PORT}/"


def log(msg: str) -> None:
    print(f"[启动器] {msg}", flush=True)


def kill_port(port: int) -> None:
    """关闭占用指定端口的 LISTENING 进程。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception as e:  # noqa: BLE001
        log(f"netstat 调用失败: {e}")
        return
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            pid = line.split()[-1]
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, text=True, timeout=10,
                )
                log(f"已关闭占用端口 {port} 的进程 (PID {pid})")
            except Exception as e:  # noqa: BLE001
                log(f"关闭 PID {pid} 失败: {e}")


def wait_health(timeout: int = 30) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/health", timeout=2
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return False


def main() -> None:
    log(f"项目根目录: {PROJECT_ROOT}")
    if not Path(PY).exists():
        log(f"[错误] 未找到 Python 解释器: {PY}")
        sys.exit(1)

    log(f"清理端口 {PORT}（避免冲突）...")
    kill_port(PORT)
    time.sleep(1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    log("启动 L5 网关（独立窗口，出错也会保持）...")
    try:
        # cmd /k 包裹：即使 python 报错，窗口也会停留显示 traceback
        subprocess.Popen(
            ["cmd", "/k", PY, "-m", "ai_shadowbot.l5_gateway",
             "--mode", "http", "--port", str(PORT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as e:  # noqa: BLE001
        log(f"[错误] 网关启动失败: {e}")
        sys.exit(1)

    log("等待网关就绪（最长 30 秒）...")
    if wait_health():
        log(f"[OK] 网关已就绪，正在打开画布: {URL}")
        try:
            webbrowser.open(URL)
        except Exception:  # noqa: BLE001
            pass
    else:
        log(f"[!] 网关启动超时。请查看弹出的“网关”窗口中的报错。")
        log(f"    仍可手动在浏览器访问: {URL}")
        try:
            webbrowser.open(URL)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
