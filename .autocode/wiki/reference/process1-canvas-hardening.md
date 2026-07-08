# L5 流程 1 · ai-shadowbot 收口与增强门禁清单

> 用途：L5 Go 模式前置门禁（process1_gate.py 校验）。七类必须填满，否则 🛑 STOP。
> 来源：ye-zhiqiu 需求盘点（2026-07-08）+ yun-jianwei 三道门禁评审（B4 spec 漂移 / B3 process1 文档 / B1 git）。
> 关联 spec：F012 / F013 / F014；里程碑 M9 / M10。

---

## 1. 目标与边界
**目标**：将 ai-shadowbot 从「后端 + React Flow MVP 画布」推进到「Vue3 + LiteGraph 生产级画布 + 工程卫生达标」的可发布/可自驱状态，为后续 L5 Go 模式（A）扫清三道致命门禁。

**范围内（IN）**：
- 画布生产级交互收口（F012）：节点拖拽放置、调度/日志/模板三面板前端化、属性面板 combo 候选值对接后端 /api/palette、DPR 精细优化。
- 工程卫生与治理（F013）：task.json 刷新（补 F007–F011）、临时文件清理、git 初始化 + 首提交、旧 React Flow 残留清理、README/规格一致性。
- 启动器与网关健壮性（F014）：端口口径统一 8792、`--mode both` 端口冲突修复。

**边界外（OUT）**：
- 不改动 F001–F011 已交付的后端能力（370 passed / 安全 34 PASS 零回归硬约束）。
- 不新增动作类型、不削弱 guardrails 安全铁律。
- 不做 LLM 规划能力增强（属后续 Phase）。
- 旧 React Flow 画布仅在 F013.4 中删除，不维护。

---

## 2. 验收标准
- **F012**：①调色板拖拽到画布落点可创建节点（非仅点击）②调度/日志/模板三面板数据正确来自后端 API ③属性面板 combo 候选值由 /api/palette 实时拉取 ④高 DPI（≥150%/多屏）下渲染清晰、坐标命中无偏移。
- **F013**：①task.json 含 F001–F014 且状态/claimed_by 与 spec 一致 ②根目录及 .autocode 无 `_*` 临时文件、auto-coding-agent/ 已移除 ③git 已 init 且首提交存在、.gitignore 覆盖 __pycache__/node_modules/.pytest_cache/data/*.db ④旧 static/reactflow.*、static/canvas.html 已删 ⑤README 与 spec F008 一致（370 passed、Vue 画布）。
- **F014**：①l5_gateway docstring/help 端口均为 8792 ②`--mode both` 可同时起 HTTP(8792)+MCP(stdio) 无端口冲突、进程不崩。
- **整体**：pytest 全量 370 passed 无回归；verify_security_fixes.py 34 PASS 无回归。

---

## 3. 决策点与未知项
| 决策点 | 现状 | 待定 |
|---|---|---|
| 旧 React Flow 静态文件（static/reactflow.css\|umd.js\|canvas.html）删除时机 | F013.4（git 首提交后） | 确认 l5_gateway 根路由 `/` 是否已指向 Vue dist，删除后无 404 |
| auto-coding-agent/ 夹带目录去向 | F013.2 评估 | 移出仓库根 or 删（43KB zip 非本项目资产）|
| F012 实现者 | 留空（claimed_by=""） | 派前端负责人 |
| `--mode both` 冲突根因 | FastMCP stdio 回退占 8792 | 实现时确认传输层隔离方式（stdio 不绑端口 / 显式端口分离）|
| 是否需补充前端（Vue）自动化测试 | 当前 pytest 仅覆盖旧 canvas_api/canvas.html | F012 落地时补前端回归（含 .on() 修复回归）|

---

## 4. 依赖与约束
- **依赖**：F012 → F008（画布基座，done）；F012.2→F009、F012.3→F010、F012.4→F011（后端路由已存在）；F014 → F007（网关，done）。
- **硬约束**：
  - 不破 F001–F011（370 passed / 34 PASS 安全零回归）。
  - additive 原则，不修改 workflow.py/compiler.py/engine.py/guardrails.py/canvas_api.py 现有逻辑。
  - 端口统一 **8792**（run_server.py / launcher_gui.py / l5_gateway PORT 默认已一致，仅 docstring/help 文案待改）。
  - 安全铁律不动：deny-unconfirmed、dry_run 不 import pyautogui、调度/执行仍过 guardrails.check()。

---

## 5. 风险与回滚点
| 风险 | 等级 | 缓解 / 回滚点 |
|---|---|---|
| 双前端并存（旧 React Flow canvas.html 仍被服务）导致回归检测/BugHunter 巡检混淆、P0:0 假阴性 | 高（B4） | F013.4 删除旧 static 文件前先确认 `/` 路由指向 Vue dist；BugHunter 节点支持(get_canvas_nodes/drag_node)对准 LiteGraph |
| `--mode both` 修复触及 FastMCP 传输层，可能引入新启动失败 | 中 | F014.2 加启动/冲突单测；回滚点 = git 首提交（F013.3）|
| combo 候选值依赖后端 /api/palette 稳定性，后端变更致前端空候选 | 中 | F012.5 前端缓存 + 失败兜底；palette 接口契约锁定 |
| git 初始化前夹带大文件（auto-coding-agent 43KB zip）污染历史 | 中（B1） | F013.2 先清夹带再 F013.3 git init |
| 高 DPI 坐标映射误差导致点击偏移 | 中 | F012.6 用 devicePixelRatio 校正；截图回读验证命中 |

---

## 6. 里程碑拆解
- **M-A（卫生快赢，归 M10/F013 前部）**：F013.1 task.json 刷新 → F013.2 临时文件清理 → F013.3 git init+首提交 → F013.5 README/规格一致性。**前置，先过 B1。**
- **M-B（画布增强，M9/F012）**：F012.1 拖拽放置 → F012.2/3/4 三面板 → F012.5 combo 对接 → F012.6 DPR。
- **M-C（网关收口，M9/F014）**：F014.1 端口口径统一 → F014.2 mode both 修复。
- **M-D（旧画布清理 + 测试/文档闭环，M10/F013.4）**：F013.4 删旧 static → 前端回归测试 + 全量 pytest 370 / 安全 34 复测。

执行顺序建议：**M-A → M-C → M-B → M-D**（先治理 git 与端口，再画布，最后清理旧栈并闭环测试）。

---

## 7. 知识挂钩
- [[anti_pattern: Spec 漂移(画布技术栈)在 L5 自驱前必须先 reconcile]]（knowledge-base.md，yun-jianwei 2026-07-08，B4 反例）→ 直接驱动 F013.4 + F008 描述已校正。
- [[anti_pattern: 纯正则提示注入防护可被同义改写绕过]] / [[黑名单扩面须区分 BLOCK 动词与危险子命令]] / [[R2↔R3 在 git reset --hard 张力]]（knowledge-base.md）→ 约束 F012/F014 不得削弱 guardrails。
- [[.autocode/wiki/index]] / [[.autocode/wiki/tasks/自动系统-tasks]]（CLAUDE.md 索引）→ 任务追踪对齐。
- 共识评审（待 yun-jianwei 在 spec 落定后执行）：F012/F013/F014 的 AC 与依赖链复核，重点确认 B4/B1 已闭环、mode both 修复方案可行。
