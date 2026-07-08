---
title: "[鲁千机] F006 工作流引擎 Phase 1 TDD 实现完成 — 全量 pytest 全绿（新增 87 项），verify_security_fixes."
type: concept
project: "自动系统"
source: journal.md
tags: ["API", "LLM", "dry_run", "pytest", "安全", "测试", "规格"]
concept_id: journal-027
created: 2026-07-08
updated: 2026-07-08 11:29
---

# [鲁千机] F006 工作流引擎 Phase 1 TDD 实现完成 — 全量 pytest 全绿（新增 87 项），verify_security_fixes.

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔧 [2026-07-07] [鲁千机] F006 工作流引擎 Phase 1 TDD 实现完成 — 全量 pytest 全绿（新增 87 项），verify_security_fixes.py 34 PASS 无回归。
- **workflow.py**: Workflow/Node/Trigger/Variable/ErrorStrategy dataclasses（匹配 §1.1 JSON schema），WorkflowSchema.validate() 9 条 DAG 约束，to_dict/from_dict 序列化，parse_variable_ref 变量模板解析。
- **compiler.py**: WorkflowCompiler 核心 API compile(natural_language_query) → CompileResult。复用 Config.make_llm_client()/MockLLMClient。compile_workflow tool_choice（单一 tool 输出完整 DAG JSON）。Mock 模式内置启发式（关键词→预置模板流）。编译时安全校验（validate_dag + _scan_injection 快筛）。异常降级。
- **variables.py**: VariableScope 类 set/get/has/clear/类型检查。resolve_template/resolve_params 模板解析替换 {{variables.xxx}}。内建变量 workflow.id/workflow.step/last_result/last_screenshot。
- **errors.py**: ErrorHandler 类 handle(node_error, strategy) → retry/skip/abort/degrade 四种策略。指数退避+±10% 抖动。重试耗尽 fallback abort。
- **engine.py**: Engine 类 execute/dry_run 共享同一状态机（_run）。NodeStatus 七态。迭代式栈遍历 DAG（防递归爆栈）。每个 atomic 节点执行前过 guardrails.check()（§6 硬要求）。condition 节点支持 ==/!=/>/</>=/<= 比较和 and/or/not 逻辑。loop 支持 while/for/for_each，max_iterations 硬上限 1000。wait 节点 dry_run 不真 sleep。
- **cli.py additive**: 新增 --compile "需求"（编译→展示→确认→执行）、--run-workflow wf.json（加载→执行）、--workflow-demo（演示完整流水线）。全部 additive，不影响现有 --dry-run/--real/--vision/--confirm。
- **测试 87 项**: test_workflow.py 24 项（DAG 校验/序列化/变量解析）、test_compiler.py 14 项（mock 编译器/关键词匹配/安全编译时校验/IO 序列化）、test_engine.py 49 项（线性/条件/循环/错误策略/dry_run铁律/guardrails集成/变量解析/表达式评估/ErrorHandler集成）。
- **铁律遵守**: 全部 additive 不修改 guards.py/planner.py/executor.py 现有逻辑；mock 零 LLM 依赖；dry_run 不 import pyautogui；每个 atomic 节点过 guardrails.check()；engine.py 顶层无 pyautogui import。
- **偏离设计**: 无。严格按 docs/workflow-design.md 和 docs/gap-analysis-vision-v1.md 落地。VariableType/ErrorStrategyType 枚举成员名加 _type 后缀避免与 builtins 冲突。

---
*由 extract_concepts_from_journal.py 自动提炼*