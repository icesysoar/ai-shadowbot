"""交互层（F004） —— CLI 聊天入口。

聊天循环：自然语言输入 → planner 规划 → 展示计划并确认（受 F003 策略影响）
→ executor 执行（默认 dry_run 安全演练）→ 展示进度。支持中途停止与会话导出。

铁律：默认 dry_run=True，**绝不**无确认地真实移动用户鼠标（见 executor 模块）。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List

# Windows 中文日志防 GBK 崩溃（知识库「Windows Python GBK 编码崩溃」）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except Exception:
    pass

from ai_shadowbot.config import Config
from ai_shadowbot.planner import Planner
from ai_shadowbot.executor import Executor
from ai_shadowbot.guardrails import Guardrails, EmergencyStop
from ai_shadowbot.observer import Observer
from ai_shadowbot.vision import VisionLocator  # F005：视觉坐标系统
from ai_shadowbot.actions import Action
from ai_shadowbot.compiler import WorkflowCompiler, save_workflow  # F006：工作流编译器
from ai_shadowbot.engine import Engine  # F006：工作流执行引擎
from ai_shadowbot.workflow import NodeType  # F006：节点类型枚举


class SessionRecorder:
    """会话记录与 action 脚本导出（AC4）。"""

    def __init__(self) -> None:
        self.instructions: List[str] = []
        self.plan_log: List[List[dict]] = []

    def record(self, instruction: str, actions: List[Action]) -> None:
        self.instructions.append(instruction)
        self.plan_log.append([a.to_dict() for a in actions])

    def export(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"instructions": self.instructions, "plans": self.plan_log},
                f, ensure_ascii=False, indent=2,
            )


def build_runtime(args) -> tuple:
    config = Config.from_env()
    if args.mock:
        config.mock = True
    # 传入 config 使注入语义分类器（R1）在真实模式下可用 LLM；
    # mock 下分类器自动回退 patterns（零 LLM、不崩）。enable_llm 默认开、可关。
    guardrails = Guardrails(strategy=args.confirm, config=config)
    emergency = EmergencyStop()
    # P1-2：接线 ESC/Ctrl+C 全局热键（无 keyboard 库/无权限时静默失败，不阻塞）
    emergency.arm_hotkey()
    # 真实模式才需要截图；脱敏标志来自环境变量 SCREEN_MASK_SENSITIVE（AC5）
    observer = Observer(screen_mask_sensitive=config.screen_mask_sensitive) if not args.dry_run else None
    planner = Planner(config)
    executor = Executor(
        guardrails=guardrails,
        dry_run=args.dry_run,
        observer=observer,
        emergency_stop=emergency,
        # P0：移除「auto_confirm = (confirm == "skip")」整体放行短路。
        # 危险动作永不在无确认下自动执行；仅白名单低危只读原语本就 ALLOW，
        # CONFIRM/BLOCK 动作始终受 deny-unconfirmed 约束，skip 不再放行高危。
        auto_confirm=False,
    )
    return config, planner, executor, guardrails, emergency


def show_plan(actions: List[Action], guardrails: Guardrails) -> None:
    print("\n📋 计划（%d 步）：" % len(actions))
    for i, a in enumerate(actions, 1):
        verdict = guardrails.check(a)
        tag = {"allow": "✅", "block": "⛔", "confirm": "⚠️"}.get(verdict.decision, "")
        print(f"  {i}. {tag} {guardrails.summarize(a)}")


def run_cli(args) -> None:
    config, planner, executor, guardrails, emergency = build_runtime(args)
    recorder = SessionRecorder()
    mode = "DRY_RUN(安全演练)" if args.dry_run else "REAL(真实执行)"
    print("=" * 56)
    print("  AI 版影刀 · ai-shadowbot  (mode=%s)" % mode)
    print("  输入自然语言指令；输入 exit/quit 退出；ESC 中途停止")
    if config.mock:
        print("  [mock 模式] 未使用真实 LLM（启发式规划）")
    print("=" * 56)

    while True:
        try:
            instruction = input("\n👤 你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[已退出]")
            break
        if not instruction:
            continue
        if instruction.lower() in ("exit", "quit", "q"):
            break
        if emergency.is_stopped():
            print("[紧急停止已触发，队列中止。输入 reset 解除]")
            if input("  继续? (reset/其他)> ").strip().lower() == "reset":
                emergency.reset()
            continue

        # 1) 规划
        result = planner.plan(instruction)
        if not result.success:
            print(f"⚠️ 无法规划：{result.reason}")
            continue

        # 2) 展示计划
        show_plan(result.actions, guardrails)

        # 3) 确认（dry_run 下默认直接演练；真实模式按策略）
        if not args.dry_run and args.confirm in ("single", "batch"):
            if args.confirm == "batch":
                guardrails.confirm_batch()
            ans = input("确认执行？(y/n)> ").strip().lower()
            if ans != "y":
                print("[已取消]")
                continue
            # 计划级确认通过：本批次放行（含 CONFIRM 高危动作），
            # 落实共识「计划级批量确认 + deny-unconfirmed」——未确认过的高危动作绝不自动执行。
            executor.auto_confirm = True

        # 4) 执行
        recorder.record(instruction, result.actions)
        results = executor.run_plan(result.actions)
        print("\n🤖 执行结果：")
        for r in results:
            print("  " + r.summary)

    # 会话导出
    if recorder.instructions:
        out = "session_plan.json"
        recorder.export(out)
        print(f"\n[会话已导出到 {out}]")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="AI 版影刀 · 自然语言驱动电脑操作")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="安全演练模式（默认开，绝不真动鼠标）")
    parser.add_argument("--real", action="store_true",
                        help="真实执行模式（关掉 dry_run，会真动鼠标！）")
    parser.add_argument("--mock", action="store_true",
                        help="强制 mock 规划（无需 API key）")
    parser.add_argument("--confirm", choices=["skip", "single", "batch"],
                        default="single", help="确认策略（默认 single：危险动作需人工确认）")
    parser.add_argument("--vision", action="store_true",
                        help="视觉坐标系统演示（dry_run 安全演练，不真截图/识别/点击）")
    parser.add_argument("--compile", type=str, metavar="QUERY",
                        help="自然语言→工作流编译: 输入需求，输出 DAG，确认后执行")
    parser.add_argument("--run-workflow", type=str, metavar="PATH",
                        help="加载已有工作流 JSON 并执行")
    parser.add_argument("--workflow-demo", action="store_true",
                        help="dry_run 下展示工作流完整流水线（编译→展示→执行→日志）")
    args = parser.parse_args(argv)
    if args.real:
        args.dry_run = False
    # P0：真实模式禁止与 --confirm skip 共存（否则确认闸门整体关闭，危险 app 零确认）
    if args.real and args.confirm == "skip":
        parser.error("--real 模式禁止与 --confirm skip 共存：真实执行至少需 single/batch 确认策略")
    if args.vision:
        run_vision_demo(args)
        return
    if args.compile:
        run_workflow_compile(args, args.compile)
        return
    if args.run_workflow:
        run_workflow_file(args, args.run_workflow)
        return
    if args.workflow_demo:
        run_workflow_demo(args)
        return
    run_cli(args)


def run_vision_demo(args) -> None:
    """F005 CLI 演示：dry_run 下展示「截图→脱敏→识别→坐标→动作→护栏」全流程，不真执行。

    无显示/GPU/API key 环境下用 Observer.screenshot(_image=...) 注入演示截图，
    用明确标注 [演示桩] 的 VisionLocator 返回固定坐标，仅演示流水线，绝不伪造真实识别。
    """
    config, planner, executor, guardrails, emergency = build_runtime(args)
    print("=" * 56)
    print("  AI 影刀 · 视觉坐标系统演示 (dry_run, 不真执行)")
    print("=" * 56)

    # 1) 构造演示截图（无显示环境用 _image 注入，避免真实截图）
    try:
        from PIL import Image
        demo_img = Image.new("RGB", (400, 300), (240, 240, 240))
    except Exception:
        print("[演示] 无 PIL，无法构造演示截图，退出")
        return
    observer = Observer(screen_mask_sensitive=config.screen_mask_sensitive)
    shot_b64 = observer.screenshot(_image=demo_img)  # 含 AC5 脱敏
    print("\n[1] 截图 → 脱敏(AC5): 已生成脱敏截图 base64（敏感区已打码）")

    # 2) 演示桩定位器（明确标注 [演示桩]，非真实 LLM，仅用于演示流水线）
    class DemoLocator(VisionLocator):
        def vision_resolve(self, screenshot_bytes, query):
            return {"x": 120, "y": 80, "label": "登录", "confidence": 0.95}

    locator = DemoLocator(config)
    print(f"[2] 视觉识别 → 坐标: query='点击登录按钮' → (x=120, y=80, label=登录) [演示桩]")

    # 3) 坐标 → 动作（grounding）
    result = planner.ground_to_action("点击登录按钮", shot_b64, locator)
    if not result.success:
        print(f"[!] grounding 失败: {result.reason}")
        return
    print(f"[3] 坐标→动作: {[guardrails.summarize(a) for a in result.actions]}")

    # 4) 过 guardrails 闸门（视觉派生动作原样过，deny-unconfirmed 不削弱）
    print("[4] 过 guardrails 闸门:")
    for a in result.actions:
        v = guardrails.check(a)
        print(f"    {guardrails.summarize(a)} → {v.decision}")

    print("\n[dry_run] 未真实点击/移动鼠标（演示结束）")


def show_workflow(workflow, guardrails) -> None:
    """展示工作流节点图（§6.3 用户审查机制）。"""
    print(f"\n📋 工作流「{workflow.name}」")
    if workflow.triggers:
        for t in workflow.triggers:
            tc = t.config or {}
            if t.type.value == "cron":
                print(f"  ⏰ 触发器: cron({tc.get('cron', '')}, {tc.get('timezone', 'Asia/Shanghai')})")
            elif t.type.value == "hotkey":
                print(f"  ⌨️ 触发器: hotkey({tc.get('hotkey', '')})")
            else:
                print(f"  🔄 触发器: manual")
    if workflow.variables:
        print(f"  📊 变量:")
        for var_name, var_def in workflow.variables.items():
            default_val = var_def.default if var_def.default is not None else ""
            print(f"    {var_name} ({var_def.type.value} = {default_val})")
    print(f"\n  ┌─ 节点图:")
    for n in workflow.nodes:
        label = n.label or n.type.value
        if n.type == NodeType.start:
            print(f"  ├─ {n.id} [start]")
        elif n.type == NodeType.end:
            print(f"  ├─ {n.id} [end]")
        elif n.type == NodeType.atomic:
            act = n.params.get("atomic_action", "")
            detail = ""
            if act == "open_app":
                detail = f" {n.params.get('name', '')}"
            elif act == "type_text":
                detail = f" \"{n.params.get('text', '')}\""
            elif act == "screenshot":
                detail = ""
            elif act == "wait":
                detail = f" {n.params.get('seconds', '')}s"
            elif act == "click":
                detail = f" ({n.params.get('x', '?')}, {n.params.get('y', '?')})"
            elif act:
                detail = f" {act}"
            # guardrails 预检标记
            action = type("_Action", (), {"type": act, "params": n.params})()
            try:
                verdict = guardrails.check(action)
                tag = {"allow": "✅", "block": "⛔", "confirm": "⚠️"}.get(verdict.decision, "")
            except Exception:
                tag = "❓"
            print(f"  ├─ {n.id} [{label}]{detail} {tag}")
        elif n.type == NodeType.condition:
            expr = n.params.get("expression", "")
            print(f"  ├─ {n.id} [condition] {expr}")
            for b in n.branches:
                bc = b.get("condition", "")
                bn = b.get("next", "")
                print(f"  │    ├─ {bc} → {bn}")
        elif n.type == NodeType.loop:
            lt = n.params.get("loop_type", "while")
            cond = n.params.get("condition", "")
            mi = n.params.get("max_iterations", 100)
            print(f"  ├─ {n.id} [loop] {lt} ({cond}), max={mi}")
            for c in n.children:
                print(f"  │    └─ child: {c}")
        elif n.type == NodeType.wait:
            secs = n.params.get("seconds", "?")
            print(f"  ├─ {n.id} [wait] {secs}s")
    if workflow.error_strategy:
        es = workflow.error_strategy
        print(f"\n  错误策略: {es.type.value}(max={es.max_retries}, interval={es.retry_interval}s)")
    print()


def run_workflow_compile(args, query: str) -> None:
    """模式 1: --compile "自然语言需求" → 编译 → 展示 → 确认 → 执行。"""
    config = Config.from_env()
    if args.mock:
        config.mock = True
    compiler = WorkflowCompiler(config)
    print(f"\n🔧 正在编译: \"{query}\"")
    compile_result = compiler.compile(query)
    if not compile_result.success:
        print(f"❌ 编译失败：{compile_result.reason}")
        return
    workflow = compile_result.workflow
    print(f"✅ 编译成功 ({compile_result.reason})")
    guardrails = Guardrails(strategy=args.confirm, config=config)
    show_workflow(workflow, guardrails)
    # 确认
    ans = input("确认执行？(y/n)> ").strip().lower()
    if ans != "y":
        print("[已取消]")
        return
    # 执行
    emergency = EmergencyStop()
    executor = Executor(
        guardrails=guardrails,
        dry_run=args.dry_run,
        emergency_stop=emergency,
        auto_confirm=True,
    )
    engine = Engine(
        executor=executor,
        guardrails=guardrails,
        dry_run=args.dry_run,
        emergency_stop=emergency,
    )
    if args.dry_run:
        result = engine.dry_run(workflow)
    else:
        result = engine.execute(workflow)
    # 展示结果
    print(f"\n🤖 执行结果（{result.total_duration:.2f}s）：")
    for log in result.node_logs:
        status_icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️",
                       "ABORTED": "🚫", "DEGRADED": "⚠️", "RUNNING": "⏳",
                       "PENDING": "⏸️"}.get(log.status, "❓")
        label = f"[{log.node_type}]" if log.node_type else ""
        print(f"  {log.node_id} {status_icon} {label} {log.error or ''}")
    print(f"\n{'✅' if result.success else '❌'} 执行{'完成' if result.success else '失败'}")
    if not args.dry_run:
        save_workflow(workflow, f"{workflow.id}.json")
        print(f"[工作流已保存到 {workflow.id}.json]")


def run_workflow_file(args, path: str) -> None:
    """模式 2: --run-workflow wf.json → 加载 → 展示 → 确认 → 执行。"""
    from ai_shadowbot.compiler import load_workflow
    try:
        workflow = load_workflow(path)
    except Exception as e:
        print(f"❌ 加载工作流失败：{e}")
        return
    config = Config.from_env()
    guardrails = Guardrails(strategy=args.confirm, config=config)
    show_workflow(workflow, guardrails)
    ans = input("确认执行？(y/n)> ").strip().lower()
    if ans != "y":
        print("[已取消]")
        return
    emergency = EmergencyStop()
    executor = Executor(
        guardrails=guardrails,
        dry_run=args.dry_run,
        emergency_stop=emergency,
        auto_confirm=True,
    )
    engine = Engine(
        executor=executor,
        guardrails=guardrails,
        dry_run=args.dry_run,
        emergency_stop=emergency,
    )
    if args.dry_run:
        result = engine.dry_run(workflow)
    else:
        result = engine.execute(workflow)
    print(f"\n🤖 执行结果（{result.total_duration:.2f}s）：")
    for log in result.node_logs:
        status_icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️",
                       "ABORTED": "🚫", "DEGRADED": "⚠️", "RUNNING": "⏳",
                       "PENDING": "⏸️"}.get(log.status, "❓")
        print(f"  {log.node_id} {status_icon} [{log.node_type}] {log.error or ''}")
    print(f"\n{'✅' if result.success else '❌'} 执行{'完成' if result.success else '失败'}")


def run_workflow_demo(args) -> None:
    """模式 3: --workflow-demo 演示完整流水线（dry_run）。"""
    config = Config.from_env()
    config.mock = True
    compiler = WorkflowCompiler(config)
    guardrails = Guardrails(strategy="single", config=config)
    print("=" * 56)
    print("  🔬 工作流流水线演示 (dry_run)")
    print("=" * 56)
    query = "打开记事本并输入Hello然后截图"
    print(f"\n[1] 编译: \"{query}\"")
    result = compiler.compile(query)
    if not result.success:
        print(f"  ❌ 编译失败：{result.reason}")
        return
    wf = result.workflow
    print(f"  工作流: {wf.name} ({wf.id})")
    show_workflow(wf, guardrails)
    print(f"\n[2] 执行 (dry_run):")
    executor = Executor(guardrails=guardrails, dry_run=True)
    engine = Engine(executor=executor, guardrails=guardrails, dry_run=True)
    exec_result = engine.dry_run(wf)
    for log in exec_result.node_logs:
        status_icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️",
                       "ABORTED": "🚫", "DEGRADED": "⚠️"}.get(log.status, "❓")
        print(f"  {log.node_id} {status_icon} [{log.node_type}] {log.error or ''}")
    print(f"\n[3] 变量最终状态: {exec_result.final_variables}")
    print(f"[4] 总耗时: {exec_result.total_duration:.2f}s")
    print("[dry_run] 未真实执行任何动作")


if __name__ == "__main__":
    main()
