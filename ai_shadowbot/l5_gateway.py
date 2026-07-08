#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 版影刀 · L5 跨 AI 触发网关

扩展 soara-l5bridge，新增工作流引擎 API，让外部 AI 工具（trae / 网页AI / MCP客户端等）
能通过 HTTP REST API 或 MCP stdio 调用我们的工作流编译器 + 执行引擎。

一键编译+执行：
  POST /l5/ai-run  {"query":"打开记事本输入hello并截图"} -> {workflow, execution}

用法：
  # 启动网关（HTTP + MCP 双模）
  #   HTTP  监听 --port（默认 8792）
  #   MCP   通过 streamable-http 监听独立端口 8794（http://127.0.0.1:8794/mcp），与 HTTP 不冲突
  python -m ai_shadowbot.l5_gateway --mode both --port 8792

  # 外部 AI 调用（HTTP）
  curl -X POST http://127.0.0.1:8792/l5/ai-run \
    -H 'content-type: application/json' \
    -d '{"query": "打开记事本输入hello并截图"}'
"""
from __future__ import annotations

import json
import os
import sys
import threading
import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel

# ----------------------------------------------------------------------------
# 工作流引擎导入
# ----------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ai_shadowbot/.. -> 自动系统
sys.path.insert(0, str(_PROJECT_ROOT))

from ai_shadowbot.config import Config
from ai_shadowbot.compiler import WorkflowCompiler, CompileResult
from ai_shadowbot.engine import Engine, ExecutionResult
from ai_shadowbot.guardrails import Guardrails, EmergencyStop
from ai_shadowbot.executor import Executor
from ai_shadowbot.observer import Observer

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
PORT = int(os.environ.get("L5BRIDGE_PORT", "8792"))
# both 模式下 MCP 使用的独立端口（streamable-http），与 HTTP 的 --port 分离，避免二次 bind 冲突
MCP_PORT = int(os.environ.get("L5BRIDGE_MCP_PORT", "8794"))
TOKEN = os.environ.get("L5BRIDGE_TOKEN", "")

_runs: dict = {}
_lock = threading.Lock()


# ----------------------------------------------------------------------------
# 运行实例
# ----------------------------------------------------------------------------
class L5Run:
    def __init__(self, run_id: str, query: str, mode: str = "dry_run"):
        self.run_id = run_id
        self.query = query
        self.mode = mode
        self.status = "pending"
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.started_at = datetime.datetime.now().isoformat(timespec="seconds")

    def start(self):
        """执行一次 ai-run（编译 + 执行）。"""
        self.status = "compiling"
        try:
            config = Config()
            guardrails = Guardrails(config=config, strategy="single")
            emergency = EmergencyStop()
            emergency.arm_hotkey()
            observer = Observer(screen_mask_sensitive=config.screen_mask_sensitive)
            executor = Executor(
                dry_run=(self.mode != "real"),
                guardrails=guardrails,
                emergency_stop=emergency,
                observer=observer,
            )
            compiler = WorkflowCompiler(config)

            # F015.3: 创建 BrowserWorker（auto_start=False，L5 网关不自动拉起 bridge）
            from ai_shadowbot.browser_worker import BrowserWorker
            browser_worker = BrowserWorker(auto_start=False)

            engine = Engine(
                executor=executor,
                guardrails=guardrails,
                emergency_stop=emergency,
                browser_worker=browser_worker,
            )

            # Step 1: 编译
            compile_result = compiler.compile(self.query)
            if not compile_result.success:
                self.status = "compile_failed"
                self.error = compile_result.reason
                return

            workflow = compile_result.workflow
            self.status = "compiled"

            # Step 2: 执行
            if self.mode == "compile_only":
                self.status = "completed"
                self.result = {"workflow": workflow.to_dict() if hasattr(workflow, 'to_dict') else str(workflow)}
                return

            self.status = "executing"
            exec_result = engine.execute(workflow)
            self.status = "completed"
            self.result = {
                "workflow": workflow.to_dict() if hasattr(workflow, 'to_dict') else str(workflow),
                "execution": {
                    "success": exec_result.success,
                    "final_state": exec_result.final_state,
                    "total_duration": exec_result.total_duration,
                    "node_count": len(exec_result.node_logs),
                    "node_logs": [
                        {"node_id": n.node_id, "node_type": n.node_type,
                         "status": n.status, "error": n.error,
                         "duration": round((n.finished_at or 0) - (n.started_at or 0), 2)}
                        for n in exec_result.node_logs
                    ],
                }
            }

        except Exception as e:
            self.status = "failed"
            self.error = str(e)
            import traceback
            self._traceback = traceback.format_exc()

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "mode": self.mode,
            "status": self.status,
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
        }


# ----------------------------------------------------------------------------
# 核心逻辑
# ----------------------------------------------------------------------------
def compile_workflow(query: str) -> Dict[str, Any]:
    """编译自然语言需求为工作流 DAG。"""
    try:
        config = Config()
        compiler = WorkflowCompiler(config)
        result = compiler.compile(query)
        if result.success:
            wf = result.workflow
            return {
                "success": True,
                "workflow": wf.to_dict() if hasattr(wf, 'to_dict') else str(wf),
                "reason": result.reason,
            }
        return {"success": False, "reason": result.reason}
    except Exception as e:
        return {"success": False, "reason": str(e)}


def run_workflow(workflow_json: Dict[str, Any], mode: str = "dry_run") -> Dict[str, Any]:
    """执行一个工作流 DAG。"""
    try:
        from ai_shadowbot.workflow import Workflow, WorkflowSchema
        if hasattr(Workflow, 'from_dict'):
            wf = Workflow.from_dict(workflow_json)
        else:
            # 手动构建
            wf = Workflow(
                id=workflow_json.get("id", "wf_manual"),
                name=workflow_json.get("name", "manual"),
                nodes=[Node(**n) for n in workflow_json.get("nodes", [])],
                triggers=[Trigger(**t) for t in workflow_json.get("triggers", [])],
                variables={k: Variable(**v) for k, v in workflow_json.get("variables", {}).items()},
                error_strategy=ErrorStrategy(**workflow_json["error_strategy"]) if "error_strategy" in workflow_json else None,
            )
        errors = WorkflowSchema.validate(wf)
        if errors:
            return {"success": False, "reason": f"DAG 校验失败: {errors}"}

        config = Config()
        guardrails = Guardrails(config=config, strategy="single")
        emergency = EmergencyStop()
        observer = Observer(screen_mask_sensitive=config.screen_mask_sensitive)
        executor = Executor(
            dry_run=(mode != "real"),
            guardrails=guardrails,
            emergency_stop=emergency,
            observer=observer,
        )

        # F015.3: 创建 BrowserWorker（auto_start=False，L5 网关不自动拉起 bridge）
        from ai_shadowbot.browser_worker import BrowserWorker
        browser_worker = BrowserWorker(auto_start=False)

        engine = Engine(
            executor=executor,
            guardrails=guardrails,
            browser_worker=browser_worker,
        )

        exec_result = engine.execute(wf)
        return {
            "success": exec_result.success,
            "final_state": exec_result.final_state,
            "total_duration": exec_result.total_duration,
            "node_count": len(exec_result.node_logs),
            "node_logs": [
                {"node_id": n.node_id, "node_type": n.node_type,
                 "status": n.status, "error": n.error,
                 "duration": round((n.finished_at or 0) - (n.started_at or 0), 2)}
                for n in exec_result.node_logs
            ],
        }
    except Exception as e:
        import traceback
        return {"success": False, "reason": str(e), "traceback": traceback.format_exc()}


def ai_run(query: str, mode: str = "dry_run") -> Dict[str, Any]:
    """一键编译+执行（外部 AI 最常用的入口）。"""
    rid = uuid.uuid4().hex[:12]
    run = L5Run(rid, query, mode)
    with _lock:
        _runs[rid] = run
    run.start()
    return run.snapshot()


# ----------------------------------------------------------------------------
# API 数据模型（必须在模块级别以被 Pydantic 解析）
# ----------------------------------------------------------------------------
class CompileReq(BaseModel):
    query: str

class RunWorkflowReq(BaseModel):
    workflow: Dict[str, Any]
    mode: str = "dry_run"

class AiRunReq(BaseModel):
    query: str
    mode: str = "dry_run"


# ----------------------------------------------------------------------------
# Canvas API 实例（F008 可视化画布）
# ----------------------------------------------------------------------------
from ai_shadowbot.canvas_api import CanvasAPI, flow_to_workflow, workflow_to_flow
from ai_shadowbot.scheduler import Scheduler

_canvas_api = CanvasAPI()
_scheduler = Scheduler(_canvas_api)

# 画布 API 静态文件目录
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


# ----------------------------------------------------------------------------
# HTTP REST API (FastAPI)
# ----------------------------------------------------------------------------
def build_app():
    from fastapi import FastAPI, HTTPException, Header, Body, Query
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="AI 影刀 · L5 Gateway", version="2.0.0")

    def _auth(authorization: str = Header(None)):
        if TOKEN and authorization != f"Bearer {TOKEN}":
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "http", "port": PORT, "service": "ai-shadowbot-workflow"}

    # ---- 画布 API 端点（F008） ----

    # 根路径 → 返回画布页面
    @app.get("/", response_class=HTMLResponse)
    def canvas_root():
        # 唯一权威画布：frontend/dist（Vue3 + LiteGraph）。旧 React Flow 单文件回退已清理。
        dist_index = _DIST_DIR / "index.html"
        if dist_index.exists():
            # no-cache：避免浏览器缓存旧构建（每次 npm run build 资源哈希会变）
            return HTMLResponse(
                dist_index.read_text(encoding="utf-8"),
                headers={"Cache-Control": "no-cache"},
            )
        return HTMLResponse("<h1>AI 影刀 · 工作流画布</h1><p>前端未构建，请先 npm run build</p>")

    # 新版构建产物（Vue3+LiteGraph）：JS/CSS 资源
    if _DIST_DIR.exists():
        dist_assets = _DIST_DIR / "assets"
        if dist_assets.exists():
            app.mount("/assets", StaticFiles(directory=str(dist_assets)), name="dist-assets")

    # 静态文件服务（旧 React Flow 单文件回退 + 依赖）
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # 列出工作流
    @app.get("/api/workflows")
    def list_workflows():
        return _canvas_api.list_workflows()

    # 创建工作流
    @app.post("/api/workflows")
    def create_workflow(body: Dict[str, Any] = Body(...)):
        wf_id = _canvas_api.create_workflow(body)
        return {"id": wf_id, "success": True}

    # 获取工作流详情
    @app.get("/api/workflows/{wf_id}")
    def get_workflow(wf_id: str):
        wf = _canvas_api.get_workflow(wf_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return wf

    # 更新工作流
    @app.put("/api/workflows/{wf_id}")
    def update_workflow(wf_id: str, body: Dict[str, Any] = Body(...)):
        ok = _canvas_api.update_workflow(wf_id, body)
        if not ok:
            raise HTTPException(status_code=404, detail="workflow not found")
        return {"success": True}

    # 删除工作流
    @app.delete("/api/workflows/{wf_id}")
    def delete_workflow(wf_id: str):
        ok = _canvas_api.delete_workflow(wf_id)
        if not ok:
            raise HTTPException(status_code=404, detail="workflow not found")
        return {"success": True}

    # 执行工作流
    @app.post("/api/workflows/{wf_id}/execute")
    def execute_workflow(wf_id: str, mode: str = Query("dry_run")):
        result = _canvas_api.execute_workflow(wf_id, mode=mode)
        if result is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return result

    # 执行历史
    @app.get("/api/workflows/{wf_id}/runs")
    def get_execution_runs(wf_id: str):
        return _canvas_api.get_execution_runs(wf_id)

    # AI 编译 → Flow
    @app.post("/api/compile-to-flow")
    def compile_to_flow(body: Dict[str, Any] = Body(...)):
        query = body.get("query", "")
        return _canvas_api.compile_to_flow(query)

    # 调色板
    @app.get("/api/palette")
    def get_palette():
        return _canvas_api.get_palette()

    # Flow 校验
    @app.post("/api/flow/validate")
    def validate_flow(body: Dict[str, Any] = Body(...)):
        return _canvas_api.validate_flow(body)

    # 执行进度（轮询）
    @app.get("/api/execution/{run_id}")
    def get_execution_progress(run_id: str):
        progress = _canvas_api.get_execution_progress(run_id)
        if progress is None:
            raise HTTPException(status_code=404, detail="run not found")
        return progress

    # ---- Phase 3: 调度器路由 ----

    # 列出触发器
    @app.get("/api/scheduler/triggers")
    def list_triggers(workflow_id: str = Query(None)):
        return _canvas_api.list_triggers(workflow_id)

    # 创建触发器
    @app.post("/api/scheduler/triggers")
    def create_trigger(body: Dict[str, Any] = Body(...)):
        tid = _scheduler.add_trigger(body)
        return {"id": tid, "success": True}

    # 更新触发器
    @app.put("/api/scheduler/triggers/{tid}")
    def update_trigger(tid: str, body: Dict[str, Any] = Body(...)):
        ok = _canvas_api.update_trigger(tid, body)
        if not ok:
            raise HTTPException(status_code=404, detail="trigger not found")
        _scheduler._load_active_triggers()
        return {"success": True}

    # 删除触发器
    @app.delete("/api/scheduler/triggers/{tid}")
    def delete_trigger(tid: str):
        ok = _scheduler.remove_trigger(tid)
        if not ok:
            raise HTTPException(status_code=404, detail="trigger not found")
        return {"success": True}

    # 切换触发器
    @app.post("/api/scheduler/triggers/{tid}/toggle")
    def toggle_trigger(tid: str):
        new_state = _scheduler.toggle_trigger(tid)
        if new_state is None:
            raise HTTPException(status_code=404, detail="trigger not found")
        return {"enabled": new_state, "success": True}

    # 调度器状态
    @app.get("/api/scheduler/status")
    def scheduler_status():
        return _scheduler.status()

    # ---- Phase 3: 日志路由 ----

    # 执行详情（含节点日志）
    @app.get("/api/execution/{run_id}/detail")
    def execution_detail(run_id: str):
        detail = _canvas_api.get_execution_detail(run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="run not found")
        return detail

    # 节点日志
    @app.get("/api/execution/{run_id}/nodes")
    def execution_nodes(run_id: str):
        return _canvas_api.get_node_logs(run_id)

    # 节点截图
    @app.get("/api/execution/{run_id}/screenshot/{node_id}")
    def execution_screenshot(run_id: str, node_id: str):
        b64 = _canvas_api.get_node_screenshot(run_id, node_id)
        if b64 is None:
            raise HTTPException(status_code=404, detail="screenshot not found")
        return {"screenshot_b64": b64}

    # 扩展执行历史（含 summary）
    @app.get("/api/workflows/{wf_id}/runs-extended")
    def get_runs_extended(wf_id: str, limit: int = Query(50)):
        return _canvas_api.get_execution_runs_extended(wf_id, limit)

    # ---- Phase 3: 模板路由 ----

    # 模板列表
    @app.get("/api/templates")
    def list_templates(
        category: str = Query(None),
        search: str = Query(None),
    ):
        return _canvas_api.list_templates(category, search)

    # 模板详情
    @app.get("/api/templates/{tid}")
    def get_template(tid: str):
        tmpl = _canvas_api.get_template(tid)
        if tmpl is None:
            raise HTTPException(status_code=404, detail="template not found")
        return tmpl

    # 从模板创建工作流
    @app.post("/api/workflows/from-template/{tid}")
    def create_from_template(tid: str, body: Dict[str, Any] = Body(...)):
        name = body.get("name")
        wf_id = _canvas_api.create_from_template(tid, name)
        if wf_id is None:
            raise HTTPException(status_code=404, detail="template not found")
        return {"id": wf_id, "success": True}

    # 当前工作流另存为模板
    @app.post("/api/workflows/{wf_id}/save-template")
    def save_as_template(wf_id: str, body: Dict[str, Any] = Body(...)):
        tid = _canvas_api.save_as_template(wf_id, body)
        if tid is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return {"id": tid, "success": True}

    # 增加模板使用计数
    @app.post("/api/templates/{tid}/usage")
    def increment_usage(tid: str):
        ok = _canvas_api.increment_template_usage(tid)
        if not ok:
            raise HTTPException(status_code=404, detail="template not found")
        return {"success": True}

    # ---- F021 导入/导出 ----
    @app.get("/api/workflows/{wf_id}/export")
    def export_workflow(wf_id: str):
        data = _canvas_api.export_workflow(wf_id)
        if data is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return data

    @app.post("/api/workflows/import")
    def import_workflow(body: Dict[str, Any] = Body(...)):
        wf_id = _canvas_api.import_workflow(body)
        if wf_id is None:
            raise HTTPException(status_code=400, detail="导入失败")
        return {"id": wf_id, "success": True}

    # ------------------------------------------------------------------
    # 启动调度器
    # ------------------------------------------------------------------
    _scheduler.start()

    # ---- 原有 L5 端点 ----

    @app.post("/l5/compile")
    def compile_endpoint(body: CompileReq = Body(...), authorization: str = Header(None)):
        _auth(authorization)
        return compile_workflow(body.query)

    @app.post("/l5/run-workflow")
    def run_workflow_endpoint(body: RunWorkflowReq = Body(...), authorization: str = Header(None)):
        _auth(authorization)
        return run_workflow(body.workflow, body.mode)

    @app.post("/l5/ai-run")
    def ai_run_endpoint(body: AiRunReq = Body(...), authorization: str = Header(None)):
        """一键 AI 运行：编译 + 执行，外部 AI 的单一入口。"""
        _auth(authorization)
        return ai_run(body.query, body.mode)

    @app.get("/l5/list")
    def lst(authorization: str = Header(None)):
        _auth(authorization)
        with _lock:
            return [r.snapshot() for r in _runs.values()]

    @app.get("/l5/{rid}/status")
    def status(rid: str, authorization: str = Header(None)):
        _auth(authorization)
        with _lock:
            run = _runs.get(rid)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run.snapshot()

    # ---- Phase 3: L5 调度/日志/模板端点 ----

    @app.post("/l5/schedule")
    def l5_schedule(body: Dict[str, Any] = Body(...), authorization: str = Header(None)):
        """外部 AI 设置定时触发。"""
        _auth(authorization)
        tid = _scheduler.add_trigger(body)
        return {"id": tid, "success": True, "status": _scheduler.status()}

    @app.get("/l5/logs/{workflow_id}")
    def l5_logs(workflow_id: str, limit: int = Query(10), authorization: str = Header(None)):
        """外部 AI 查询工作流执行日志。"""
        _auth(authorization)
        return _canvas_api.get_execution_runs_extended(workflow_id, limit)

    @app.get("/l5/templates")
    def l5_templates(category: str = Query(None), authorization: str = Header(None)):
        """外部 AI 查询模板列表。"""
        _auth(authorization)
        return _canvas_api.list_templates(category)

    @app.post("/l5/templates/{tid}/use")
    def l5_use_template(tid: str, body: Dict[str, Any] = Body(...), authorization: str = Header(None)):
        """外部 AI 使用模板创建工作流。"""
        _auth(authorization)
        name = body.get("name")
        wf_id = _canvas_api.create_from_template(tid, name)
        if wf_id is None:
            raise HTTPException(status_code=404, detail="template not found")
        return {"id": wf_id, "success": True}

    return app


# ----------------------------------------------------------------------------
# MCP server (stdio)
# ----------------------------------------------------------------------------
def build_mcp(port: Optional[int] = None):
    from mcp.server.fastmcp import FastMCP

    # port 为 None 时使用 FastMCP 默认端口（mcp 模式 stdio 不占端口）；
    # both 模式传入 MCP_PORT，使 MCP 在独立端口暴露（streamable-http）
    mcp_kwargs: Dict[str, Any] = {"name": "ai-shadowbot-l5"}
    if port is not None:
        mcp_kwargs["host"] = "127.0.0.1"
        mcp_kwargs["port"] = port
    mcp = FastMCP(**mcp_kwargs)

    @mcp.tool()
    def compile_workflow_tool(query: str) -> str:
        """编译自然语言需求为工作流 DAG（节点图），返回结构化工作流 JSON。"""
        return json.dumps(compile_workflow(query), ensure_ascii=False)

    @mcp.tool()
    def run_workflow_tool(workflow_json: str) -> str:
        """执行一个工作流 DAG（JSON 字符串），dry_run 模式下安全演练。"""
        try:
            wf = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({"success": False, "reason": f"JSON 解析失败: {e}"}, ensure_ascii=False)
        return json.dumps(run_workflow(wf), ensure_ascii=False)

    @mcp.tool()
    def ai_run_tool(query: str, mode: str = "dry_run") -> str:
        """【推荐】一键 AI 运行：用自然语言描述需求，自动编译工作流并执行。mode='dry_run'（默认安全演练，不真动电脑）或 'real'（真执行）。"""
        return json.dumps(ai_run(query, mode), ensure_ascii=False)

    @mcp.tool()
    def schedule_workflow(workflow_id: str, cron_expr: str) -> str:
        """为指定工作流设置定时触发。workflow_id：工作流ID，cron_expr：cron表达式(如 '*/5 * * * *' 每5分钟)。"""
        data = {
            "workflow_id": workflow_id,
            "type": "cron",
            "config": {"cron": cron_expr},
            "enabled": True,
        }
        tid = _scheduler.add_trigger(data)
        return json.dumps({"id": tid, "success": True, "status": _scheduler.status()}, ensure_ascii=False)

    @mcp.tool()
    def get_execution_logs(workflow_id: str, limit: int = 10) -> str:
        """查询工作流的执行日志。workflow_id：工作流ID，limit：返回条数（默认10）。"""
        logs = _canvas_api.get_execution_runs_extended(workflow_id, limit)
        return json.dumps(logs, ensure_ascii=False, default=str)

    @mcp.tool()
    def list_templates(category: str = "") -> str:
        """列出可用模板。category：分类筛选（办公/网页/系统等，空=全部）。"""
        cat = category if category else None
        templates = _canvas_api.list_templates(cat)
        return json.dumps(templates, ensure_ascii=False, default=str)

    @mcp.tool()
    def use_template(template_id: str, name: str = "") -> str:
        """使用模板创建新工作流。template_id：模板ID，name：可选的新工作流名称。"""
        wf_name = name if name else None
        wf_id = _canvas_api.create_from_template(template_id, wf_name)
        if wf_id is None:
            return json.dumps({"success": False, "reason": "template not found"}, ensure_ascii=False)
        return json.dumps({"id": wf_id, "success": True}, ensure_ascii=False)

    return mcp


# ----------------------------------------------------------------------------
# CLI 入口
# ----------------------------------------------------------------------------
def main():
    global PORT, TOKEN
    import argparse
    ap = argparse.ArgumentParser(description="AI 版影刀 · L5 跨 AI 触发网关")
    ap.add_argument("--mode", choices=["http", "mcp", "both"], default="http",
                    help="运行模式：http=仅HTTP API(--port)；mcp=仅MCP stdio；both=HTTP(--port) + MCP(streamable-http, 独立端口 8794)")
    ap.add_argument("--port", type=int, default=PORT, help="HTTP 端口（默认 8792）")
    ap.add_argument("--token", default=TOKEN, help="Bearer Token 鉴权")
    args = ap.parse_args()

    PORT = args.port
    TOKEN = args.token

    print(f"[l5] AI 版影刀 L5 网关启动 | mode={args.mode} port={PORT}", flush=True)

    if args.mode in ("http", "both"):
        import uvicorn
        app = build_app()
        if args.mode == "both":
            # HTTP 在后台线程（--port），MCP 在独立端口 MCP_PORT（8794）通过 streamable-http 暴露，
            # 两者端口分离，避免二次 bind 冲突；stdio 不占端口，故 both 模式改走网络传输供外部 AI 接入。
            t = threading.Thread(
                target=lambda: uvicorn.run(app, host="127.0.0.1", port=PORT,
                                           log_level="info"),
                daemon=True,
            )
            t.start()
            print(f"[l5] HTTP API 已启动 http://127.0.0.1:{PORT}  (后台线程)", flush=True)
            mcp = build_mcp(port=MCP_PORT)
            print(f"[l5] MCP server 已启动 http://127.0.0.1:{MCP_PORT}/mcp  (streamable-http)", flush=True)
            mcp.run(transport="streamable-http")
        else:
            uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")

    elif args.mode == "mcp":
        mcp = build_mcp()
        print("[l5] MCP stdio server 启动", flush=True)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
