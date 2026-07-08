---
title: "[鲁千机] Phase 3 调度与生态 TDD 实现完成（F009/F010/F011）— 全量 pytest 370 passed（含新增 70 项 Phas"
type: concept
project: "自动系统"
source: journal.md
tags: ["API", "LLM", "dry_run", "pytest", "安全", "测试"]
concept_id: journal-028
created: 2026-07-08
updated: 2026-07-08 11:29
---

# [鲁千机] Phase 3 调度与生态 TDD 实现完成（F009/F010/F011）— 全量 pytest 370 passed（含新增 70 项 Phas

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔧 [2026-07-07] [鲁千机] Phase 3 调度与生态 TDD 实现完成（F009/F010/F011）— 全量 pytest 370 passed（含新增 70 项 Phase 3 测试），verify_security_fixes.py 34 PASS 无回归。
- **canvas_api.py 扩展**（Phase 3 表 + CRUD + 种子模板）：新增 triggers/trigger_runs/node_logs/templates 表（CREATE TABLE IF NOT EXISTS），execution_runs 扩展 summary/screenshot_b64 列（_ensure_column 兼容旧表）。新 API：触发器 CRUD（list_triggers/create_trigger/update_trigger/delete_trigger/toggle_trigger）、日志查询（get_execution_detail/get_node_logs/get_node_screenshot/get_execution_runs_extended）、模板 CRUD（list_templates/get_template/create_from_template/save_as_template/increment_template_usage）。种子模板 4 个（每日邮件对账/网页截图存档/文件整理/系统监控）。save_as_template 自动剔除 params 中的敏感字段（password/token/api_key/secret/credential/auth → ***）。execute_workflow 自动持久化节点级日志。
- **scheduler.py 新增**：Scheduler 类，后台线程驱动（threading.RLock 防死锁）。简化 cron 解析器（零外部依赖，支持 */N / N,M / N-M / * 格式）。start/stop/add_trigger/remove_trigger/toggle_trigger/status API。从数据库加载已启用触发器，按 _check_interval（默认 30s）轮询到期触发。触发时调用 Engine.execute()（仍过 guardrails.check()）。canvas_api.execute_workflow 走真实模式（mode="real"）。
- **l5_gateway.py 扩展**：新增调度路由（/api/scheduler/triggers CRUD + toggle + /status）、日志路由（/api/execution/{run_id}/detail /nodes /screenshot/{node_id} + /runs-extended）、模板路由（/api/templates CRUD + /workflows/from-template/{id} + /workflows/{id}/save-template + /templates/{id}/usage）。L5 新增端点（/l5/schedule /l5/logs/{workflow_id} /l5/templates /l5/templates/{tid}/use）。MCP tools 新增 4 个（schedule_workflow/get_execution_logs/list_templates/use_template）。build_app() 启动时自动 _scheduler.start()。
- **static/canvas.html 前端扩展**：右侧面板改为 4 选项卡（属性/调度/日志/模板）。**调度面板**：触发器列表（类型/状态/下次执行时间）、创建新触发器（cron 表达式/间隔秒数）、切换启用/删除按钮。**日志面板**：执行历史列表（时间/模式/状态/耗时）、点击展开节点级时间线。**模板面板**：搜索+分类筛选、模板列表（名称/分类/使用计数/标签）、点击展开预览、使用模板按钮、另存为模板按钮。全部通过 fetch() 调后端 API。
- **测试 70 项**：test_scheduler.py 17 项（CRUD/生命周期/cron 解析/调度执行 mock Engine）、test_logs.py 9 项（节点日志 CRUD/截图存储/扩展执行历史）、test_templates.py 16 项（种子模板/模板 CRUD/从模板创建/另存为模板/敏感字段剔除）、test_phase3_api.py 28 项（调度/日志/模板/L5 端点集成测试）。
- **铁律遵守**：全部 additive，不修改 workflow.py/compiler.py/guardrails.py。调度执行仍过 guardrails.check()。dry_run 不截屏。模板保存时自动剔除敏感字段。pytest 默认 mock 零 LLM。

---
*由 extract_concepts_from_journal.py 自动提炼*